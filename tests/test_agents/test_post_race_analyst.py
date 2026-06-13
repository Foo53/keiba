"""PostRaceAnalyst のテスト

context保存・evidence/web比較の拡張ロジックを検証する。
analyze() は内部で _quantitative_comparison 等の多数の依存を持つため、
ここでは拡張した _evidence_analysis / _web_research_analysis / _build_report
の単体テストに絞る。
"""

import pytest

from keiba.agents.post_race_analyst import PostRaceAnalyst


@pytest.fixture
def analyst():
    return PostRaceAnalyst(data_source=None)


@pytest.fixture
def evidence():
    """2頭のサンプルevidence（ルシードS・逃げ / ピューロマジックC・差し）"""
    return {
        "horses": [
            {
                "entry_id": "202602010111_12",
                "horse_name": "ルシード",
                "evidence_grade": "S",
                "style": "逃げ",
            },
            {
                "entry_id": "202602010111_07",
                "horse_name": "ピューロマジック",
                "evidence_grade": "C",
                "style": "差し",
            },
        ]
    }


@pytest.fixture
def finish_map():
    """馬番→結果（ルシード12着・実際は差し / ピューロマジック1着・実際は逃げ）"""
    return {
        12: {"post_position": 12, "finish_position": 12, "running_style": "差し"},
        7: {"post_position": 7, "finish_position": 1, "running_style": "逃げ"},
    }


class TestEvidenceAnalysis:
    def test_grade_summary(self, analyst, evidence, finish_map):
        result = analyst._evidence_analysis(evidence, finish_map)
        grades = {g["grade"]: g for g in result["grade_summary"]}
        assert "S" in grades and "C" in grades
        assert grades["S"]["count"] == 1
        assert grades["S"]["avg_finish"] == 12.0
        assert grades["S"]["in_top3_rate"] == 0.0
        assert grades["C"]["avg_finish"] == 1.0
        assert grades["C"]["in_top3_rate"] == 1.0

    def test_high_grade_miss(self, analyst, evidence, finish_map):
        result = analyst._evidence_analysis(evidence, finish_map)
        misses = result["high_grade_misses"]
        assert len(misses) == 1
        assert misses[0]["name"] == "ルシード"
        assert misses[0]["grade"] == "S"
        assert misses[0]["finish"] == 12

    def test_low_grade_hit(self, analyst, evidence, finish_map):
        result = analyst._evidence_analysis(evidence, finish_map)
        hits = result["low_grade_hits"]
        assert len(hits) == 1
        assert hits[0]["name"] == "ピューロマジック"
        assert hits[0]["finish"] == 1

    def test_umaban_extraction_from_entry_id(self, analyst, evidence, finish_map):
        """entry_id（{race_id}_{umaban:02d}・アンダースコア区切り）から馬番を抽出できること"""
        result = analyst._evidence_analysis(evidence, finish_map)
        # 両馬とも finish_map と紐付いて集計されている（計2頭）
        total = sum(g["count"] for g in result["grade_summary"])
        assert total == 2

    def test_style_match_rate(self, analyst, evidence, finish_map):
        """脚質予想(style)と実際のrunning_styleの一致率"""
        result = analyst._evidence_analysis(evidence, finish_map)
        # ルシード: 逃げ vs 差し(不一致) / ピューロマジック: 差し vs 逃げ(不一致) → 0%
        assert result["style_match_rate"] == 0.0

    def test_excluded_horse_not_counted(self, analyst):
        """除外馬（finish_position=0）は集計外"""
        evidence = {
            "horses": [
                {
                    "entry_id": "202602010111_09",
                    "horse_name": "除外馬",
                    "evidence_grade": "B",
                    "style": "差し",
                }
            ]
        }
        finish_map = {9: {"post_position": 9, "finish_position": 0, "running_style": ""}}
        result = analyst._evidence_analysis(evidence, finish_map)
        assert result["grade_summary"] == []
        assert result["style_match_rate"] is None

    def test_empty_horses(self, analyst):
        """evidence.horses が空でも安全"""
        result = analyst._evidence_analysis({"horses": []}, {})
        assert result["grade_summary"] == []
        assert result["high_grade_misses"] == []
        assert result["style_match_rate"] is None


class TestWebResearchAnalysis:
    def test_empty_intel_safe(self, analyst):
        """horse_intel空配列・気象なしでも安全に動く"""
        result = analyst._web_research_analysis({"horse_intel": [], "weather_forecast": None}, {})
        assert result["intel_count"] == 0
        assert result["has_weather"] is False

    def test_with_weather(self, analyst):
        result = analyst._web_research_analysis(
            {
                "horse_intel": [{"a": 1}],
                "weather_forecast": {"weather": "晴", "track_condition": "良"},
            },
            {},
        )
        assert result["has_weather"] is True
        assert result["weather"] == "晴"
        assert result["track_condition"] == "良"
        assert result["intel_count"] == 1


class TestBuildReportSections:
    """_build_report の evidence/web セクション出力を検証（後方互換含む）"""

    def _base_kwargs(self, **overrides):
        kwargs = dict(
            race_id="202602010111",
            race_info={"race_name": "テストレース"},
            results_entries=[],
            finish_map={},
            predictions=[],
            model_info={},
            picks={},
            comparison={},
            qualitative={},
            five_axis=[],
            improvements=[],
        )
        kwargs.update(overrides)
        return kwargs

    def test_no_evidence_section_when_none(self, analyst):
        """evidence_analysis/web_analysis 未指定 → 該当セクションが出ない（後方互換）"""
        report = analyst._build_report(**self._base_kwargs())
        assert "根拠（evidence）の検証" not in report
        assert "Web情報の検証" not in report

    def test_evidence_section_when_provided(self, analyst):
        """evidence_analysis 指定 → 根拠検証セクションが出る"""
        report = analyst._build_report(
            **self._base_kwargs(
                evidence_analysis={
                    "grade_summary": [
                        {"grade": "S", "count": 1, "avg_finish": 12.0, "in_top3_rate": 0.0}
                    ],
                    "high_grade_misses": [
                        {"name": "ルシード", "umaban": 12, "grade": "S", "finish": 12}
                    ],
                    "low_grade_hits": [],
                    "style_match_rate": 0.0,
                },
                web_analysis={
                    "has_weather": True,
                    "weather": "晴",
                    "track_condition": "",
                    "intel_count": 0,
                },
            )
        )
        assert "根拠（evidence）の検証" in report
        assert "Web情報の検証" in report
        assert "ルシード" in report
        assert "12.0着" in report
