"""安田記念 2026 予測スクリプト

JRA-VAN DBから各馬の過去成績・騎手厩舎統計を取得し、
学習済みLightGBMモデルで勝率を推定する。
"""

import sys
sys.path.insert(0, "src")

import sqlite3
import json
from pathlib import Path
from collections import Counter
from datetime import datetime

from keiba.data.jrvan.loader import JrVanLoader, JYO_CODE_MAP, _infer_track_type

# 安田記念 2026 出走馬（枠順確定済・6/5時点・17頭立て）
# アスクイキゴミ(回避・BCマイル)、アドマイヤズーム(回避・蹄故障)、セフィロ(回避)を除外
HORSES = [
    {"name": "レーベンスティール", "hid": "2020102078", "umaban": 1,  "sex": "1", "age": 6, "weight": 58.0, "jockey_code": "05386", "jockey_name": "戸崎圭太",   "trainer_name": "田中博康"},
    {"name": "ロングラン",         "hid": "2018104708", "umaban": 2,  "sex": "3", "age": 8, "weight": 58.0, "jockey_code": "05675", "jockey_name": "ゴンサルベ",   "trainer_name": "和田勇介"},
    {"name": "オフトレイル",       "hid": "2021110031", "umaban": 3,  "sex": "1", "age": 5, "weight": 58.0, "jockey_code": "01179", "jockey_name": "菅原明良",   "trainer_name": "吉村圭司"},
    {"name": "シックスペンス",     "hid": "2021105724", "umaban": 4,  "sex": "1", "age": 5, "weight": 58.0, "jockey_code": "00666", "jockey_name": "武豊",       "trainer_name": "田中博康"},
    {"name": "サクラトゥジュール", "hid": "2017103751", "umaban": 5,  "sex": "3", "age": 9, "weight": 58.0, "jockey_code": "01197", "jockey_name": "佐々木大輔", "trainer_name": "堀宣行"},
    {"name": "ステレンボッシュ",   "hid": "2021105743", "umaban": 6,  "sex": "2", "age": 5, "weight": 56.0, "jockey_code": "05585", "jockey_name": "レーン",     "trainer_name": "宮田敬介"},
    {"name": "スズハローム",       "hid": "2020105018", "umaban": 7,  "sex": "1", "age": 6, "weight": 58.0, "jockey_code": "01138", "jockey_name": "藤懸貴志",   "trainer_name": "牧田和弥"},
    {"name": "シャンパンカラー",   "hid": "2020103075", "umaban": 8,  "sex": "1", "age": 6, "weight": 58.0, "jockey_code": "05203", "jockey_name": "岩田康誠",   "trainer_name": "田中剛"},
    {"name": "ウォーターリヒト",   "hid": "2021100953", "umaban": 9,  "sex": "1", "age": 5, "weight": 58.0, "jockey_code": "01213", "jockey_name": "高杉吏麒",   "trainer_name": "石橋守"},
    {"name": "ルクソールカフェ",   "hid": "2022110083", "umaban": 10, "sex": "1", "age": 4, "weight": 58.0, "jockey_code": "01174", "jockey_name": "岩田望来",   "trainer_name": "堀宣行"},
    {"name": "ワールズエンド",     "hid": "2021105864", "umaban": 11, "sex": "1", "age": 5, "weight": 58.0, "jockey_code": "01092", "jockey_name": "津村明秀",   "trainer_name": "池添学"},
    {"name": "シリウスコルト",     "hid": "2021104094", "umaban": 12, "sex": "1", "age": 5, "weight": 58.0, "jockey_code": "01140", "jockey_name": "横山和生",   "trainer_name": "田中勝春"},
    {"name": "セイウンハーデス",   "hid": "2019102632", "umaban": 13, "sex": "1", "age": 7, "weight": 58.0, "jockey_code": "00732", "jockey_name": "幸英明",     "trainer_name": "橋口慎介"},
    {"name": "ガイアフォース",     "hid": "2019104476", "umaban": 14, "sex": "1", "age": 7, "weight": 58.0, "jockey_code": "01170", "jockey_name": "横山武史",   "trainer_name": "杉山晴紀"},
    {"name": "ドラゴンブースト",   "hid": "2022105891", "umaban": 15, "sex": "1", "age": 4, "weight": 58.0, "jockey_code": "01091", "jockey_name": "丹内祐次",   "trainer_name": "藤野健太"},
    {"name": "パンジャタワー",     "hid": "2022101732", "umaban": 16, "sex": "1", "age": 4, "weight": 58.0, "jockey_code": "01126", "jockey_name": "松山弘平",   "trainer_name": "橋口慎介"},
    {"name": "トロヴァトーレ",     "hid": "2021105557", "umaban": 17, "sex": "1", "age": 5, "weight": 58.0, "jockey_code": "05339", "jockey_name": "ルメール",   "trainer_name": "鹿戸雄一"},
]

RACE_DATE = "2026-06-07"
RACE_INFO = {
    "race_id": "202606070511",
    "race_name": "安田記念",
    "course": "東京",
    "distance": 1600,
    "track_type": "芝",
    "grade": "GI",
    "field_size": 17,
}


def get_past_performances(conn, horse_ids, before_date):
    """過去戦績を取得（JrVanDataSource._get_past_performances と同じロジック）"""
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
        }
        perfs.setdefault(hid, []).append(pp)
    return perfs


def _infer_style(row):
    """コーナー通過順から脚質推定"""
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
    """騎手成績を集計"""
    if not jockey_ids:
        return {}
    placeholders = ",".join("?" for _ in jockey_ids)
    rows = conn.execute(
        f"SELECT jockey_code, "
        f"COUNT(*) as total, "
        f"SUM(CASE WHEN arrival_order = '1' THEN 1 ELSE 0 END) as wins "
        f"FROM race_horse_detail "
        f"WHERE jockey_code IN ({placeholders}) AND race_date < ? "
        f"AND is_valid_result = '1' "
        f"GROUP BY jockey_code",
        (*jockey_ids, before_date),
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
            "course_stats": {},
        }

    # 東京コース成績
    for jid in jockey_ids:
        course_rows = conn.execute(
            "SELECT jyo_code, "
            "COUNT(*) as total, "
            "SUM(CASE WHEN arrival_order = '1' THEN 1 ELSE 0 END) as wins "
            "FROM race_horse_detail "
            "WHERE jockey_code = ? AND race_date < ? AND is_valid_result = '1' "
            "GROUP BY jyo_code",
            (jid, before_date),
        ).fetchall()
        for cr in course_rows:
            course = JYO_CODE_MAP.get(cr["jyo_code"], "")
            if course and cr["total"] > 0:
                stats.setdefault(jid, {}).setdefault("course_stats", {})[course] = {
                    "win_rate": round(cr["wins"] / cr["total"], 3)
                }
    return stats


def get_trainer_stats(conn, trainer_names, before_date):
    """調教師成績を集計"""
    if not trainer_names:
        return {}
    placeholders = ",".join("?" for _ in trainer_names)
    rows = conn.execute(
        f"SELECT trainer_name_short, "
        f"COUNT(*) as total, "
        f"SUM(CASE WHEN arrival_order = '1' THEN 1 ELSE 0 END) as wins "
        f"FROM race_horse_detail "
        f"WHERE trainer_name_short IN ({placeholders}) AND race_date < ? "
        f"AND is_valid_result = '1' "
        f"GROUP BY trainer_name_short",
        (*trainer_names, before_date),
    ).fetchall()

    stats = {}
    for r in rows:
        name = r["trainer_name_short"]
        total = r["total"]
        wins = r["wins"]
        stats[name] = {
            "win_rate": round(wins / total, 3) if total > 0 else 0,
            "total_runs": total,
            "wins": wins,
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


def detect_class_change(pp_list):
    if len(pp_list) < 2:
        return "same"
    sorted_pp = sorted(pp_list, key=lambda x: x.get("race_date", ""), reverse=True)
    grades = {"GI": 4, "GII": 3, "GIII": 2, "L": 1}
    current = grades.get(sorted_pp[0].get("grade", ""), 0)
    prev = grades.get(sorted_pp[1].get("grade", ""), 0) if len(sorted_pp) > 1 else 0
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


def get_jt_rates(jockey_id, trainer_name, jockey_stats, trainer_stats):
    js = jockey_stats.get(jockey_id, {})
    ts = trainer_stats.get(trainer_name, {})
    jt_rate = js.get("win_rate", 0)
    jc_rate = js.get("course_stats", {}).get("東京", {}).get("win_rate", 0)
    return round(jt_rate, 3), round(jc_rate, 3)


def main():
    # DB接続
    loader = JrVanLoader()
    conn = loader.get_connection()

    horse_ids = [h["hid"] for h in HORSES]
    jockey_ids = list({h["jockey_code"] for h in HORSES})
    trainer_names = list({h["trainer_name"] for h in HORSES})

    # データ取得
    print("📊 過去戦績・騎手厩舎統計を取得中...", flush=True)
    past_perfs = get_past_performances(conn, horse_ids, RACE_DATE)
    jockey_stats = get_jockey_stats(conn, jockey_ids, RACE_DATE)
    trainer_stats = get_trainer_stats(conn, trainer_names, RACE_DATE)
    conn.close()

    # 各馬の特徴量生成
    distance = RACE_INFO["distance"]
    course = RACE_INFO["course"]
    field_size = len(HORSES)

    horse_features = []
    print(f"\n🐎 出走馬特徴量生成 ({len(HORSES)}頭)", flush=True)
    print("=" * 80, flush=True)

    for h in HORSES:
        hid = h["hid"]
        pp_list = past_perfs.get(hid, [])

        dist_score = calc_distance_aptitude(pp_list, distance)
        turf_score, dirt_score = calc_track_aptitude(pp_list)
        course_score = calc_course_score(pp_list, course)
        style, consistency = classify_style(pp_list)
        avg_3f, best_3f = calc_closing_speed(pp_list)
        recent3, recent5, form_score = calc_form(pp_list)
        class_change = detect_class_change(pp_list)
        distance_change = detect_distance_change(pp_list, distance)
        jt_rate, jc_rate = get_jt_rates(h["jockey_code"], h["trainer_name"], jockey_stats, trainer_stats)

        # 近走成績
        podium_count = sum(1 for p in recent3 if 1 <= p <= 3)
        recent_win_rate = podium_count / len(recent3) if recent3 else 0.0
        place_count = sum(1 for p in recent5 if 1 <= p <= 3)
        recent_place_rate = place_count / len(recent5) if recent5 else 0.0
        avg_recent_position = sum(recent5) / len(recent5) if recent5 else 5.0
        last_run_position = float(recent3[0]) if recent3 else 5.0

        # 上がり一貫性
        avg_3f_val = avg_3f if avg_3f is not None else 34.0
        best_3f_val = best_3f if best_3f is not None else 34.5
        best_3f_gap = avg_3f_val - best_3f_val

        # コース適性best値
        course_best = max(course_score.values()) if course_score else 50.0

        hf = {
            "entry_id": f"{RACE_INFO['race_id']}_{h['umaban']:02d}",
            "horse_id": hid,
            "distance_aptitude_score": dist_score,
            "track_turf_score": turf_score,
            "track_dirt_score": dirt_score,
            "course_specific_score": course_score,
            "primary_style": style,
            "style_consistency": consistency,
            "average_last_3f": avg_3f_val,
            "best_last_3f": best_3f_val,
            "closing_speed_rank": None,  # 後で設定
            "recent_3_runs": recent3,
            "recent_5_runs": recent5,
            "form_score": form_score,
            "class_change": class_change,
            "distance_change": distance_change,
            "jockey_trainer_win_rate": jt_rate,
            "jockey_course_win_rate": jc_rate,
        }
        horse_features.append(hf)

        # ログ出力
        pp_count = len(pp_list)
        recent_str = "→".join(str(p) for p in recent3) if recent3 else "N/A"
        print(
            f"  {h['umaban']:2d}番 {h['name']:14s} "
            f"戦{pp_count:2d} 近走[{recent_str}] "
            f"脚質={style} 距離適性={dist_score:.0f} "
            f"上3F={avg_3f_val:.1f} "
            f"騎手勝率={jt_rate:.1%} "
            f"フォーム={form_score:.0f}",
            flush=True,
        )

    # 上がりランク再計算（全馬比較）
    all_avg = [(i, hf["average_last_3f"]) for i, hf in enumerate(horse_features) if hf["average_last_3f"] is not None]
    all_avg.sort(key=lambda x: x[1])
    for rank, (idx, _) in enumerate(all_avg, 1):
        horse_features[idx]["closing_speed_rank"] = rank

    # vectorize_race と同じ形式に変換
    from keiba.ml.feature_vectorizer import vectorize_horse_features, FEATURE_COLUMNS

    features = {
        "horse_features": horse_features,
        "field_size": field_size,
    }

    rows = [vectorize_horse_features(hf, field_size) for hf in horse_features]
    aligned_data = [[row.get(col, 0.0) for col in FEATURE_COLUMNS] for row in rows]

    # LightGBM予測
    print(f"\n📈 LightGBM予測実行...", flush=True)

    import lightgbm as lgb
    import numpy as np

    model_path = Path("data/store/models/lgbm_latest.txt")
    metadata_path = Path("data/store/models/lgbm_metadata.json")

    if not model_path.exists():
        print("❌ 学習済みモデルが存在しません", flush=True)
        return

    model = lgb.Booster(model_file=str(model_path))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}

    X = np.array(aligned_data)
    raw_scores = model.predict(X).tolist()

    # softmax正規化
    import math
    mean_score = sum(raw_scores) / len(raw_scores)
    centered = [(s - mean_score) for s in raw_scores]
    exps = [math.exp(min(s, 500)) for s in centered]
    total_exp = sum(exps)
    probabilities = [e / total_exp for e in exps]

    # 結果表示
    print("\n" + "=" * 80, flush=True)
    print("🏇 第76回安田記念(GI) 2026/6/7 東京 芝1600m", flush=True)
    print("=" * 80, flush=True)
    print(f"モデル: val_AUC={metadata.get('val_auc', 'N/A')} test_AUC={metadata.get('test_auc', 'N/A')}", flush=True)
    print(f"学習データ: {metadata.get('train_samples', 0):,}件 (JRA-VAN 27年分)", flush=True)
    print("-" * 80, flush=True)

    # ランキング
    ranked = list(enumerate(range(len(HORSES))))
    ranked.sort(key=lambda x: raw_scores[x[1]], reverse=True)

    results = []
    for rank, (idx, _) in enumerate(ranked, 1):
        h = HORSES[idx]
        prob = probabilities[idx]
        raw = raw_scores[idx]
        hf = horse_features[idx]
        style = hf["primary_style"]
        form = hf["form_score"]

        line = (
            f"  {rank:2d}位 ★{h['umaban']:2d}番 {h['name']:14s} "
            f"勝率={prob:.1%}  スコア={raw:.4f}  "
            f"脚質={style}  近走F={form:.0f}"
        )
        if rank <= 5:
            line = "🔥" + line[1:]
        print(line, flush=True)
        results.append({
            "rank": rank,
            "umaban": h["umaban"],
            "name": h["name"],
            "probability": round(prob, 4),
            "raw_score": round(raw, 4),
            "style": style,
            "form_score": form,
        })

    # 上位3頭の詳細
    print("\n" + "=" * 80, flush=True)
    print("🎯 注目馬ピックアップ", flush=True)
    print("=" * 80, flush=True)

    for r in results[:5]:
        h = HORSES[[h["umaban"] for h in HORSES].index(r["umaban"])]
        pp_list = past_perfs.get(h["hid"], [])
        print(f"\n{r['rank']}位 {h['name']} ({h['jockey_name']}騎手)", flush=True)
        print(f"  勝率推定: {r['probability']:.1%}  MLスコア: {r['raw_score']:.4f}", flush=True)
        if pp_list:
            print(f"  戦績: {len(pp_list)}戦  近走: {'→'.join(str(pp['finish_position']) for pp in sorted(pp_list, key=lambda x: x['race_date'], reverse=True)[:5])}", flush=True)
            print(f"  脚質: {r['style']}  距離適性: {horse_features[[h['umaban'] for h in HORSES].index(h['umaban'])]['distance_aptitude_score']:.0f}", flush=True)

    # 特徴量重要度
    print("\n🔑 特徴量重要度 (Top 5)", flush=True)
    importance = model.feature_importance(importance_type="gain").tolist()
    feat_imp = sorted(zip(FEATURE_COLUMNS, importance), key=lambda x: x[1], reverse=True)
    total_imp = sum(v for _, v in feat_imp) or 1
    for name, imp in feat_imp[:5]:
        print(f"  {name:<30s} {imp/total_imp:.3f}", flush=True)

    # JSON保存
    output = {
        "race": RACE_INFO,
        "model_info": {
            "val_auc": metadata.get("val_auc"),
            "test_auc": metadata.get("test_auc"),
            "train_samples": metadata.get("train_samples"),
        },
        "predictions": results,
        "generated_at": datetime.now().isoformat(),
    }

    output_path = Path("output/yasuda_kinen_2026.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n💾 予測結果保存: {output_path}", flush=True)

    return output


if __name__ == "__main__":
    main()
