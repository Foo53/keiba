"""分析結果モデル"""

from datetime import datetime
from typing import Optional

from keiba.models.base import KeibaBaseModel


class ProbabilityEstimate(KeibaBaseModel):
    entry_id: str
    horse_name: str
    win_probability: float
    place_probability: float
    model_confidence: float
    rank_by_model: int


class AnalysisResult(KeibaBaseModel):
    race_id: str
    analyzed_at: datetime
    method: str
    probabilities: list[ProbabilityEstimate]
    key_factors: list[str]
    caveats: list[str]
    data_sufficiency: str
