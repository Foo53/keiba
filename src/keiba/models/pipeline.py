"""パイプライン実行コンテキスト"""

from datetime import datetime
from typing import Optional

from keiba.models.base import KeibaBaseModel


class AgentResult(KeibaBaseModel):
    agent_name: str
    success: bool
    started_at: datetime
    completed_at: datetime
    duration_seconds: float
    output: dict
    error: Optional[str] = None


class PipelineContext(KeibaBaseModel):
    pipeline_id: str
    race_id: str
    started_at: datetime
    current_stage: str
    # 各エージェント出力
    historical_data: Optional[dict] = None
    current_race_data: Optional[dict] = None
    quality_check: Optional[dict] = None
    features: Optional[dict] = None
    analysis: Optional[dict] = None
    web_research: Optional[dict] = None
    evidence: Optional[dict] = None
    predicted_odds_eval: Optional[dict] = None
    actual_odds_eval: Optional[dict] = None
    prediction_predicted: Optional[dict] = None
    prediction_actual: Optional[dict] = None
    backtest: Optional[dict] = None
    note_suggestion: Optional[dict] = None
    note_article: Optional[dict] = None
    qa_report: Optional[dict] = None
    # 実行ログ
    agent_results: list = []
    status: str = "running"
