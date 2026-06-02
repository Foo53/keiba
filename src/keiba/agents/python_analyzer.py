"""エージェント5: Python分析"""

import math
from datetime import datetime

from keiba.agents.base import BaseAgent
from keiba.models.pipeline import PipelineContext


class PythonAnalyzer(BaseAgent):
    """統計分析・スコアリング・勝率推定を行うエージェント"""

    FEATURE_WEIGHTS = {
        "distance_aptitude": 0.15,
        "track_aptitude": 0.12,
        "recent_form": 0.20,
        "closing_speed": 0.15,
        "running_style": 0.08,
        "jockey_stats": 0.12,
        "trainer_stats": 0.08,
        "pedigree": 0.05,
        "weight_factors": 0.05,
    }

    def validate_input(self, context: PipelineContext) -> bool:
        return context.features is not None

    def process(self, context: PipelineContext) -> PipelineContext:
        features = context.features.get("horse_features", [])
        if not features:
            raise ValueError("No horse features to analyze")

        # 各馬のスコア計算
        scored = []
        for hf in features:
            score = self._compute_composite_score(hf)
            scored.append((hf, score))

        # ソフトマックスで勝率推定（スコアを正規化してから適用）
        scores = [s for _, s in scored]
        # スコアを0中心に正規化してから温度付きsoftmax
        mean_score = sum(scores) / len(scores) if scores else 0
        normalized = [(s - mean_score) / 5.0 for s in scores]  # スケール調整
        probabilities = self._softmax_raw(normalized, temperature=1.0)

        # 複勝率（top3確率）の近似: Harville公式
        results = []
        sorted_indices = sorted(range(len(scored)), key=lambda i: scored[i][1], reverse=True)

        for rank, idx in enumerate(sorted_indices, 1):
            hf, score = scored[idx]
            win_prob = probabilities[idx]
            place_prob = min(1.0, win_prob * 2.5)  # 簡易近似
            results.append({
                "entry_id": hf["entry_id"],
                "horse_id": hf["horse_id"],
                "horse_name": self._get_horse_name(context, hf["entry_id"]),
                "win_probability": round(win_prob, 4),
                "place_probability": round(place_prob, 4),
                "model_confidence": round(min(1.0, score / 80), 3),
                "rank_by_model": rank,
                "composite_score": round(score, 2),
            })

        # データ十分性評価
        field_size = len(features)
        data_sufficiency = "sufficient" if field_size >= 8 else "limited" if field_size >= 5 else "minimal"

        # 主要ファクター
        key_factors = self._identify_key_factors(results[:3], scored)

        # 注意事項
        caveats = []
        if data_sufficiency != "sufficient":
            caveats.append(f"出走馬数が{field_size}頭のため、統計的信頼性に限界があります")
        caveats.append("本分析は統計モデルに基づく推定であり、実際のレース結果を保証するものではありません")

        context.analysis = {
            "race_id": context.race_id,
            "analyzed_at": datetime.now().isoformat(),
            "method": "statistical",
            "probabilities": results,
            "key_factors": key_factors,
            "caveats": caveats,
            "data_sufficiency": data_sufficiency,
        }
        self.logger.info(f"Analyzed {len(results)} horses, top pick: {results[0]['horse_name'] if results else 'N/A'}")
        return context

    def _compute_composite_score(self, hf: dict) -> float:
        """特徴量の加重和でスコア計算"""
        w = self.FEATURE_WEIGHTS
        score = 0.0
        score += hf.get("distance_aptitude_score", 50) * w["distance_aptitude"]
        score += hf.get("track_turf_score", 50) * w["track_aptitude"]
        score += hf.get("form_score", 50) * w["recent_form"]
        # 上がり性能: 速いほど高スコア（34秒→100, 36秒→0）
        avg_3f = hf.get("average_last_3f")
        closing_score = max(0, min(100, (36 - avg_3f) * 50)) if avg_3f else 50
        score += closing_score * w["closing_speed"]
        # 脚質: 逃げ・先行は東京2400でやや有利
        style = hf.get("primary_style", "差し")
        style_bonus = {"逃げ": 55, "先行": 60, "差し": 65, "追込": 45}.get(style, 50)
        score += style_bonus * w["running_style"]
        # 騎手成績
        jt_rate = hf.get("jockey_trainer_win_rate", 0)
        jockey_score = min(100, jt_rate * 300)
        score += jockey_score * w["jockey_stats"]
        # 馬体重トレンド
        trend = hf.get("horse_weight_trend", "stable")
        weight_score = {"increasing": 40, "stable": 60, "decreasing": 50}.get(trend, 50)
        score += weight_score * w["weight_factors"]
        # コース適性
        course_scores = hf.get("course_specific_score", {})
        best_course = max(course_scores.values()) if course_scores else 50
        score += best_course * w["trainer_stats"]
        # 距離変更ボーナス
        dist_change = hf.get("distance_change", "same")
        if dist_change == "same":
            score += 5
        elif dist_change == "up":
            score -= 3
        return score

    def _softmax_raw(self, scores: list[float], temperature: float = 1.0) -> list[float]:
        if not scores:
            return []
        exps = [math.exp(s / temperature) for s in scores]
        total = sum(exps)
        return [e / total for e in exps]

    def _get_horse_name(self, context: PipelineContext, entry_id: str) -> str:
        entries = (context.current_race_data or {}).get("entries", [])
        for e in entries:
            if e.get("entry_id") == entry_id:
                return e.get("horse", {}).get("horse_name", "不明")
        return "不明"

    def _identify_key_factors(self, top3: list[dict], scored: list) -> list[str]:
        factors = []
        if top3:
            factors.append(f"本命候補: {top3[0]['horse_name']}（モデル勝率 {top3[0]['win_probability']:.1%}）")
        if len(top3) >= 2:
            gap = top3[0]['win_probability'] - top3[1]['win_probability']
            if gap > 0.10:
                factors.append("1番手と2番手の差が大きく、実力差が明確")
            else:
                factors.append("上位陣の実力差が小さく、混戦模様")
        return factors
