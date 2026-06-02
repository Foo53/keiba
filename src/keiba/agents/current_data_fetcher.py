"""エージェント2: 当日・前日データ取得"""

from keiba.agents.base import BaseAgent
from keiba.data.base_source import DataSource
from keiba.models.pipeline import PipelineContext


class CurrentDataFetcher(BaseAgent):
    """対象レースの最新情報を取得するエージェント"""

    def __init__(self, data_source: DataSource):
        super().__init__()
        self.data_source = data_source

    def validate_input(self, context: PipelineContext) -> bool:
        return context.historical_data is not None and bool(context.race_id)

    def process(self, context: PipelineContext) -> PipelineContext:
        self.logger.info(f"Fetching current race card for {context.race_id}")
        card = self.data_source.get_current_race_card(context.race_id)
        n_entries = len(card.get("entries", []))
        self.logger.info(f"Loaded race card with {n_entries} entries")
        context.current_race_data = card
        return context
