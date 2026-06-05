"""LightGBM学習パイプラインのテスト"""

import json
from pathlib import Path

import pytest

from keiba.data.sample.sample_source import SampleDataSource
from keiba.ml.trainer import LightGBMTrainer


class TestTrainerWithSampleData:
    def test_collects_data(self):
        trainer = LightGBMTrainer(SampleDataSource())
        X, y, _ = trainer.collect_training_data()
        assert len(X) > 0
        assert len(X) == len(y)
        assert 1 in y  # 勝者が含まれる
        assert 0 in y  # 非勝者が含まれる

    def test_feature_dimension(self):
        from keiba.ml.feature_vectorizer import FEATURE_COLUMNS
        trainer = LightGBMTrainer(SampleDataSource())
        X, _, _ = trainer.collect_training_data()
        for row in X:
            assert len(row) == len(FEATURE_COLUMNS)

    def test_trains_and_saves_model(self, tmp_path, monkeypatch):
        """サンプルデータで学習→モデル保存を確認"""
        monkeypatch.setattr("keiba.ml.trainer.MODEL_DIR", tmp_path)

        trainer = LightGBMTrainer(SampleDataSource())
        report = trainer.train(months=1, max_races=10, optuna_trials=3)

        # モデルファイル確認
        model_path = tmp_path / "lgbm_latest.txt"
        assert model_path.exists()

        # メタデータ確認
        meta_path = tmp_path / "lgbm_metadata.json"
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert "train_samples" in meta
        assert "val_auc" in meta
        assert "feature_names" in meta
        assert meta["train_samples"] > 0

    def test_metadata_has_top_features(self, tmp_path, monkeypatch):
        monkeypatch.setattr("keiba.ml.trainer.MODEL_DIR", tmp_path)

        trainer = LightGBMTrainer(SampleDataSource())
        report = trainer.train(months=1, max_races=10, optuna_trials=3)

        assert "top_features" in report
        assert len(report["top_features"]) > 0
        for feat in report["top_features"]:
            assert "feature" in feat
            assert "importance" in feat

    def test_best_params_in_report(self, tmp_path, monkeypatch):
        monkeypatch.setattr("keiba.ml.trainer.MODEL_DIR", tmp_path)

        trainer = LightGBMTrainer(SampleDataSource())
        report = trainer.train(months=1, max_races=10, optuna_trials=3)

        assert "best_params" in report
        assert "num_leaves" in report["best_params"]
        assert "learning_rate" in report["best_params"]
