"""騎手モデル"""

from typing import Optional

from keiba.models.base import KeibaBaseModel


class Jockey(KeibaBaseModel):
    jockey_id: str
    jockey_name: str
    license_year: Optional[int] = None


class JockeyStats(KeibaBaseModel):
    jockey_id: str
    period: str
    total_rides: int
    wins: int
    places: int
    win_rate: float
    place_rate: float
    favorite_win_rate: Optional[float] = None
    course_stats: Optional[dict] = None
