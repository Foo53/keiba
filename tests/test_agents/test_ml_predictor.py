"""ML予測エージェントのテスト"""

import json
from datetime import datetime
from pathlib import Path

import pytest

from keiba.agents.ml_predictor import MLPredictor
from keiba.data.sample.sample_source import SampleDataSource
from keiba.models.pipeline import PipelineContext


def _build_context_with_features():
    """特徴量まで生成したcontextを構築"""
    from keiba.agents.historical_data_manager import HistoricalDataManager
    from keiba.agents.current_data_fetcher import CurrentDataFetcher
    from keiba.agents.data_quality_checker import DataQualityChecker
    from keiba.agents.feature_generator import FeatureGenerator

    ds = SampleDataSource()
    ctx = PipelineContext(
        pipeline_id="test", race_id="20260607-Tokyo-11",
        started_at=datetime.now(), current_stage="init",
    )
    ctx = HistoricalDataManager(ds).execute(ctx)
    ctx = CurrentDataFetcher(ds).execute(ctx)
    ctx = DataQualityChecker().execute(ctx)
    ctx = FeatureGenerator().execute(ctx)
    return ctx


class TestMLPredictorNoModel:
    def test_skips_gracefully(self):
        """モデルなしでもエラーにならずml_analysis=None"""
        ctx = _build_context_with_features()
        agent = MLPredictor()
        # モデルパスをクリア
        agent.model = None
        result = agent.process(ctx)
        assert result.ml_analysis is None

    def test_validate_passes_with_features(self):
        ctx = _build_context_with_features()
        agent = MLPredictor()
        assert agent.validate_input(ctx) is True

    def test_validate_fails_without_features(self):
        ctx = PipelineContext(
            pipeline_id="t", race_id="test",
            started_at=datetime.now(), current_stage="x",
        )
        agent = MLPredictor()
        assert agent.validate_input(ctx) is False


class TestMLPredictorWithModel:
    def test_predicts_with_trained_model(self, tmp_path, monkeypatch):
        """学習済みモデルで予測できる"""
        # モデル学習
        monkeypatch.setattr("keiba.ml.trainer.MODEL_DIR", tmp_path)
        from keiba.ml.trainer import LightGBMTrainer
        trainer = LightGBMTrainer(SampleDataSource())
        trainer.train(months=1, max_races=10, optuna_trials=3)

        # モデルパスをtmp_pathに差し替え
        monkeypatch.setattr("keiba.agents.ml_predictor.MODEL_PATH", tmp_path / "lgbm_latest.txt")
        monkeypatch.setattr("keiba.agents.ml_predictor.METADATA_PATH", tmp_path / "lgbm_metadata.json")

        ctx = _build_context_with_features()
        agent = MLPredictor()

        result = agent.process(ctx)
        assert result.ml_analysis is not None
        assert "probabilities" in result.ml_analysis
        assert len(result.ml_analysis["probabilities"]) > 0
        assert result.ml_analysis["method"] == "lightgbm"

    def test_probabilities_sum_approximately_one(self, tmp_path, monkeypatch):
        """確率の和が概ね1"""
        monkeypatch.setattr("keiba.ml.trainer.MODEL_DIR", tmp_path)
        from keiba.ml.trainer import LightGBMTrainer
        trainer = LightGBMTrainer(SampleDataSource())
        trainer.train(months=1, max_races=10, optuna_trials=3)

        monkeypatch.setattr("keiba.agents.ml_predictor.MODEL_PATH", tmp_path / "lgbm_latest.txt")
        monkeypatch.setattr("keiba.agents.ml_predictor.METADATA_PATH", tmp_path / "lgbm_metadata.json")

        ctx = _build_context_with_features()
        agent = MLPredictor()
        result = agent.process(ctx)

        probs = result.ml_analysis["probabilities"]
        total = sum(p["win_probability"] for p in probs)
        assert 0.95 < total < 1.05, f"Probabilities sum to {total}"

    def test_output_format_matches_rule_based(self, tmp_path, monkeypatch):
        """出力キーがPythonAnalyzerと同じ構造"""
        monkeypatch.setattr("keiba.ml.trainer.MODEL_DIR", tmp_path)
        from keiba.ml.trainer import LightGBMTrainer
        trainer = LightGBMTrainer(SampleDataSource())
        trainer.train(months=1, max_races=10, optuna_trials=3)

        monkeypatch.setattr("keiba.agents.ml_predictor.MODEL_PATH", tmp_path / "lgbm_latest.txt")
        monkeypatch.setattr("keiba.agents.ml_predictor.METADATA_PATH", tmp_path / "lgbm_metadata.json")

        ctx = _build_context_with_features()
        agent = MLPredictor()
        result = agent.process(ctx)

        for p in result.ml_analysis["probabilities"]:
            assert "entry_id" in p
            assert "horse_name" in p
            assert "win_probability" in p
            assert "place_probability" in p
            assert "rank_by_model" in p
            assert "composite_score" in p

    def test_feature_importance_present(self, tmp_path, monkeypatch):
        monkeypatch.setattr("keiba.ml.trainer.MODEL_DIR", tmp_path)
        from keiba.ml.trainer import LightGBMTrainer
        trainer = LightGBMTrainer(SampleDataSource())
        trainer.train(months=1, max_races=10, optuna_trials=3)

        monkeypatch.setattr("keiba.agents.ml_predictor.MODEL_PATH", tmp_path / "lgbm_latest.txt")
        monkeypatch.setattr("keiba.agents.ml_predictor.METADATA_PATH", tmp_path / "lgbm_metadata.json")

        ctx = _build_context_with_features()
        agent = MLPredictor()
        result = agent.process(ctx)

        imp = result.ml_analysis.get("feature_importance", [])
        assert len(imp) > 0
        for item in imp:
            assert "feature" in item
            assert "importance" in item
