"""馬・出走情報モデル"""

from datetime import date
from typing import Optional

from keiba.models.base import (
    Gender,
    KeibaBaseModel,
    RunningStyle,
    TrackCondition,
    TrackType,
)


class Horse(KeibaBaseModel):
    horse_id: str
    horse_name: str
    birth_year: int
    gender: Gender
    age: int
    trainer_name: str
    owner_name: Optional[str] = None
    breeder_name: Optional[str] = None
    pedigree_sire: Optional[str] = None
    pedigree_dam_sire: Optional[str] = None


class PastPerformance(KeibaBaseModel):
    """馬の過去1走の成績"""
    race_id: str
    race_date: date
    race_name: str
    course: str
    distance: int
    track_type: TrackType
    track_condition: TrackCondition
    finish_position: int
    total_runners: int
    jockey_name: str
    weight_carried: float
    finish_time: Optional[float] = None
    margin: Optional[str] = None
    popularity: int
    odds: float
    last_3f: Optional[float] = None
    running_style: Optional[RunningStyle] = None
    passing_order: Optional[str] = None


class Entry(KeibaBaseModel):
    """レースへの出走1頭分"""
    entry_id: str
    horse: Horse
    jockey: object  # Jockey モデルへの前方参照
    weight_carried: float
    post_position: int
    bracket_number: int
    horse_weight: Optional[float] = None
    weight_change: Optional[float] = None
    past_performances: list = []
