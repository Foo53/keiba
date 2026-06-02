"""レース関連モデル"""

from datetime import date
from typing import Optional

from keiba.models.base import (
    KeibaBaseModel,
    RaceGrade,
    TrackCondition,
    TrackType,
    Weather,
)


class Race(KeibaBaseModel):
    race_id: str
    race_name: str
    race_date: date
    race_number: int
    course: str
    distance: int
    track_type: TrackType
    grade: RaceGrade
    weather: Optional[Weather] = None
    track_condition: Optional[TrackCondition] = None
    post_time: Optional[str] = None
    prize_money_first: Optional[int] = None


class RaceCard(KeibaBaseModel):
    """1レースの出走馬一覧"""
    race: Race
    entries: list
