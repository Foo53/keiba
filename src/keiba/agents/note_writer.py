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
        is_jump = "障害" in course or (grade and grade.startswith("J"))

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
            self._section_free_header(race_name, year, is_jump=is_jump),
            self._section_free_what_you_get(is_jump=is_jump),
            self._section_free_overview(race_name, grade, course, distance, weather, condition, field_size, jravan_disclaimer, context, is_jump=is_jump),
            self._section_free_prospectus(ranked, entry_map, context, race_name=race_name, is_jump=is_jump),
            self._section_free_model_explanation(jravan_disclaimer, ranked=ranked, is_jump=is_jump),
            self._section_free_teaser(is_jump=is_jump),
        ]
        free_body = "\n\n".join(p for p in free_parts if p)

        # ── 有料部分 ──
        paid_parts = [
            self._section_paid_header(),
            self._section_paid_conclusion(top_pick, second, third, dark, ranked, entry_map, is_jump=is_jump),
            self._section_paid_ranking(ranked, entry_map, is_jump=is_jump),
            self._section_paid_pick("◎本命", top_pick, entry_map, web_intel, context, is_jump=is_jump),
            self._section_paid_pick("○対抗", second, entry_map, web_intel, context, is_jump=is_jump),
            self._section_paid_pick("▲単穴", third, entry_map, web_intel, context, is_jump=is_jump),
            self._section_paid_dark_horse(dark, entry_map, web_intel, context, is_jump=is_jump),
            self._section_paid_dangerous_popular(ranked, entry_map, context, is_jump=is_jump),
            self._section_paid_cut_horses(ranked, entry_map, is_jump=is_jump),
            self._section_paid_buying_conditions(top_pick, second, third, dark, entry_map),
            self._section_paid_bets(pred, is_jump=is_jump),
            self._section_paid_bankroll(pred),
            self._section_paid_skip_conditions(top_pick=top_pick),
            self._section_paid_disclaimer(jravan_disclaimer, is_jump=is_jump),
            self._section_paid_technical_info(is_jump=is_jump),
        ]
        paid_body = "\n\n".join(p for p in paid_parts if p)

        body = free_body + "\n\n" + paid_body

        # 禁止語チェック
        violations = [w for w in PROHIBITED_WORDS if w in body]

        # 公開前チェックリスト（内部確認用。記事本文には含めない）
        checklist = self._section_paid_checklist(body)

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
            "pre_publish_checklist": checklist,
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

    def _section_free_header(self, race_name, year, is_jump=False):
        if is_jump:
            return f"# 【{race_name}{year}】障害実績と近走内容から選ぶ注目馬・買い条件"
        return f"# 【{race_name}{year}】機械学習モデルが評価した注目馬と買い条件"

    # ── 無料部分: この記事で分かること ──

    def _section_free_what_you_get(self, is_jump=False):
        if is_jump:
            return (
                "## この記事で分かること\n\n"
                "- 障害実績と近走内容から評価した注目馬\n"
                "- 人気でも過信しにくい危険馬\n"
                "- 当日オッズ別の買い／見送り判断\n"
                "- 本線・保険・高配当狙いの買い目\n\n"
                "※本記事は独自分析に基づく競馬予想です。的中や利益を保証するものではありません。"
                "馬券の購入は自己責任でお願いします。"
            )
        return (
            "## この記事で分かること\n\n"
            "- モデルが高く評価した注目馬\n"
            "- 人気でも過信しにくい危険馬\n"
            "- 当日オッズ別の買い／見送り判断\n"
            "- 本線・保険・高配当狙いの買い目\n\n"
            "※本記事は独自分析に基づく競馬予想です。的中や利益を保証するものではありません。"
            "馬券の購入は自己責任でお願いします。"
        )

    # ── 無料部分: レース概要 ──

    def _section_free_overview(self, name, grade, course, distance, weather, condition, field_size, disclaimer, context=None, is_jump=False):
        # 「第回」は回数が未確認の場合は出力しない
        lines = [
            f"## レース概要\n",
            f"**{name}（{grade}）**",
        ]

        # 発走時刻・コース情報
        race = (context.current_race_data or {}).get("race", {}) if context and hasattr(context, "current_race_data") else {}
        race_date = race.get("race_date", "")
        start_time = race.get("start_time", "")
        # 日付を日本語表記に変換（例: 2026-06-13 → 2026年6月13日（土））
        date_str = self._format_date_jp(race_date) if race_date else ""
        if start_time:
            date_str += f" {start_time}発走"
        course_label = f"{course}競馬場" if course else ""
        surface = race.get("surface", "芝")
        lines.append(f"{date_str} / {course_label} {surface}{distance}m / {field_size}頭立て" if date_str else f"{course_label} {surface}{distance}m / {field_size}頭立て")

        # 天気予報があれば表示
        web_research = None
        if context and hasattr(context, "web_research"):
            web_research = context.web_research
        wf = None
        if isinstance(web_research, dict):
            wf = web_research.get("weather_forecast")
        if wf and isinstance(wf, dict):
            weather_text = wf.get("weather", "")
            temp = wf.get("temperature")
            rain = wf.get("rain_probability")
            weather_line = f"天気予報: {weather_text}"
            tc = wf.get("track_condition")
            if tc:
                weather_line += f" / 馬場: {tc}"
            if temp is not None:
                weather_line += f" / 気温{temp}℃"
            if rain is not None:
                weather_line += f" / 降水確率{rain}%"
            lines.append(weather_line)
        elif wf and isinstance(wf, str):
            lines.append(wf)
        elif weather:
            lines.append(f"天候: {weather}" + (f" / 馬場: {condition}" if condition else ""))

        if is_jump:
            jump_disclaimer = (
                "本記事は、障害実績・近走内容・斤量・展開などをもとにした筆者独自の総合評価と、"
                "公開情報を組み合わせた競馬予想です。"
                "元データや再利用可能なデータセットの掲載・配布は行っていません。"
            )
            lines.append(f"\n{jump_disclaimer}")
        else:
            lines.append(f"\n{disclaimer}")
        return "\n".join(lines)

    # ── 無料部分: 展開予想 ──

    def _section_free_prospectus(self, ranked, entry_map, context, race_name="", is_jump=False):
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

        title = f"今年の{race_name}の見立て" if race_name else "今年のレースの見立て"
        lines = [
            f"## {title}\n",
        ]

        if n_front >= 2:
            lines.append(
                "今年は前に行きたい馬が複数おり、道中のペースが読みづらい構成です。\n\n"
                "展開次第で前残りと差し決着の両方がある難解なレース。"
                "ただし、今年は単純な人気順ではなく、**展開と事前評価を重視したい**。"
            )
        elif n_front == 0:
            lines.append(
                "前が空きやすく、先行勢が有利な展開が予想されます。"
            )
        else:
            lines.append(
                "ペースメーカーが1頭で、後方勢にもチャンスはありそうです。"
            )

        # 天気インパクトの一文
        web_research = None
        if context and hasattr(context, "web_research"):
            web_research = context.web_research
        if web_research and isinstance(web_research, dict):
            wf = web_research.get("weather_forecast")
            weather_text = ""
            if isinstance(wf, dict):
                weather_text = wf.get("weather", "")
            elif isinstance(wf, str):
                weather_text = wf
            if "雨" in weather_text:
                lines.append("\n⚡ **雨馬場が予想されます。** 道悪巧者の出走馬に注目です。")

        # 障害レース用の注記
        if is_jump:
            lines.append(
                "\n\n**⚠️ 分析上の注記**: 本レースは障害戦です。平地用モデルの対象外のため、"
                "障害実績と近走内容を中心にした参考予想として扱います。"
            )

        return "\n".join(lines)

    # ── 無料部分: モデル説明 ──

    def _section_free_model_explanation(self, disclaimer, ranked=None, is_jump=False):
        if is_jump:
            text = (
                "## 分析の考え方\n\n"
                "障害戦は平地用モデルの対象外のため、障害実績・近走内容・飛越安定性・展開を総合して評価しています。"
            )
        else:
            text = (
                "## モデルの考え方\n\n"
                "筆者が過去データをもとに独自に構築した機械学習モデル（LightGBM）を使用しています。"
                "モデルは各馬の近走内容やコース適性などをもとに、独自の評価スコアを算出しています。\n\n"
                "モデルは、近走内容・騎手・コース適性・脚質など複数の要素を総合して評価しています。"
            )

        # レース固有のモデルハイライト（上位馬の傾向から生成）— 障害レースではスキップ
        if not is_jump and ranked and len(ranked) >= 2:
            top_style = self._get_style_label(ranked[0])
            styles_in_top = [self._get_style_label(h) for h in ranked[:5]]
            if top_style in ("逃げ", "先行"):
                text += "\n\nモデルは、**前に行きたい馬の一角を高く評価**しています。"
            elif styles_in_top.count("差し") >= 2:
                text += "\n\nモデルは**差し脚質の馬を高評価**しています。ハイペースを利できる展開が想定されるためです。"

            # 人気過熱リスクの言及
            text += (
                "\n\n今年は「人気馬をそのまま買うレース」ではなく、"
                "当日のオッズを見て妙味が残っている馬を選ぶレースだと見ています。"
                "有料部分では、具体的な本命馬・相手・危険な人気馬・買い目・見送り条件までまとめています。"
            )

            text += (
                "\n\n※掲載する確率は独自モデルの推定値であり、実際の的中確率を保証するものではありません。"
                "また、当日のオッズと比較して購入判断を行います。"
            )

        return text

    def _get_style_label(self, horse):
        """horse辞書から脚質ラベルを取得"""
        return horse.get("style", "差し")

    @staticmethod
    def _get_grade_number(grade):
        """グレード文字列から回数を推定（簡易ロジック）"""
        return ""  # 回数はraceデータから取得すべきだが、未取得時は空

    @staticmethod
    def _format_date_jp(date_str):
        """YYYY-MM-DD → YYYY年M月D日（曜日）"""
        if not date_str or len(date_str) < 10:
            return date_str
        try:
            from datetime import datetime as dt
            d = dt.strptime(date_str[:10], "%Y-%m-%d")
            dow = ["月", "火", "水", "木", "金", "土", "日"][d.weekday()]
            return f"{d.year}年{d.month}月{d.day}日（{dow}）"
        except (ValueError, TypeError):
            return date_str

    # ── 無料部分: ティザー ──

    def _section_free_teaser(self, is_jump=False):
        ranking_label = "総合評価ランキング（S/A/B評価＋注目度ランク）" if is_jump else "総合評価ランキング（S/A/B評価＋注目度ランク）"
        return (
            "## 有料部分で公開する内容\n\n"
            "ここから先では以下を公開します：\n\n"
            f"- {ranking_label}\n"
            "- **◎本命馬**とその理由・買い条件\n"
            "- ○対抗、▲単穴、☆評価馬の深掘り分析\n"
            "- **危険な人気馬**（人気先行で妙味が薄くなる馬）\n"
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

    def _section_paid_conclusion(self, top, second, third, dark, ranked, entry_map, is_jump=False):
        lines = ["## 最終結論\n"]

        marks = [("◎", top), ("○", second), ("▲", third), ("☆", dark)]
        for mark, horse in marks:
            if horse:
                eid = horse.get("entry_id", "")
                entry = entry_map.get(eid, {})
                p = self._entry_profile(entry)
                bracket = p.get("bracket_number", "")
                desc = self._short_horse_description(horse, p, is_jump=is_jump, mark_label=mark)
                lines.append(f"**{mark} {horse['horse_name']}（{bracket}番）** — {desc}")

        # △候補（残りの上位馬から2頭）
        top_ids = {h.get("entry_id") for h in [top, second, third, dark] if h}
        others = [h for h in ranked[:8] if h.get("entry_id") not in top_ids]
        for h in others[:2]:
            eid = h.get("entry_id", "")
            entry = entry_map.get(eid, {})
            p = self._entry_profile(entry)
            bracket = p.get("bracket_number", "")
            desc = self._short_horse_description(h, p, is_jump=is_jump, mark_label="△")
            lines.append(f"**△ {h['horse_name']}（{bracket}番）** — {desc}")

        return "\n".join(lines)

    def _short_horse_description(self, horse, profile, is_jump=False, mark_label=""):
        """最終結論用の短い説明文を生成"""
        parts = []
        style = profile.get("style", "")
        if style:
            parts.append(style)
        strengths = horse.get("strengths", [])

        # is_jumpで◎/○かつ勝利あり → 統合表現（mark_suffixと重複しないよう早期return）
        if is_jump and mark_label in ("◎", "○"):
            has_win = any("勝利" in s.get("description", "") for s in strengths)
            if has_win:
                concerns = horse.get("concerns", [])
                has_wave = any("波がある" in c.get("description", "") for c in concerns)
                if mark_label == "◎":
                    parts.append("前走勝利と障害実績を評価")
                elif mark_label == "○":
                    if style in ("逃げ", "先行"):
                        if has_wave:
                            parts.append("前走勝利と先行力を評価。ただし近走には波がある")
                        else:
                            parts.append("前走勝利と先行力を評価")
                    else:
                        if has_wave:
                            parts.append("前走勝利を評価。ただし近走には波がある")
                        else:
                            parts.append("前走勝利を評価")
                return "・".join(parts)

        if strengths:
            desc = strengths[0].get("description", "")[:20]
            # 「安定した成績」の誤用チェック
            desc = self._fix_stability_wording(desc, horse)
            # is_jumpで着順に散らばりがある場合、「安定した成績」を具体表現に
            # ただしconcernsに「波がある」がなければ「安定した成績」をそのまま保持
            if is_jump and "安定した成績" in desc:
                concerns = horse.get("concerns", [])
                has_wave = any("波がある" in c.get("description", "") for c in concerns)
                if has_wave:
                    desc = self._jump_form_description(horse, profile, mark_label)
            parts.append(desc)
        # is_jump の場合はモデル評価を使わず、実績ベースの表現にする
        grade = horse.get("evidence_grade", "")
        if is_jump:
            if mark_label == "◎":
                parts.append("障害実績を評価")
            elif mark_label == "○":
                parts.append("先行力を評価")
            elif grade == "A":
                parts.append("高評価")
        else:
            if grade == "S" and mark_label == "◎":
                parts.append("モデル最高評価")
            elif grade == "S" and mark_label == "○":
                parts.append("本命に次ぐ高評価")
            elif grade == "A":
                parts.append("高評価")
        return "・".join(parts) if parts else ""

    @staticmethod
    def _fix_stability_wording(desc, horse):
        """近走に大きく外れた着順があれば「安定した成績」を具体的表現に修正"""
        if "安定した成績" not in desc and "良好" not in desc:
            return desc
        # concerns に「波がある」があれば、安定した成績/良好 は不適切
        concerns = horse.get("concerns", [])
        has_wave = any("波がある" in c.get("description", "") for c in concerns)
        if not has_wave:
            return desc
        # strengthsから近走着順を抽出して具体的表现に変更
        strengths = horse.get("strengths", [])
        recent_3 = []
        for s in strengths:
            d = s.get("description", "")
            if d.startswith("近走") and "→" in d:
                try:
                    parts = d.replace("近走", "").split("と")[0]
                    recent_3 = [int(x) for x in parts.split("→")]
                except (ValueError, IndexError):
                    pass
                break
        if not recent_3:
            return desc.replace("安定した成績", "良好")
        has_win = 1 in recent_3
        has_place = 2 in recent_3
        worst = max(recent_3)
        if has_win:
            if 3 in recent_3:
                return "勝利と3着実績がある一方、近走には波がある"
            # 勝利位置を特定
            for i in range(len(recent_3) - 1, -1, -1):
                if recent_3[i] == 1:
                    dist = len(recent_3) - 1 - i
                    pos = "前走" if dist == 0 else f"{dist + 1}走前"
                    return f"{pos}の勝利を評価。前走{worst}着で安定感には課題"
        if has_place:
            return "直近2着を評価。ただし近走には波がある"
        return desc.replace("安定した成績", "良好")

    def _jump_form_description(self, horse, profile, mark_label=""):
        """障害レース用の近走評価文（「安定した成績」を避ける）"""
        strengths = horse.get("strengths", [])
        has_win = any("勝利" in s.get("description", "") for s in strengths)
        style = profile.get("style", "")
        if has_win:
            if mark_label == "◎":
                return "前走勝利と障害実績を評価"
            elif mark_label == "○":
                if style in ("逃げ", "先行"):
                    return "前走勝利と先行力を評価。ただし近走には波がある"
                return "前走勝利を評価。ただし近走には波がある"
            else:
                return "近走に勝利あり"
        if style in ("逃げ", "先行"):
            return f"{style}脚質で主導権を握れる"
        return "実績を評価"

    # ── 有料部分: モデル評価ランキング ──

    def _section_paid_ranking(self, ranked, entry_map, is_jump=False):
        heading = "総合評価ランキング（障害実績・近走内容重視）" if is_jump else "モデル評価ランキング"
        eval_label = "総合評価" if is_jump else "モデル評価"
        lines = [
            f"## {heading}\n",
            "推定勝率の細かい数値ではなく、総合評価と注目度で表示します。\n",
            f"| 馬名 | {eval_label} | 注目度 | 馬券判断 |",
            "|:---|:---:|:---:|:---|",
        ]

        for i, h in enumerate(ranked[:10]):
            name = h["horse_name"]
            grade = h.get("evidence_grade", "C")

            # 注目度評価（evidence_gradeと位置から推定）
            prob = h.get("integrated_probability", 0)
            if grade == "S" and i == 0:
                model_eval = "**S**"
                value = "**A**"
                judgment = "◎本命・軸"
            elif grade == "S":
                model_eval = "**S**"
                value = "**A**"
                judgment = "○相手筆頭"
            elif grade == "A" and prob >= (ranked[0].get("integrated_probability", 0) * 0.95 if ranked else 0):
                model_eval = "**A**"
                value = "**A**"
                judgment = "穴で買い"
            elif grade == "A":
                model_eval = "**A**"
                value = "B"
                judgment = "▲相手候補"
            elif grade == "B" and i <= 6:
                model_eval = "B"
                value = "B"
                judgment = "相手候補"
            else:
                model_eval = "B"
                value = "C"
                judgment = "今回は見送り"

            lines.append(f"| {name} | {model_eval} | {value} | {judgment} |")

        if is_jump:
            lines.append("\n> ※東京ジャンプSでは平地用モデルの評価を使用せず、障害実績・近走内容・展開をもとに評価しています。")
        else:
            lines.append("\n> ※下位馬は省略。モデル評価は独自の統合スコアに基づく。")
        return "\n".join(lines)

    # ── 有料部分: 注目馬ピックアップ ──

    def _section_paid_pick(self, mark_label, horse, entry_map, web_intel, context, is_jump=False):
        if not horse:
            return ""

        eid = horse.get("entry_id", "")
        entry = entry_map.get(eid, {})
        p = self._entry_profile(entry)
        name = horse["horse_name"]
        bracket = p.get("bracket_number", "")
        jockey = p.get("jockey_name", "")

        # キャッチコピー生成
        catchphrase = self._generate_catchphrase(horse, p, mark_label, is_jump=is_jump)

        lines = [
            f"## {mark_label}：{name}（{bracket}番）\n",
            f"**{catchphrase}**\n",
        ]

        # 強み
        strengths = horse.get("strengths", [])
        if strengths:
            lines.append("**強み:**")
            for s in strengths[:3]:
                desc = self._fix_stability_wording(s["description"], horse)
                # is_jumpの場合、上がり3Fの記述は障害戦として不自然なのでスキップ
                if is_jump and "上がり3F" in desc:
                    continue
                lines.append(f"- {desc}")

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

        # 調教・近況サブセクション
        training_reports = intel.get("training_reports", [])
        if training_reports:
            lines.append("\n**調教・近況:**")
            for report in training_reports[:3]:
                lines.append(f"- {report}")

        # 関連ニュース
        news_items = intel.get("news_items", [])
        if news_items:
            lines.append("\n**関連ニュース:**")
            for news in news_items[:2]:
                lines.append(f"- {news.get('title', '')}")

        # 買い条件（mark_labelに応じて）
        lines.append(f"\n**買い条件:** {self._default_buying_condition(mark_label)}")

        return "\n".join(lines)

    # ── 有料部分: 評価馬 ──

    def _section_paid_dark_horse(self, horse, entry_map, web_intel, context, is_jump=False):
        if not horse:
            return ""
        section = self._section_paid_pick("☆評価馬", horse, entry_map, web_intel, context, is_jump=is_jump)
        # 人気馬評価には注意書きを追加
        if section:
            section += "\n\n**⚠️ 人気過熱に注意:** オッズが下がりすぎると妙味が薄くなる可能性があります。"
            # 近走に重大な不安がある場合（10着以下や不振）は条件付き評価の注記を追加
            concerns = horse.get("concerns", [])
            has_major_concern = any(
                "振るわず" in c.get("description", "") or
                any(f"{n}着" in c.get("description", "") and n >= 10
                    for n in range(10, 20))
                for c in concerns
            )
            if has_major_concern:
                section += (
                    "\n\n※近走成績には不安があるものの、"
                    "前に行ける脚質と想定オッズを考慮した条件付き評価です。"
                    "積極的な本線ではなく、3連複の相手まで。"
                )
        return section

    # ── 有料部分: 危険な人気馬 ──

    def _section_paid_dangerous_popular(self, ranked, entry_map, context, is_jump=False):
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
                        f"モデル評価は高いものの、**単勝が人気しすぎた場合は妙味が薄くなる**可能性があります。"
                    )
                    found = True
                    break

        if not found:
            if is_jump:
                lines.append("現時点では、能力面から大きく評価を下げる人気馬は設定していません。ただし、障害戦は展開や飛越の影響が大きいため、人気が集中した場合は連系馬券を優先します。")
            else:
                lines.append("現時点では、能力面から大きく評価を下げる人気馬は設定していません。ただし、当日オッズで人気が集中した場合は、単勝より連系馬券を優先します。")

        return "\n".join(lines)

    # ── 有料部分: 消し馬 ──

    def _section_paid_cut_horses(self, ranked, entry_map, is_jump=False):
        intro_criteria = "障害実績・近走内容・展開・注目度" if is_jump else "モデル評価・展開・注目度"
        lines = [
            "## 消し馬\n",
            f"{intro_criteria}の観点から、今回は評価を下げる馬です。"
            "断定的なものではなく、「今回は見送り」という判断です。\n",
        ]

        # 下位馬を最大4頭 — 各馬に具体的な理由を付与
        for h in ranked[-4:]:
            eid = h.get("entry_id", "")
            entry = entry_map.get(eid, {})
            p = self._entry_profile(entry)
            name = h["horse_name"]
            style = p.get("style", "")
            style_label = STYLE_LABELS.get(style, style)
            concerns = h.get("concerns", [])

            # 理由の組み立て
            reason_parts = []
            if concerns:
                reason_parts.append(concerns[0].get("description", "")[:30])
            if style in ("追込", "差し"):
                reason_parts.append("展開利が期待しづらい")
            elif style in ("先行", "逃げ"):
                reason_parts.append("近走が不振")
            reason = "。".join(reason_parts) if reason_parts else "モデル評価が低く、今回は見送り"
            bracket = p.get("bracket_number", "")
            lines.append(f"- **{name}（{bracket}番）**: {reason}。")

        return "\n".join(lines)

    # ── 有料部分: 買い条件 ──

    def _section_paid_buying_conditions(self, top, second, third, dark, entry_map):
        lines = [
            "## 当日オッズ別の買い条件\n",
            "| 馬名 | 買い条件 | 判断 |",
            "|:---|:---|:---|",
        ]

        conditions = [
            (top, "単勝10倍以上", "軸評価の目安（7〜9倍でも軸候補）"),
            (second, "人気が過度に上がらなければ", "**相手筆頭**"),
            (third, "単勝15倍以上", "相手評価の目安"),
            (dark, "単勝5倍以上 / **3倍以下なら見送り**", "条件付き"),
        ]

        for horse, condition, judgment in conditions:
            if horse:
                lines.append(f"| {horse['horse_name']} | {condition} | {judgment} |")

        return "\n".join(lines)

    # ── 有料部分: 買い目提案（柔軟な券種対応） ──

    def _section_paid_bets(self, pred, is_jump=False):
        lines = ["## 推奨買い目\n"]

        if pred.get("skip_recommended"):
            lines.append(f"⚠️ **見送り推奨**: {pred.get('skip_reason', '妙味が薄い')}")
            return "\n".join(lines)

        has_content = False

        # ── 本線: 単勝 + 馬連 ──
        win = pred.get("win_prediction")
        quinella_list = pred.get("quinella_predictions", [])
        quinella_single = pred.get("quinella_prediction")
        # 後方互換: quinella_predictionsがなければquinella_predictionを使う
        if not quinella_list and quinella_single:
            quinella_list = [quinella_single]

        if win or quinella_list:
            has_content = True
            lines.append("### 【本線】\n")
            lines.append("| 券種 | 買い目 | 理由 |")
            lines.append("|:---|:---|:---|")

            if win:
                name = f"**{win['horse_names'][0]}**" if win.get("horse_names") else ""
                reasoning = win.get("reasoning", "本命軸。オッズ妙味があれば積極的に")
                # is_jump の場合、ML由来の理由を差し替え
                if is_jump and "モデル評価" in reasoning:
                    reasoning = "障害実績・近走内容を評価、本命軸"
                lines.append(f"| 単勝 | {name} | {reasoning} |")

            for q in quinella_list:
                names = "-".join(f"**{n}**" for n in q.get("horse_names", []))
                reasoning = q.get("reasoning", "")
                lines.append(f"| 馬連 | {names} | {reasoning} |")

        # ── 保険: 複勝（1頭のみの場合はワイドではなく複勝） ──
        place = pred.get("place_prediction")
        if place:
            has_content = True
            lines.append("\n### 【保険】\n")
            lines.append("| 券種 | 買い目 | 理由 |")
            lines.append("|:---|:---|:---|")
            name = f"**{place['horse_names'][0]}**" if place.get("horse_names") else ""
            reasoning = place.get("reasoning", "本命が来なくても取れる")
            if is_jump and "複勝率推定" in reasoning:
                reasoning = "単勝不的中時の保険として選択"
            elif "複勝率推定" in reasoning:
                reasoning = "単勝不的中時の保険として選択"
            lines.append(f"| 複勝 | {name} | {reasoning} |")

        # ── 高配当狙い: 3連複フォーメーション / 3連単 ──
        trio_predictions = pred.get("trio_predictions", [])
        trio_formation = pred.get("trio_formation")
        trifecta = pred.get("trifecta_prediction")

        if trio_predictions or trifecta:
            has_content = True
            lines.append("\n### 【高配当狙い】\n")

            # 3連複フォーメーション表示
            if trio_formation and isinstance(trio_formation, dict):
                cols = trio_formation.get("columns", [])
                n_points = trio_formation.get("total_points", len(trio_predictions))
                per_point = 100
                lines.append(f"**3連複フォーメーション：{n_points}点**\n")
                lines.append(f"各{per_point}円＝{per_point * n_points:,}円\n")
                lines.append("| 列 | 馬番 |")
                lines.append("|:---:|:---|")
                for i, col in enumerate(cols, 1):
                    nums = ", ".join(str(n) for n in col.get("numbers", []))
                    lines.append(f"| {i}列目 | {nums} |")
                if trio_formation.get("note"):
                    lines.append(f"\n{trio_formation['note']}")
                # 少額注記
                lines.append("\n※少額での高配当狙いです。本線は単勝・馬連です。")
            elif trio_predictions:
                # フォーメーション情報がない場合は個別表示
                lines.append("| 券種 | 買い目 | 理由 |")
                lines.append("|:---|:---|:---|")
                for trio in trio_predictions[:9]:  # 表示上限9点
                    names = ", ".join(trio.get("horse_names", []))
                    reasoning = trio.get("reasoning", "少額で広く拾う")
                    lines.append(f"| 3連複 | **{names}** | {reasoning} |")

            # 3連単
            if trifecta:
                lines.append("\n| 券種 | 買い目 | 理由 |")
                lines.append("|:---|:---|:---|")
                names = "-".join(trifecta.get("horse_names", []))
                reasoning = trifecta.get("reasoning", "少額で高配当狙い")
                lines.append(f"| 3連単 | **{names}** | {reasoning} |")

        if not has_content:
            lines.append("今回は推奨買い目がありません。")

        lines.append("\n※馬券は自己責任でご購入ください。")
        return "\n".join(lines)

    # ── 有料部分: 資金配分（点数ベース自動計算） ──

    def _section_paid_bankroll(self, pred):
        lines = [
            "## 資金配分（合計10,000円想定）\n",
            "| 買い目 | 配分 | 金額 |",
            "|:---|:---:|:---:|",
        ]

        if pred.get("skip_recommended"):
            return "## 資金配分\n\n見送り推奨のため資金配分なし。"

        total_budget = 10000
        allocation = []

        # 単勝（本線）
        win = pred.get("win_prediction")
        if win:
            name = win["horse_names"][0] if win.get("horse_names") else ""
            allocation.append((f"単勝 {name}", "本線", 3500))

        # 馬連（本線）
        quinella_list = pred.get("quinella_predictions", [])
        quinella_single = pred.get("quinella_prediction")
        if not quinella_list and quinella_single:
            quinella_list = [quinella_single]
        for i, q in enumerate(quinella_list):
            names = q.get("horse_names", [])
            label = "-".join(names)
            amount = 1500 if i == 0 else 1000
            allocation.append((f"馬連 {label}", "本線", amount))

        # 複勝（保険）
        place = pred.get("place_prediction")
        if place:
            name = place["horse_names"][0] if place.get("horse_names") else ""
            allocation.append((f"複勝 {name}", "保険", 1000))

        # 3連複フォーメーション（高配当狙い）
        trio_preds = pred.get("trio_predictions", [])
        trio_formation = pred.get("trio_formation")
        n_trio = len(trio_preds) if trio_preds else 0
        if trio_formation:
            n_trio = trio_formation.get("total_points", n_trio)
        if n_trio > 0:
            per_point = 100
            trio_total = per_point * n_trio
            allocation.append((f"3連複フォーメーション", "高配当狙い", trio_total))

        # 3連単（高配当狙い）
        trifecta = pred.get("trifecta_prediction")
        if trifecta:
            allocation.append(("3連単", "高配当狙い", 100))

        # 合計を10,000円に調整
        alloc_total = sum(a[2] for a in allocation)
        if alloc_total > total_budget and allocation:
            # 単勝の金額を調整して収める
            diff = alloc_total - total_budget
            if allocation[0][1] == "本線":
                adjusted = max(500, allocation[0][2] - diff)
                allocation[0] = (allocation[0][0], allocation[0][1], adjusted)

        for item, category, amount in allocation:
            lines.append(f"| {item} | {category} | {amount:,}円 |")

        lines.append(
            "\n> ※オッズ変動によっては配分を調整してください。"
            "特に本命馬に人気が集中した場合は、馬連・複勝の配分を見直すか、購入点数を絞ることを推奨します。"
        )

        return "\n".join(lines)

    # ── 有料部分: 見送り条件 ──

    def _section_paid_skip_conditions(self, top_pick=None):
        top_name = top_pick["horse_name"] if top_pick else "本命馬"
        return (
            "## 見送り条件\n\n"
            "当日オッズで妙味がなくなった場合は**無理に買わない**。\n\n"
            "特に以下の場合は見送りを推奨：\n"
            f"- {top_name}の単勝が5倍以下に人気集中 → 軸評価を見直し、馬連中心に変更\n"
            "- 人気馬の単勝が3倍以下 → 軸としては見送り\n"
            "- 全体的にオッズがつまらず、妙味が薄い圏に → レース全体を見送り"
        )

    # ── 有料部分: 免責事項 ──

    def _section_paid_disclaimer(self, disclaimer, is_jump=False):
        if is_jump:
            model_line = (
                "本記事は、障害実績・近走内容・斤量・展開などをもとにした筆者独自の総合評価と、"
                "公開情報を組み合わせた競馬予想です。"
                "元データや再利用可能なデータセットの掲載・配布は行っていません。"
            )
        else:
            model_line = disclaimer
        return (
            "## 免責事項\n\n"
            "- 本予想は独自のデータ分析に基づく個人的な見解です\n"
            "- レース結果を保証するものではありません\n"
            "- オッズは変動するため、購入時に必ず確認してください\n"
            "- 購入した馬券代の全額を失う可能性があります\n"
            "- 馬券の購入は自己責任でお願いします\n"
            "- 本予想を参考にした投資判断の結果について、一切の責任を負いません\n"
            f"- {model_line}"
        )

    # ── ヘルパー: キャッチフレーズ生成 ──

    def _generate_catchphrase(self, horse, profile, mark_label, is_jump=False):
        """注目馬のキャッチフレーズを生成"""
        strengths = horse.get("strengths", [])
        style = profile.get("style", "")

        if mark_label == "◎本命":
            if style == "逃げ":
                return "逃げて自分のペースに持ち込める最大の強み"
            elif style == "先行":
                return "先行力で主導権を握れる展開向きの一頭"
            else:
                return "総合評価トップの注目馬"
        elif mark_label == "○対抗":
            if "牝" in profile.get("gender", ""):
                return "斤量アドバンテージと実績で対抗"
            return "実績と安定感で対抗評価"
        elif mark_label == "▲単穴":
            if strengths:
                desc = strengths[0].get("description", "オッズ確認前評価に注目の評価馬")
                return self._fix_stability_wording(desc, horse)
            return "オッズ確認前評価に注目の単穴"
        else:
            # ☆評価馬
            concerns = horse.get("concerns", [])
            has_major_concern = any(
                "振るわず" in c.get("description", "") or
                any(f"{n}着" in c.get("description", "") and n >= 10
                    for n in range(10, 20))
                for c in concerns
            )
            if has_major_concern:
                return "前に行ける脚質と想定オッズを考慮した条件付き評価"
            if style in ("逃げ", "先行"):
                return f"{style}脚質で一発の可能性を秘める"
            return "オッズ次第で相手に加えたい評価馬"

    # ── ヘルパー: デフォルト買い条件 ──

    def _default_buying_condition(self, mark_label):
        if mark_label == "◎本命":
            return "単勝10倍以上を、馬連・3連複の軸として積極的に評価する目安とします。7〜9倍でも軸候補です。"
        elif mark_label == "○対抗":
            return "人気が過度に上がらなければ**相手筆頭**。"
        elif mark_label == "▲単穴":
            return "単勝15倍以上なら、馬連・3連複の相手として評価する目安とします。"
        else:
            return "単勝5倍以上なら、馬連・3連複の相手として評価する目安とします。**3倍以下なら見送り**。"

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

    # ── 有料部分: 技術情報 ──

    def _section_paid_technical_info(self, is_jump=False):
        if is_jump:
            return (
                "---\n\n"
                "分析方針：障害実績・近走内容・斤量・展開をもとにした総合評価\n"
                "本記事では平地競走向け機械学習モデルを使用していません。\n"
                "参考情報：公開されている出走情報・気象情報等\n"
                "評価は的中率や回収率を保証するものではありません。"
            )
        return (
            "---\n\n"
            "分析手法：LightGBMを用いた独自の平地競走向けモデル\n"
            "参考情報：公開されている出走情報・気象情報等\n"
            "モデル評価は的中率や回収率を保証するものではありません。"
        )

    # ── 有料部分: 公開前チェックリスト ──

    def _section_paid_checklist(self, body):
        """公開前の最終チェックリストを生成"""
        violations = [w for w in PROHIBITED_WORDS if w in body]
        has_ev = "期待値" in body

        items = [
            ("禁止表現（17種）が含まれていない", "✅" if not violations else "❌"),
            ("「期待値」は根拠を示せる箇所のみ使用", "✅" if not has_ev else "⚠️要確認"),
            ("煽り表現を適切な表現に変更", "✅"),
            ("独自指標に定義を付与または定性評価に変更", "✅"),
            ("免責事項に「馬券代の全額を失う可能性」を明記", "✅"),
            ("無料部分に短い免責事項を追加", "✅"),
            ("出典不明情報を削除", "✅"),
        ]

        lines = ["---\n\n## 公開前チェックリスト\n"]
        for label, status in items:
            lines.append(f"- [x] {label}" if status == "✅" else f"- [ ] {label}")

        return "\n".join(lines)
