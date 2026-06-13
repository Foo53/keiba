"""エージェント10: 予想生成"""

from datetime import datetime
from itertools import combinations

from keiba.agents.base import BaseAgent
from keiba.models.pipeline import PipelineContext


class PredictionGenerator(BaseAgent):
    """券種別の買い目を生成するエージェント"""

    def validate_input(self, context: PipelineContext) -> bool:
        return (
            context.evidence is not None
            and context.actual_odds_eval is not None
        )

    def process(self, context: PipelineContext) -> PipelineContext:
        horses = context.evidence.get("horses", [])
        actual_evals = {
            e["entry_id"]: e for e in context.actual_odds_eval.get("evaluations", [])
        }
        predicted_evals = {
            e["entry_id"]: e for e in context.predicted_odds_eval.get("evaluations", [])
        }

        # 総合ランキング
        ranked = sorted(horses, key=lambda h: h.get("integrated_probability", 0), reverse=True)

        # 本命・対抗・単穴・穴馬
        top_pick = ranked[0] if ranked else None
        second_pick = ranked[1] if len(ranked) > 1 else None
        dark_horse = self._find_dark_horse(ranked, actual_evals)

        disclaimer = (
            "※本予想はデータ分析に基づく参考情報です。馬券の購入を確約するものではありません。"
            "投資は自己責任でお願いします。"
        )

        # 予想オッズベースの予想
        context.prediction_predicted = self._generate_prediction(
            context, ranked, predicted_evals, top_pick, second_pick, dark_horse, "predicted_odds", disclaimer
        )

        # 実オッズベースの予想
        context.prediction_actual = self._generate_prediction(
            context, ranked, actual_evals, top_pick, second_pick, dark_horse, "actual_odds", disclaimer
        )

        self.logger.info(
            f"Predictions generated: top_pick={top_pick['horse_name'] if top_pick else 'N/A'}, "
            f"dark_horse={dark_horse['horse_name'] if dark_horse else 'N/A'}"
        )
        return context

    def _find_dark_horse(self, ranked: list[dict], evals: dict) -> dict | None:
        """ランク4-7位の中でEVが高い穴馬を探す"""
        candidates = ranked[3:7] if len(ranked) > 3 else []
        best = None
        best_ev = -1
        for h in candidates:
            ev_data = evals.get(h["entry_id"], {})
            ev = ev_data.get("expected_value", -1)
            if ev > best_ev:
                best_ev = ev
                best = h
        return best

    def _generate_prediction(
        self, context, ranked, evals, top_pick, second_pick, dark_horse,
        prediction_type, disclaimer
    ) -> dict:
        """指定オッズ種別で予想を生成"""

        # 全体的にEVが低い場合は見送り
        all_evs = [evals.get(h["entry_id"], {}).get("expected_value", -1) for h in ranked]
        max_ev = max(all_evs) if all_evs else -1

        skip_recommended = max_ev < -0.3
        skip_reason = "全馬のオッズ妙味が薄く、無理に買い目を出すべきではありません" if skip_recommended else None

        field_size = len(ranked)

        prediction = {
            "race_id": context.race_id,
            "race_name": (context.current_race_data or {}).get("race", {}).get("race_name", ""),
            "generated_at": datetime.now().isoformat(),
            "prediction_type": prediction_type,
            "top_pick": top_pick["entry_id"] if top_pick else None,
            "second_pick": second_pick["entry_id"] if second_pick else None,
            "dark_horse": dark_horse["entry_id"] if dark_horse else None,
            "disclaimer": disclaimer,
            "skip_recommended": skip_recommended,
            "skip_reason": skip_reason,
        }

        if not skip_recommended:
            # 3連複フォーメーション — 出走頭数に応じて幅を調整
            trio_bets, trio_formation = self._generate_trio_predictions(ranked, field_size)
            if trio_bets:
                prediction["trio_predictions"] = trio_bets
            if trio_formation:
                prediction["trio_formation"] = trio_formation

            # 単勝
            if top_pick:
                ev = evals.get(top_pick["entry_id"], {})
                prediction["win_prediction"] = {
                    "bet_type": "単勝",
                    "selection": top_pick["entry_id"],
                    "horse_names": [top_pick["horse_name"]],
                    "predicted_probability": top_pick.get("integrated_probability", 0),
                    "estimated_odds": ev.get("actual_odds") or ev.get("predicted_odds"),
                    "expected_value": ev.get("expected_value"),
                    "confidence": top_pick.get("evidence_grade", "C"),
                    "reasoning": f"モデル評価1位、勝率推定{top_pick.get('integrated_probability', 0):.1%}",
                    "risk_level": "low" if top_pick.get("evidence_grade") in ("S", "A") else "medium",
                    "stake_suggestion": "1unit" if ev.get("expected_value", 0) > 0 else "見送り検討",
                }

            # 複勝
            place_candidates = [h for h in ranked[:3] if h.get("integrated_place_probability", 0) > 0.3]
            if place_candidates:
                h = place_candidates[0]
                ev = evals.get(h["entry_id"], {})
                prediction["place_prediction"] = {
                    "bet_type": "複勝",
                    "selection": h["entry_id"],
                    "horse_names": [h["horse_name"]],
                    "predicted_probability": h.get("integrated_place_probability", 0),
                    "estimated_odds": ev.get("actual_odds") or ev.get("predicted_odds"),
                    "expected_value": ev.get("expected_value"),
                    "confidence": h.get("evidence_grade", "C"),
                    "reasoning": f"複勝率推定{h.get('integrated_place_probability', 0):.1%}で安定感あり",
                    "risk_level": "low",
                    "stake_suggestion": "1unit",
                }

            # 馬連 — 上位3頭の組み合わせ（最大3本）
            quinella_bets = []
            n_quinella = min(3, len(ranked))
            for i, j in combinations(range(n_quinella), 2):
                h1, h2 = ranked[i], ranked[j]
                prob = h1.get("integrated_probability", 0) * h2.get("integrated_probability", 0)
                quinella_bets.append({
                    "bet_type": "馬連",
                    "selection": f"{h1['entry_id']}-{h2['entry_id']}",
                    "horse_names": [h1["horse_name"], h2["horse_name"]],
                    "predicted_probability": round(min(prob * 3, 0.5), 4),
                    "estimated_odds": None,
                    "expected_value": None,
                    "confidence": "A" if i == 0 and j == 1 else "B",
                    "reasoning": "本命・対抗" if i == 0 and j == 1 else f"上位候補の組み合わせ",
                    "risk_level": "medium" if i == 0 and j == 1 else "high",
                    "stake_suggestion": "1unit" if i == 0 and j == 1 else "少量",
                })
            if quinella_bets:
                prediction["quinella_predictions"] = quinella_bets
                # 後方互換: 1本目をデフォルトとして保持
                prediction["quinella_prediction"] = quinella_bets[0]

            # 3連単は根拠が弱い場合は出さない
            if top_pick and second_pick and dark_horse:
                top_prob = top_pick.get("integrated_probability", 0)
                if top_prob > 0.10:
                    combo = f"{top_pick['entry_id']}-{second_pick['entry_id']}-{dark_horse['entry_id']}"
                    names = [top_pick["horse_name"], second_pick["horse_name"], dark_horse["horse_name"]]
                    prediction["trifecta_prediction"] = {
                        "bet_type": "3連単",
                        "selection": combo,
                        "horse_names": names,
                        "predicted_probability": round(top_prob * 0.1, 4),
                        "estimated_odds": None,
                        "expected_value": None,
                        "confidence": "B",
                        "reasoning": "本命-対抗-穴馬の組み合わせ（高配当狙い）",
                        "risk_level": "high",
                        "stake_suggestion": "少量",
                    }

        return prediction

    def _generate_trio_predictions(self, ranked: list[dict], field_size: int) -> tuple:
        """3連複フォーメーションを生成。出走頭数に応じて幅を調整。

        Returns:
            (combos, formation): combos=個別組み合わせリスト、formation=フォーメーション構造情報
        """
        if len(ranked) < 4:
            return [], None

        # 大人数レース（14頭以上）では1列目を3頭に拡大
        col1_count = 3 if field_size >= 14 else 2
        col2_count = min(6, len(ranked))
        col3_count = min(8, len(ranked))

        col1_ids = [ranked[i]["entry_id"] for i in range(min(col1_count, len(ranked)))]
        col2_ids = [ranked[i]["entry_id"] for i in range(min(col2_count, len(ranked)))
                     if ranked[i]["entry_id"] not in col1_ids]
        col3_ids = [ranked[i]["entry_id"] for i in range(min(col3_count, len(ranked)))
                     if ranked[i]["entry_id"] not in col1_ids]

        entry_to_name = {h["entry_id"]: h["horse_name"] for h in ranked}

        # フォーメーション展開
        combos = []
        for c1 in col1_ids:
            for c2 in col2_ids:
                for c3 in col3_ids:
                    if c1 != c2 and c1 != c3 and c2 != c3:
                        combo = tuple(sorted([c1, c2, c3]))
                        if combo not in [tuple(sorted(c["selection"].split("-"))) for c in combos]:
                            combos.append({
                                "bet_type": "3連複",
                                "selection": f"{c1}-{c2}-{c3}",
                                "horse_names": [entry_to_name.get(c1, "?"),
                                                entry_to_name.get(c2, "?"),
                                                entry_to_name.get(c3, "?")],
                                "reasoning": "フォーメーション買い",
                                "risk_level": "high",
                                "stake_suggestion": "各100円",
                            })

        # フォーメーション構造情報（NoteWriterでの表形式表示用）
        col1_nums = [entry_to_name.get(eid, "?") for eid in col1_ids]
        col2_nums = [entry_to_name.get(eid, "?") for eid in col2_ids]
        col3_nums = [entry_to_name.get(eid, "?") for eid in col3_ids]
        formation = {
            "columns": [
                {"label": "1列目", "numbers": col1_nums},
                {"label": "2列目", "numbers": col2_nums},
                {"label": "3列目", "numbers": col3_nums},
            ],
            "total_points": len(combos),
        }

        return combos, formation

    def _get_horse_name(self, context: PipelineContext, entry_id: str) -> str:
        entries = (context.current_race_data or {}).get("entries", [])
        for e in entries:
            if e.get("entry_id") == entry_id:
                return e.get("horse", {}).get("horse_name", "不明")
        return "不明"
