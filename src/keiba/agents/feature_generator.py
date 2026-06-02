"""エージェント4: 特徴量生成"""

from datetime import datetime

from keiba.agents.base import BaseAgent
from keiba.models.pipeline import PipelineContext


class FeatureGenerator(BaseAgent):
    """各馬の特徴量を生成するエージェント"""

    def validate_input(self, context: PipelineContext) -> bool:
        return (
            context.current_race_data is not None
            and context.quality_check is not None
            and context.quality_check.get("passed", False) is not False
            or (context.quality_check is not None
                and not any(i["severity"] == "critical" for i in context.quality_check.get("issues", [])))
        )

    def process(self, context: PipelineContext) -> PipelineContext:
        entries = context.current_race_data.get("entries", [])
        race = context.current_race_data.get("race", {})
        past_perfs = (context.historical_data or {}).get("past_performances", {})
        jockey_stats = (context.historical_data or {}).get("jockey_stats", {})
        trainer_stats = (context.historical_data or {}).get("trainer_stats", {})

        race_distance = race.get("distance", 2000)
        horse_features = []

        for entry in entries:
            horse_id = entry.get("horse", {}).get("horse_id", "")
            pp_list = past_perfs.get(horse_id, [])

            # 距離適性
            distance_scores = self._calc_distance_aptitude(pp_list, race_distance)
            # 馬場適性
            turf_score, dirt_score = self._calc_track_aptitude(pp_list)
            # コース適性
            course_score = self._calc_course_score(pp_list, race.get("course", ""))
            # 脚質
            style, consistency = self._classify_style(pp_list, entry.get("style", "差し"))
            # 上がり性能
            avg_last3f, best_last3f, closing_rank = self._calc_closing_speed(pp_list, entries, past_perfs)
            # 近走成績
            recent3, recent5, form_score = self._calc_form(pp_list)
            # クラス・距離変更
            class_change = self._detect_class_change(pp_list)
            distance_change = self._detect_distance_change(pp_list, race_distance)
            # 馬体重トレンド
            weight_trend = self._detect_weight_trend(entry)
            # 騎手・厩舎成績
            jt_rate, jc_rate = self._get_jockey_trainer_rates(entry, jockey_stats, trainer_stats)

            horse_features.append({
                "entry_id": entry.get("entry_id", ""),
                "horse_id": horse_id,
                "distance_aptitude_score": distance_scores["score"],
                "optimal_distance_min": distance_scores["min"],
                "optimal_distance_max": distance_scores["max"],
                "track_turf_score": turf_score,
                "track_dirt_score": dirt_score,
                "course_specific_score": course_score,
                "primary_style": style,
                "style_consistency": consistency,
                "average_last_3f": avg_last3f,
                "best_last_3f": best_last3f,
                "closing_speed_rank": closing_rank,
                "recent_3_runs": recent3,
                "recent_5_runs": recent5,
                "form_score": form_score,
                "class_change": class_change,
                "distance_change": distance_change,
                "weight_carried_change": entry.get("weight_change"),
                "horse_weight_trend": weight_trend,
                "jockey_trainer_win_rate": jt_rate,
                "jockey_course_win_rate": jc_rate,
            })

        # 上がりランクを再計算（全馬比較）
        all_avg = [(i, hf.get("average_last_3f")) for i, hf in enumerate(horse_features) if hf.get("average_last_3f")]
        all_avg.sort(key=lambda x: x[1])
        for rank, (idx, _) in enumerate(all_avg, 1):
            horse_features[idx]["closing_speed_rank"] = rank

        context.features = {
            "race_id": context.race_id,
            "generated_at": datetime.now().isoformat(),
            "horse_features": horse_features,
            "field_size": len(entries),
        }
        self.logger.info(f"Generated features for {len(entries)} horses")
        return context

    def _calc_distance_aptitude(self, pp_list: list, target_distance: int) -> dict:
        if not pp_list:
            return {"score": 50.0, "min": 1800, "max": 2400}
        scores = []
        distances = []
        for pp in pp_list:
            d = pp.get("distance", 2000)
            dist_diff = abs(d - target_distance)
            score = max(0, 100 - dist_diff * 0.05)
            pos = pp.get("finish_position", 5)
            total = pp.get("total_runners", 10)
            score *= (1 - pos / total * 0.5)
            scores.append(score)
            distances.append(d)
        avg_score = sum(scores) / len(scores)
        return {
            "score": round(min(100, max(0, avg_score)), 1),
            "min": min(distances) if distances else 1800,
            "max": max(distances) if distances else 2400,
        }

    def _calc_track_aptitude(self, pp_list: list) -> tuple[float, float]:
        if not pp_list:
            return 50.0, 50.0
        turf_positions, dirt_positions = [], []
        for pp in pp_list:
            if pp.get("track_type") == "芝":
                turf_positions.append(pp.get("finish_position", 5))
            else:
                dirt_positions.append(pp.get("finish_position", 5))
        turf_score = self._positions_to_score(turf_positions) if turf_positions else 50.0
        dirt_score = self._positions_to_score(dirt_positions) if dirt_positions else 50.0
        return round(turf_score, 1), round(dirt_score, 1)

    def _positions_to_score(self, positions: list) -> float:
        if not positions:
            return 50.0
        avg_pos = sum(positions) / len(positions)
        return min(100, max(0, 100 - (avg_pos - 1) * 20))

    def _calc_course_score(self, pp_list: list, target_course: str) -> dict:
        if not pp_list:
            return {target_course: 50.0}
        course_data = {}
        for pp in pp_list:
            c = pp.get("course", "")
            if c not in course_data:
                course_data[c] = []
            course_data[c].append(pp.get("finish_position", 5))
        result = {}
        for c, positions in course_data.items():
            result[c] = self._positions_to_score(positions)
        if target_course not in result:
            result[target_course] = 50.0
        return result

    def _classify_style(self, pp_list: list, default_style: str) -> tuple[str, float]:
        if not pp_list:
            return default_style, 0.5
        styles = [pp.get("running_style", default_style) for pp in pp_list]
        if not styles:
            return default_style, 0.5
        from collections import Counter
        counter = Counter(styles)
        primary = counter.most_common(1)[0][0]
        consistency = counter.most_common(1)[0][1] / len(styles)
        return primary, round(consistency, 2)

    def _calc_closing_speed(self, pp_list: list, entries: list, all_pp: dict) -> tuple:
        last3fs = [pp.get("last_3f") for pp in pp_list if pp.get("last_3f")]
        avg = round(sum(last3fs) / len(last3fs), 2) if last3fs else None
        best = round(min(last3fs), 2) if last3fs else None
        return avg, best, None  # rankは全馬比較後に設定

    def _calc_form(self, pp_list: list) -> tuple[list, list, float]:
        sorted_pp = sorted(pp_list, key=lambda x: x.get("race_date", ""), reverse=True)
        recent3 = [pp.get("finish_position", 0) for pp in sorted_pp[:3]]
        recent5 = [pp.get("finish_position", 0) for pp in sorted_pp[:5]]
        if recent3:
            avg = sum(recent3) / len(recent3)
            form_score = min(100, max(0, 100 - (avg - 1) * 25))
        else:
            form_score = 50.0
        return recent3, recent5, round(form_score, 1)

    def _detect_class_change(self, pp_list: list) -> str | None:
        if len(pp_list) < 2:
            return None
        sorted_pp = sorted(pp_list, key=lambda x: x.get("race_date", ""), reverse=True)
        grades = {"GI": 4, "GII": 3, "GIII": 2, "L": 1}
        current = grades.get(sorted_pp[0].get("grade", ""), 0)
        prev = grades.get(sorted_pp[1].get("grade", ""), 0) if len(sorted_pp) > 1 else 0
        if current > prev:
            return "up"
        elif current < prev:
            return "down"
        return "same"

    def _detect_distance_change(self, pp_list: list, target: int) -> str | None:
        if not pp_list:
            return None
        sorted_pp = sorted(pp_list, key=lambda x: x.get("race_date", ""), reverse=True)
        last_dist = sorted_pp[0].get("distance", target)
        diff = target - last_dist
        if diff > 200:
            return "up"
        elif diff < -200:
            return "down"
        return "same"

    def _detect_weight_trend(self, entry: dict) -> str:
        change = entry.get("weight_change")
        if change is None:
            return "stable"
        if change > 4:
            return "increasing"
        elif change < -4:
            return "decreasing"
        return "stable"

    def _get_jockey_trainer_rates(self, entry: dict, jockey_stats: dict, trainer_stats: dict) -> tuple:
        jockey_id = entry.get("jockey", {}).get("jockey_id", "")
        trainer_name = entry.get("horse", {}).get("trainer_name", "")
        js = jockey_stats.get(jockey_id, {})
        ts = trainer_stats.get(trainer_name, {})
        jt_rate = js.get("win_rate", 0)
        jc_rate = (js.get("course_stats", {}).get("東京", {}).get("win_rate", 0))
        return round(jt_rate, 3), round(jc_rate, 3)
