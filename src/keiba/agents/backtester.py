"""エージェント11: バックテスト"""

from keiba.agents.base import BaseAgent
from keiba.data.base_source import DataSource
from keiba.models.pipeline import PipelineContext


class Backtester(BaseAgent):
    """過去データで予想ロジックを検証するエージェント"""

    def __init__(self, data_source: DataSource):
        super().__init__()
        self.data_source = data_source

    def validate_input(self, context: PipelineContext) -> bool:
        return context.prediction_actual is not None or context.prediction_predicted is not None

    def process(self, context: PipelineContext) -> PipelineContext:
        bt_data = self.data_source.get_backtest_data({})

        total_races = len(bt_data)
        if total_races == 0:
            context.backtest = self._empty_result()
            return context

        # 単勝的中率・回収率
        win_hits = 0
        win_payout = 0.0
        win_bets = 0
        # 複勝的中率・回収率
        place_hits = 0
        place_payout = 0.0
        place_bets = 0

        for race in bt_data:
            predicted = race.get("predicted_rank", [])
            actual = race.get("actual_result", [])
            win_odds_fav = race.get("win_odds_favorite", 2.0)
            win_div = race.get("win_dividend", 0)
            place_div = race.get("place_dividend", 0)

            # 単勝: 予想1位が実際1位か
            win_bets += 1
            if predicted and actual and predicted[0] == actual[0]:
                win_hits += 1
                win_payout += win_div / 100  # 100円あたり

            # 複勝: 予想1位が実際3着以内か
            place_bets += 1
            if predicted and actual and predicted[0] in actual[:3]:
                place_hits += 1
                place_payout += place_div / 100

        win_hit_rate = win_hits / win_bets if win_bets > 0 else 0
        win_roi = (win_payout / win_bets) if win_bets > 0 else 0
        place_hit_rate = place_hits / place_bets if place_bets > 0 else 0
        place_roi = (place_payout / place_bets) if place_bets > 0 else 0

        # 全体ROI
        total_invested = total_races * 200  # 単複各100円
        total_return = win_payout * 100 + place_payout * 100
        overall_roi = total_return / total_invested if total_invested > 0 else 0

        context.backtest = {
            "period": f"sample_{total_races}_races",
            "total_races": total_races,
            "hit_rate": round(win_hit_rate, 3),
            "roi": round(overall_roi, 3),
            "profit_loss_total": round(total_return - total_invested, 0),
            "breakdown_by_bet_type": {
                "単勝": {"hit_rate": round(win_hit_rate, 3), "roi": round(win_roi, 3), "hits": win_hits, "bets": win_bets},
                "複勝": {"hit_rate": round(place_hit_rate, 3), "roi": round(place_roi, 3), "hits": place_hits, "bets": place_bets},
            },
            "breakdown_by_course": self._breakdown_by(bt_data, "course"),
            "breakdown_by_distance": self._breakdown_by(bt_data, "distance"),
            "breakdown_by_condition": self._breakdown_by(bt_data, "condition"),
            "improvement_suggestions": self._generate_suggestions(win_hit_rate, win_roi, place_hit_rate),
        }
        self.logger.info(f"Backtest: {total_races} races, hit_rate={win_hit_rate:.1%}, ROI={overall_roi:.1%}")
        return context

    def _breakdown_by(self, data: list[dict], key: str) -> dict:
        groups = {}
        for race in data:
            k = str(race.get(key, "unknown"))
            if k not in groups:
                groups[k] = {"hits": 0, "bets": 0}
            groups[k]["bets"] += 1
            predicted = race.get("predicted_rank", [])
            actual = race.get("actual_result", [])
            if predicted and actual and predicted[0] == actual[0]:
                groups[k]["hits"] += 1
        result = {}
        for k, v in groups.items():
            result[k] = {"hit_rate": round(v["hits"] / v["bets"], 3) if v["bets"] else 0, "total": v["bets"]}
        return result

    def _generate_suggestions(self, win_hr: float, win_roi: float, place_hr: float) -> list[str]:
        suggestions = []
        if win_hr < 0.25:
            suggestions.append("単勝的中率が低めです。上位予想の精度向上が必要です")
        if win_roi < 0.8:
            suggestions.append("単勝回収率が80%を下回っています。期待値評価の閾値見直しを検討してください")
        if place_hr < 0.40:
            suggestions.append("複勝的中率が40%を下回っています。複勝圏内予測の改善を検討してください")
        if not suggestions:
            suggestions.append("バックテスト結果は概ね良好です。継続的にデータを蓄積して精度を高めてください")
        return suggestions

    def _empty_result(self) -> dict:
        return {
            "period": "no_data",
            "total_races": 0,
            "hit_rate": 0,
            "roi": 0,
            "profit_loss_total": 0,
            "breakdown_by_bet_type": {},
            "breakdown_by_course": {},
            "breakdown_by_distance": {},
            "breakdown_by_condition": {},
            "improvement_suggestions": ["バックテストデータがありません。データ蓄積後に再実行してください"],
        }
