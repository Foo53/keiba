"""サンプルデータソース実装

MVP用。外部サイトへの実アクセスは一切行わない。
"""

from keiba.data.base_source import DataSource
from keiba.data.sample.races import SAMPLE_RACE, SAMPLE_RACES_HISTORY
from keiba.data.sample.horses import SAMPLE_HORSES
from keiba.data.sample.past_performances import SAMPLE_PAST_PERFORMANCES
from keiba.data.sample.odds import SAMPLE_PREDICTED_ODDS, SAMPLE_ACTUAL_ODDS
from keiba.data.sample.web_content import SAMPLE_WEB_CONTENT


class SampleDataSource(DataSource):
    """サンプルデータを提供するDataSource実装"""

    def get_historical_data(self, race_id: str) -> dict:
        return {
            "races": SAMPLE_RACES_HISTORY,
            "horses": {h["horse_id"]: h for h in SAMPLE_HORSES},
            "past_performances": SAMPLE_PAST_PERFORMANCES,
            "jockey_stats": self._sample_jockey_stats(),
            "trainer_stats": self._sample_trainer_stats(),
        }

    def get_current_race_card(self, race_id: str) -> dict:
        return {
            "race": SAMPLE_RACE,
            "entries": [
                {
                    "entry_id": f"{race_id}-{h['post_position']:02d}",
                    "horse": {
                        "horse_id": h["horse_id"],
                        "horse_name": h["horse_name"],
                        "birth_year": h["birth_year"],
                        "gender": h["gender"],
                        "age": h["age"],
                        "trainer_name": h["trainer_name"],
                        "pedigree_sire": h.get("pedigree_sire"),
                        "pedigree_dam_sire": h.get("pedigree_dam_sire"),
                    },
                    "jockey": {
                        "jockey_id": h["jockey_id"],
                        "jockey_name": h["jockey_name"],
                    },
                    "weight_carried": h["weight_carried"],
                    "post_position": h["post_position"],
                    "bracket_number": h["bracket_number"],
                    "horse_weight": h.get("horse_weight"),
                    "weight_change": h.get("weight_change"),
                    "past_performances": SAMPLE_PAST_PERFORMANCES.get(h["horse_id"], []),
                    "style": h.get("style", "差し"),
                }
                for h in SAMPLE_HORSES
            ],
        }

    def get_predicted_odds(self, race_id: str) -> dict:
        return SAMPLE_PREDICTED_ODDS

    def get_actual_odds(self, race_id: str) -> dict:
        return SAMPLE_ACTUAL_ODDS

    def get_web_content(self, race_id: str, horse_ids: list[str]) -> dict:
        content = dict(SAMPLE_WEB_CONTENT)
        content["horse_intel"] = [
            h for h in content["horse_intel"] if h["horse_id"] in horse_ids
        ]
        return content

    def get_backtest_data(self, config: dict) -> list[dict]:
        return self._sample_backtest_data()

    def _sample_jockey_stats(self) -> dict:
        return {
            "J001": {"jockey_id": "J001", "period": "2026", "total_rides": 120, "wins": 32, "places": 58, "win_rate": 0.267, "place_rate": 0.483, "favorite_win_rate": 0.45, "course_stats": {"東京": {"win_rate": 0.30}}},
            "J002": {"jockey_id": "J002", "period": "2026", "total_rides": 110, "wins": 28, "places": 50, "win_rate": 0.255, "place_rate": 0.455, "favorite_win_rate": 0.40, "course_stats": {"東京": {"win_rate": 0.25}}},
            "J003": {"jockey_id": "J003", "period": "2026", "total_rides": 130, "wins": 30, "places": 55, "win_rate": 0.231, "place_rate": 0.423, "favorite_win_rate": 0.38, "course_stats": {"東京": {"win_rate": 0.24}}},
            "J004": {"jockey_id": "J004", "period": "2026", "total_rides": 95, "wins": 22, "places": 40, "win_rate": 0.232, "place_rate": 0.421, "favorite_win_rate": 0.35, "course_stats": {"東京": {"win_rate": 0.22}}},
            "J005": {"jockey_id": "J005", "period": "2026", "total_rides": 100, "wins": 28, "places": 48, "win_rate": 0.280, "place_rate": 0.480, "favorite_win_rate": 0.42, "course_stats": {"東京": {"win_rate": 0.30}}},
            "J006": {"jockey_id": "J006", "period": "2026", "total_rides": 115, "wins": 24, "places": 46, "win_rate": 0.209, "place_rate": 0.400, "favorite_win_rate": 0.33, "course_stats": {"東京": {"win_rate": 0.20}}},
            "J007": {"jockey_id": "J007", "period": "2026", "total_rides": 80, "wins": 18, "places": 34, "win_rate": 0.225, "place_rate": 0.425, "favorite_win_rate": 0.36, "course_stats": {"東京": {"win_rate": 0.22}}},
            "J008": {"jockey_id": "J008", "period": "2026", "total_rides": 90, "wins": 16, "places": 35, "win_rate": 0.178, "place_rate": 0.389, "favorite_win_rate": 0.30, "course_stats": {"東京": {"win_rate": 0.18}}},
            "J009": {"jockey_id": "J009", "period": "2026", "total_rides": 105, "wins": 17, "places": 38, "win_rate": 0.162, "place_rate": 0.362, "favorite_win_rate": 0.28, "course_stats": {"東京": {"win_rate": 0.16}}},
            "J010": {"jockey_id": "J010", "period": "2026", "total_rides": 85, "wins": 15, "places": 30, "win_rate": 0.176, "place_rate": 0.353, "favorite_win_rate": 0.25, "course_stats": {"東京": {"win_rate": 0.17}}},
        }

    def _sample_trainer_stats(self) -> dict:
        return {
            "田中太郎": {"trainer_id": "T001", "period": "2026", "total_runs": 80, "wins": 18, "win_rate": 0.225, "place_rate": 0.425, "distance_stats": {"2400": {"win_rate": 0.25}}},
            "佐藤次郎": {"trainer_id": "T002", "period": "2026", "total_runs": 70, "wins": 15, "win_rate": 0.214, "place_rate": 0.400, "distance_stats": {"2400": {"win_rate": 0.20}}},
            "鈴木三郎": {"trainer_id": "T003", "period": "2026", "total_runs": 90, "wins": 20, "win_rate": 0.222, "place_rate": 0.411, "distance_stats": {"2000": {"win_rate": 0.23}}},
            "高橋四郎": {"trainer_id": "T004", "period": "2026", "total_runs": 65, "wins": 14, "win_rate": 0.215, "place_rate": 0.400, "distance_stats": {"2400": {"win_rate": 0.22}}},
            "伊藤五郎": {"trainer_id": "T005", "period": "2026", "total_runs": 75, "wins": 19, "win_rate": 0.253, "place_rate": 0.453, "distance_stats": {"2000": {"win_rate": 0.28}}},
            "山田六郎": {"trainer_id": "T006", "period": "2026", "total_runs": 60, "wins": 10, "win_rate": 0.167, "place_rate": 0.367, "distance_stats": {"2400": {"win_rate": 0.15}}},
            "中村七郎": {"trainer_id": "T007", "period": "2026", "total_runs": 55, "wins": 10, "win_rate": 0.182, "place_rate": 0.382, "distance_stats": {"2400": {"win_rate": 0.18}}},
            "小林八郎": {"trainer_id": "T008", "period": "2026", "total_runs": 50, "wins": 8, "win_rate": 0.160, "place_rate": 0.340, "distance_stats": {"2400": {"win_rate": 0.15}}},
            "加藤九郎": {"trainer_id": "T009", "period": "2026", "total_runs": 65, "wins": 9, "win_rate": 0.138, "place_rate": 0.323, "distance_stats": {"2400": {"win_rate": 0.12}}},
            "斎藤十郎": {"trainer_id": "T010", "period": "2026", "total_runs": 45, "wins": 7, "win_rate": 0.156, "place_rate": 0.333, "distance_stats": {"2000": {"win_rate": 0.18}}},
        }

    def _sample_backtest_data(self) -> list[dict]:
        """バックテスト用サンプルデータ（20レース分）"""
        results = []
        import random
        random.seed(42)
        courses = ["東京", "中山", "京都", "阪神"]
        distances = [2000, 2200, 2400]
        conditions = ["良", "稍重"]
        for i in range(20):
            n_runners = random.randint(8, 18)
            pred_order = [f"H{j:03d}" for j in random.sample(range(1, 19), n_runners)]
            actual_order = list(pred_order)
            random.shuffle(actual_order)
            results.append({
                "race_id": f"BT-{i:04d}",
                "course": random.choice(courses),
                "distance": random.choice(distances),
                "condition": random.choice(conditions),
                "predicted_rank": pred_order[:5],
                "actual_result": actual_order[:5],
                "win_odds_favorite": round(random.uniform(1.5, 5.0), 1),
                "win_dividend": random.choice([0, 0, 0, random.randint(100, 500)]),
                "place_dividend": random.choice([0, 0, random.randint(80, 300)]),
            })
        return results
