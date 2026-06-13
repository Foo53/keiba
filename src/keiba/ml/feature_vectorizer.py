"""特徴量ベクトル化ユーティリティ

FeatureGenerator の出力を LightGBM 入力用の平坦な数値ベクトルに変換する。
競馬ML予測の文献調査に基づく25次元特徴量。

参照:
  - 芦原氏 SHAP分析: preprize, horse_age, preorder, last_3F が高重要度
  - Teddy Koker: jockey/trainer win % が有効
  - CodeWorks: Horse Win %, Place % が有効
"""

FEATURE_COLUMNS = [
    # 既存特徴量 (1-18)
    "distance_aptitude_score",
    "track_turf_score",
    "track_dirt_score",
    "course_specific_best",
    "style_consistency",
    "style_front_runner",
    "style_stalker",
    "style_midpack",
    "style_closer",
    "avg_last_3f",
    "best_last_3f",
    "closing_speed_rank",
    "form_score",
    "class_change_up",
    "class_change_down",
    "distance_change_up",
    "distance_change_down",
    "jockey_trainer_win_rate",
    # 調査で判明した高効果特徴量 (19-25)
    "recent_win_rate",
    "recent_place_rate",
    "avg_recent_position",
    "last_run_position",
    "field_size",
    "jockey_course_win_rate",
    "best_3f_gap",
    # 重賞特化特徴量 (26-28)
    "jockey_grade_win_rate",
    "horse_grade_top3_rate",
    "grade_form_score",
]


def vectorize_horse_features(hf: dict, field_size: int) -> dict[str, float]:
    """1頭分の特徴量を平坦な数値dictに変換。

    Args:
        hf: FeatureGenerator の horse_features の1要素
        field_size: 出走頭数
    """
    # 脚質のone-hot符号化
    style = hf.get("primary_style", "差し")
    style_map = {"逃げ": "style_front_runner", "先行": "style_stalker",
                 "差し": "style_midpack", "追込": "style_closer"}

    # コース適性のbest値
    course_scores = hf.get("course_specific_score", {})
    course_best = max(course_scores.values()) if course_scores else 50.0

    # 上がり3F
    avg_3f = hf.get("average_last_3f")
    best_3f = hf.get("best_last_3f")

    # 近走成績の派生特徴量
    recent3 = hf.get("recent_3_runs", [])
    recent5 = hf.get("recent_5_runs", [])

    # 3着以内率（win_rate）と複勝率（place_rate）
    podium_count = sum(1 for p in recent3 if 1 <= p <= 3)
    recent_win_rate = podium_count / len(recent3) if recent3 else 0.0

    place_count = sum(1 for p in recent5 if 1 <= p <= 3)
    recent_place_rate = place_count / len(recent5) if recent5 else 0.0

    # 平均着順
    avg_recent_position = sum(recent5) / len(recent5) if recent5 else 5.0

    # 前走着順
    last_run_position = float(recent3[0]) if recent3 else 5.0

    # クラス・距離変更
    class_change = hf.get("class_change", "same")
    distance_change = hf.get("distance_change", "same")

    # 上がり一貫性（avgとbestの差が小さいほど一貫性が高い）
    avg_3f_val = avg_3f if avg_3f is not None else 34.0
    best_3f_val = best_3f if best_3f is not None else 34.5
    best_3f_gap = avg_3f_val - best_3f_val

    row = {
        # 既存特徴量
        "distance_aptitude_score": float(hf.get("distance_aptitude_score", 50)),
        "track_turf_score": float(hf.get("track_turf_score", 50)),
        "track_dirt_score": float(hf.get("track_dirt_score", 50)),
        "course_specific_best": float(course_best),
        "style_consistency": float(hf.get("style_consistency", 0.5)),
        "style_front_runner": 1.0 if style == "逃げ" else 0.0,
        "style_stalker": 1.0 if style == "先行" else 0.0,
        "style_midpack": 1.0 if style == "差し" else 0.0,
        "style_closer": 1.0 if style == "追込" else 0.0,
        "avg_last_3f": avg_3f_val,
        "best_last_3f": best_3f_val,
        "closing_speed_rank": float(hf.get("closing_speed_rank") or field_size),
        "form_score": float(hf.get("form_score", 50)),
        "class_change_up": 1.0 if class_change == "up" else 0.0,
        "class_change_down": 1.0 if class_change == "down" else 0.0,
        "distance_change_up": 1.0 if distance_change == "up" else 0.0,
        "distance_change_down": 1.0 if distance_change == "down" else 0.0,
        "jockey_trainer_win_rate": float(hf.get("jockey_trainer_win_rate", 0)),
        # 調査由来特徴量
        "recent_win_rate": recent_win_rate,
        "recent_place_rate": recent_place_rate,
        "avg_recent_position": avg_recent_position,
        "last_run_position": last_run_position,
        "field_size": float(field_size),
        "jockey_course_win_rate": float(hf.get("jockey_course_win_rate") or 0),
        "best_3f_gap": best_3f_gap,
        # 重賞特化特徴量
        "jockey_grade_win_rate": float(hf.get("jockey_grade_win_rate") or 0),
        "horse_grade_top3_rate": float(hf.get("horse_grade_top3_rate") or 0),
        "grade_form_score": float(hf.get("grade_form_score") or 0),
    }
    return row


def vectorize_race(features: dict) -> list[dict[str, float]]:
    """レース全馬の特徴量をベクトル化。

    Args:
        features: context.features dict（horse_features, field_size を含む）
    """
    horse_features = features.get("horse_features", [])
    field_size = features.get("field_size", len(horse_features))
    return [vectorize_horse_features(hf, field_size) for hf in horse_features]
