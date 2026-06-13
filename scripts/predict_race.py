"""汎用レース予測スクリプト

racecard JSON + レース情報から ML予測を実行する。
JRA-VAN DBから過去成績・騎手厩舎統計を取得し、学習済みLightGBMモデルで勝率を推定。
"""

import sys
sys.path.insert(0, "src")

import json
import math
import argparse
from pathlib import Path
from collections import Counter
from datetime import datetime

import numpy as np
import lightgbm as lgb

from keiba.data.jrvan.loader import JrVanLoader, JYO_CODE_MAP, _infer_track_type


def load_racecard(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_past_performances(conn, horse_ids, before_date):
    if not horse_ids:
        return {}
    placeholders = ",".join("?" for _ in horse_ids)
    rows = conn.execute(
        f"SELECT * FROM race_horse_detail "
        f"WHERE ketto_toroku_bango IN ({placeholders}) "
        f"AND race_date < ? AND is_valid_result = '1' "
        f"ORDER BY race_date DESC",
        (*horse_ids, before_date),
    ).fetchall()

    perfs = {}
    for r in rows:
        hid = r["ketto_toroku_bango"]
        # sqlite3.Row は .get() 非対応のため括弧アクセス＋try
        popular = r["popular"] if "popular" in r.keys() else ""
        horse_w = r["horse_weight"] if "horse_weight" in r.keys() else ""
        pp = {
            "distance": int(r["distance_m"]) if r["distance_m"] else 2000,
            "finish_position": int(r["arrival_order"]) if r["arrival_order"] else 0,
            "total_runners": int(r["registered_count"]) if r["registered_count"] else 10,
            "track_type": _infer_track_type(r["track_code"]),
            "course": JYO_CODE_MAP.get(r["jyo_code"], ""),
            "last_3f": float(r["last_3f_horse"]) if r["last_3f_horse"] else None,
            "running_style": _infer_style(r),
            "grade": _decode_grade(r["grade_code"]),
            "race_date": r["race_date"],
            "popularity": int(popular) if popular and str(popular).isdigit() else None,
            "horse_weight": int(horse_w) if horse_w and str(horse_w).isdigit() else None,
        }
        perfs.setdefault(hid, []).append(pp)
    return perfs


def _infer_style(row):
    corners = []
    for c in ["corner1_order", "corner2_order", "corner3_order", "corner4_order"]:
        val = row[c] if c in row.keys() else ""
        try:
            pos = int(val) if val else 0
        except (ValueError, TypeError):
            pos = 0
        if pos > 0:
            corners.append(pos)
    if not corners:
        return "差し"
    total_runners = 14
    try:
        total_runners = int(row["registered_count"]) if row["registered_count"] else 14
    except (ValueError, TypeError):
        pass
    avg_pos = sum(corners) / len(corners)
    ratio = avg_pos / total_runners if total_runners > 0 else 0.5
    if ratio <= 0.25:
        return "逃げ"
    elif ratio <= 0.45:
        return "先行"
    elif ratio <= 0.65:
        return "差し"
    return "追込"


def _decode_grade(grade_code):
    grade_map = {"A": "GI", "B": "GII", "C": "GIII", "D": "L", "E": "L", "F": "L"}
    if not grade_code:
        return "L"
    return grade_map.get(grade_code[0].upper() if grade_code else "", "L")


def get_jockey_stats(conn, jockey_ids, before_date):
    valid_ids = [j for j in jockey_ids if j and j != "00000"]
    if not valid_ids:
        return {}
    placeholders = ",".join("?" for _ in valid_ids)
    rows = conn.execute(
        f"SELECT jockey_code, "
        f"COUNT(*) as total, "
        f"SUM(CASE WHEN arrival_order = '1' THEN 1 ELSE 0 END) as wins "
        f"FROM race_horse_detail "
        f"WHERE jockey_code IN ({placeholders}) AND race_date < ? "
        f"AND is_valid_result = '1' "
        f"GROUP BY jockey_code",
        (*valid_ids, before_date),
    ).fetchall()

    stats = {}
    for r in rows:
        jid = r["jockey_code"]
        total = r["total"]
        wins = r["wins"]
        stats[jid] = {
            "jockey_id": jid,
            "total_rides": total,
            "wins": wins,
            "win_rate": round(wins / total, 3) if total > 0 else 0,
            "grade_stats": {},
        }

    # 重賞限定成績
    grade_rows = conn.execute(
        f"SELECT jockey_code, "
        f"COUNT(*) as total, "
        f"SUM(CASE WHEN arrival_order = '1' THEN 1 ELSE 0 END) as wins "
        f"FROM race_horse_detail "
        f"WHERE jockey_code IN ({placeholders}) AND race_date < ? "
        f"AND is_valid_result = '1' "
        f"AND (grade_code LIKE 'A%' OR grade_code LIKE 'B%' OR grade_code LIKE 'C%') "
        f"GROUP BY jockey_code",
        (*valid_ids, before_date),
    ).fetchall()
    for r in grade_rows:
        jid = r["jockey_code"]
        total = r["total"]
        wins = r["wins"]
        stats.setdefault(jid, {})["grade_stats"] = {
            "grade_total": total,
            "grade_wins": wins,
            "grade_win_rate": round(wins / total, 3) if total > 0 else 0,
        }
    return stats


def calc_distance_aptitude(pp_list, target_distance):
    if not pp_list:
        return 50.0
    scores = []
    for pp in pp_list:
        d = pp.get("distance", 2000)
        diff = abs(d - target_distance)
        score = max(0, 100 - diff * 0.05)
        pos = pp.get("finish_position", 5)
        total = pp.get("total_runners", 10)
        score *= (1 - pos / max(total, 1) * 0.5)
        scores.append(score)
    return round(min(100, max(0, sum(scores) / len(scores))), 1)


def calc_track_aptitude(pp_list):
    if not pp_list:
        return 50.0, 50.0
    turf_pos, dirt_pos = [], []
    for pp in pp_list:
        if pp.get("track_type") == "芝":
            turf_pos.append(pp.get("finish_position", 5))
        else:
            dirt_pos.append(pp.get("finish_position", 5))
    turf_score = min(100, max(0, 100 - (sum(turf_pos)/len(turf_pos) - 1) * 20)) if turf_pos else 50.0
    dirt_score = min(100, max(0, 100 - (sum(dirt_pos)/len(dirt_pos) - 1) * 20)) if dirt_pos else 50.0
    return round(turf_score, 1), round(dirt_score, 1)


def calc_course_score(pp_list, target_course):
    if not pp_list:
        return {target_course: 50.0}
    course_data = {}
    for pp in pp_list:
        c = pp.get("course", "")
        if c not in course_data:
            course_data[c] = []
        course_data[c].append(pp.get("finish_position", 5))
    result = {}
    for c, positions in course_data.items():
        avg = sum(positions) / len(positions)
        result[c] = round(min(100, max(0, 100 - (avg - 1) * 20)), 1)
    if target_course not in result:
        result[target_course] = 50.0
    return result


def classify_style(pp_list, default="差し"):
    if not pp_list:
        return default, 0.5
    styles = [pp.get("running_style", default) for pp in pp_list]
    counter = Counter(styles)
    primary = counter.most_common(1)[0][0]
    consistency = counter.most_common(1)[0][1] / len(styles)
    return primary, round(consistency, 2)


def calc_closing_speed(pp_list):
    last3fs = [pp["last_3f"] for pp in pp_list if pp.get("last_3f")]
    avg = round(sum(last3fs) / len(last3fs), 2) if last3fs else None
    best = round(min(last3fs), 2) if last3fs else None
    return avg, best


def calc_form(pp_list):
    sorted_pp = sorted(pp_list, key=lambda x: x.get("race_date", ""), reverse=True)
    recent3 = [pp.get("finish_position", 0) for pp in sorted_pp[:3]]
    recent5 = [pp.get("finish_position", 0) for pp in sorted_pp[:5]]
    if recent3:
        avg = sum(recent3) / len(recent3)
        form_score = min(100, max(0, 100 - (avg - 1) * 25))
    else:
        form_score = 50.0
    return recent3, recent5, round(form_score, 1)


def calc_grade_form(pp_list):
    grade_pp = [pp for pp in pp_list if pp.get("grade") in ("GI", "GII", "GIII")]
    if not grade_pp:
        return 0.0
    sorted_pp = sorted(grade_pp, key=lambda x: x.get("race_date", ""), reverse=True)
    recent3 = [pp.get("finish_position", 0) for pp in sorted_pp[:3]]
    if recent3:
        avg = sum(recent3) / len(recent3)
        return round(min(100, max(0, 100 - (avg - 1) * 20)), 1)
    return 0.0


def calc_horse_grade_top3_rate(pp_list):
    grade_pp = [pp for pp in pp_list if pp.get("grade") in ("GI", "GII", "GIII")]
    if not grade_pp:
        return 0.0
    top3 = sum(1 for pp in grade_pp if 1 <= pp.get("finish_position", 0) <= 3)
    return round(top3 / len(grade_pp), 3)


def detect_class_change(pp_list):
    if len(pp_list) < 2:
        return "same"
    sorted_pp = sorted(pp_list, key=lambda x: x.get("race_date", ""), reverse=True)
    grades = {"GI": 4, "GII": 3, "GIII": 2, "L": 1}
    current = grades.get(sorted_pp[0].get("grade", ""), 0)
    prev = grades.get(sorted_pp[1].get("grade", ""), 0)
    if current > prev:
        return "up"
    elif current < prev:
        return "down"
    return "same"


def detect_distance_change(pp_list, target):
    if not pp_list:
        return "same"
    sorted_pp = sorted(pp_list, key=lambda x: x.get("race_date", ""), reverse=True)
    last_dist = sorted_pp[0].get("distance", target)
    diff = target - last_dist
    if diff > 200:
        return "up"
    elif diff < -200:
        return "down"
    return "same"


def run_prediction(racecard_path: str, race_name: str, course: str,
                   distance: int, track_type: str, grade: str,
                   race_date: str, output_path: str):
    """予測パイプライン実行"""
    racecard = load_racecard(racecard_path)
    horses = racecard["horses"]
    race_id = racecard["race_id"]
    field_size = len(horses)

    is_jump = track_type == "障害"
    print(f"\n{'='*80}")
    print(f"🏇 {race_name}({grade}) {race_date} {course} {track_type}{distance}m")
    if is_jump:
        print("⚠️ 障害レース: MLモデルは平地競走で学習しているため参考値として扱う")
    print(f"{'='*80}")

    # DB接続
    loader = JrVanLoader()
    conn = loader.get_connection()

    horse_ids = [h["horse_id"] for h in horses if h.get("horse_id")]
    jockey_ids = list({h.get("jockey_code") for h in horses if h.get("jockey_code") and h["jockey_code"] != "00000"})

    # データ取得
    print("📊 過去戦績・騎手統計を取得中...", flush=True)
    past_perfs = get_past_performances(conn, horse_ids, race_date)
    jockey_stats = get_jockey_stats(conn, jockey_ids, race_date)
    conn.close()

    # 特徴量生成
    print(f"\n🐎 出走馬特徴量生成 ({field_size}頭)", flush=True)
    print("-" * 80, flush=True)

    horse_features = []
    for h in horses:
        hid = h.get("horse_id", "")
        pp_list = past_perfs.get(hid, [])

        dist_score = calc_distance_aptitude(pp_list, distance)
        turf_score, dirt_score = calc_track_aptitude(pp_list)
        course_score = calc_course_score(pp_list, course)
        style, consistency = classify_style(pp_list)
        avg_3f, best_3f = calc_closing_speed(pp_list)
        recent3, recent5, form_score = calc_form(pp_list)
        class_change = detect_class_change(pp_list)
        distance_change = detect_distance_change(pp_list, distance)

        jid = h.get("jockey_code", "")
        js = jockey_stats.get(jid, {})
        jt_rate = js.get("win_rate", 0)
        grade_stats = js.get("grade_stats", {})
        jockey_grade_rate = grade_stats.get("grade_win_rate", 0)

        grade_form = calc_grade_form(pp_list)
        grade_top3_rate = calc_horse_grade_top3_rate(pp_list)

        podium_count = sum(1 for p in recent3 if 1 <= p <= 3)
        recent_win_rate = podium_count / len(recent3) if recent3 else 0.0
        place_count = sum(1 for p in recent5 if 1 <= p <= 3)
        recent_place_rate = place_count / len(recent5) if recent5 else 0.0
        avg_recent_position = sum(recent5) / len(recent5) if recent5 else 5.0
        last_run_position = float(recent3[0]) if recent3 else 5.0

        avg_3f_val = avg_3f if avg_3f is not None else 34.0
        best_3f_val = best_3f if best_3f is not None else 34.5
        best_3f_gap = avg_3f_val - best_3f_val
        course_best = max(course_score.values()) if course_score else 50.0

        hf = {
            "entry_id": f"{race_id}_{h['umaban']:02d}",
            "horse_id": hid,
            "distance_aptitude_score": dist_score,
            "track_turf_score": turf_score,
            "track_dirt_score": dirt_score,
            "course_specific_score": course_score,
            "primary_style": style,
            "style_consistency": consistency,
            "average_last_3f": avg_3f_val,
            "best_last_3f": best_3f_val,
            "closing_speed_rank": None,
            "recent_3_runs": recent3,
            "recent_5_runs": recent5,
            "form_score": form_score,
            "class_change": class_change,
            "distance_change": distance_change,
            "jockey_trainer_win_rate": jt_rate,
            "jockey_course_win_rate": 0,
            "jockey_grade_win_rate": jockey_grade_rate,
            "horse_grade_top3_rate": grade_top3_rate,
            "grade_form_score": grade_form,
        }
        horse_features.append(hf)

        pp_count = len(pp_list)
        recent_str = "→".join(str(p) for p in recent3) if recent3 else "N/A"
        print(
            f"  {h['umaban']:2d}番 {h['name']:14s} "
            f"戦{pp_count:2d} 近走[{recent_str}] "
            f"脚質={style} 距離適性={dist_score:.0f} "
            f"上3F={avg_3f_val:.1f} "
            f"騎手勝率={jt_rate:.1%} "
            f"フォーム={form_score:.0f} 重賞F={grade_form:.0f}",
            flush=True,
        )

    # 上がりランク
    all_avg = [(i, hf["average_last_3f"]) for i, hf in enumerate(horse_features)]
    all_avg.sort(key=lambda x: x[1])
    for rank, (idx, _) in enumerate(all_avg, 1):
        horse_features[idx]["closing_speed_rank"] = rank

    # ML予測
    from keiba.ml.feature_vectorizer import vectorize_horse_features, FEATURE_COLUMNS

    rows = [vectorize_horse_features(hf, field_size) for hf in horse_features]

    model_path = Path("data/store/models/lgbm_latest.txt")
    metadata_path = Path("data/store/models/lgbm_metadata.json")

    if not model_path.exists():
        print("❌ 学習済みモデルなし", flush=True)
        return None

    model = lgb.Booster(model_file=str(model_path))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}

    model_feature_names = metadata.get("feature_names", FEATURE_COLUMNS)
    aligned_data = [[row.get(col, 0.0) for col in model_feature_names] for row in rows]

    X = np.array(aligned_data)
    raw_scores = model.predict(X).tolist()

    # 正規化
    total_raw = sum(raw_scores)
    if total_raw > 0 and all(s >= 0 for s in raw_scores):
        probabilities = [s / total_raw for s in raw_scores]
    else:
        mean_score = total_raw / len(raw_scores)
        centered = [(s - mean_score) / 0.05 for s in raw_scores]
        exps = [math.exp(min(s, 500)) for s in centered]
        total_exp = sum(exps)
        probabilities = [e / total_exp for e in exps]

    # ランキング
    ranked_indices = sorted(range(len(horses)), key=lambda i: raw_scores[i], reverse=True)

    results = []
    for rank, idx in enumerate(ranked_indices, 1):
        h = horses[idx]
        prob = probabilities[idx]
        raw = raw_scores[idx]
        hf = horse_features[idx]

        results.append({
            "rank": rank,
            "umaban": h["umaban"],
            "wakuban": h["wakuban"],
            "name": h["name"],
            "sex": h["sex"],
            "age": h["age"],
            "weight": h["weight"],
            "jockey": h["jockey"],
            "trainer": h["trainer"],
            "barn": h["barn"],
            "horse_id": h.get("horse_id", ""),
            "probability": round(prob, 4),
            "raw_score": round(raw, 4),
            "style": hf["primary_style"],
            "form_score": hf["form_score"],
            "distance_aptitude": hf["distance_aptitude_score"],
            "avg_3f": hf["average_last_3f"],
            "recent_3": hf["recent_3_runs"],
            "recent_5": hf["recent_5_runs"],
            "grade_form": hf["grade_form_score"],
            "jockey_grade_rate": hf["jockey_grade_win_rate"],
        })

    # 表示
    print(f"\n📈 予測結果", flush=True)
    print("-" * 80, flush=True)
    print(f"モデル: val_AUC={metadata.get('val_auc', 'N/A')} test_AUC={metadata.get('test_auc', 'N/A')}", flush=True)
    for r in results:
        marker = "🔥" if r["rank"] <= 5 else "  "
        print(
            f"{marker} {r['rank']:2d}位 {r['umaban']:2d}番 {r['name']:14s} "
            f"勝率={r['probability']:.1%} スコア={r['raw_score']:.4f} "
            f"脚質={r['style']} 近走F={r['form_score']:.0f}",
            flush=True,
        )

    # 保存
    output = {
        "race": {
            "race_id": race_id,
            "race_name": race_name,
            "course": course,
            "distance": distance,
            "track_type": track_type,
            "grade": grade,
            "race_date": race_date,
            "field_size": field_size,
            "is_jump": is_jump,
        },
        "model_info": {
            "val_auc": metadata.get("val_auc"),
            "test_auc": metadata.get("test_auc"),
            "train_samples": metadata.get("train_samples"),
            "note": "障害レースのため参考値" if is_jump else None,
        },
        "predictions": results,
        "generated_at": datetime.now().isoformat(),
    }

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n💾 保存: {out}", flush=True)

    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="汎用レース予測")
    parser.add_argument("racecard", help="racecard JSON path")
    parser.add_argument("--name", required=True, help="レース名")
    parser.add_argument("--course", required=True, help="競馬場")
    parser.add_argument("--distance", required=True, type=int, help="距離(m)")
    parser.add_argument("--track", required=True, help="コース種別 (芝/ダート/障害)")
    parser.add_argument("--grade", required=True, help="グレード (GI/GII/GIII/JGIII等)")
    parser.add_argument("--date", required=True, help="レース日付 (YYYY-MM-DD)")
    parser.add_argument("--output", "-o", required=True, help="出力先")
    args = parser.parse_args()

    run_prediction(
        args.racecard, args.name, args.course,
        args.distance, args.track, args.grade,
        args.date, args.output,
    )
