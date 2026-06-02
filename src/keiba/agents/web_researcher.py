"""エージェント6: Web調査

MVPではSampleDataSourceのデータをそのまま返す。
本番実装時はWeb検索API等を使用するが、
対象サイトの利用規約・robots.txt・アクセス頻度制限を必ず確認すること。
"""

from datetime import datetime

from keiba.agents.base import BaseAgent
from keiba.data.base_source import DataSource
from keiba.models.pipeline import PipelineContext


class WebResearcher(BaseAgent):
    """Web検索で補足情報を集めるエージェント"""

    def __init__(self, data_source: DataSource):
        super().__init__()
        self.data_source = data_source

    def validate_input(self, context: PipelineContext) -> bool:
        return context.current_race_data is not None

    def process(self, context: PipelineContext) -> PipelineContext:
        entries = context.current_race_data.get("entries", [])
        horse_ids = [
            e.get("horse", {}).get("horse_id", "")
            for e in entries
            if e.get("horse", {}).get("horse_id")
        ]

        self.logger.info(f"Researching web content for {len(horse_ids)} horses")
        content = self.data_source.get_web_content(context.race_id, horse_ids)

        # 信頼度評価を付与
        for intel in content.get("horse_intel", []):
            intel["reliability"] = self._assess_reliability(intel)
            intel["impact_on_prediction"] = self._assess_impact(intel)

        context.web_research = {
            "race_id": context.race_id,
            "researched_at": datetime.now().isoformat(),
            "track_tendencies": content.get("track_tendencies", []),
            "weather_forecast": content.get("weather_forecast"),
            "horse_intel": content.get("horse_intel", []),
            "data_source": "sample",
            "note": "MVP: サンプルデータを使用。本番ではWeb検索APIを使用予定。",
        }
        self.logger.info(f"Web research complete: {len(content.get('horse_intel', []))} horses covered")
        return context

    def _assess_reliability(self, intel: dict) -> str:
        """情報の信頼度を評価"""
        news = intel.get("news_items", [])
        if not news:
            return "medium"
        avg_relevance = sum(n.get("relevance", 0) for n in news) / len(news)
        if avg_relevance >= 0.8:
            return "high"
        elif avg_relevance >= 0.5:
            return "medium"
        return "low"

    def _assess_impact(self, intel: dict) -> str:
        """予想への影響度を評価"""
        factors = intel.get("notable_factors", [])
        has_negative = any("不安" in f or "注意" in f or "減少" in f for f in factors)
        has_positive = any("好調" in f or "好時計" in f or "勢い" in f for f in factors)
        if has_negative and has_positive:
            return "mixed"
        elif has_positive:
            return "positive"
        elif has_negative:
            return "negative"
        return "neutral"
