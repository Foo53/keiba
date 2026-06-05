"""LightGBM 学習パイプライン

Optuna によるハイパーパラメータ最適化 + 時系列CV + モデル保存。

参照:
  - LightGBM公式: min_data_in_leaf, feature_fraction, bagging_fraction, lambda_l1/l2 で過学習対策
  - CodeWorks: HyperOpt最適化パターン
  - 芦原氏: Optuna + LightGBM パターン
"""

import json
import random
from datetime import datetime
from pathlib import Path

from keiba.data.base_source import DataSource
from keiba.ml.feature_vectorizer import vectorize_race, FEATURE_COLUMNS

MODEL_DIR = Path("data/store/models")


class LightGBMTrainer:
    """LightGBMモデルの学習・最適化を行う"""

    def __init__(self, data_source: DataSource, config: dict | None = None):
        self.data_source = data_source
        self.config = config or {}

    def train(self, months: int = 12, max_races: int = 500,
              optuna_trials: int = 100) -> dict:
        """モデル学習のエントリポイント。

        1. 学習データ収集
        2. 時系列 train/val/test 分割 (70/15/15)
        3. Optuna でハイパーパラメータ最適化 (train→val)
        4. 最適パラメータで本番学習 (train+val)
        5. test セットで真の汎化性能を評価
        6. モデル + メタデータ保存
        """
        import numpy as np
        import pandas as pd

        # データ収集
        X, y, race_dates = self.collect_training_data(months, max_races)
        if len(X) < 20:
            raise ValueError(f"学習データが不足しています: {len(X)}件（最低20件必要）")

        df = pd.DataFrame(X, columns=FEATURE_COLUMNS)
        df["label"] = y
        df["race_date"] = race_dates
        # race_date で時系列ソート（同日内は元の順序を維持）
        df = df.sort_values("race_date").reset_index(drop=True)

        # 時系列3分割: train 70% / val 15% / test 15%
        n = len(df)
        train_end = int(n * 0.70)
        val_end = int(n * 0.85)

        train_df = df.iloc[:train_end]
        val_df = df.iloc[train_end:val_end]
        test_df = df.iloc[val_end:]

        X_train = train_df[FEATURE_COLUMNS]
        y_train = train_df["label"]
        X_val = val_df[FEATURE_COLUMNS]
        y_val = val_df["label"]
        X_test = test_df[FEATURE_COLUMNS]
        y_test = test_df["label"]

        self.logger_info(
            f"時系列3分割: train={len(train_df)}, val={len(val_df)}, test={len(test_df)}"
        )

        # Optuna最適化（train → val で最適化）
        best_params = self._optimize_hyperparameters(
            X_train, y_train, X_val, y_val, optuna_trials
        )

        # 最適パラメータで本番学習（train + val を使用）
        import lightgbm as lgb

        train_val_df = pd.concat([train_df, val_df])
        X_trainval = train_val_df[FEATURE_COLUMNS]
        y_trainval = train_val_df["label"]

        train_data = lgb.Dataset(X_trainval, label=y_trainval)
        val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)

        model = lgb.train(
            {**best_params, "objective": "binary", "metric": "auc",
             "verbose": -1},
            train_data,
            num_boost_round=1000,
            valid_sets=[val_data],
            callbacks=[lgb.early_stopping(50, verbose=False)],
        )

        # 特徴量重要度
        importance = model.feature_importance(importance_type="gain")
        if hasattr(importance, "tolist"):
            importance = importance.tolist()
        feat_imp = sorted(
            zip(FEATURE_COLUMNS, importance), key=lambda x: x[1], reverse=True
        )
        total_imp = sum(v for _, v in feat_imp) or 1
        top_features = [
            {"feature": name, "importance": round(imp / total_imp, 4)}
            for name, imp in feat_imp[:10]
        ]

        # test セットで真の汎化性能を評価
        test_pred = model.predict(X_test)
        test_auc = self._calc_auc(y_test.tolist(), test_pred.tolist() if hasattr(test_pred, "tolist") else list(test_pred))

        # val AUC（参考値）
        val_pred = model.predict(X_val)
        val_auc = self._calc_auc(y_val.tolist(), val_pred.tolist() if hasattr(val_pred, "tolist") else list(val_pred))

        # モデル保存
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        model.save_model(str(MODEL_DIR / "lgbm_latest.txt"))

        metadata = {
            "trained_at": datetime.now().isoformat(),
            "train_samples": len(train_df),
            "val_samples": len(val_df),
            "test_samples": len(test_df),
            "val_auc": round(val_auc, 4),
            "test_auc": round(test_auc, 4),
            "feature_names": FEATURE_COLUMNS,
            "best_params": best_params,
            "top_features": top_features,
            "data_source": type(self.data_source).__name__,
        }
        (MODEL_DIR / "lgbm_metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        return metadata

    def collect_training_data(self, months: int = 12,
                              max_races: int = 500) -> tuple[list[list[float]], list[int], list[str]]:
        """学習データを収集して特徴量ベクトル + ラベル + race_dates を返す。"""
        from keiba.data.sample.sample_source import SampleDataSource
        from keiba.data.jrvan.data_source import JrVanDataSource

        if isinstance(self.data_source, SampleDataSource):
            X, y = self._collect_sample_data()
            return X, y, [""] * len(X)

        if isinstance(self.data_source, JrVanDataSource):
            return self._collect_jrvan_data(max_races)

        X, y = self._collect_production_data(months, max_races)
        return X, y, [""] * len(X)

    def _collect_sample_data(self) -> tuple[list[list[float]], list[int]]:
        """サンプルデータソースから学習データを生成。

        データ量が少ないため、ガウシアンノイズ追加でデータ拡張する。
        """
        from keiba.agents.feature_generator import FeatureGenerator
        from keiba.agents.historical_data_manager import HistoricalDataManager
        from keiba.agents.current_data_fetcher import CurrentDataFetcher
        from keiba.agents.data_quality_checker import DataQualityChecker
        from keiba.models.pipeline import PipelineContext

        ds = self.data_source
        ctx = PipelineContext(
            pipeline_id="train", race_id="20260607-Tokyo-11",
            started_at=datetime.now(), current_stage="init",
        )
        ctx = HistoricalDataManager(ds).execute(ctx)
        ctx = CurrentDataFetcher(ds).execute(ctx)
        ctx = DataQualityChecker().execute(ctx)
        ctx = FeatureGenerator().execute(ctx)

        horse_features = ctx.features.get("horse_features", [])
        rows = vectorize_race(ctx.features)

        X = []
        y = []
        # オリジナルデータ（サンプルデータの1位馬を勝者とする）
        # サンプルデータでは最初の馬が高スコアなので簡易的に1頭を勝者とする
        winner_idx = 0  # sample dataでは1頭目が最強

        for i, row in enumerate(rows):
            feature_vec = [row.get(col, 0.0) for col in FEATURE_COLUMNS]
            X.append(feature_vec)
            y.append(1 if i == winner_idx else 0)

        # データ拡張: ノイズ追加で5倍に増幅
        import numpy as np
        rng = np.random.RandomState(42)
        augmented_X = list(X)
        augmented_y = list(y)

        for _ in range(5):
            for i, row in enumerate(X):
                noise = rng.normal(0, 0.02, len(row)).tolist()
                noisy = [v + n for v, n in zip(row, noise)]
                augmented_X.append(noisy)
                augmented_y.append(y[i])

        self.logger_info(f"サンプルデータ拡張: {len(X)}件 → {len(augmented_X)}件")
        return augmented_X, augmented_y

    def _collect_jrvan_data(self, max_races: int) -> tuple[list[list[float]], list[int], list[str]]:
        """JRA-VAN SQLiteデータから学習データを収集。

        Returns:
            (X, y, race_dates) — race_datesは時系列ソート用
        """
        from keiba.agents.feature_generator import FeatureGenerator
        from keiba.agents.historical_data_manager import HistoricalDataManager
        from keiba.agents.current_data_fetcher import CurrentDataFetcher
        from keiba.agents.data_quality_checker import DataQualityChecker
        from keiba.models.pipeline import PipelineContext

        bt_data = self.data_source.get_backtest_data({"months": 12, "max_races": max_races})

        X = []
        y = []
        race_dates = []

        for i, race in enumerate(bt_data[:max_races]):
            race_id = race.get("race_id", "")
            race_date = race.get("race_date", "")
            try:
                ctx = PipelineContext(
                    pipeline_id="train", race_id=race_id,
                    started_at=datetime.now(), current_stage="init",
                )
                ctx = HistoricalDataManager(self.data_source).execute(ctx)
                ctx = CurrentDataFetcher(self.data_source).execute(ctx)
                ctx = DataQualityChecker().execute(ctx)
                ctx = FeatureGenerator().execute(ctx)

                horse_features = ctx.features.get("horse_features", [])
                rows = vectorize_race(ctx.features)

                actual_result = race.get("actual_result", [])
                winner_id = actual_result[0] if actual_result else None

                for hf, row in zip(horse_features, rows):
                    feature_vec = [row.get(col, 0.0) for col in FEATURE_COLUMNS]
                    horse_id = hf.get("horse_id", "")
                    X.append(feature_vec)
                    y.append(1 if horse_id == winner_id else 0)
                    race_dates.append(race_date)

            except Exception as e:
                self.logger_info(f"レース {race_id} の処理をスキップ: {e}")
                continue

            if (i + 1) % 100 == 0:
                self.logger_info(f"JRA-VANデータ処理: {i + 1}/{len(bt_data[:max_races])}レース完了")

        self.logger_info(f"JRA-VANデータ収集: {len(X)}件")
        return X, y, race_dates

    def _collect_production_data(self, months: int,
                                  max_races: int) -> tuple[list[list[float]], list[int]]:
        """本番データソースから学習データを収集。"""
        from keiba.agents.feature_generator import FeatureGenerator
        from keiba.agents.historical_data_manager import HistoricalDataManager
        from keiba.agents.current_data_fetcher import CurrentDataFetcher
        from keiba.agents.data_quality_checker import DataQualityChecker
        from keiba.models.pipeline import PipelineContext

        bt_data = self.data_source.get_backtest_data({"months": months, "max_races": max_races})

        X = []
        y = []

        for race in bt_data[:max_races]:
            race_id = race.get("race_id", "")
            try:
                ctx = PipelineContext(
                    pipeline_id="train", race_id=race_id,
                    started_at=datetime.now(), current_stage="init",
                )
                ctx = HistoricalDataManager(self.data_source).execute(ctx)
                ctx = CurrentDataFetcher(self.data_source).execute(ctx)
                ctx = DataQualityChecker().execute(ctx)
                ctx = FeatureGenerator().execute(ctx)

                horse_features = ctx.features.get("horse_features", [])
                rows = vectorize_race(ctx.features)

                # 実際の結果でラベル付け
                actual_result = race.get("actual_result", [])
                winner_id = actual_result[0] if actual_result else None

                entries = ctx.current_race_data.get("entries", [])
                for i, (hf, row) in enumerate(zip(horse_features, rows)):
                    feature_vec = [row.get(col, 0.0) for col in FEATURE_COLUMNS]
                    horse_id = hf.get("horse_id", "")
                    X.append(feature_vec)
                    y.append(1 if horse_id == winner_id else 0)

            except Exception as e:
                self.logger_info(f"レース {race_id} の処理をスキップ: {e}")
                continue

        self.logger_info(f"本番データ収集: {len(X)}件")
        return X, y

    def _optimize_hyperparameters(self, X_train, y_train, X_val, y_val,
                                   n_trials: int) -> dict:
        """Optunaでハイパーパラメータ最適化。"""
        import optuna
        import lightgbm as lgb

        optuna.logging.set_verbosity(optuna.logging.WARNING)

        def objective(trial):
            params = {
                "objective": "binary",
                "metric": "auc",
                "verbosity": -1,
                "num_leaves": trial.suggest_int("num_leaves", 15, 63),
                "max_depth": trial.suggest_int("max_depth", 3, 10),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
                "min_child_samples": trial.suggest_int("min_child_samples", 5, 50),
                "feature_fraction": trial.suggest_float("feature_fraction", 0.5, 1.0),
                "bagging_fraction": trial.suggest_float("bagging_fraction", 0.5, 1.0),
                "bagging_freq": 5,
                "lambda_l1": trial.suggest_float("lambda_l1", 1e-3, 10.0, log=True),
                "lambda_l2": trial.suggest_float("lambda_l2", 1e-3, 10.0, log=True),
            }
            train_data = lgb.Dataset(X_train, label=y_train)
            val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)

            model = lgb.train(
                params, train_data, num_boost_round=200,
                valid_sets=[val_data],
                callbacks=[lgb.early_stopping(20, verbose=False)],
            )
            pred = model.predict(X_val)
            return self._calc_auc(y_val.tolist(), pred.tolist() if hasattr(pred, "tolist") else list(pred))

        study = optuna.create_study(direction="maximize")
        study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

        best = study.best_params
        self.logger_info(f"Optuna最適化完了: best_auc={study.best_value:.4f}, trials={n_trials}")
        return best

    def _calc_auc(self, y_true: list[int], y_pred: list[float]) -> float:
        """AUC計算（sklearnなしでも動くよう簡易実装、あればsklearnを使用）。"""
        try:
            from sklearn.metrics import roc_auc_score
            return roc_auc_score(y_true, y_pred)
        except ImportError:
            pass
        # フォールバック: Mann-Whitney U ベース
        pos = [p for t, p in zip(y_true, y_pred) if t == 1]
        neg = [p for t, p in zip(y_true, y_pred) if t == 0]
        if not pos or not neg:
            return 0.5
        correct = sum(1 for pp in pos for np_ in neg if pp > np_)
        ties = sum(1 for pp in pos for np_ in neg if pp == np_)
        return (correct + 0.5 * ties) / (len(pos) * len(neg))

    def logger_info(self, msg: str) -> None:
        """ログ出力（BaseAgentを継承していないため独自）。"""
        from keiba.utils.logging import get_agent_logger
        logger = get_agent_logger("LightGBMTrainer")
        logger.info(msg)
