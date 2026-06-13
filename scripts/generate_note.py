"""予測JSONからNote記事を生成するスクリプト

Usage:
    source .venv/bin/activate
    python scripts/generate_note.py output/20260613/hakodate_sprint_prediction.json
    python scripts/generate_note.py output/20260613/tokyo_js_prediction.json
"""

import sys
sys.path.insert(0, "src")

import json
from datetime import datetime
from pathlib import Path
from itertools import combinations

from keiba.models.pipeline import PipelineContext
from keiba.agents.note_writer import NoteWriter


# ── 予測JSON → PipelineContext 変換 ──


def build_context(pred_json: dict) -> PipelineContext:
    """予測JSONからNoteWriter実行に必要なPipelineContextを構築する"""
    race_info = pred_json["race"]
    predictions = pred_json["predictions"]
    race_id = race_info["race_id"]
    field_size = race_info["field_size"]
    is_jump = race_info.get("is_jump", False) or "障害" in race_info.get("track_type", "")

    # ── 1. current_race_data ──
    sex_map = {"1": "牡", "2": "牝", "3": "セン"}
    entries = []
    for p in predictions:
        entry_id = f"{race_id}_{p['umaban']:02d}"
        entries.append({
            "entry_id": entry_id,
            "post_position": p["umaban"],
            "bracket_number": p["umaban"],
            "weight_carried": p.get("weight"),
            "style": p.get("style", "差し"),
            "horse": {
                "horse_name": p["name"],
                "horse_id": p.get("horse_id", ""),
                "gender": sex_map.get(p.get("sex", ""), ""),
                "age": p.get("age"),
            },
            "jockey": {"jockey_name": p.get("jockey", "")},
        })

    current_race_data = {
        "race": {
            "race_id": race_id,
            "race_name": race_info["race_name"],
            "course": race_info["course"],
            "distance": race_info["distance"],
            "surface": race_info.get("track_type", "芝"),
            "grade": race_info["grade"],
            "race_date": race_info.get("race_date", ""),
            "field_size": field_size,
            "weather": race_info.get("weather", ""),
            "track_condition": race_info.get("track_condition", ""),
        },
        "entries": entries,
    }

    # ── 2. evidence (horses) ──
    horses_evidence = []
    for p in predictions:
        entry_id = f"{race_id}_{p['umaban']:02d}"
        prob = p["probability"]
        grade = _assign_grade(prob, p, predictions)

        strengths = _build_strengths(p, predictions)
        concerns = _build_concerns(p, predictions)

        place_prob = min(0.99, prob * 3.5)
        horses_evidence.append({
            "entry_id": entry_id,
            "horse_name": p["name"],
            "integrated_probability": prob,
            "integrated_place_probability": round(place_prob, 4),
            "evidence_grade": grade,
            "strengths": strengths,
            "concerns": concerns,
            "style": p.get("style", "差し"),
        })

    evidence = {
        "race_id": race_id,
        "integrated_at": datetime.now().isoformat(),
        "horses": horses_evidence,
    }

    # ── 3. prediction_actual ──
    ranked = sorted(horses_evidence, key=lambda h: h["integrated_probability"], reverse=True)
    top_pick = ranked[0] if ranked else None
    second_pick = ranked[1] if len(ranked) > 1 else None
    third_pick = ranked[2] if len(ranked) > 2 else None
    dark_horse = _find_dark_horse(ranked)

    prediction_actual = {
        "race_id": race_id,
        "race_name": race_info["race_name"],
        "generated_at": datetime.now().isoformat(),
        "prediction_type": "actual_odds",
        "top_pick": top_pick["entry_id"] if top_pick else None,
        "second_pick": second_pick["entry_id"] if second_pick else None,
        "dark_horse": dark_horse["entry_id"] if dark_horse else None,
        "disclaimer": "※本予想はデータ分析に基づく参考情報です。",
        "skip_recommended": False,
        "skip_reason": None,
    }

    # 買い目生成
    _add_bet_predictions(prediction_actual, ranked, entries, field_size, is_jump=is_jump)

    # ── 4. note_suggestion ──
    if is_jump:
        suggested_title = f"【{race_info['race_name']}】障害実績と近走内容から選ぶ注目馬・買い条件"
    else:
        suggested_title = f"【{race_info['race_name']}】機械学習モデルが評価した注目馬と買い条件"

    if is_jump:
        jravan_text = (
            "本記事は、障害実績・近走内容・斤量・展開などをもとにした筆者独自の総合評価と、"
            "公開情報を組み合わせた競馬予想です。"
            "元データや再利用可能なデータセットの掲載・配布は行っていません。"
        )
    else:
        jravan_text = (
            "本記事は、筆者が取得・加工した過去データをもとに構築した独自モデルと、"
            "公開情報を組み合わせた競馬予想です。"
            "元データや再利用可能なデータセットの掲載・配布は行っていません。"
        )

    note_suggestion = {
        "suggested_title": suggested_title,
        "structure": [
            "この記事で分かること", "レース概要", "今年のレースの見立て",
            "モデルの考え方", "有料部分で公開する内容",
            "最終結論", "モデル評価ランキング",
            "◎本命", "○対抗", "▲単穴", "☆評価馬",
            "危険な人気馬", "消し馬", "買い条件", "推奨買い目",
            "資金配分", "見送り条件", "免責事項",
        ],
        "tone": "reader_friendly_actionable",
        "jravan_disclaimer": jravan_text,
    }

    # ── 5. web_research ──
    weather = race_info.get("weather", "")
    track_cond = race_info.get("track_condition", "")
    weather_forecast = None
    if weather:
        weather_forecast = {"weather": weather}
        if track_cond:
            weather_forecast["track_condition"] = track_cond

    # 出走馬ニュース
    horse_intel = []
    for p in predictions:
        news_items = []
        # ジューンベロシティ4連覇関連ニュース
        if "4連覇" in race_info.get("notes", "") or p.get("name") == "ジューンベロシティ":
            if p.get("name") == "ジューンベロシティ":
                news_items.append({
                    "source": "netkeiba",
                    "title": "ジューンベロシティ4連覇挑戦",
                    "content": "東京ジャンプステークス4連覇に挑戦。8歳牡馬、斤量61kgを背負う歴史的挑戦。",
                    "relevance": 0.95,
                    "news_date": "2026-06-12",
                })
        if news_items:
            horse_intel.append({
                "horse_id": p.get("horse_id", ""),
                "horse_name": p.get("name", ""),
                "training_reports": [],
                "connections_comments": [],
                "news_items": news_items,
                "notable_factors": [],
            })

    web_research = {"horse_intel": horse_intel, "weather_forecast": weather_forecast}

    # ── PipelineContext 構築 ──
    context = PipelineContext(
        pipeline_id=f"note-gen-{race_id}",
        race_id=race_id,
        started_at=datetime.now(),
        current_stage="note_write",
        current_race_data=current_race_data,
        evidence=evidence,
        prediction_actual=prediction_actual,
        prediction_predicted=prediction_actual,
        note_suggestion=note_suggestion,
        web_research=web_research,
        actual_odds_eval={"evaluations": []},
        predicted_odds_eval={"evaluations": []},
    )

    return context


def _assign_grade(prob: float, horse: dict, all_predictions: list) -> str:
    """勝率とランクからエビデンスグレードを判定"""
    rank = horse["rank"]
    form = horse.get("form_score", 0)

    if prob > 0.15 and rank <= 2 and form >= 50:
        return "S"
    elif prob > 0.08 and rank <= 4 and form >= 20:
        return "A"
    elif prob > 0.03 and rank <= 8:
        return "B"
    return "C"


def _build_strengths(horse: dict, all_predictions: list) -> list[dict]:
    """強みリストを生成"""
    strengths = []
    recent_3 = horse.get("recent_3", [])
    style = horse.get("style", "")
    dist_apt = horse.get("distance_aptitude", 50)

    # 近走成績
    if recent_3:
        best = min(recent_3)
        worst = max(recent_3)
        spread = worst - best
        has_win = 1 in recent_3
        has_place = 2 in recent_3

        if best <= 2:
            if spread >= 3:
                # 着順に散らばりあり → 具体的表現
                desc = _nuanced_form_description(recent_3, has_win, has_place, worst)
                strengths.append({"category": "form", "type": "strength",
                                  "description": desc, "confidence": 0.7, "source": "statistical"})
            else:
                strengths.append({"category": "form", "type": "strength",
                                  "description": f"近走{'→'.join(str(r) for r in recent_3)}と安定した成績", "confidence": 0.7, "source": "statistical"})
        if has_win:
            count_win = recent_3.count(1)
            strengths.append({"category": "win", "type": "strength",
                              "description": f"近3走で{count_win}勝" if count_win > 1 else "近走に勝利あり",
                              "confidence": 0.7, "source": "statistical"})

    # 距離適性
    if dist_apt >= 80:
        strengths.append({"category": "distance", "type": "strength",
                          "description": "距離適性：高評価", "confidence": 0.6, "source": "statistical"})

    # 脚質
    if style in ("逃げ", "先行"):
        strengths.append({"category": "style", "type": "strength",
                          "description": f"{style}脚質で主導権を握れる", "confidence": 0.5, "source": "statistical"})

    # 上がり3F
    avg_3f = horse.get("avg_3f")
    if avg_3f and avg_3f < 35.0:
        strengths.append({"category": "closing", "type": "strength",
                          "description": f"上がり3Fは{avg_3f:.1f}秒と優秀", "confidence": 0.6, "source": "statistical"})

    return strengths


def _nuanced_form_description(recent_3, has_win, has_place, worst):
    """着順に散らばりがある場合の具体的近走評価文"""
    if has_win:
        if worst >= 7 and 3 in recent_3:
            return "勝利と3着実績がある一方、近走には波がある"
        # 勝利位置を特定
        for i in range(len(recent_3) - 1, -1, -1):
            if recent_3[i] == 1:
                dist = len(recent_3) - 1 - i
                pos = "前走" if dist == 0 else f"{dist + 1}走前"
                if worst >= 6:
                    return f"{pos}の勝利を評価。ただし近走には波がある"
                return f"{pos}の勝利と実績を評価"
        return "近走に勝利あり"
    if has_place:
        if worst >= 7:
            return "直近2着を評価。ただし近走には波がある"
        return f"近走{'→'.join(str(r) for r in recent_3)}と良好"
    return f"近走{'→'.join(str(r) for r in recent_3)}と良好"


def _build_concerns(horse: dict, all_predictions: list) -> list[dict]:
    """懸念リストを生成"""
    concerns = []
    recent_3 = horse.get("recent_3", [])
    recent_5 = horse.get("recent_5", [])
    age = horse.get("age", 0)
    form = horse.get("form_score", 0)

    # 近走不振
    if recent_3:
        worst = max(recent_3)
        if worst >= 6:
            concerns.append({"category": "form", "type": "concern",
                             "description": f"近走に{worst}着が挟まり、波がある", "confidence": 0.6, "source": "statistical"})

    # フォームスコア低
    if form == 0 and recent_3:
        avg_pos = sum(recent_3) / len(recent_3)
        if avg_pos > 5:
            concerns.append({"category": "consistency", "type": "concern",
                             "description": "近走内容が振るわず", "confidence": 0.5, "source": "statistical"})

    # 年齢
    if age >= 8:
        concerns.append({"category": "age", "type": "concern",
                         "description": f"{age}歳馬。年齢的な衰えのリスク", "confidence": 0.4, "source": "statistical"})

    # 重量ハンデ（障害レース等）
    weight = horse.get("weight", 57)
    if weight >= 61:
        concerns.append({"category": "weight", "type": "concern",
                         "description": f"斤量{weight:.0f}kgは出走馬中最重量クラス", "confidence": 0.5, "source": "statistical"})

    return concerns


def _find_dark_horse(ranked: list[dict]) -> dict | None:
    """ランク4-7位から評価の高い穴馬を選出"""
    candidates = ranked[3:7] if len(ranked) > 3 else []
    if not candidates:
        return None
    # evidence_gradeがA以上の馬を優先
    for h in candidates:
        if h.get("evidence_grade") in ("A", "B"):
            return h
    return candidates[0]


def _add_bet_predictions(prediction: dict, ranked: list[dict], entries: list, field_size: int, is_jump=False):
    """買い目予測を追加"""
    entry_map = {e["entry_id"]: e for e in entries}

    top_pick = ranked[0] if ranked else None
    second_pick = ranked[1] if len(ranked) > 1 else None

    # 3連複フォーメーション — 本命1頭固定で10〜15点に絞る
    if len(ranked) >= 4:
        col1 = ranked[:1]  # 本命1頭固定
        col2 = ranked[1:3]  # 相手筆頭2頭
        col3 = ranked[3:min(8, len(ranked))]  # 残り上位から5頭まで

        entry_to_name = {h["entry_id"]: h["horse_name"] for h in ranked}
        entry_to_num = {}
        for e in entries:
            entry_to_num[e["entry_id"]] = e["bracket_number"]
        col1_ids = [h["entry_id"] for h in col1]
        col2_ids = [h["entry_id"] for h in col2]
        col3_ids = [h["entry_id"] for h in col3 if h["entry_id"] not in col1_ids and h["entry_id"] not in col2_ids]

        combos = []
        seen = set()
        for c1 in col1_ids:
            for c2 in col2_ids:
                for c3 in col3_ids:
                    if c1 != c2 and c1 != c3 and c2 != c3:
                        key = tuple(sorted([c1, c2, c3]))
                        if key not in seen:
                            seen.add(key)
                            combos.append({
                                "bet_type": "3連複",
                                "selection": f"{c1}-{c2}-{c3}",
                                "horse_names": [
                                    entry_to_name.get(c1, "?"),
                                    entry_to_name.get(c2, "?"),
                                    entry_to_name.get(c3, "?"),
                                ],
                                "reasoning": "フォーメーション買い",
                                "risk_level": "high",
                                "stake_suggestion": "各100円",
                            })

        prediction["trio_predictions"] = combos
        prediction["trio_formation"] = {
            "columns": [
                {"label": "1列目", "numbers": [entry_to_num.get(eid, "?") for eid in col1_ids]},
                {"label": "2列目", "numbers": [entry_to_num.get(eid, "?") for eid in col2_ids]},
                {"label": "3列目", "numbers": [entry_to_num.get(eid, "?") for eid in col3_ids]},
            ],
            "total_points": len(combos),
        }

    # 単勝
    if top_pick:
        if is_jump:
            win_reasoning = "障害実績・近走内容を評価、本命軸"
        else:
            win_reasoning = "モデル評価1位。本命軸として評価"
        prediction["win_prediction"] = {
            "bet_type": "単勝",
            "selection": top_pick["entry_id"],
            "horse_names": [top_pick["horse_name"]],
            "predicted_probability": top_pick.get("integrated_probability", 0),
            "estimated_odds": None,
            "expected_value": None,
            "confidence": top_pick.get("evidence_grade", "C"),
            "reasoning": win_reasoning,
            "risk_level": "low",
            "stake_suggestion": "1unit",
        }

    # 複勝
    place_candidates = [h for h in ranked[:3] if h.get("integrated_place_probability", 0) > 0.3]
    if place_candidates:
        h = place_candidates[0]
        prediction["place_prediction"] = {
            "bet_type": "複勝",
            "selection": h["entry_id"],
            "horse_names": [h["horse_name"]],
            "predicted_probability": h.get("integrated_place_probability", 0),
            "estimated_odds": None,
            "expected_value": None,
            "confidence": h.get("evidence_grade", "C"),
            "reasoning": "単勝不的中時の保険として選択",
            "risk_level": "low",
            "stake_suggestion": "1unit",
        }

    # 馬連
    quinella_bets = []
    n_quinella = min(3, len(ranked))
    for i, j in combinations(range(n_quinella), 2):
        h1, h2 = ranked[i], ranked[j]
        quinella_bets.append({
            "bet_type": "馬連",
            "selection": f"{h1['entry_id']}-{h2['entry_id']}",
            "horse_names": [h1["horse_name"], h2["horse_name"]],
            "predicted_probability": None,
            "estimated_odds": None,
            "expected_value": None,
            "confidence": "A" if i == 0 and j == 1 else "B",
            "reasoning": "本命・対抗" if i == 0 and j == 1 else "上位候補の組み合わせ",
            "risk_level": "medium" if i == 0 and j == 1 else "high",
            "stake_suggestion": "1unit" if i == 0 and j == 1 else "少量",
        })
    if quinella_bets:
        prediction["quinella_predictions"] = quinella_bets
        prediction["quinella_prediction"] = quinella_bets[0]


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/generate_note.py <prediction_json_path> [--strict]")
        sys.exit(1)

    args = sys.argv[1:]
    strict_mode = "--strict" in args
    args = [a for a in args if a != "--strict"]

    pred_path = Path(args[0])
    if not pred_path.exists():
        print(f"❌ File not found: {pred_path}")
        sys.exit(1)

    pred_json = json.loads(pred_path.read_text(encoding="utf-8"))
    race_name = pred_json["race"]["race_name"]
    print(f"📝 Note記事生成: {race_name}", flush=True)

    # PipelineContext構築
    context = build_context(pred_json)

    # NoteWriter実行
    writer = NoteWriter()

    # validate
    if not writer.validate_input(context):
        print("❌ NoteWriterの入力検証に失敗しました", flush=True)
        sys.exit(1)

    # process
    context = writer.process(context)

    # 出力
    article = context.note_article
    if not article:
        print("❌ 記事生成に失敗しました", flush=True)
        sys.exit(1)

    body = article["body_markdown"]
    violations = article.get("prohibited_word_violations", [])
    quality_issues = article.get("quality_issues", [])

    # 品質チェック結果
    if quality_issues:
        print("⚠️ 記事品質チェックで問題が見つかりました:", flush=True)
        for issue in quality_issues:
            print(f"  - {issue}", flush=True)
        if strict_mode:
            raise SystemExit("❌ 品質チェックに失敗したため、記事生成を停止しました。（--strict モード）")

    # 保存
    out_dir = pred_path.parent
    date_part = out_dir.name  # e.g., "20260613"
    race_key = pred_path.stem.replace("_prediction", "")
    out_path = out_dir / f"note_{date_part}_{race_key}.md"
    out_path.write_text(body, encoding="utf-8")

    # 予測に使用した情報（PipelineContext全体）を保存。
    # レース後の反省レポートで evidence/web_research 等を比較するために保持する。
    context_path = out_dir / f"{race_key}_context.json"
    context_path.write_text(context.model_dump_json(indent=2), encoding="utf-8")
    print(f"💾 context保存: {context_path}", flush=True)

    print(f"\n✅ 記事保存: {out_path}", flush=True)
    print(f"   文字数: {len(body)}", flush=True)
    print(f"   禁止表現違反: {len(violations)}" + (f" ({violations})" if violations else ""), flush=True)

    # 先頭100行プレビュー
    print("\n" + "=" * 60)
    preview_lines = body.split("\n")[:40]
    print("\n".join(preview_lines))
    print("...")


if __name__ == "__main__":
    main()
