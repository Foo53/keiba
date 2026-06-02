"""厩舎モデル"""

from typing import Optional

from keiba.models.base import KeibaBaseModel


class Trainer(KeibaBaseModel):
    trainer_id: str
    trainer_name: str


class TrainerStats(KeibaBaseModel):
    trainer_id: str
    period: str
    total_runs: int
    wins: int
    win_rate: float
    place_rate: float
    distance_stats: Optional[dict] = None
    track_type_stats: Optional[dict] = None
