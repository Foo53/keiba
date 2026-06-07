"""エージェント15: Note作成

人気競馬Note記事のベストプラクティスに基づき、無料/有料境界付きの記事を生成する。
JRA-VAN DataLab利用規約に準拠（生データ・再配布可能な集計表は掲載しない）。
"""

from keiba.agents.base import BaseAgent
from keiba.models.note import PROHIBITED_WORDS, JRAVAN_ATTRIBUTION
from keiba.models.pipeline import PipelineContext

STYLE_LABELS = {"逃げ": "逃", "先行": "先", "差し": "差", "追込": "追"}
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

        race_name = race.get("race_name", "重賞レース")
        grade = race.get("grade", "GI")
        course = race.get("course", "")
        distance = race.get("distance", 0)
        weather = race.get("weather", "")
        condition = race.get("track_condition", "")
        race_date = race.get("race_date", "")
        field_size = race.get("field_size", len(entries))
        year = race_date[:4] if race_date else ""

        horses = evidence.get("horses", [])
        ranked = sorted(horses, key=lambda h: h.get("integrated_probability", 0), reverse=True)

        top_pick = ranked[0] if ranked else None
        second = ranked[1] if len(ranked) > 1 else None
        third = ranked[2] if len(ranked) > 2 else None
        dark = next(
            (h for h in ranked[3:] if h.get("evidence_grade") in ("A", "B")),
            ranked[3] if len(ranked) > 3 else None,
        )

        # entry_id → entry情報のマッピング
        entry_map = {e.get("entry_id", ""): e for e in entries}
        # horse_id → web intelのマッピング
        web_intel = {}
        for intel in (context.web_research or {}).get("horse_intel", []):
            web_intel[intel.get("horse_id", "")] = intel

        jravan_disclaimer = suggestion.get(
            "jravan_disclaimer",
            "本記事は独自の機械学習モデルに基づく予想です。記事内では元データや再利用可能な集計表は掲載しません。",
        )

        # ── 無料部分 ──
        free_parts = [
            self._section_free_header(race_name, year),
            self._section_free_what_you_get(),
            self._section_free_overview(race_name, grade, course, distance, weather, condition, field_size, jravan_disclaimer),
            self._section_free_prospectus(ranked, entry_map, context),
            self._section_free_model_explanation(jravan_disclaimer),
            self._section_free_teaser(),
        ]
        free_body = "\n\n".join(p for p in free_parts if p)

        # ── 有料部分 ──
        paid_parts = [
            self._section_paid_header(),
            self._section_paid_conclusion(top_pick, second, third, dark, ranked, entry_map),
            self._section_paid_ranking(ranked, entry_map),
            self._section_paid_pick("◎本命", top_pick, entry_map, web_intel, context),
            self._section_paid_pick("○対抗", second, entry_map, web_intel, context),
            self._section_paid_pick("▲単穴", third, entry_map, web_intel, context),
            self._section_paid_dark_horse(dark, entry_map, web_intel, context),
            self._section_paid_dangerous_popular(ranked, entry_map, context),
            self._section_paid_cut_horses(ranked, entry_map),
            self._section_paid_buying_conditions(top_pick, second, third, dark, entry_map),
            self._section_paid_bets(pred),
            self._section_paid_bankroll(pred),
            self._section_paid_skip_conditions(),
            self._section_paid_disclaimer(jravan_disclaimer),
        ]
        paid_body = "\n\n".join(p for p in paid_parts if p)

        body = free_body + "\n\n" + paid_body

        # 禁止語チェック
        violations = [w for w in PROHIBITED_WORDS if w in body]

        summary = self._make_summary(top_pick, second, third, dark, pred)

        context.note_article = {
            "race_id": context.race_id,
            "race_name": race_name,
            "title": suggestion.get("suggested_title", f"【{grade}予想】{race_name}"),
            "structure_used": suggestion.get("structure", []),
            "body_markdown": body,
            "summary_box": summary,
            "key_prediction": f"本命: {top_pick['horse_name']}" if top_pick else "見送り推奨",
            "risk_warning": jravan_disclaimer,
            "word_count": len(body),
            "prohibited_word_violations": violations,
            "data_sources": JRAVAN_ATTRIBUTION,
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

    # ── 無料部分: ヘッダー ──

    def _section_free_header(self, race_name, year):
        return f"# 【{race_name}{year}】JRA-VANデータ×機械学習で導いた期待値◎｜危険な人気馬と勝負買い目"

    # ── 無料部分: この記事で分かること ──

    def _section_free_what_you_get(self):
        return (
            "## この記事で分かること\n\n"
            "- モデルが高く評価した期待値馬\n"
            "- 人気でも過信しにくい危険馬\n"
            "- 当日オッズ別の買い／見送り判断\n"
            "- 本線・保険・高配当狙いの買い目"
        )

    # ── 無料部分: レース概要 ──

    def _section_free_overview(self, name, grade, course, distance, weather, condition, field_size, disclaimer):
        return (
            f"## レース概要\n\n"
            f"**{name}（{grade}）**\n"
            f"{course}競馬場 芝{distance}m / {field_size}頭立て\n\n"
            f"{disclaimer}"
        )

    # ── 無料部分: 展開予想 ──

    def _section_free_prospectus(self, ranked, entry_map, context):
        """脚質構成からペースシナリオを推定（馬名は出さない）"""
        styles = []
        for h in ranked:
            eid = h.get("entry_id", "")
            entry = entry_map.get(eid, {})
            style = entry.get("style", "差し")
            styles.append(style)

        n_front = styles.count("逃げ")
        n_stalker = styles.count("先行")
        n_mid = styles.count("差し")
        n_closer = styles.count("追込")

        lines = [
            "## 今年のレースの見立て\n",
            "今年は前に行きたい馬が複数おり、道中のペースが読みづらい構成です。",
        ]

        if n_front >= 2:
            lines.append(
                "展開次第で前残りと差し決着の両方がある難解なレース。"
                "ただし、今年は単純な人気順ではなく、**展開とオッズ妙味を重視したい**。"
            )
        elif n_front == 0:
            lines.append(
                "前が空きやすく、先行勢が有利な展開が予想されます。"
            )
        else:
            lines.append(
                "ペースメーカーが1頭で、後方勢にもチャンスはありそうです。"
            )

        return "\n".join(lines)

    # ── 無料部分: モデル説明 ──

    def _section_free_model_explanation(self, disclaimer):
        return (
            "## モデルの考え方\n\n"
            "筆者がJRA-VAN Data Labの過去データをもとに独自に構築した機械学習モデル（LightGBM）を使用しています。"
            "モデルは各馬の過去成績やコース適性などを学習し、勝率を推定しています。\n\n"
            "モデルが重視しているのは**近走内容・騎手・コース適性・脚質**など複数の要素。"
            "総合的に評価し、期待値の高い馬を抽出しています。"
        )

    # ── 無料部分: ティザー ──

    def _section_free_teaser(self):
        return (
            "## 有料部分で公開する内容\n\n"
            "ここから先では以下を公開します：\n\n"
            "- モデル評価ランキング（S/A/B評価＋妙味ランク）\n"
            "- **◎本命馬**とその理由・買い条件\n"
            "- ○対抗、▲単穴、☆評価馬の深掘り分析\n"
            "- **危険な人気馬**（人気先行で期待値が下がる馬）\n"
            "- **消し馬**（今回は評価を下げる馬）\n"
            "- 当日オッズ別の**買い／見送り条件**\n"
            "- 本線・保険・高配当狙いの**推奨買い目**\n"
            "- **資金配分**（合計10,000円想定）\n"
            "- **見送り条件**\n\n"
            "---\n\n*以下、有料部分です*\n\n---"
        )

    # ── 有料部分: ヘッダー ──

    def _section_paid_header(self):
        return ""

    # ── 有料部分: 最終結論 ──

    def _section_paid_conclusion(self, top, second, third, dark, ranked, entry_map):
        lines = ["## 最終結論\n"]

        marks = [("◎", top), ("○", second), ("▲", third), ("☆", dark)]
        for mark, horse in marks:
            if horse:
                eid = horse.get("entry_id", "")
                entry = entry_map.get(eid, {})
                p = self._entry_profile(entry)
                bracket = p.get("bracket_number", "")
                jockey = p.get("jockey_name", "")
                lines.append(f"**{mark} {horse['horse_name']}（{bracket}番）** — {jockey}騎手")

        # △候補（残りの上位馬から2頭）
        top_ids = {h.get("entry_id") for h in [top, second, third, dark] if h}
        others = [h for h in ranked[:8] if h.get("entry_id") not in top_ids]
        for h in others[:2]:
            eid = h.get("entry_id", "")
            entry = entry_map.get(eid, {})
            p = self._entry_profile(entry)
            bracket = p.get("bracket_number", "")
            lines.append(f"**△ {h['horse_name']}（{bracket}番）**")

        return "\n".join(lines)

    # ── 有料部分: モデル評価ランキング ──

    def _section_paid_ranking(self, ranked, entry_map):
        lines = [
            "## モデル評価ランキング\n",
            "推定勝率の細かい数値ではなく、総合評価とオッズ妙味で表示します。\n",
            "| 馬名 | モデル評価 | 妙味 | 馬券判断 |",
            "|:---|:---:|:---:|:---|",
        ]

        for h in ranked[:10]:
            eid = h.get("entry_id", "")
            entry = entry_map.get(eid, {})
            p = self._entry_profile(entry)
            name = h["horse_name"]
            grade = h.get("evidence_grade", "C")

            # 妙味評価（evidence_gradeと位置から推定）
            prob = h.get("integrated_probability", 0)
            if grade == "S":
                model_eval = "**S**"
                value = "**A**"
                judgment = "本命・軸"
            elif grade == "A" and prob >= (ranked[0].get("integrated_probability", 0) * 0.95 if ranked else 0):
                model_eval = "**A**"
                value = "**A**"
                judgment = "穴で買い"
            elif grade == "A":
                model_eval = "**A**"
                value = "B"
                judgment = "相手筆頭"
            elif grade == "B":
                model_eval = "B"
                value = "B"
                judgment = "相手候補"
            else:
                model_eval = "B"
                value = "C"
                judgment = "今回は見送り"

            lines.append(f"| {name} | {model_eval} | {value} | {judgment} |")

        lines.append("\n> ※下位馬は省略。モデル評価は独自の統合スコアに基づく。")
        return "\n".join(lines)

    # ── 有料部分: 注目馬ピックアップ ──

    def _section_paid_pick(self, mark_label, horse, entry_map, web_intel, context):
        if not horse:
            return ""

        eid = horse.get("entry_id", "")
        entry = entry_map.get(eid, {})
        p = self._entry_profile(entry)
        name = horse["horse_name"]
        bracket = p.get("bracket_number", "")
        jockey = p.get("jockey_name", "")

        # キャッチコピー生成
        catchphrase = self._generate_catchphrase(horse, p, mark_label)

        lines = [
            f"## {mark_label}：{name}（{bracket}番）\n",
            f"**{catchphrase}**\n",
        ]

        # 強み
        strengths = horse.get("strengths", [])
        if strengths:
            lines.append("**強み:**")
            for s in strengths[:3]:
                lines.append(f"- {s['description']}")

        # 懸念材料
        concerns = horse.get("concerns", [])
        if concerns:
            lines.append("\n**懸念材料:**")
            for c in concerns[:2]:
                lines.append(f"- {c['description']}")

        # Web情報
        horse_id = p.get("horse_id", "")
        intel = web_intel.get(horse_id, {})
        notable = intel.get("notable_factors", [])
        if notable:
            lines.append(f"\n近況では{notable[0]}と伝えられています。")

        # 買い条件（mark_labelに応じて）
        lines.append(f"\n**買い条件:** {self._default_buying_condition(mark_label)}")

        return "\n".join(lines)

    # ── 有料部分: 評価馬 ──

    def _section_paid_dark_horse(self, horse, entry_map, web_intel, context):
        if not horse:
            return ""
        section = self._section_paid_pick("☆評価馬", horse, entry_map, web_intel, context)
        # 人気馬評価には注意書きを追加
        if section:
            section += "\n\n**⚠️ 人気過熱に注意:** オッズが下がりすぎると期待値がマイナスに転じる可能性があります。"
        return section

    # ── 有料部分: 危険な人気馬 ──

    def _section_paid_dangerous_popular(self, ranked, entry_map, context):
        # 人気上位だが妙味が低い馬を抽出
        lines = ["## 危険な人気馬\n"]

        # 簡易ロジック：evidence_gradeがAだが上位で、ML分析で人気過熱リスクがある馬
        # 実際はweb_research等の情報も活用したいが、ここでは簡易的に上位馬から抽出
        found = False
        for h in ranked[1:5]:
            grade = h.get("evidence_grade", "C")
            if grade in ("A", "B"):
                eid = h.get("entry_id", "")
                entry = entry_map.get(eid, {})
                p = self._entry_profile(entry)
                name = h["horse_name"]
                jockey = p.get("jockey_name", "")

                # 有名騎手なら人気過熱リスク
                popular_jockeys = {"ルメール", "レーン", "武豊", "戸崎圭太", "川田将雅"}
                if jockey in popular_jockeys:
                    lines.append(
                        f"### {name}\n\n"
                        f"{jockey}騎手の人気でオッズが下がりやすい。"
                        f"モデル評価は高いものの、**単勝が人気しすぎた場合は期待値がマイナスに転じる**可能性があります。"
                    )
                    found = True
                    break

        if not found:
            lines.append("今回は特段危険な人気馬は検出されていません。ただし、当日オッズで人気過熱している場合は注意してください。")

        return "\n".join(lines)

    # ── 有料部分: 消し馬 ──

    def _section_paid_cut_horses(self, ranked, entry_map):
        lines = [
            "## 消し馬\n",
            "モデル評価・展開・オッズ妙味の観点から、今回は評価を下げる馬です。"
            "断定的なものではなく、「今回は見送り」という判断です。\n",
        ]

        # 下位馬を最大4頭
        for h in ranked[-4:]:
            eid = h.get("entry_id", "")
            entry = entry_map.get(eid, {})
            p = self._entry_profile(entry)
            name = h["horse_name"]
            style = p.get("style", "")
            style_label = STYLE_LABELS.get(style, style)
            lines.append(f"- **{name}**: {style_label}脚質。モデル評価が低く、今回は見送り。")

        return "\n".join(lines)

    # ── 有料部分: 買い条件 ──

    def _section_paid_buying_conditions(self, top, second, third, dark, entry_map):
        lines = [
            "## 当日オッズ別の買い条件\n",
            "| 馬名 | 買い条件 | 判断 |",
            "|:---|:---|:---|",
        ]

        conditions = [
            (top, "単勝10倍以上", "**買い**（7〜9倍でも軸候補）"),
            (second, "人気が過度に上がらなければ", "**相手筆頭**"),
            (third, "単勝15倍以上", "**妙味あり**"),
            (dark, "単勝5倍以上 / **3倍以下なら見送り**", "条件付き"),
        ]

        for horse, condition, judgment in conditions:
            if horse:
                lines.append(f"| {horse['horse_name']} | {condition} | {judgment} |")

        return "\n".join(lines)

    # ── 有料部分: 買い目提案（3段階） ──

    def _section_paid_bets(self, pred):
        lines = ["## 推奨買い目\n"]

        if pred.get("skip_recommended"):
            lines.append(f"⚠️ **見送り推奨**: {pred.get('skip_reason', '期待値が低い')}")
            return "\n".join(lines)

        # 本線
        lines.append("### 【本線】\n")
        lines.append("| 券種 | 買い目 | 理由 |")
        lines.append("|:---|:---|:---|")

        for bet_key in ["win_prediction", "quinella_prediction"]:
            bet = pred.get(bet_key)
            if not bet:
                continue
            bet_type = bet["bet_type"]
            names = " / ".join(
                [f"**{n}**" for n in bet.get("horse_names", [])]
                if bet_key == "quinella_prediction"
                else [f"**{bet['horse_names'][0]}**"]
            )
            reasoning = bet.get("reasoning", "")
            lines.append(f"| {bet_type} | {names} | {reasoning} |")

        # 保険
        lines.append("\n### 【保険】\n")
        lines.append("| 券種 | 買い目 | 理由 |")
        lines.append("|:---|:---|:---|")
        place = pred.get("place_prediction")
        if place:
            names = f"**{place['horse_names'][0]}**"
            reasoning = place.get("reasoning", "本命が来なくても取れる")
            lines.append(f"| ワイド | {names} | {reasoning} |")

        # 高配当狙い
        trifecta = pred.get("trifecta_prediction")
        if trifecta:
            lines.append("\n### 【高配当狙い】\n")
            lines.append("| 券種 | 買い目 | 理由 |")
            lines.append("|:---|:---|:---|")
            names = ", ".join(trifecta.get("horse_names", []))
            reasoning = trifecta.get("reasoning", "少額で広く拾う")
            lines.append(f"| 3連複 | **{names}** | {reasoning} |")

        lines.append("\n※馬券は自己責任でご購入ください。")
        return "\n".join(lines)

    # ── 有料部分: 資金配分 ──

    def _section_paid_bankroll(self, pred):
        lines = [
            "## 資金配分（合計10,000円想定）\n",
            "| 買い目 | 区分 | 金額 |",
            "|:---|:---:|:---:|",
        ]

        if pred.get("skip_recommended"):
            return "## 資金配分\n\n見送り推奨のため資金配分なし。"

        # 標準配分パターン
        allocation = []
        win = pred.get("win_prediction")
        if win:
            allocation.append((f"単勝 {win['horse_names'][0]}", "本線", "3,000円"))

        quinella = pred.get("quinella_prediction")
        if quinella:
            names = quinella.get("horse_names", [])
            for i, name in enumerate(names):
                amount = "1,500円" if i == 0 else "1,000円"
                allocation.append((f"馬連 {name}", "本線", amount))

        place = pred.get("place_prediction")
        if place:
            allocation.append((f"ワイド {place['horse_names'][0]}", "保険", "1,000円"))

        trifecta = pred.get("trifecta_prediction")
        if trifecta:
            allocation.append(("3連複フォーメーション", "高配当狙い", "900円（各100円×9点）"))

        for item, category, amount in allocation:
            lines.append(f"| {item} | {category} | {amount} |")

        lines.append(
            "\n> ※オッズ変動によっては配分を調整してください。"
            "特に本命馬の単勝が想定より売れた場合は、単勝より馬連・ワイド中心に変更することを推奨します。"
        )

        return "\n".join(lines)

    # ── 有料部分: 見送り条件 ──

    def _section_paid_skip_conditions(self):
        return (
            "## 見送り条件\n\n"
            "当日オッズで妙味がなくなった場合は**無理に買わない**。\n\n"
            "特に以下の場合は見送りを推奨：\n"
            "- 本命馬の単勝が5倍以下に人気集中 → 単勝は見送り、馬連中心に変更\n"
            "- 人気馬の単勝が3倍以下 → 軸としては見送り\n"
            "- 全体的にオッズがつまらず、期待値がマイナス圏に → レース全体を見送り"
        )

    # ── 有料部分: 免責事項 ──

    def _section_paid_disclaimer(self, disclaimer):
        return (
            "## 免責事項\n\n"
            "- 本予想は独自のデータ分析に基づく個人的な見解です\n"
            "- レース結果を保証するものではありません\n"
            "- オッズは変動するため、購入時に必ず確認してください\n"
            "- 投資額以上の損失が生じる可能性があります\n"
            "- 馬券の購入は自己責任でお願いします\n"
            "- 本予想を参考にした投資判断の結果について、一切の責任を負いません\n"
            f"- {disclaimer}"
        )

    # ── ヘルパー: キャッチフレーズ生成 ──

    def _generate_catchphrase(self, horse, profile, mark_label):
        """注目馬のキャッチフレーズを生成"""
        strengths = horse.get("strengths", [])
        style = profile.get("style", "")

        if mark_label == "◎本命":
            if style == "逃げ":
                return "逃げて自分のペースに持ち込める最大の強み"
            elif style == "先行":
                return "先行力で主導権を握れる展開向きの一頭"
            else:
                return "モデル最高評価の期待値馬"
        elif mark_label == "○対抗":
            if "牝" in profile.get("gender", ""):
                return "斤量アドバンテージと実績で対抗"
            return "実績と安定感で対抗評価"
        elif mark_label == "▲単穴":
            if strengths:
                return strengths[0].get("description", "オッズ妙味に注目の評価馬")
            return "オッズ妙味に注目の単穴"
        else:
            return "人気薄で一発の可能性を秘める"

    # ── ヘルパー: デフォルト買い条件 ──

    def _default_buying_condition(self, mark_label):
        if mark_label == "◎本命":
            return "単勝10倍以上なら**積極的に買い**。7〜9倍でも軸としては悪くない。"
        elif mark_label == "○対抗":
            return "人気が過度に上がらなければ**相手筆頭**。"
        elif mark_label == "▲単穴":
            return "単勝15倍以上なら**妙味あり**。馬連の相手としても優秀。"
        else:
            return "単勝5倍以上なら買い。**単勝3倍以下なら見送り**。"

    # ── サマリーボックス ──

    def _make_summary(self, top, second, third, dark, pred):
        parts = []
        if top:
            parts.append(f"◎{top['horse_name']}")
        if second:
            parts.append(f"○{second['horse_name']}")
        if third:
            parts.append(f"▲{third['horse_name']}")
        if dark:
            parts.append(f"☆{dark['horse_name']}")
        if pred.get("skip_recommended"):
            parts.append("⚠️見送り推奨")
        return " / ".join(parts) + "\n\n※あくまで予想です。自己責任でご判断ください。"
