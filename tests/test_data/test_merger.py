"""DataMerger のテスト"""

import pytest

from keiba.data.production.exceptions import AllSourcesFailedError
from keiba.data.production.merger import DataMerger


@pytest.fixture
def merger():
    return DataMerger()


# ------------------------------------------------------------------
# エントリマージ
# ------------------------------------------------------------------

class TestMergeEntry:
    def test_fills_none_from_secondary(self, merger):
        primary = {"horse_name": "ディープインパクト", "age": None, "gender": ""}
        secondary = {"horse_name": "別名", "age": 4, "gender": "牡"}
        result = merger._merge_entry(primary, secondary)
        assert result["horse_name"] == "ディープインパクト"
        assert result["age"] == 4
        assert result["gender"] == "牡"

    def test_keeps_non_none_primary(self, merger):
        primary = {"horse_name": "ディープインパクト", "age": 5}
        secondary = {"horse_name": "別名", "age": 3}
        result = merger._merge_entry(primary, secondary)
        assert result["horse_name"] == "ディープインパクト"
        assert result["age"] == 5

    def test_merges_nested_dicts(self, merger):
        primary = {"horse": {"name": "A", "age": None}}
        secondary = {"horse": {"name": "B", "age": 4}}
        result = merger._merge_entry(primary, secondary)
        assert result["horse"]["name"] == "A"
        assert result["horse"]["age"] == 4


# ------------------------------------------------------------------
# レースカードマージ
# ------------------------------------------------------------------

class TestMergeRaceCards:
    def test_uses_jra_entries_as_base(self, merger):
        jra_card = {
            "race": {"race_name": "ダービー", "distance": 2400},
            "entries": [
                {"entry_id": "E1", "horse_name": "馬A"},
                {"entry_id": "E2", "horse_name": "馬B"},
            ],
        }
        nk_card = {
            "race": {"race_name": "日本ダービー", "distance": 2400},
            "entries": [
                {"entry_id": "E1", "horse_name": "馬A", "pedigree_sire": "ディープ"},
            ],
        }
        result = merger.merge_race_cards(nk_card, jra_card)
        assert len(result["entries"]) == 2
        # JRAのエントリにnetkeibaのpedigree_sireが補完される
        assert result["entries"][0].get("pedigree_sire") == "ディープ"

    def test_netkeiba_only(self, merger):
        nk_card = {"race": {"race_name": "テスト"}, "entries": [{"entry_id": "E1"}]}
        result = merger.merge_race_cards(nk_card, None)
        assert result["entries"] == [{"entry_id": "E1"}]

    def test_jra_only(self, merger):
        jra_card = {"race": {"race_name": "テスト"}, "entries": [{"entry_id": "E1"}]}
        result = merger.merge_race_cards(None, jra_card)
        assert result["entries"] == [{"entry_id": "E1"}]

    def test_both_none_raises_error(self, merger):
        with pytest.raises(AllSourcesFailedError):
            merger.merge_race_cards(None, None)


# ------------------------------------------------------------------
# 過去データマージ
# ------------------------------------------------------------------

class TestMergeHistoricalData:
    def test_merges_horses(self, merger):
        nk_data = {
            "races": [{"race_id": "R1"}],
            "horses": {"H1": {"horse_name": "馬A", "last_3f": 33.5}},
            "past_performances": {"H1": [{"race_id": "R1", "last_3f": 33.5}]},
            "jockey_stats": {"J1": {"win_rate": 0.3}},
            "trainer_stats": {},
        }
        jra_data = {
            "races": [{"race_id": "R2"}],
            "horses": {"H1": {"horse_name": "馬A", "weather": "晴"}},
            "past_performances": {"H1": [{"race_id": "R2", "weather": "晴"}]},
            "jockey_stats": {},
            "trainer_stats": {},
        }
        result = merger.merge_historical_data(nk_data, jra_data)

        # レースは両方含まれる
        assert len(result["races"]) == 2

        # 馬データ: netkeibaのlast_3fが保持される
        assert result["horses"]["H1"]["last_3f"] == 33.5

        # 過去成績: netkeiba版が優先（フィールド数が多い）
        assert len(result["past_performances"]["H1"]) == 2

    def test_netkeiba_only(self, merger):
        nk_data = {
            "races": [], "horses": {}, "past_performances": {},
            "jockey_stats": {}, "trainer_stats": {},
        }
        result = merger.merge_historical_data(nk_data, None)
        assert result["horses"] == {}

    def test_both_none_raises_error(self, merger):
        with pytest.raises(AllSourcesFailedError):
            merger.merge_historical_data(None, None)


# ------------------------------------------------------------------
# オッズマージ
# ------------------------------------------------------------------

class TestMergeOdds:
    def test_prefers_jra_for_actual(self, merger):
        jra_odds = {
            "entries": [
                {"entry_id": "E1", "win_odds": 3.0},
                {"entry_id": "E2", "win_odds": 5.0},
            ]
        }
        nk_odds = {
            "entries": [
                {"entry_id": "E1", "win_odds": 2.8},
                {"entry_id": "E3", "win_odds": 10.0},
            ]
        }
        result = merger.merge_odds(nk_odds, jra_odds)

        # JRAのE1オッズが優先
        assert result["entries"][0]["win_odds"] == 3.0

        # netkeibaのみのE3も含まれる
        entry_ids = [e["entry_id"] for e in result["entries"]]
        assert "E3" in entry_ids

    def test_jra_only(self, merger):
        jra_odds = {"entries": [{"entry_id": "E1", "win_odds": 3.0}]}
        result = merger.merge_odds(None, jra_odds)
        assert len(result["entries"]) == 1

    def test_both_none_raises_error(self, merger):
        with pytest.raises(AllSourcesFailedError):
            merger.merge_odds(None, None)


# ------------------------------------------------------------------
# Web コンテンツマージ
# ------------------------------------------------------------------

class TestMergeWebContent:
    def test_unions_track_tendencies(self, merger):
        nk = {"race_id": "R1", "track_tendencies": ["芝速い"], "horse_intel": []}
        jra = {"race_id": "R1", "track_tendencies": ["馬場良"], "horse_intel": []}
        result = merger.merge_web_content(nk, jra)
        assert "芝速い" in result["track_tendencies"]
        assert "馬場良" in result["track_tendencies"]

    def test_merges_horse_intel(self, merger):
        nk = {"race_id": "R1", "track_tendencies": [], "horse_intel": [
            {"horse_id": "H1", "notable_factors": ["好調"]}
        ]}
        jra = {"race_id": "R1", "track_tendencies": [], "horse_intel": [
            {"horse_id": "H1", "weather_forecast": "晴"}
        ]}
        result = merger.merge_web_content(nk, jra)
        assert len(result["horse_intel"]) == 1
        assert result["horse_intel"][0].get("notable_factors") == ["好調"]

    def test_both_none_raises_error(self, merger):
        with pytest.raises(AllSourcesFailedError):
            merger.merge_web_content(None, None)
