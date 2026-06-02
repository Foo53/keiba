"""Agent 1-6 のテスト"""

import pytest
from keiba.agents.historical_data_manager import HistoricalDataManager
from keiba.agents.current_data_fetcher import CurrentDataFetcher
from keiba.agents.data_quality_checker import DataQualityChecker
from keiba.agents.feature_generator import FeatureGenerator
from keiba.agents.python_analyzer import PythonAnalyzer
from keiba.agents.web_researcher import WebResearcher


class TestHistoricalDataManager:
    def test_loads_historical_data(self, fresh_context, sample_data_source):
        agent = HistoricalDataManager(sample_data_source)
        result = agent.execute(fresh_context)
        assert result.historical_data is not None
        assert "horses" in result.historical_data
        assert len(result.historical_data["horses"]) == 10

    def test_validate_requires_race_id(self, sample_data_source):
        from keiba.models.pipeline import PipelineContext
        ctx = PipelineContext(pipeline_id="t", race_id="", started_at="2026-01-01T00:00:00", current_stage="x")
        agent = HistoricalDataManager(sample_data_source)
        assert agent.validate_input(ctx) is False

    def test_agent_result_recorded(self, fresh_context, sample_data_source):
        agent = HistoricalDataManager(sample_data_source)
        result = agent.execute(fresh_context)
        assert len(result.agent_results) == 1
        assert result.agent_results[0]["success"] is True


class TestCurrentDataFetcher:
    def test_loads_race_card(self, context_with_historical, sample_data_source):
        agent = CurrentDataFetcher(sample_data_source)
        result = agent.execute(context_with_historical)
        assert result.current_race_data is not None
        assert len(result.current_race_data["entries"]) == 10

    def test_validate_requires_historical(self, fresh_context, sample_data_source):
        agent = CurrentDataFetcher(sample_data_source)
        assert agent.validate_input(fresh_context) is False


class TestDataQualityChecker:
    def test_passes_clean_data(self, context_with_current):
        agent = DataQualityChecker()
        result = agent.execute(context_with_current)
        assert result.quality_check is not None
        assert result.quality_check["passed"] is True
        assert result.quality_check["completeness_score"] > 0.9

    def test_completeness_score_is_float(self, context_with_current):
        agent = DataQualityChecker()
        result = agent.execute(context_with_current)
        assert isinstance(result.quality_check["completeness_score"], float)


class TestFeatureGenerator:
    def test_generates_features(self, context_with_quality):
        agent = FeatureGenerator()
        result = agent.execute(context_with_quality)
        assert result.features is not None
        assert len(result.features["horse_features"]) == 10

    def test_feature_scores_in_range(self, context_with_quality):
        agent = FeatureGenerator()
        result = agent.execute(context_with_quality)
        for hf in result.features["horse_features"]:
            assert 0 <= hf["distance_aptitude_score"] <= 100
            assert 0 <= hf["track_turf_score"] <= 100
            assert 0 <= hf["form_score"] <= 100
            assert 0 <= hf["style_consistency"] <= 1

    def test_closing_speed_rank_assigned(self, context_with_quality):
        agent = FeatureGenerator()
        result = agent.execute(context_with_quality)
        ranked = [hf for hf in result.features["horse_features"] if hf.get("closing_speed_rank")]
        assert len(ranked) > 0


class TestPythonAnalyzer:
    def test_probabilities_sum_near_one(self, context_with_features):
        agent = PythonAnalyzer()
        result = agent.execute(context_with_features)
        total = sum(p["win_probability"] for p in result.analysis["probabilities"])
        assert 0.95 < total < 1.05

    def test_ranking_is_consistent(self, context_with_features):
        agent = PythonAnalyzer()
        result = agent.execute(context_with_features)
        probs = result.analysis["probabilities"]
        for i in range(len(probs) - 1):
            assert probs[i]["win_probability"] >= probs[i + 1]["win_probability"]

    def test_method_is_statistical(self, context_with_features):
        agent = PythonAnalyzer()
        result = agent.execute(context_with_features)
        assert result.analysis["method"] == "statistical"


class TestWebResearcher:
    def test_returns_intel_for_all_horses(self, context_with_current, sample_data_source):
        agent = WebResearcher(sample_data_source)
        result = agent.execute(context_with_current)
        assert result.web_research is not None
        assert len(result.web_research["horse_intel"]) == 10

    def test_track_tendencies_present(self, context_with_current, sample_data_source):
        agent = WebResearcher(sample_data_source)
        result = agent.execute(context_with_current)
        assert len(result.web_research["track_tendencies"]) > 0
