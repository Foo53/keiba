"""エージェント6b: LightGBM ML予測

学習済みLightGBMモデルをロードし、特徴量から勝率を推定する。
モデルが存在しない場合はgraceful degradationでスキップ。
"""

import json
import math
from datetime import datetime
from pathlib import Path

from keiba.agents.base import BaseAgent
from keiba.models.pipeline import PipelineContext

MODEL_PATH = Path("data/store/models/lgbm_latest.txt")
METADATA_PATH = Path("data/store/models/lgbm_metadata.json")


class MLPredictor(BaseAgent):
    """LightGBMモデルによる勝率推定エージェント"""

    def __init__(self):
        super().__init__()
        self.model = None
        self.feature_names: list[str] = []
        self.metadata: dict = {}
        self._try_load_model()

    def _try_load_model(self) -> bool:
        """学習済みモデルのロードを試みる"""
        try:
            import lightgbm as lgb
        except ImportError:
            self.logger.warning("lightgbmがインストールされていません。ML予測をスキップします")
            return False

        if not MODEL_PATH.exists():
            self.logger.info("学習済みモデルが存在しません。ML予測をスキップします")
            return False

        try:
            self.model = lgb.Booster(model_file=str(MODEL_PATH))
            if METADATA_PATH.exists():
                self.metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
                self.feature_names = self.metadata.get("feature_names", [])
            self.logger.info(f"LightGBMモデル読込完了: {MODEL_PATH}")
            return True
        except Exception as e:
            self.logger.warning(f"モデル読込失敗: {e}。ML予測をスキップします")
            self.model = None
            return False

    def validate_input(self, context: PipelineContext) -> bool:
        return context.features is not None

    def process(self, context: PipelineContext) -> PipelineContext:
        if self.model is None:
            context.ml_analysis = None
            self.logger.info("学習済みモデルがないためML予測をスキップ")
            return context

        from keiba.ml.feature_vectorizer import vectorize_race, FEATURE_COLUMNS

        # 特徴量ベクトル化
        rows = vectorize_race(context.features)
        if not rows:
            context.ml_analysis = None
            return context

        # DataFrame構築（feature_namesに整列）
        aligned_data = []
        for row in rows:
            aligned_data.append([row.get(col, 0.0) for col in FEATURE_COLUMNS])

        try:
            import numpy as np
            X = np.array(aligned_data)
        except ImportError:
            # numpyなしの場合
            X = aligned_data

        # 予測
        raw_scores = self.model.predict(X)
        if hasattr(raw_scores, "tolist"):
            raw_scores = raw_scores.tolist()

        # softmax正規化（Teddy Koker アプローチ: レース内相対評価）
        probabilities = self._softmax(raw_scores)

        # feature importance取得
        importance = self._get_feature_importance()

        # 出力構築（PythonAnalyzerと同じキー構造）
        features_list = context.features.get("horse_features", [])
        results = []
        paired = list(zip(range(len(features_list)), raw_scores, probabilities))
        paired.sort(key=lambda x: x[1], reverse=True)

        for rank, (idx, raw, prob) in enumerate(paired, 1):
            hf = features_list[idx]
            results.append({
                "entry_id": hf["entry_id"],
                "horse_id": hf["horse_id"],
                "horse_name": self._get_horse_name(context, hf["entry_id"]),
                "win_probability": round(prob, 4),
                "place_probability": round(min(1.0, prob * 2.5), 4),
                "model_confidence": round(min(1.0, raw), 3),
                "rank_by_model": rank,
                "composite_score": round(raw, 4),
            })

        results.sort(key=lambda r: r["rank_by_model"])

        context.ml_analysis = {
            "race_id": context.race_id,
            "analyzed_at": datetime.now().isoformat(),
            "method": "lightgbm",
            "model_version": self.metadata.get("trained_at", "unknown"),
            "model_confidence": self.metadata.get("val_auc", 0),
            "probabilities": results,
            "feature_importance": importance,
            "caveats": [
                "ML予測は学習データに基づく統計的推定です",
                "学習データ量によっては過学習の可能性があります",
            ],
        }
        self.logger.info(f"ML予測完了: {len(results)}頭, 1位={results[0]['horse_name'] if results else 'N/A'}")
        return context

    def _softmax(self, scores: list[float], temperature: float = 1.0) -> list[float]:
        """ソフトマックスで確率を正規化"""
        if not scores:
            return []
        mean = sum(scores) / len(scores)
        centered = [(s - mean) / max(temperature, 0.01) for s in scores]
        exps = [math.exp(min(s, 500)) for s in centered]  # overflow防止
        total = sum(exps)
        return [e / total for e in exps]

    def _get_horse_name(self, context: PipelineContext, entry_id: str) -> str:
        entries = (context.current_race_data or {}).get("entries", [])
        for e in entries:
            if e.get("entry_id") == entry_id:
                return e.get("horse", {}).get("horse_name", "不明")
        return "不明"

    def _get_feature_importance(self) -> list[dict]:
        """gain ベースの特徴量重要度を取得"""
        if self.model is None:
            return []
        try:
            importance = self.model.feature_importance(importance_type="gain")
            if hasattr(importance, "tolist"):
                importance = importance.tolist()
            from keiba.ml.feature_vectorizer import FEATURE_COLUMNS
            paired = list(zip(FEATURE_COLUMNS, importance))
            paired.sort(key=lambda x: x[1], reverse=True)
            total = sum(v for _, v in paired) or 1
            return [
                {"feature": name, "importance": round(imp / total, 4)}
                for name, imp in paired[:10]
            ]
        except Exception:
            return []
