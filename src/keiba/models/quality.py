"""品質保証モデル"""

from datetime import datetime
from typing import Optional

from keiba.models.base import KeibaBaseModel


class QACriterion(KeibaBaseModel):
    criterion_name: str
    max_score: int
    actual_score: int
    passed: bool
    notes: str


class QAReport(KeibaBaseModel):
    target_agent: str
    race_id: str
    evaluated_at: datetime
    total_score: int
    passed: bool
    criteria: list[QACriterion]
    overall_feedback: str
    route_back_to: Optional[str] = None
    retry_count: int = 0
