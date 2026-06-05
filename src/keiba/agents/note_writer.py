"""エージェント13: Note作成

パイプラインの全分析結果を統合し、Note読者向けの叙述的な記事を生成する。
各セクションは _section_* メソッドで構成。
"""

from keiba.agents.base import BaseAgent
from keiba.models.pipeline import PipelineContext

PROHIBITED_WORDS = ["絶対", "確定", "鉄板", "必ず儲かる", "回収保証", "100%", "間違いなく", "間違いない", "これだけ買えば勝てる"]

STYLE_LABELS = {"逃げ": "逃", "先行": "先", "差し": "差", "追込": "追"}
GRADE_ICONS = {"S": "🔴", "A": "🟠", "B": "🟡", "C": "⚪"}
RISK_ICONS = {"low": "🟢", "medium": "🟡", "high": "🔴"}


class NoteWriter(BaseAgent):
    """予想結果をもとにNote記事案を作成するエージェント"""

    def validate_input(self, context: PipelineContext) -> bool:
        return (
            context.note_suggestion is not None
            and context.prediction_actual is not None
            and context.evidence is not None
        )

    def process(self, context: PipelineContext) -> PipelineContext:
        suggestion = context.note_suggestion
        race = (context.current_race_data or {}).get("race", {})
        entries = (context.current_race_data or {}).get("entries", [])
        evidence = context.evidence or {}
        pred = context.prediction_actual or {}
        backtest = context.backtest or {}
        eda_images = context.eda_images or {}

        race_name = race.get("race_name", "重賞レース")
        grade = race.get("grade", "GI")
        course = race.get("course", "")
        distance = race.get("distance", 0)
        weather = race.get("weather", "")
        condition = race.get("track_condition", "")

        horses = evidence.get("horses", [])
        ranked = sorted(horses, key=lambda h: h.get("integrated_probability", 0), reverse=True)

        top_pick = ranked[0] if ranked else None
        second = ranked[1] if len(ranked) > 1 else None
        dark = next((h for h in ranked[3:] if h.get("evidence_grade") in ("A", "B")), ranked[3] if len(ranked) > 3 else None)

        # entry_id → entry情報のマッピングを構築
        entry_map = {e.get("entry_id", ""): e for e in entries}
        # horse_id → web intelのマッピング
        web_intel = {}
        for intel in (context.web_research or {}).get("horse_intel", []):
            web_intel[intel.get("horse_id", "")] = intel

        # 各セクション構築
        intro = self._section_intro(race_name, grade, course, distance, weather, condition)
        prospectus = self._section_race_prospectus(ranked, entry_map, context)
        horse_list = self._section_horse_list(ranked, entry_map)
        analysis = self._section_analysis(ranked[:5], entry_map, web_intel, context, eda_images)
        picks = self._section_picks(top_pick, second, dark, entry_map, web_intel, context)
        ml_insight = self._section_ml_insight(context)
        odds_eval = self._section_odds_eval(context, eda_images)
        eda_charts = self._section_eda_charts(eda_images, backtest)
        bets = self._section_bets(pred)
        skip = self._section_skip(pred)
        risk = self._section_risk()
        checklist = self._section_checklist()

        parts = [intro, prospectus, horse_list, analysis, picks, ml_insight,
                 odds_eval, eda_charts, bets, skip, risk, checklist]
        body = "\n\n".join(p for p in parts if p)

        # 禁止語チェック
        violations = [w for w in PROHIBITED_WORDS if w in body]

        summary = self._make_summary(top_pick, second, dark, pred)

        context.note_article = {
            "race_id": context.race_id,
            "race_name": race_name,
            "title": suggestion.get("suggested_title", f"【{grade}予想】{race_name}"),
            "structure_used": suggestion.get("structure", []),
            "body_markdown": body,
            "summary_box": summary,
            "key_prediction": f"本命: {top_pick['horse_name']}" if top_pick else "見送り推奨",
            "risk_warning": risk,
            "word_count": len(body),
            "prohibited_word_violations": violations,
        }
        self.logger.info(f"Note article created: {len(body)} chars, violations={len(violations)}")
        return context

    # ── ヘルパー: entry情報から基本プロフィール文字列を生成 ──

    def _entry_profile(self, entry: dict) -> dict:
        """entry辞書から表示用プロフィール情報を抽出する"""
        horse = entry.get("horse", {})
        jockey = entry.get("jockey", {})
        return {
            "horse_name": horse.get("horse_name", ""),
            "horse_id": horse.get("horse_id", ""),
            "jockey_name": jockey.get("jockey_name", ""),
            "gender": horse.get("gender", ""),
            "age": horse.get("age", ""),
            "weight_carried": entry.get("weight_carried"),
            "post_position": entry.get("post_position", ""),
            "bracket_number": entry.get("bracket_number", ""),
            "horse_weight": entry.get("horse_weight"),
            "weight_change": entry.get("weight_change"),
            "style": entry.get("style", ""),
            "sire": horse.get("pedigree_sire", ""),
            "dam_sire": horse.get("pedigree_dam_sire", ""),
        }

    def _format_sex_age(self, gender: str, age) -> str:
        sex = {"牡": "牡", "牝": "牝", "セン": "セ"}.get(gender, "")
        return f"{sex}{age}" if sex else str(age)

    # ── セクション1: レース概要 ──

    def _section_intro(self, name, grade, course, distance, weather, condition):
        return (
            f"# 【{grade}予想】{name}\n\n"
            f"## レース概要\n\n"
            f"{name}（{course} {distance}m 芝 / {weather} / {condition}）の分析結果です。\n\n"
            f"本記事はデータ分析と統計モデルに基づく予想です。あくまで参考情報としてお読みください。\n"
            f"馬券の購入は自己責任でお願いいたします。"
        )

    # ── セクション2: レース展望（NEW） ──

    def _section_race_prospectus(self, ranked, entry_map, context):
        """脚質構成からペースシナリオを推定し、展開予想を叙述する"""
        styles = []
        for h in ranked:
            eid = h.get("entry_id", "")
            entry = entry_map.get(eid, {})
            style = entry.get("style", "差し")
            styles.append(style)

        n_front_runner = styles.count("逃げ")
        n_stalker = styles.count("先行")
        n_midpack = styles.count("差し")
        n_closer = styles.count("追込")

        # ペース予想
        if n_front_runner == 0:
            pace = "スローペース"
            pace_desc = "逃げ馬が不在のため、ペースは上がりにくいと予想されます。"
        elif n_front_runner == 1:
            pace = "平均ペース"
            pace_desc = "逃げ馬1頭でマイペースに持ち込める可能性があります。"
        else:
            pace = "ハイペース"
            pace_desc = "逃げ馬が複数いるため、前半から厳しいペースになる可能性があります。"

        lines = [
            "## レース展望\n",
            f"出走馬の脚質構成は、逃げ{n_front_runner}頭・先行{n_stalker}頭・"
            f"差し{n_midpack}頭・追込{n_closer}頭です。",
            pace_desc,
        ]

        # 展開のポイント
        if n_front_runner == 0 and n_stalker >= 2:
            lines.append("逃げ馬がいないため、先行勢が楽に先頭を奪える展開になりそうです。"
                         "前残りの可能性も意識したいところです。")
        elif n_front_runner >= 2:
            lines.append("逃げ争いが激化すると後方集団に有利な展開になりやすく、"
                         "差し・追込脚質の馬にチャンスが回る可能性があります。")
        if n_closer >= 3:
            lines.append("追込馬が多く見られるため、直線での一気の決着も視野に入ります。")

        # web_researchのtrack_tendenciesがあれば引用
        web = context.web_research or {}
        tendencies = web.get("track_tendencies", [])
        if tendencies:
            lines.append(f"\n📋 **コース傾向**: {tendencies[0]}")

        return "\n".join(lines)

    # ── セクション3: 出走馬評価一覧（改善） ──

    def _section_horse_list(self, ranked, entry_map):
        lines = [
            "## 出走馬評価一覧\n",
            "| 枠 | 馬名 | 騎手 | 性齢 | 斤量 | 脚質 | 勝率 | 評価 |",
            "|:---:|:---|:---|:---:|:---:|:---:|:---:|:---:|",
        ]
        for i, h in enumerate(ranked, 1):
            eid = h.get("entry_id", "")
            entry = entry_map.get(eid, {})
            p = self._entry_profile(entry)
            bracket = p["bracket_number"] or i
            jockey = p["jockey_name"] or "不明"
            sex_age = self._format_sex_age(p["gender"], p["age"])
            weight = f"{p['weight_carried']}" if p["weight_carried"] else "-"
            style = STYLE_LABELS.get(p["style"], p["style"])
            prob = h.get("integrated_probability", 0)
            grade_icon = GRADE_ICONS.get(h.get("evidence_grade", "C"), "⚪")
            lines.append(
                f"| {bracket} | {grade_icon} {h['horse_name']} | {jockey} | "
                f"{sex_age} | {weight} | {style} | {prob:.1%} | {h.get('evidence_grade', 'C')} |"
            )
        return "\n".join(lines)

    # ── セクション4: データ分析結果（叙述化） ──

    def _section_analysis(self, top5, entry_map, web_intel, context, eda_images):
        lines = ["## データ分析結果\n"]
        ml_analysis = context.ml_analysis

        for h in top5:
            eid = h.get("entry_id", "")
            entry = entry_map.get(eid, {})
            p = self._entry_profile(entry)
            name = h["horse_name"]
            prob = h.get("integrated_probability", 0)
            grade = h.get("evidence_grade", "C")

            # 叙述的分析文を構築
            sentences = [f"**{name}**（{p.get('sire', '')} × {p.get('dam_sire', '')}）"
                         f"は統合勝率推定 {prob:.1%} で評価{grade}。"]

            # 強み
            strengths = h.get("strengths", [])
            if strengths:
                strength_texts = [s["description"] for s in strengths[:3]]
                sentences.append("強みとして" + "、".join(strength_texts) + "が挙げられます。")

            # 懸念
            concerns = h.get("concerns", [])
            if concerns:
                concern_texts = [c["description"] for c in concerns[:2]]
                sentences.append("一方で" + "、".join(concern_texts) + "に注意が必要です。")

            # Web情報（調教・陣営コメント）
            horse_id = p.get("horse_id", "")
            intel = web_intel.get(horse_id, {})
            training = intel.get("training_reports", [])
            comments = intel.get("connections_comments", [])
            if training:
                sentences.append(f"調教では{training[0]}との報告があります。")
            if comments:
                sentences.append(comments[0] + "とのことです。")

            # ML評価の言及
            if ml_analysis and ml_analysis.get("probabilities"):
                ml_rank = next(
                    (r["rank_by_model"] for r in ml_analysis["probabilities"]
                     if r["entry_id"] == eid),
                    None
                )
                if ml_rank and ml_rank <= 3:
                    sentences.append(f"MLモデルでも{ml_rank}位と高く評価しています。")

            lines.append(" ".join(sentences))
            lines.append("")

        if eda_images.get("horse_comparison"):
            lines.append(f"![出走馬勝率ランキング]({eda_images['horse_comparison']})\n")
        if eda_images.get("feature_comparison"):
            lines.append(f"![特徴量比較]({eda_images['feature_comparison']})\n")
        return "\n".join(lines)

    # ── セクション5: 注目馬ピックアップ（深掘り） ──

    def _section_picks(self, top, second, dark, entry_map, web_intel, context):
        lines = ["## 注目馬ピックアップ\n"]

        if top:
            eid = top.get("entry_id", "")
            entry = entry_map.get(eid, {})
            p = self._entry_profile(entry)
            name = top["horse_name"]
            prob = top.get("integrated_probability", 0)

            sentences = [
                f"### 🏆 本命: {name}\n",
                f"{name}（{p.get('sire', '')}産駒、{p.get('jockey_name', '')}騎手騎乗）"
                f"は統合勝率推定 {prob:.1%} で最も高い評価を得ています。",
            ]
            for s in top.get("strengths", [])[:3]:
                sentences.append(f"{s['description']}という強みがあります。")

            # Web情報
            horse_id = p.get("horse_id", "")
            intel = web_intel.get(horse_id, {})
            notable = intel.get("notable_factors", [])
            if notable:
                sentences.append(f"近況では{notable[0]}と伝えられています。")

            lines.append(" ".join(sentences))
            lines.append("")

        if second:
            eid = second.get("entry_id", "")
            entry = entry_map.get(eid, {})
            p = self._entry_profile(entry)
            name = second["horse_name"]
            prob = second.get("integrated_probability", 0)

            sentences = [
                f"### 🥈 対抗: {name}\n",
                f"{name}は統合勝率推定 {prob:.1%} で2番手の評価。",
            ]
            for s in second.get("strengths", [])[:2]:
                sentences.append(f"{s['description']}点は魅力です。")
            for c in second.get("concerns", [])[:1]:
                sentences.append(f"ただし{c['description']}という要素にも留意したいところです。")
            lines.append(" ".join(sentences))
            lines.append("")

        if dark:
            eid = dark.get("entry_id", "")
            entry = entry_map.get(eid, {})
            p = self._entry_profile(entry)
            name = dark["horse_name"]
            prob = dark.get("integrated_probability", 0)

            sentences = [
                f"### 💎 穴馬候補: {name}\n",
                f"{name}は統合勝率推定 {prob:.1%} ながら、オッズ面で妙味がある可能性を秘めています。",
            ]
            horse_id = p.get("horse_id", "")
            intel = web_intel.get(horse_id, {})
            training = intel.get("training_reports", [])
            if training:
                sentences.append(f"調教での{training[0]}という報告は好材料です。")
            lines.append(" ".join(sentences))
            lines.append("")

        return "\n".join(lines)

    # ── セクション6: ML分析インサイト（NEW） ──

    def _section_ml_insight(self, context):
        ml = context.ml_analysis
        if not ml:
            return ""

        confidence = ml.get("model_confidence", 0)
        importance = ml.get("feature_importance", [])

        lines = [
            "## ML分析インサイト\n",
            f"LightGBMモデル（Optuna最適化済み）による分析結果です。"
            f"モデル信頼度（検証AUC）: **{confidence:.4f}**\n",
        ]

        if importance:
            lines.append("**特徴量重要度 Top5（gain ベース）**:\n")
            lines.append("| 順位 | 特徴量 | 重要度 |")
            lines.append("|:---:|:---|:---:|")
            feature_labels = {
                "distance_aptitude_score": "距離適性",
                "track_turf_score": "芝適性",
                "track_dirt_score": "ダート適性",
                "course_specific_best": "コース実績",
                "style_consistency": "脚質一貫性",
                "style_front_runner": "逃げ",
                "style_stalker": "先行",
                "style_midpack": "差し",
                "style_closer": "追込",
                "avg_last_3f": "平均上がり",
                "best_last_3f": "最速上がり",
                "closing_speed_rank": "上がり順位",
                "form_score": "近走調子",
                "class_change_up": "クラス昇級",
                "class_change_down": "クラス降級",
                "distance_change_up": "距離延長",
                "distance_change_down": "距離短縮",
                "jockey_trainer_win_rate": "騎手勝率",
                "recent_win_rate": "近走勝率",
                "recent_place_rate": "近走連対率",
                "avg_recent_position": "平均着順",
                "last_run_position": "前走着順",
                "field_size": "頭数",
                "jockey_course_win_rate": "コース騎手勝率",
                "best_3f_gap": "上がり一貫性",
            }
            for i, item in enumerate(importance[:5], 1):
                feat_name = feature_labels.get(item["feature"], item["feature"])
                lines.append(f"| {i} | {feat_name} | {item['importance']:.3f} |")

            # 一行サマリー
            top_feat = importance[0]["feature"]
            top_label = feature_labels.get(top_feat, top_feat)
            lines.append(f"\nこのレースでは**{top_label}**が最も予測に影響しています。")

        return "\n".join(lines)

    # ── セクション7: 期待値評価（比較テーブル化） ──

    def _section_odds_eval(self, context, eda_images):
        lines = ["## 期待値評価\n"]

        predicted_evals = {
            e.get("entry_id") or e.get("horse_name"): e
            for e in (context.predicted_odds_eval or {}).get("evaluations", [])
        }
        actual_evals = {
            e.get("entry_id") or e.get("horse_name"): e
            for e in (context.actual_odds_eval or {}).get("evaluations", [])
        }

        # actual_evalsをベースにテーブル構築
        if actual_evals:
            lines.append("| 馬名 | 実オッズ | 期待値 | 判定 | コメント |")
            lines.append("|:---|:---:|:---:|:---:|:---|")
            for e in (context.actual_odds_eval or {}).get("evaluations", []):
                name = e.get("horse_name", "")
                odds = e.get("actual_odds", "?")
                ev = e.get("expected_value", 0)
                grade = e.get("recommendation_grade", "?")
                ev_mark = "📈" if ev > 0 else "📉"
                comment = ""
                if ev > 5:
                    comment = "高い期待値"
                elif ev > 0:
                    comment = "プラス圏内"
                elif ev > -1:
                    comment = "ほぼ適正"
                else:
                    comment = "割高"
                lines.append(
                    f"| {name} | {odds} | {ev_mark}{ev:+.2f} | {grade} | {comment} |"
                )

        lines.append(
            "\n※予想オッズと実オッズの両方で評価しています。"
            "オッズは変動するため、購入時に再確認してください。"
        )

        if eda_images.get("expected_value"):
            lines.append(f"\n![期待値評価チャート]({eda_images['expected_value']})\n")
        return "\n".join(lines)

    # ── セクション8: バックテスト可視化（数値解説追加） ──

    def _section_eda_charts(self, eda_images, backtest):
        lines = []
        if not eda_images.get("backtest_summary") and not backtest:
            return ""

        if backtest and backtest.get("total_races", 0) > 0:
            n = backtest["total_races"]
            hit = backtest.get("hit_rate", 0)
            roi = backtest.get("roi", 0)
            lines.append("## バックテスト可視化\n")
            lines.append(
                f"過去{n}レースのバックテストでは、"
                f"的中率 **{hit:.1%}**、回収率 **ROI {roi:.1%}** という結果です。"
            )
            # 内訳があれば追加
            breakdown = backtest.get("breakdown_by_bet_type", {})
            place_data = breakdown.get("複勝", {})
            if place_data:
                place_hit = place_data.get("hit_rate", 0)
                lines.append(f"複勝的中率は {place_hit:.1%} です。")
        elif eda_images.get("backtest_summary"):
            lines.append("## バックテスト可視化\n")

        if eda_images.get("backtest_summary"):
            lines.append(f"\n![バックテスト結果]({eda_images['backtest_summary']})\n")
        if eda_images.get("recent_form_heatmap"):
            lines.append(f"![近走着順ヒートマップ]({eda_images['recent_form_heatmap']})\n")
        return "\n".join(lines) if lines else ""

    # ── セクション9: 買い目提案（深掘り） ──

    def _section_bets(self, pred):
        lines = ["## 買い目提案\n"]
        if pred.get("skip_recommended"):
            lines.append(f"⚠️ **見送り推奨**: {pred.get('skip_reason', '期待値が低い')}")
            return "\n".join(lines)

        for bet_key in ["win_prediction", "place_prediction", "quinella_prediction", "trifecta_prediction"]:
            bet = pred.get(bet_key)
            if not bet:
                continue
            risk = RISK_ICONS.get(bet.get("risk_level", "medium"), "🟡")
            bet_type = bet["bet_type"]
            names = ", ".join(bet["horse_names"])
            confidence = bet.get("confidence", "?")
            ev = bet.get("expected_value")

            lines.append(f"### {risk} {bet_type}: {names}")
            lines.append(f"- 確度: {confidence}")
            if bet.get("reasoning"):
                lines.append(f"- 理由: {bet['reasoning']}")
            if ev is not None:
                ev_mark = "プラス" if ev > 0 else "マイナス"
                lines.append(f"- 期待値: {ev:+.2f}（{ev_mark}）")
            stake = bet.get("stake_suggestion", "")
            if stake:
                lines.append(f"- 買い目目安: {stake}")
            lines.append("")

        lines.append("※馬券は自己責任でご購入ください。")
        return "\n".join(lines)

    # ── セクション10: 見送り判定 ──

    def _section_skip(self, pred):
        if pred.get("skip_recommended"):
            return f"## 見送り判定\n\n{pred.get('skip_reason', '全体的に期待値が低く、無理に購入するべきではありません')}"
        return "## 見送り判定\n\n今回は見送り判定なし。ただし、オッズ変動によっては見送りを推奨する場合があります。"

    # ── セクション11: リスク説明 ──

    def _section_risk(self):
        return (
            "## ⚠️ リスク説明・免責事項\n\n"
            "- 本予想はデータ分析に基づく個人的な見解です\n"
            "- レース結果を保証するものではありません\n"
            "- オッズは変動するため、購入時に必ず確認してください\n"
            "- 投資額以上の損失が生じる可能性があります\n"
            "- 馬券の購入は自己責任でお願いします\n"
            "- 本予想を参考にした投資判断の結果について、一切の責任を負いません"
        )

    # ── セクション12: 当日チェックリスト ──

    def _section_checklist(self):
        return (
            "## 📋 当日更新チェックリスト\n\n"
            "- [ ] 馬場状態の最終確認\n"
            "- [ ] 天候の最終確認\n"
            "- [ ] 出走取消・変更の確認\n"
            "- [ ] オッズ変動の確認（実オッズでの再評価）\n"
            "- [ ] 騎手変更の確認\n"
            "- [ ] 馬体重の最終確認"
        )

    # ── サマリーボックス ──

    def _make_summary(self, top, second, dark, pred):
        parts = []
        if top:
            parts.append(f"本命: {top['horse_name']}")
        if second:
            parts.append(f"対抗: {second['horse_name']}")
        if dark:
            parts.append(f"穴: {dark['horse_name']}")
        if pred.get("skip_recommended"):
            parts.append("⚠️ 見送り推奨")
        return " / ".join(parts) + "\n\n※あくまで予想です。自己責任でご判断ください。"
