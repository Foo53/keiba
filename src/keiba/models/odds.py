"""オッズ関連モデル"""

from datetime import datetime
from typing import Optional

from keiba.models.base import KeibaBaseModel


class OddsEntry(KeibaBaseModel):
    entry_id: str
    horse_name: str
    win_odds: float
    place_odds_min: Optional[float] = None
    place_odds_max: Optional[float] = None
    popularity_rank: int


class PredictedOdds(KeibaBaseModel):
    race_id: str
    is_provisional: bool = True
    calculated_at: datetime
    entries: list[OddsEntry]
    method: str = "model"


class ActualOdds(KeibaBaseModel):
    race_id: str
    is_final: bool
    recorded_at: datetime
    entries: list[OddsEntry]
    total_pool: Optional[int] = None
