"""データマージャー

netkeiba と JRA の両方から取得したデータを統合・重複排除する。
主ソース + 補完ソースのモデル: 主ソースのデータをベースに、
None / 空のフィールドをセカンダリソースから補完する。
"""

import logging

from keiba.data.production.exceptions import AllSourcesFailedError

logger = logging.getLogger("keiba.DataMerger")


class DataMerger:
    """複数ソースのデータをマージ・重複排除"""

    # ------------------------------------------------------------------
    # レースカード統合
    # ------------------------------------------------------------------

    def merge_race_cards(self, netkeiba_card: dict | None, jra_card: dict | None) -> dict:
        """レースカードを統合。JRA（公式）が主、netkeiba が補完。"""
        if netkeiba_card is None and jra_card is None:
            raise AllSourcesFailedError("No race card data from any source")

        if jra_card is None:
            logger.info("Using netkeiba race card only (JRA unavailable)")
            return netkeiba_card  # type: ignore
        if netkeiba_card is None:
            logger.info("Using JRA race card only (netkeiba unavailable)")
            return jra_card

        # JRA の entries をベースに、netkeiba で補完
        nk_entries = {
            e.get("horse_id") or e.get("horse_name", ""): e
            for e in netkeiba_card.get("entries", [])
        }

        merged_entries = []
        for jra_entry in jra_card.get("entries", []):
            key = jra_entry.get("horse_id") or jra_entry.get("horse_name", "")
            nk_entry = nk_entries.get(key, {})
            merged_entries.append(self._merge_entry(jra_entry, nk_entry))

        # レース基本情報はフィールドが多い方を採用
        merged_race = self._merge_entry(
            jra_card.get("race", {}),
            netkeiba_card.get("race", {}),
        )

        return {"race": merged_race, "entries": merged_entries}

    # ------------------------------------------------------------------
    # 過去データ統合
    # ------------------------------------------------------------------

    def merge_historical_data(self, netkeiba_data: dict | None, jra_data: dict | None) -> dict:
        """過去データを統合。netkeiba（データ豊富）が主、JRA が補完。"""
        if netkeiba_data is None and jra_data is None:
            raise AllSourcesFailedError("No historical data from any source")

        if netkeiba_data is None:
            logger.info("Using JRA historical data only (netkeiba unavailable)")
            return jra_data  # type: ignore
        if jra_data is None:
            logger.info("Using netkeiba historical data only (JRA unavailable)")
            return netkeiba_data

        # 馬データ: netkeiba をベースに JRA で補完
        nk_horses = netkeiba_data.get("horses", {})
        jra_horses = jra_data.get("horses", {})
        merged_horses = {}
        all_ids = set(nk_horses.keys()) | set(jra_horses.keys())
        for hid in all_ids:
            merged_horses[hid] = self._merge_entry(
                nk_horses.get(hid, {}),
                jra_horses.get(hid, {}),
            )

        # 過去成績: netkeiba 優先（last_3f 等の詳細データがあるため）
        nk_pp = netkeiba_data.get("past_performances", {})
        jra_pp = jra_data.get("past_performances", {})
        merged_pp = {}
        all_ids_pp = set(nk_pp.keys()) | set(jra_pp.keys())
        for hid in all_ids_pp:
            nk_races = {r.get("race_id", ""): r for r in nk_pp.get(hid, [])}
            jra_races = {r.get("race_id", ""): r for r in jra_pp.get(hid, [])}
            merged_list = []
            for rid in set(nk_races.keys()) | set(jra_races.keys()):
                # netkeiba 版を優先（フィールド数が多い）
                if rid in nk_races:
                    merged_list.append(nk_races[rid])
                elif rid in jra_races:
                    merged_list.append(jra_races[rid])
            merged_pp[hid] = merged_list

        # 騎手成績
        merged_jockey = self._merge_dicts(
            netkeiba_data.get("jockey_stats", {}),
            jra_data.get("jockey_stats", {}),
        )

        # 厩舎成績
        merged_trainer = self._merge_dicts(
            netkeiba_data.get("trainer_stats", {}),
            jra_data.get("trainer_stats", {}),
        )

        result = {
            "races": netkeiba_data.get("races", []) + jra_data.get("races", []),
            "horses": merged_horses,
            "past_performances": merged_pp,
            "jockey_stats": merged_jockey,
            "trainer_stats": merged_trainer,
        }

        # _predicted_odds, _actual_odds があれば引き継ぎ
        for key in ["_predicted_odds", "_actual_odds"]:
            if key in netkeiba_data:
                result[key] = netkeiba_data[key]
            elif key in jra_data:
                result[key] = jra_data[key]

        return result

    # ------------------------------------------------------------------
    # オッズ統合
    # ------------------------------------------------------------------

    def merge_odds(self, netkeiba_odds: dict | None, jra_odds: dict | None) -> dict:
        """オッズを統合。JRA（リアルタイム）が主、netkeiba が補完。"""
        if netkeiba_odds is None and jra_odds is None:
            raise AllSourcesFailedError("No odds data from any source")

        if jra_odds is None:
            return netkeiba_odds  # type: ignore
        if netkeiba_odds is None:
            return jra_odds  # type: ignore

        # entries のマージ
        nk_map = {
            e.get("entry_id", ""): e for e in netkeiba_odds.get("entries", [])
        }
        merged_entries = []
        for jra_entry in jra_odds.get("entries", []):
            eid = jra_entry.get("entry_id", "")
            nk_entry = nk_map.get(eid, {})
            merged_entries.append(self._merge_entry(jra_entry, nk_entry))

        # JRA にないエントリを netkeiba から追加
        jra_ids = {e.get("entry_id", "") for e in jra_odds.get("entries", [])}
        for nk_entry in netkeiba_odds.get("entries", []):
            if nk_entry.get("entry_id", "") not in jra_ids:
                merged_entries.append(nk_entry)

        result = dict(jra_odds)
        result["entries"] = merged_entries
        return result

    # ------------------------------------------------------------------
    # Web コンテンツ統合
    # ------------------------------------------------------------------

    def merge_web_content(self, netkeiba_content: dict | None, jra_content: dict | None) -> dict:
        """Web コンテンツを統合。補完的関係なので union。"""
        if netkeiba_content is None and jra_content is None:
            raise AllSourcesFailedError("No web content from any source")

        if netkeiba_content is None:
            return jra_content  # type: ignore
        if jra_content is None:
            return netkeiba_content  # type: ignore

        # track_tendencies: union
        nk_tendencies = netkeiba_content.get("track_tendencies", [])
        jra_tendencies = jra_content.get("track_tendencies", [])
        merged_tendencies = list(dict.fromkeys(nk_tendencies + jra_tendencies))

        # horse_intel: netkeiba をベースに JRA で補完
        nk_intel = {h["horse_id"]: h for h in netkeiba_content.get("horse_intel", []) if "horse_id" in h}
        jra_intel = {h["horse_id"]: h for h in jra_content.get("horse_intel", []) if "horse_id" in h}
        merged_intel = []
        all_ids = set(nk_intel.keys()) | set(jra_intel.keys())
        for hid in all_ids:
            merged_intel.append(self._merge_entry(
                nk_intel.get(hid, {}),
                jra_intel.get(hid, {}),
            ))

        return {
            "race_id": netkeiba_content.get("race_id", ""),
            "track_tendencies": merged_tendencies,
            "weather_forecast": jra_content.get("weather_forecast") or netkeiba_content.get("weather_forecast"),
            "horse_intel": merged_intel,
        }

    # ------------------------------------------------------------------
    # ユーティリティ
    # ------------------------------------------------------------------

    def _merge_entry(self, primary: dict, secondary: dict) -> dict:
        """2つの dict をマージ。primary の None/空フィールドを secondary で補完。"""
        merged = dict(primary)
        for key, value in secondary.items():
            if key not in merged or merged[key] is None or merged[key] == "" or merged[key] == []:
                merged[key] = value
            elif isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = self._merge_entry(merged[key], value)
        return merged

    def _merge_dicts(self, primary: dict, secondary: dict) -> dict:
        """キーで dict をマージ。primary をベースに secondary のみのキーを追加。"""
        merged = dict(primary)
        for key, value in secondary.items():
            if key not in merged:
                merged[key] = value
            else:
                merged[key] = self._merge_entry(merged[key], value)
        return merged
