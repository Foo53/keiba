"""予想・買い目モデル"""

from datetime import datetime
from typing import Optional

from keiba.models.base import BetType, ConfidenceGrade, KeibaBaseModel


class BetRecommendation(KeibaBaseModel):
    bet_type: BetType
    selection: str
    horse_names: list[str]
    predicted_probability: float
    estimated_odds: Optional[float] = None
    expected_value: Optional[float] = None
    confidence: ConfidenceGrade
    reasoning: str
    risk_level: str
    stake_suggestion: Optional[str] = None


class RacePrediction(KeibaBaseModel):
    race_id: str
    race_name: str
    generated_at: datetime
    prediction_type: str  # "predicted_odds" | "actual_odds"
    top_pick: Optional[str] = None  # 本命 entry_id
    second_pick: Optional[str] = None  # 対抗
    dark_horse: Optional[str] = None  # 穴馬
    win_prediction: Optional[BetRecommendation] = None
    place_prediction: Optional[BetRecommendation] = None
    wide_prediction: Optional[BetRecommendation] = None
    quinella_prediction: Optional[BetRecommendation] = None
    exacta_prediction: Optional[BetRecommendation] = None
    trio_prediction: Optional[BetRecommendation] = None
    trifecta_prediction: Optional[BetRecommendation] = None
    skip_recommended: bool = False
    skip_reason: Optional[str] = None
    disclaimer: str = ""
