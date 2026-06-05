"""特徴量ベクトル化のテスト"""

from keiba.ml.feature_vectorizer import (
    FEATURE_COLUMNS,
    vectorize_horse_features,
    vectorize_race,
)


def _sample_horse_feature(overrides=None):
    """テスト用のサンプル特徴量"""
    base = {
        "entry_id": "e1",
        "horse_id": "h1",
        "distance_aptitude_score": 70.0,
        "track_turf_score": 65.0,
        "track_dirt_score": 40.0,
        "course_specific_score": {"東京": 75.0, "中山": 60.0},
        "primary_style": "先行",
        "style_consistency": 0.8,
        "average_last_3f": 33.5,
        "best_last_3f": 33.0,
        "closing_speed_rank": 2,
        "form_score": 80.0,
        "class_change": "same",
        "distance_change": "up",
        "horse_weight_trend": "stable",
        "jockey_trainer_win_rate": 0.15,
        "jockey_course_win_rate": 0.12,
        "recent_3_runs": [1, 3, 2],
        "recent_5_runs": [1, 3, 2, 5, 4],
    }
    if overrides:
        base.update(overrides)
    return base


class TestVectorizeHorseFeatures:
    def test_produces_all_columns(self):
        hf = _sample_horse_feature()
        result = vectorize_horse_features(hf, field_size=10)
        for col in FEATURE_COLUMNS:
            assert col in result, f"Missing column: {col}"
        assert len(result) == len(FEATURE_COLUMNS)

    def test_feature_columns_constant_matches(self):
        hf = _sample_horse_feature()
        result = vectorize_horse_features(hf, field_size=10)
        assert set(result.keys()) == set(FEATURE_COLUMNS)

    def test_style_one_hot(self):
        for style, expected_key in [("逃げ", "style_front_runner"), ("先行", "style_stalker"),
                                     ("差し", "style_midpack"), ("追込", "style_closer")]:
            hf = _sample_horse_feature({"primary_style": style})
            result = vectorize_horse_features(hf, field_size=10)
            assert result[expected_key] == 1.0
            other_keys = {"style_front_runner", "style_stalker", "style_midpack", "style_closer"} - {expected_key}
            for k in other_keys:
                assert result[k] == 0.0

    def test_missing_values_have_defaults(self):
        hf = {"entry_id": "e1", "horse_id": "h1"}  # 全フィールド欠損
        result = vectorize_horse_features(hf, field_size=10)
        assert result["avg_last_3f"] == 34.0  # Noneのデフォルト
        assert result["best_last_3f"] == 34.5
        assert result["closing_speed_rank"] == 10  # field_size
        assert result["field_size"] == 10

    def test_recent_win_rate(self):
        hf = _sample_horse_feature({"recent_3_runs": [1, 2, 3]})
        result = vectorize_horse_features(hf, field_size=10)
        assert result["recent_win_rate"] == 1.0  # 3着以内3/3

    def test_recent_place_rate(self):
        hf = _sample_horse_feature({"recent_5_runs": [1, 2, 3, 4, 5]})
        result = vectorize_horse_features(hf, field_size=10)
        assert result["recent_place_rate"] == 0.6  # 3着以内3/5

    def test_last_run_position(self):
        hf = _sample_horse_feature({"recent_3_runs": [5, 1, 3]})
        result = vectorize_horse_features(hf, field_size=10)
        assert result["last_run_position"] == 5.0  # 最初の要素

    def test_avg_recent_position(self):
        hf = _sample_horse_feature({"recent_5_runs": [1, 2, 3, 4, 5]})
        result = vectorize_horse_features(hf, field_size=10)
        assert result["avg_recent_position"] == 3.0

    def test_course_specific_best(self):
        hf = _sample_horse_feature({"course_specific_score": {"東京": 80, "中山": 60}})
        result = vectorize_horse_features(hf, field_size=10)
        assert result["course_specific_best"] == 80.0

    def test_class_change_flags(self):
        hf = _sample_horse_feature({"class_change": "up"})
        result = vectorize_horse_features(hf, field_size=10)
        assert result["class_change_up"] == 1.0
        assert result["class_change_down"] == 0.0

    def test_best_3f_gap(self):
        hf = _sample_horse_feature({"average_last_3f": 34.0, "best_last_3f": 33.0})
        result = vectorize_horse_features(hf, field_size=10)
        assert result["best_3f_gap"] == 1.0

    def test_empty_recent_runs(self):
        hf = _sample_horse_feature({"recent_3_runs": [], "recent_5_runs": []})
        result = vectorize_horse_features(hf, field_size=10)
        assert result["recent_win_rate"] == 0.0
        assert result["last_run_position"] == 5.0
        assert result["avg_recent_position"] == 5.0


class TestVectorizeRace:
    def test_vectorizes_all_horses(self):
        features = {
            "horse_features": [
                _sample_horse_feature({"entry_id": "e1"}),
                _sample_horse_feature({"entry_id": "e2", "primary_style": "逃げ"}),
            ],
            "field_size": 2,
        }
        result = vectorize_race(features)
        assert len(result) == 2
        assert result[0]["style_stalker"] == 1.0
        assert result[1]["style_front_runner"] == 1.0

    def test_empty_features(self):
        result = vectorize_race({"horse_features": [], "field_size": 0})
        assert result == []
