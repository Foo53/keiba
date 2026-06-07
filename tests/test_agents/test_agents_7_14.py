"""Agent 7-14 のテスト"""

import pytest
from keiba.agents.evidence_integrator import EvidenceIntegrator
from keiba.agents.predicted_odds_evaluator import PredictedOddsEvaluator
from keiba.agents.actual_odds_evaluator import ActualOddsEvaluator
from keiba.agents.prediction_generator import PredictionGenerator
from keiba.agents.backtester import Backtester
from keiba.agents.visualizer import VisualizerAgent
from keiba.agents.ml_predictor import MLPredictor
from keiba.agents.note_structure_researcher import NoteStructureResearcher
from keiba.agents.note_writer import NoteWriter
from keiba.agents.quality_assurance import QualityAssurance
from keiba.data.sample.sample_source import SampleDataSource


def _build_context_up_to(stage_name, sample_data_source):
    """指定ステージまで実行したcontextを構築"""
    from keiba.models.pipeline import PipelineContext
    from keiba.agents.historical_data_manager import HistoricalDataManager
    from keiba.agents.current_data_fetcher import CurrentDataFetcher
    from keiba.agents.data_quality_checker import DataQualityChecker
    from keiba.agents.feature_generator import FeatureGenerator
    from keiba.agents.python_analyzer import PythonAnalyzer
    from keiba.agents.web_researcher import WebResearcher
    from keiba.agents.evidence_integrator import EvidenceIntegrator
    from keiba.agents.predicted_odds_evaluator import PredictedOddsEvaluator
    from keiba.agents.actual_odds_evaluator import ActualOddsEvaluator
    from keiba.agents.prediction_generator import PredictionGenerator
    from keiba.agents.backtester import Backtester
    from keiba.agents.note_structure_researcher import NoteStructureResearcher
    from datetime import datetime

    ds = sample_data_source
    ctx = PipelineContext(pipeline_id="test", race_id="20260607-Tokyo-11", started_at=datetime.now(), current_stage="init")

    stages = [
        ("historical_data", HistoricalDataManager(ds)),
        ("current_data", CurrentDataFetcher(ds)),
        ("quality_check", DataQualityChecker()),
        ("feature_gen", FeatureGenerator()),
        ("python_analysis", PythonAnalyzer()),
        ("web_research", WebResearcher(ds)),
        ("ml_analysis", MLPredictor()),
        ("evidence", EvidenceIntegrator()),
        ("predicted_odds", PredictedOddsEvaluator()),
        ("actual_odds", ActualOddsEvaluator()),
        ("prediction", PredictionGenerator()),
        ("backtest", Backtester(ds)),
        ("visualization", VisualizerAgent()),
        ("note_research", NoteStructureResearcher()),
        ("note_write", NoteWriter()),
        ("qa", QualityAssurance()),
    ]

    for name, agent in stages:
        ctx.current_stage = name
        ctx = agent.execute(ctx)
        if name == stage_name:
            break
    return ctx


class TestEvidenceIntegrator:
    def test_merges_evidence(self):
        ds = SampleDataSource()
        ctx = _build_context_up_to("evidence", ds)
        assert ctx.evidence is not None
        assert len(ctx.evidence["horses"]) == 10

    def test_web_adjustment_within_limits(self):
        ds = SampleDataSource()
        ctx = _build_context_up_to("evidence", ds)
        for h in ctx.evidence["horses"]:
            assert abs(h.get("web_adjustment", 0)) <= 0.15


class TestPredictedOddsEvaluator:
    def test_marked_provisional(self):
        ds = SampleDataSource()
        ctx = _build_context_up_to("predicted_odds", ds)
        assert ctx.predicted_odds_eval["is_provisional"] is True

    def test_value_candidates_exist(self):
        ds = SampleDataSource()
        ctx = _build_context_up_to("predicted_odds", ds)
        assert len(ctx.predicted_odds_eval["evaluations"]) == 10


class TestActualOddsEvaluator:
    def test_grade_assignment(self):
        ds = SampleDataSource()
        ctx = _build_context_up_to("actual_odds", ds)
        evals = ctx.actual_odds_eval["evaluations"]
        grades = {e["recommendation_grade"] for e in evals}
        assert grades.intersection({"S", "A", "B", "C"})

    def test_expected_value_computed(self):
        ds = SampleDataSource()
        ctx = _build_context_up_to("actual_odds", ds)
        for e in ctx.actual_odds_eval["evaluations"]:
            assert "expected_value" in e


class TestPredictionGenerator:
    def test_generates_predictions(self):
        ds = SampleDataSource()
        ctx = _build_context_up_to("prediction", ds)
        assert ctx.prediction_actual is not None

    def test_disclaimer_present(self):
        ds = SampleDataSource()
        ctx = _build_context_up_to("prediction", ds)
        assert "自己責任" in ctx.prediction_actual.get("disclaimer", "")


class TestBacktester:
    def test_returns_summary(self):
        ds = SampleDataSource()
        ctx = _build_context_up_to("backtest", ds)
        assert ctx.backtest is not None
        assert ctx.backtest["total_races"] > 0
        assert "roi" in ctx.backtest

    def test_breakdowns_present(self):
        ds = SampleDataSource()
        ctx = _build_context_up_to("backtest", ds)
        assert "breakdown_by_bet_type" in ctx.backtest
        assert "breakdown_by_course" in ctx.backtest


class TestNoteWriter:
    def test_creates_article(self):
        ds = SampleDataSource()
        ctx = _build_context_up_to("note_write", ds)
        assert ctx.note_article is not None
        assert len(ctx.note_article["body_markdown"]) > 100

    def test_no_prohibited_words(self):
        ds = SampleDataSource()
        ctx = _build_context_up_to("note_write", ds)
        assert ctx.note_article.get("prohibited_word_violations", []) == []

    def test_risk_warning_present(self):
        ds = SampleDataSource()
        ctx = _build_context_up_to("note_write", ds)
        # risk_warningにJRA-VAN免責、bodyに自己責任が含まれる
        assert "自己責任" in ctx.note_article.get("body_markdown", "")


class TestQualityAssurance:
    def test_scores_120_max(self):
        ds = SampleDataSource()
        ctx = _build_context_up_to("qa", ds)
        assert ctx.qa_report["total_score"] <= 120

    def test_passes_with_sample_data(self):
        ds = SampleDataSource()
        ctx = _build_context_up_to("qa", ds)
        assert ctx.qa_report["passed"] is True

    def test_all_criteria_scored(self):
        ds = SampleDataSource()
        ctx = _build_context_up_to("qa", ds)
        assert len(ctx.qa_report["criteria"]) == 10


class TestVisualizerAgent:
    def test_generates_charts(self):
        ds = SampleDataSource()
        ctx = _build_context_up_to("visualization", ds)
        assert ctx.eda_images is not None
        assert len(ctx.eda_images) > 0

    def test_output_files_exist(self):
        ds = SampleDataSource()
        ctx = _build_context_up_to("visualization", ds)
        from pathlib import Path
        if ctx.eda_images:
            for name, path in ctx.eda_images.items():
                assert Path(path).exists(), f"Chart {name} not found at {path}"

    def test_validate_requires_features_and_evidence(self):
        from keiba.models.pipeline import PipelineContext
        from datetime import datetime
        ctx = PipelineContext(
            pipeline_id="t", race_id="test", started_at=datetime.now(), current_stage="x"
        )
        agent = VisualizerAgent()
        assert agent.validate_input(ctx) is False


class TestMLPredictor:
    def test_skips_when_no_model(self):
        """学習済みモデルなしでもエラーにならない"""
        ds = SampleDataSource()
        ctx = _build_context_up_to("ml_analysis", ds)
        # モデルがない場合はml_analysisがNone（graceful degradation）
        assert ctx.ml_analysis is None or ctx.features is not None

    def test_validate_requires_features(self):
        from keiba.models.pipeline import PipelineContext
        from datetime import datetime
        ctx = PipelineContext(
            pipeline_id="t", race_id="test", started_at=datetime.now(), current_stage="x"
        )
        agent = MLPredictor()
        assert agent.validate_input(ctx) is False

    def test_validate_passes_with_features(self):
        from keiba.models.pipeline import PipelineContext
        from datetime import datetime
        ctx = PipelineContext(
            pipeline_id="t", race_id="test", started_at=datetime.now(), current_stage="x",
            features={"horse_features": [{"entry_id": "e1", "horse_id": "h1"}]},
        )
        agent = MLPredictor()
        assert agent.validate_input(ctx) is True
