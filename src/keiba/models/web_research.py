"""Web調査結果モデル"""

from datetime import date, datetime
from typing import Optional

from keiba.models.base import KeibaBaseModel


class NewsItem(KeibaBaseModel):
    source: str
    title: str
    content: str
    relevance: float
    date: Optional[date] = None
    url: Optional[str] = None


class HorseWebIntel(KeibaBaseModel):
    horse_id: str
    horse_name: str
    training_reports: list[str]
    connections_comments: list[str]
    news_items: list[NewsItem]
    notable_factors: list[str]


class WebResearchResult(KeibaBaseModel):
    race_id: str
    researched_at: datetime
    track_tendencies: list[str]
    weather_forecast: Optional[str] = None
    horse_intel: list[HorseWebIntel]
