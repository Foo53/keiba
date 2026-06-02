"""サンプルオッズデータ — 予想オッズ + 実オッズ"""

from datetime import datetime

SAMPLE_PREDICTED_ODDS = {
    "race_id": "20260607-Tokyo-11",
    "is_provisional": True,
    "calculated_at": datetime(2026, 6, 5, 12, 0, 0).isoformat(),
    "method": "model",
    "entries": [
        {"entry_id": "20260607-Tokyo-11-01", "horse_name": "サンライズインパクト", "win_odds": 2.8, "place_odds_min": 1.2, "place_odds_max": 1.4, "popularity_rank": 1},
        {"entry_id": "20260607-Tokyo-11-02", "horse_name": "ミッドナイトブレイド", "win_odds": 4.2, "place_odds_min": 1.4, "place_odds_max": 1.8, "popularity_rank": 2},
        {"entry_id": "20260607-Tokyo-11-03", "horse_name": "ゴールデンアロー", "win_odds": 6.5, "place_odds_min": 1.8, "place_odds_max": 2.4, "popularity_rank": 3},
        {"entry_id": "20260607-Tokyo-11-04", "horse_name": "ロイヤルストライク", "win_odds": 8.3, "place_odds_min": 2.0, "place_odds_max": 3.0, "popularity_rank": 4},
        {"entry_id": "20260607-Tokyo-11-05", "horse_name": "ウィンドヴォイス", "win_odds": 10.5, "place_odds_min": 2.5, "place_odds_max": 3.8, "popularity_rank": 5},
        {"entry_id": "20260607-Tokyo-11-06", "horse_name": "サンダーボルトキッド", "win_odds": 15.2, "place_odds_min": 3.2, "place_odds_max": 5.0, "popularity_rank": 6},
        {"entry_id": "20260607-Tokyo-11-07", "horse_name": "フロストナイト", "win_odds": 22.0, "place_odds_min": 4.0, "place_odds_max": 6.5, "popularity_rank": 7},
        {"entry_id": "20260607-Tokyo-11-08", "horse_name": "ムーンライトダンス", "win_odds": 35.0, "place_odds_min": 5.5, "place_odds_max": 9.0, "popularity_rank": 8},
        {"entry_id": "20260607-Tokyo-11-09", "horse_name": "ブレイブハート", "win_odds": 52.0, "place_odds_min": 7.0, "place_odds_max": 12.0, "popularity_rank": 9},
        {"entry_id": "20260607-Tokyo-11-10", "horse_name": "スカイブルーグラス", "win_odds": 98.3, "place_odds_min": 10.0, "place_odds_max": 18.0, "popularity_rank": 10},
    ],
}

SAMPLE_ACTUAL_ODDS = {
    "race_id": "20260607-Tokyo-11",
    "is_final": True,
    "recorded_at": datetime(2026, 6, 7, 15, 35, 0).isoformat(),
    "total_pool": 5800000000,
    "entries": [
        {"entry_id": "20260607-Tokyo-11-01", "horse_name": "サンライズインパクト", "win_odds": 3.2, "place_odds_min": 1.3, "place_odds_max": 1.5, "popularity_rank": 1},
        {"entry_id": "20260607-Tokyo-11-02", "horse_name": "ミッドナイトブレイド", "win_odds": 3.8, "place_odds_min": 1.5, "place_odds_max": 1.7, "popularity_rank": 2},
        {"entry_id": "20260607-Tokyo-11-05", "horse_name": "ウィンドヴォイス", "win_odds": 7.5, "place_odds_min": 2.2, "place_odds_max": 3.2, "popularity_rank": 3},
        {"entry_id": "20260607-Tokyo-11-03", "horse_name": "ゴールデンアロー", "win_odds": 8.0, "place_odds_min": 2.3, "place_odds_max": 3.4, "popularity_rank": 4},
        {"entry_id": "20260607-Tokyo-11-04", "horse_name": "ロイヤルストライク", "win_odds": 10.1, "place_odds_min": 2.8, "place_odds_max": 4.2, "popularity_rank": 5},
        {"entry_id": "20260607-Tokyo-11-06", "horse_name": "サンダーボルトキッド", "win_odds": 18.5, "place_odds_min": 4.0, "place_odds_max": 6.5, "popularity_rank": 6},
        {"entry_id": "20260607-Tokyo-11-07", "horse_name": "フロストナイト", "win_odds": 25.3, "place_odds_min": 4.8, "place_odds_max": 7.8, "popularity_rank": 7},
        {"entry_id": "20260607-Tokyo-11-08", "horse_name": "ムーンライトダンス", "win_odds": 45.0, "place_odds_min": 6.5, "place_odds_max": 11.0, "popularity_rank": 8},
        {"entry_id": "20260607-Tokyo-11-10", "horse_name": "スカイブルーグラス", "win_odds": 82.0, "place_odds_min": 10.0, "place_odds_max": 16.0, "popularity_rank": 9},
        {"entry_id": "20260607-Tokyo-11-09", "horse_name": "ブレイブハート", "win_odds": 58.5, "place_odds_min": 8.0, "place_odds_max": 14.0, "popularity_rank": 10},
    ],
}
