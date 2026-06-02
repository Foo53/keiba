"""エージェント8: 予想オッズ評価"""

from datetime import datetime

from keiba.agents.base import BaseAgent
from keiba.models.pipeline import PipelineContext


class PredictedOddsEvaluator(BaseAgent):
    """予想オッズベースの暫定評価を行うエージェント"""

    def validate_input(self, context: PipelineContext) -> bool:
        return context.evidence is not None and context.current_race_data is not None

    def process(self, context: PipelineContext) -> PipelineContext:
        evidence_horses = {
            h["entry_id"]: h for h in context.evidence.get("horses", [])
        }

        # 予想オッズ取得
        predicted_odds = self._get_predicted_odds(context)
        odds_map = {e["entry_id"]: e for e in predicted_odds.get("entries", [])}

        evaluations = []
        for entry_id, horse in evidence_horses.items():
            odds_entry = odds_map.get(entry_id, {})
            win_odds = odds_entry.get("win_odds", 99.9)
            model_prob = horse.get("integrated_probability", 0.0)
            market_prob = 1.0 / win_odds if win_odds > 0 else 0.0
            value_gap = model_prob - market_prob

            evaluations.append({
                "entry_id": entry_id,
                "horse_name": horse["horse_name"],
                "predicted_odds": win_odds,
                "model_probability": round(model_prob, 4),
                "market_implied_probability": round(market_prob, 4),
                "value_gap": round(value_gap, 4),
                "provisional_value": "妙味あり" if value_gap > 0.05 else "妙味薄" if value_gap > -0.05 else "見送り",
                "grade": horse.get("evidence_grade", "C"),
            })

        evaluations.sort(key=lambda x: x["value_gap"], reverse=True)

        context.predicted_odds_eval = {
            "race_id": context.race_id,
            "evaluated_at": datetime.now().isoformat(),
            "is_provisional": True,
            "note": "予想オッズベースの暫定評価です。実オッズ取得後に再評価が必要です。",
            "evaluations": evaluations,
            "value_candidates": [e for e in evaluations if e["value_gap"] > 0.05],
            "skip_candidates": [e for e in evaluations if e["value_gap"] < -0.10],
        }
        self.logger.info(
            f"Predicted odds eval: {len(evaluations)} horses, "
            f"{len(context.predicted_odds_eval['value_candidates'])} value candidates"
        )
        return context

    def _get_predicted_odds(self, context: PipelineContext) -> dict:
        """contextから予想オッズを取得。なければデータソースから"""
        if context.historical_data and "_predicted_odds" in context.historical_data:
            return context.historical_data["_predicted_odds"]
        # current_race_dataのエントリから簡易オッズを生成
        entries = context.current_race_data.get("entries", [])
        return {"entries": [
            {"entry_id": e.get("entry_id", ""), "horse_name": e.get("horse", {}).get("horse_name", ""), "win_odds": max(1.1, 50 - i * 4), "popularity_rank": i + 1}
            for i, e in enumerate(entries)
        ]}
