"""バックテストモデル"""

from keiba.models.base import BetType, KeibaBaseModel


class BacktestEntry(KeibaBaseModel):
    race_id: str
    predicted_rank: list[str]
    actual_result: list[str]
    hit: bool
    bet_type: BetType
    profit_loss: float


class BacktestSummary(KeibaBaseModel):
    period: str
    total_races: int
    hit_rate: float
    roi: float
    profit_loss_total: float
    breakdown_by_bet_type: dict
    breakdown_by_course: dict
    breakdown_by_distance: dict
    breakdown_by_condition: dict
    improvement_suggestions: list[str] = []
