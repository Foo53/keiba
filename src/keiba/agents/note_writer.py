"""エージェント13: Note作成"""

from keiba.agents.base import BaseAgent
from keiba.models.pipeline import PipelineContext

PROHIBITED_WORDS = ["絶対", "確定", "鉄板", "必ず儲かる", "回収保証", "100%", "間違いなく", "間違いない", "これだけ買えば勝てる"]


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
        evidence = context.evidence or {}
        pred = context.prediction_actual or {}
        backtest = context.backtest or {}

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

        # 各セクション構築
        intro = self._section_intro(race_name, grade, course, distance, weather, condition)
        horse_list = self._section_horse_list(ranked)
        analysis = self._section_analysis(ranked[:5])
        picks = self._section_picks(top_pick, second, dark)
        odds_eval = self._section_odds_eval(context)
        bets = self._section_bets(pred)
        skip = self._section_skip(pred)
        risk = self._section_risk()
        checklist = self._section_checklist()

        body = f"{intro}\n\n{horse_list}\n\n{analysis}\n\n{picks}\n\n{odds_eval}\n\n{bets}\n\n{skip}\n\n{risk}\n\n{checklist}"

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

    def _section_intro(self, name, grade, course, distance, weather, condition):
        return (
            f"# 【{grade}予想】{name}\n\n"
            f"## レース概要\n\n"
            f"{name}（{course} {distance}m 芝 / {weather} / {condition}）の分析結果です。\n\n"
            f"本記事はデータ分析と統計モデルに基づく予想です。あくまで参考情報としてお読みください。\n"
            f"馬券の購入は自己責任でお願いいたします。"
        )

    def _section_horse_list(self, ranked):
        lines = ["## 出走馬評価一覧\n"]
        for i, h in enumerate(ranked, 1):
            grade_icon = {"S": "🔴", "A": "🟠", "B": "🟡", "C": "⚪"}.get(h.get("evidence_grade", "C"), "⚪")
            prob = h.get("integrated_probability", 0)
            lines.append(f"| {i} | {grade_icon} {h['horse_name']} | {prob:.1%} | {h.get('evidence_grade', 'C')} |")
        header = "| 順位 | 馬名 | 勝率推定 | 評価 |\n|---|---|---|---|\n"
        return header + "\n".join(lines)

    def _section_analysis(self, top5):
        lines = ["## データ分析結果\n"]
        for h in top5:
            strengths = ", ".join(s["description"][:30] for s in h.get("strengths", [])[:2])
            concerns = ", ".join(c["description"][:30] for c in h.get("concerns", [])[:2])
            lines.append(f"### {h['horse_name']}\n")
            lines.append(f"- 統合勝率推定: {h.get('integrated_probability', 0):.1%}")
            if strengths:
                lines.append(f"- 強み: {strengths}")
            if concerns:
                lines.append(f"- 懸念: {concerns}")
            lines.append("")
        return "\n".join(lines)

    def _section_picks(self, top, second, dark):
        lines = ["## 注目馬ピックアップ\n"]
        if top:
            lines.append(f"### 本命: {top['horse_name']}\n")
            for s in top.get("strengths", [])[:2]:
                lines.append(f"- ✅ {s['description']}")
            lines.append("")
        if second:
            lines.append(f"### 対抗: {second['horse_name']}\n")
            for s in second.get("strengths", [])[:1]:
                lines.append(f"- ✅ {s['description']}")
            lines.append("")
        if dark:
            lines.append(f"### 穴馬候補: {dark['horse_name']}\n")
            lines.append("- データ上の期待値に妙味がある可能性")
            lines.append("")
        return "\n".join(lines)

    def _section_odds_eval(self, context):
        lines = ["## 期待値評価\n"]
        actual_eval = context.actual_odds_eval or {}
        for e in actual_eval.get("evaluations", [])[:5]:
            ev = e.get("expected_value", 0)
            ev_mark = "📈" if ev > 0 else "📉"
            lines.append(f"- {e['horse_name']}: オッズ{e.get('actual_odds', '?')} / EV{ev_mark}{ev:+.2f} / Grade{e.get('recommendation_grade', '?')}")
        lines.append("\n※予想オッズと実オッズの両方で評価しています。オッズは変動するため、購入時に再確認してください。")
        return "\n".join(lines)

    def _section_bets(self, pred):
        lines = ["## 買い目提案\n"]
        if pred.get("skip_recommended"):
            lines.append(f"⚠️ **見送り推奨**: {pred.get('skip_reason', '期待値が低い')}")
            return "\n".join(lines)
        for bet_key in ["win_prediction", "place_prediction", "quinella_prediction", "trifecta_prediction"]:
            bet = pred.get(bet_key)
            if bet:
                risk = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(bet.get("risk_level", "medium"), "🟡")
                lines.append(f"- **{bet['bet_type']}**: {', '.join(bet['horse_names'])} {risk}")
                if bet.get("reasoning"):
                    lines.append(f"  - 理由: {bet['reasoning']}")
        lines.append("\n※馬券は自己責任でご購入ください。")
        return "\n".join(lines)

    def _section_skip(self, pred):
        if pred.get("skip_recommended"):
            return f"## 見送り判定\n\n{pred.get('skip_reason', '全体的に期待値が低く、無理に購入するべきではありません')}"
        return "## 見送り判定\n\n今回は見送り判定なし。ただし、オッズ変動によっては見送りを推奨する場合があります。"

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
