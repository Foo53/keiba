"""エージェント6: Web調査

ProductionDataSource から調教インテリジェンス・天気・ニュースを取得し、
EvidenceIntegrator で使える構造に加工する。
"""

from datetime import datetime

from keiba.agents.base import BaseAgent
from keiba.data.base_source import DataSource
from keiba.data.sample.sample_source import SampleDataSource
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

        # 調教スコアリング
        for intel in content.get("horse_intel", []):
            intel["training_score"] = self._score_training_intelligence(intel)

        # 天気インパクト評価
        weather = content.get("weather_forecast")
        if weather:
            weather_factors = self._assess_weather_impact(
                weather, content.get("horse_intel", [])
            )
            # 馬ごとのnotable_factorsに天気要因を追加
            for intel in content.get("horse_intel", []):
                horse_name = intel.get("horse_name", "")
                wf = weather_factors.get(horse_name, [])
                intel["notable_factors"] = intel.get("notable_factors", []) + wf

        # 信頼度・影響度評価
        for intel in content.get("horse_intel", []):
            intel["reliability"] = self._assess_reliability(intel)
            intel["impact_on_prediction"] = self._assess_impact(intel)

        # data_source ラベル
        is_sample = isinstance(self.data_source, SampleDataSource)
        source_label = "sample" if is_sample else "production"
        note = ""
        if is_sample:
            note = "サンプルデータを使用。本番ではProductionDataSourceのWeb調査を使用。"

        context.web_research = {
            "race_id": context.race_id,
            "researched_at": datetime.now().isoformat(),
            "track_tendencies": content.get("track_tendencies", []),
            "weather_forecast": content.get("weather_forecast"),
            "horse_intel": content.get("horse_intel", []),
            "data_source": source_label,
            "note": note,
        }
        self.logger.info(f"Web research complete: {len(content.get('horse_intel', []))} horses covered")
        return context

    def _score_training_intelligence(self, intel: dict) -> float:
        """調教インテリジェンスからスコアを算出（-1.0 ~ +1.0）。

        form_trend と fitness_score を中心に、training_reports の
        キーワードから加減算する。
        """
        score = 0.0

        # form_trend
        trend = intel.get("form_trend", "stable")
        if trend == "improving":
            score += 0.3
        elif trend == "declining":
            score -= 0.3

        # fitness_score
        fitness = intel.get("fitness_score", 0.5)
        score += (fitness - 0.5) * 0.4  # 0.5基準で ±0.2

        # training_reports キーワード評価
        for report in intel.get("training_reports", []):
            if any(w in report for w in ["改善", "上昇"]):
                score += 0.1
            elif any(w in report for w in ["低下", "下降"]):
                score -= 0.1
            if "注意" in report:
                score -= 0.05

        return round(max(-1.0, min(1.0, score)), 2)

    def _assess_weather_impact(self, weather, horse_intel: list[dict]) -> dict[str, list[str]]:
        """天気予報から各馬への影響を評価。

        weather は dict（本番）または str（サンプル）の両方に対応。
        雨予報の場合、過去成績の track_condition から
        道悪適性を判定して notable_factors を返す。

        Returns: {horse_name: [factor_strings]}
        """
        result: dict[str, list[str]] = {}

        # 文字列（サンプル）の場合は雨判定が困難なのでスキップ
        if isinstance(weather, str):
            return result

        weather_text = weather.get("weather", "")
        rain_prob = weather.get("rain_probability")

        is_rainy = "雨" in weather_text or (rain_prob is not None and rain_prob >= 50)
        if not is_rainy:
            return result

        # 雨馬場予想 — 各馬に通知（過去成績があれば判定）
        for intel in horse_intel:
            name = intel.get("horse_name", "")
            factors = []
            # form_trend が improving で雨なら注目度アップ
            trend = intel.get("form_trend", "stable")
            if trend == "improving":
                factors.append("雨馬場予想・好調時は狙い目")
            elif trend == "declining":
                factors.append("雨馬場予想・下降中は注意")

            if factors:
                result[name] = factors

        return result

    def _assess_reliability(self, intel: dict) -> str:
        """情報の信頼度を評価"""
        news = intel.get("news_items", [])
        if not news:
            # training_reports があれば medium、なければ low
            if intel.get("training_reports"):
                return "medium"
            return "low"
        avg_relevance = sum(n.get("relevance", 0) for n in news) / len(news)
        if avg_relevance >= 0.8:
            return "high"
        elif avg_relevance >= 0.5:
            return "medium"
        return "low"

    def _assess_impact(self, intel: dict) -> str:
        """予想への影響度を評価（調教スコア込み）"""
        factors = intel.get("notable_factors", [])
        has_negative = any("不安" in f or "注意" in f or "減少" in f or "低下" in f or "下降" in f for f in factors)
        has_positive = any("好調" in f or "好時計" in f or "勢い" in f or "改善" in f or "上昇" in f for f in factors)

        # 調教スコアも考慮
        training_score = intel.get("training_score", 0.0)
        if training_score > 0.3:
            has_positive = True
        elif training_score < -0.3:
            has_negative = True

        if has_negative and has_positive:
            return "mixed"
        elif has_positive:
            return "positive"
        elif has_negative:
            return "negative"
        return "neutral"
