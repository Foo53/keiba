"""JRA-VAN データソース

race_horse_detail.csv（SQLite化済み）から FeatureGenerator が期待する形式に変換する。
"""

from keiba.data.base_source import DataSource
from keiba.data.jrvan.loader import (
    JrVanLoader,
    JYO_CODE_MAP,
    _infer_track_type,
)


class JrVanDataSource(DataSource):
    """JRA-VAN CSVデータソース — FeatureGenerator互換形式を返す"""

    def __init__(self, config: dict | None = None):
        cfg = (config or {}).get("jrvan", {})
        self.loader = JrVanLoader(
            csv_dir=cfg.get("csv_dir"),
            db_path=cfg.get("db_path"),
        )

    def get_historical_data(self, race_id: str) -> dict:
        """過去レースデータ取得

        FeatureGenerator が消費する形式:
        {races, horses, past_performances, jockey_stats, trainer_stats}
        """
        conn = self.loader.get_connection()
        try:
            race_rows = conn.execute(
                "SELECT * FROM race_horse_detail WHERE race_id = ? ORDER BY umaban",
                (race_id,),
            ).fetchall()

            if not race_rows:
                return self._empty_historical()

            race_date = race_rows[0]["race_date"]
            race_info = self._row_to_race(race_rows[0])

            # 過去戦績: このレースに出走する全馬の過去出走を一括取得
            horse_ids = [r["ketto_toroku_bango"] for r in race_rows if r["ketto_toroku_bango"]]
            past_perfs = self._get_past_performances(conn, horse_ids, race_date)

            # 馬情報
            horses = {}
            for r in race_rows:
                hid = r["ketto_toroku_bango"]
                horses[hid] = self._row_to_horse(r)

            # 騎手・調教師統計
            jockey_ids = list({r["jockey_code"] for r in race_rows if r["jockey_code"]})
            trainer_names = list({r["trainer_name_short"] for r in race_rows if r["trainer_name_short"]})

            jockey_stats = self._get_jockey_stats(conn, jockey_ids, race_date)
            trainer_stats = self._get_trainer_stats(conn, trainer_names, race_date)

            return {
                "races": [race_info],
                "horses": horses,
                "past_performances": past_perfs,
                "jockey_stats": jockey_stats,
                "trainer_stats": trainer_stats,
            }
        finally:
            conn.close()

    def get_current_race_card(self, race_id: str) -> dict:
        """当日レース出走情報

        FeatureGenerator が消費する形式: {race, entries}
        """
        conn = self.loader.get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM race_horse_detail WHERE race_id = ? ORDER BY umaban",
                (race_id,),
            ).fetchall()

            if not rows:
                return {"race": {}, "entries": []}

            race = self._row_to_race(rows[0])
            race_date = rows[0]["race_date"]
            horse_ids = [r["ketto_toroku_bango"] for r in rows if r["ketto_toroku_bango"]]
            past_perfs = self._get_past_performances(conn, horse_ids, race_date)

            entries = []
            for r in rows:
                hid = r["ketto_toroku_bango"]
                style = self._infer_style_from_corners(r)
                entries.append({
                    "entry_id": f"{race_id}_{r['umaban']}",
                    "horse": {
                        "horse_id": hid,
                        "horse_name": r["horse_name"],
                        "age": self._safe_int(r["age"]),
                        "gender": {"1": "牡", "2": "牝", "3": "セン"}.get(r["sex_code"], "牡"),
                        "trainer_name": r["trainer_name_short"],
                    },
                    "jockey": {
                        "jockey_id": r["jockey_code"],
                        "jockey_name": r["jockey_name_short"],
                    },
                    "weight_carried": self._safe_float(r["burden_weight_kg"]),
                    "post_position": self._safe_int(r["umaban"]),
                    "bracket_number": self._safe_int(r["wakuban"]),
                    "horse_weight": self._safe_int(r["body_weight_kg"]) or None,
                    "weight_change": self._safe_int(r["body_weight_diff"]) or None,
                    "past_performances": past_perfs.get(hid, []),
                    "style": style,
                })

            return {"race": race, "entries": entries}
        finally:
            conn.close()

    def get_backtest_data(self, config: dict) -> list[dict]:
        """バックテスト用過去データ — 結果が有効なレースのみ（時系列順）"""
        max_races = config.get("max_races", 500)

        conn = self.loader.get_connection()
        try:
            # 1着馬が存在する (= arrival_order = '1') レースのみを取得
            rows = conn.execute(
                "SELECT r.race_id, r.race_date "
                "FROM race_horse_detail r "
                "WHERE r.arrival_order = '1' AND r.is_valid_result = '1' "
                "GROUP BY r.race_id "
                "ORDER BY r.race_date ASC LIMIT ?",
                (max_races,),
            ).fetchall()

            results = []
            for r in rows:
                rid = r["race_id"]
                rdate = r["race_date"]
                winner_rows = conn.execute(
                    "SELECT ketto_toroku_bango FROM race_horse_detail "
                    "WHERE race_id = ? AND arrival_order = '1'",
                    (rid,),
                ).fetchall()
                winner_ids = [wr["ketto_toroku_bango"] for wr in winner_rows]
                results.append({
                    "race_id": rid,
                    "race_date": rdate,
                    "actual_result": winner_ids,
                })

            return results
        finally:
            conn.close()

    def get_predicted_odds(self, race_id: str) -> dict:
        return {"win": {}, "place": {}, "quinella": {}}

    def get_actual_odds(self, race_id: str) -> dict:
        conn = self.loader.get_connection()
        try:
            rows = conn.execute(
                "SELECT umaban, win_odds FROM race_horse_detail WHERE race_id = ?",
                (race_id,),
            ).fetchall()
            win = {}
            for r in rows:
                if r["win_odds"]:
                    win[r["umaban"]] = self._safe_float(r["win_odds"])
            return {"win": win}
        finally:
            conn.close()

    def get_web_content(self, race_id: str, horse_ids: list[str]) -> dict:
        return {"horse_intel": [], "recent_news": []}

    # ---- 内部ヘルパー ----

    def _get_past_performances(self, conn, horse_ids: list[str], before_date: str) -> dict:
        """指定日より前の出走履歴を取得"""
        if not horse_ids:
            return {}
        placeholders = ",".join("?" for _ in horse_ids)
        rows = conn.execute(
            f"SELECT * FROM race_horse_detail "
            f"WHERE ketto_toroku_bango IN ({placeholders}) "
            f"AND race_date < ? AND is_valid_result = '1' "
            f"ORDER BY race_date DESC",
            (*horse_ids, before_date),
        ).fetchall()

        perfs = {}
        for r in rows:
            hid = r["ketto_toroku_bango"]
            pp = {
                "distance": self._safe_int(r["distance_m"]) or 2000,
                "finish_position": self._safe_int(r["arrival_order"]) or 0,
                "total_runners": self._safe_int(r["registered_count"]) or 10,
                "track_type": _infer_track_type(r["track_code"]),
                "course": JYO_CODE_MAP.get(r["jyo_code"], ""),
                "last_3f": self._safe_float(r["last_3f_horse"]),
                "running_style": self._infer_style_from_corners(r),
                "grade": self._decode_grade(r["grade_code"]),
                "race_date": r["race_date"],
            }
            perfs.setdefault(hid, []).append(pp)
        return perfs

    def _get_jockey_stats(self, conn, jockey_ids: list[str], before_date: str) -> dict:
        """騎手成績を集計"""
        if not jockey_ids:
            return {}
        placeholders = ",".join("?" for _ in jockey_ids)
        rows = conn.execute(
            f"SELECT jockey_code, "
            f"COUNT(*) as total, "
            f"SUM(CASE WHEN arrival_order = '1' THEN 1 ELSE 0 END) as wins "
            f"FROM race_horse_detail "
            f"WHERE jockey_code IN ({placeholders}) AND race_date < ? "
            f"AND is_valid_result = '1' "
            f"GROUP BY jockey_code",
            (*jockey_ids, before_date),
        ).fetchall()

        stats = {}
        for r in rows:
            jid = r["jockey_code"]
            total = r["total"]
            wins = r["wins"]
            win_rate = wins / total if total > 0 else 0
            stats[jid] = {
                "jockey_id": jid,
                "total_rides": total,
                "wins": wins,
                "win_rate": round(win_rate, 3),
                "course_stats": {},
            }

        # コース別成績
        for jid in jockey_ids:
            course_rows = conn.execute(
                "SELECT jyo_code, "
                "COUNT(*) as total, "
                "SUM(CASE WHEN arrival_order = '1' THEN 1 ELSE 0 END) as wins "
                "FROM race_horse_detail "
                "WHERE jockey_code = ? AND race_date < ? AND is_valid_result = '1' "
                "GROUP BY jyo_code",
                (jid, before_date),
            ).fetchall()
            for cr in course_rows:
                course = JYO_CODE_MAP.get(cr["jyo_code"], "")
                if course and cr["total"] > 0:
                    stats.setdefault(jid, {}).setdefault("course_stats", {})[course] = {
                        "win_rate": round(cr["wins"] / cr["total"], 3)
                    }
        return stats

    def _get_trainer_stats(self, conn, trainer_names: list[str], before_date: str) -> dict:
        """調教師成績を集計"""
        if not trainer_names:
            return {}
        placeholders = ",".join("?" for _ in trainer_names)
        rows = conn.execute(
            f"SELECT trainer_name_short, "
            f"COUNT(*) as total, "
            f"SUM(CASE WHEN arrival_order = '1' THEN 1 ELSE 0 END) as wins "
            f"FROM race_horse_detail "
            f"WHERE trainer_name_short IN ({placeholders}) AND race_date < ? "
            f"AND is_valid_result = '1' "
            f"GROUP BY trainer_name_short",
            (*trainer_names, before_date),
        ).fetchall()

        stats = {}
        for r in rows:
            name = r["trainer_name_short"]
            total = r["total"]
            wins = r["wins"]
            stats[name] = {
                "win_rate": round(wins / total, 3) if total > 0 else 0,
                "total_runs": total,
                "wins": wins,
            }
        return stats

    def _row_to_race(self, row) -> dict:
        """SQLite Row → レース情報dict"""
        return {
            "race_id": row["race_id"],
            "race_date": row["race_date"],
            "course": JYO_CODE_MAP.get(row["jyo_code"], ""),
            "distance": self._safe_int(row["distance_m"]) or 2000,
            "track_type": _infer_track_type(row["track_code"]),
            "grade": self._decode_grade(row["grade_code"]),
            "weather": {"1": "晴", "2": "曇", "3": "雨"}.get(row["weather_code"], ""),
            "condition": {"1": "良", "2": "稍重", "3": "重", "4": "不良"}.get(
                row["turf_condition_code"], "良"
            ),
            "field_size": self._safe_int(row["registered_count"]) or 14,
            "race_name": row["race_name"],
        }

    def _row_to_horse(self, row) -> dict:
        """SQLite Row → 馬情報dict"""
        return {
            "horse_id": row["ketto_toroku_bango"],
            "horse_name": row["horse_name"],
            "age": self._safe_int(row["age"]),
            "sex": {"1": "牡", "2": "牝", "3": "セン"}.get(row["sex_code"], "牡"),
            "trainer_name": row["trainer_name_short"],
        }

    @staticmethod
    def _infer_style_from_corners(row) -> str:
        """コーナー通過順から脚質を推定"""
        corners = []
        for c in ["corner1_order", "corner2_order", "corner3_order", "corner4_order"]:
            val = row[c] if hasattr(row, "keys") else ""
            try:
                pos = int(val) if val else 0
            except (ValueError, TypeError):
                pos = 0
            if pos > 0:
                corners.append(pos)

        if not corners:
            return "差し"

        total_runners = 14  # fallback
        try:
            total_runners = int(row["registered_count"]) if row["registered_count"] else 14
        except (ValueError, TypeError):
            pass

        avg_pos = sum(corners) / len(corners)
        ratio = avg_pos / total_runners if total_runners > 0 else 0.5

        if ratio <= 0.25:
            return "逃げ"
        elif ratio <= 0.45:
            return "先行"
        elif ratio <= 0.65:
            return "差し"
        else:
            return "追込"

    @staticmethod
    def _decode_grade(grade_code: str) -> str:
        grade_map = {"A": "GI", "B": "GII", "C": "GIII", "D": "L", "E": "L", "F": "L"}
        if not grade_code:
            return "L"
        first = grade_code[0].upper() if grade_code else ""
        return grade_map.get(first, "L")

    @staticmethod
    def _safe_int(val) -> int | None:
        try:
            return int(val) if val else None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _safe_float(val) -> float | None:
        try:
            return float(val) if val else None
        except (ValueError, TypeError):
            return None

    def _empty_historical(self) -> dict:
        return {
            "races": [],
            "horses": {},
            "past_performances": {},
            "jockey_stats": {},
            "trainer_stats": {},
        }
