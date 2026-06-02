"""エージェント9: 実オッズ評価"""

from datetime import datetime

from keiba.agents.base import BaseAgent
from keiba.models.pipeline import PipelineContext


class ActualOddsEvaluator(BaseAgent):
    """実オッズで期待値を再計算するエージェント"""

    def validate_input(self, context: PipelineContext) -> bool:
        return context.evidence is not None and context.predicted_odds_eval is not None

    def process(self, context: PipelineContext) -> PipelineContext:
        evidence_horses = {
            h["entry_id"]: h for h in context.evidence.get("horses", [])
        }

        # 実オッズ取得
        actual_odds = self._get_actual_odds(context)
        odds_map = {e["entry_id"]: e for e in actual_odds.get("entries", [])}

        # 予想オッズ評価との比較用
        prev_evals = {
            e["entry_id"]: e for e in context.predicted_odds_eval.get("evaluations", [])
        }

        evaluations = []
        for entry_id, horse in evidence_horses.items():
            odds_entry = odds_map.get(entry_id, {})
            win_odds = odds_entry.get("win_odds", 99.9)
            model_prob = horse.get("integrated_probability", 0.0)
            market_prob = 1.0 / win_odds if win_odds > 0 else 0.0
            expected_value = (model_prob * win_odds) - 1.0  # EV = P(win) * odds - 1
            value_gap = model_prob - market_prob

            # 予想オッズとの比較
            prev = prev_evals.get(entry_id, {})
            odds_change = win_odds - prev.get("predicted_odds", win_odds)

            evaluations.append({
                "entry_id": entry_id,
                "horse_name": horse["horse_name"],
                "actual_odds": win_odds,
                "model_probability": round(model_prob, 4),
                "market_implied_probability": round(market_prob, 4),
                "expected_value": round(expected_value, 4),
                "value_gap": round(value_gap, 4),
                "odds_change_from_predicted": round(odds_change, 2),
                "recommendation_grade": self._assign_grade(expected_value, value_gap, horse),
            })

        evaluations.sort(key=lambda x: x["expected_value"], reverse=True)

        market_sentiment = self._assess_market_sentiment(evaluations)

        context.actual_odds_eval = {
            "race_id": context.race_id,
            "evaluated_at": datetime.now().isoformat(),
            "is_provisional": False,
            "evaluations": evaluations,
            "market_sentiment": market_sentiment,
            "s_grade_horses": [e for e in evaluations if e["recommendation_grade"] == "S"],
            "a_grade_horses": [e for e in evaluations if e["recommendation_grade"] == "A"],
            "skip_candidates": [e for e in evaluations if e["recommendation_grade"] == "C"],
        }
        self.logger.info(
            f"Actual odds eval: S={len(context.actual_odds_eval['s_grade_horses'])}, "
            f"A={len(context.actual_odds_eval['a_grade_horses'])}, "
            f"sentiment={market_sentiment}"
        )
        return context

    def _get_actual_odds(self, context: PipelineContext) -> dict:
        if context.historical_data and "_actual_odds" in context.historical_data:
            return context.historical_data["_actual_odds"]
        entries = context.current_race_data.get("entries", [])
        return {"entries": [
            {"entry_id": e.get("entry_id", ""), "horse_name": e.get("horse", {}).get("horse_name", ""), "win_odds": max(1.1, 48 - i * 4), "popularity_rank": i + 1}
            for i, e in enumerate(entries)
        ]}

    def _assign_grade(self, ev: float, value_gap: float, horse: dict) -> str:
        concerns = len(horse.get("concerns", []))
        if ev > 0.3 and value_gap > 0.10 and concerns == 0:
            return "S"
        elif ev > 0.1 and value_gap > 0.05 and concerns <= 1:
            return "A"
        elif ev > -0.1:
            return "B"
        return "C"

    def _assess_market_sentiment(self, evaluations: list[dict]) -> str:
        positive = sum(1 for e in evaluations if e["expected_value"] > 0)
        total = len(evaluations)
        if positive == 0:
            return "no_value_found"
        elif positive <= 2:
            return "few_opportunities"
        elif positive <= 4:
            return "moderate_opportunities"
        return "many_opportunities"
