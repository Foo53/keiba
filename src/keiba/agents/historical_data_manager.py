"""エージェント1: 過去データ管理"""

from keiba.agents.base import BaseAgent
from keiba.data.base_source import DataSource
from keiba.models.pipeline import PipelineContext


class HistoricalDataManager(BaseAgent):
    """過去レースデータを取得・保存・管理するエージェント"""

    def __init__(self, data_source: DataSource):
        super().__init__()
        self.data_source = data_source

    def validate_input(self, context: PipelineContext) -> bool:
        return bool(context.race_id)

    def process(self, context: PipelineContext) -> PipelineContext:
        self.logger.info(f"Fetching historical data for {context.race_id}")
        data = self.data_source.get_historical_data(context.race_id)
        # データ件数のサマリーログ
        n_horses = len(data.get("horses", {}))
        n_pp_keys = len(data.get("past_performances", {}))
        self.logger.info(f"Loaded {n_horses} horses, {n_pp_keys} past performance sets")
        context.historical_data = data
        return context
