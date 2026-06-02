"""エージェント14: 品質保証"""

from datetime import datetime

from keiba.agents.base import BaseAgent
from keiba.models.pipeline import PipelineContext

PROHIBITED_WORDS = ["絶対", "確定", "鉄板", "必ず儲かる", "回収保証", "100%", "間違いなく", "間違いない", "これだけ買えば勝てる"]


class QualityAssurance(BaseAgent):
    """全成果物を120点満点で採点するエージェント"""

    def validate_input(self, context: PipelineContext) -> bool:
        return context.prediction_actual is not None and context.note_article is not None

    def process(self, context: PipelineContext) -> PipelineContext:
        criteria = []

        # 1. データ鮮度 (15点)
        score, note = self._check_data_freshness(context)
        criteria.append(self._criterion("データ鮮度", 15, score, note))

        # 2. データ欠損チェック (10点)
        score, note = self._check_data_completeness(context)
        criteria.append(self._criterion("データ欠損チェック", 10, score, note))

        # 3. 分析根拠の明確さ (15点)
        score, note = self._check_analysis_clarity(context)
        criteria.append(self._criterion("分析根拠の明確さ", 15, score, note))

        # 4. Web調査の信頼性 (10点)
        score, note = self._check_web_reliability(context)
        criteria.append(self._criterion("Web調査の信頼性", 10, score, note))

        # 5. オッズ期待値 (15点)
        score, note = self._check_odds_evaluation(context)
        criteria.append(self._criterion("オッズ期待値", 15, score, note))

        # 6. バックテスト結果 (15点)
        score, note = self._check_backtest(context)
        criteria.append(self._criterion("バックテスト結果", 15, score, note))

        # 7. 券種別予想の妥当性 (10点)
        score, note = self._check_prediction_validity(context)
        criteria.append(self._criterion("券種別予想の妥当性", 10, score, note))

        # 8. Noteの読みやすさ (10点)
        score, note = self._check_note_readability(context)
        criteria.append(self._criterion("Noteの読みやすさ", 10, score, note))

        # 9. 誇大表現の排除 (10点)
        score, note = self._check_prohibited_words(context)
        criteria.append(self._criterion("誇大表現の排除", 10, score, note))

        # 10. リスク説明 (10点)
        score, note = self._check_risk_disclosure(context)
        criteria.append(self._criterion("リスク説明", 10, score, note))

        total = sum(c["actual_score"] for c in criteria)
        passed = total >= 100

        route_back = None
        if not passed:
            route_back = self._determine_route_back(criteria)

        context.qa_report = {
            "target_agent": "all",
            "race_id": context.race_id,
            "evaluated_at": datetime.now().isoformat(),
            "total_score": total,
            "passed": passed,
            "criteria": criteria,
            "overall_feedback": self._generate_feedback(total, criteria),
            "route_back_to": route_back,
            "retry_count": len([r for r in context.agent_results if r.get("agent_name") == "QualityAssurance"]),
        }
        self.logger.info(f"QA Score: {total}/120, passed={passed}" + (f", route_back={route_back}" if route_back else ""))
        return context

    def _criterion(self, name: str, max_score: int, actual: int, notes: str) -> dict:
        return {
            "criterion_name": name,
            "max_score": max_score,
            "actual_score": min(actual, max_score),
            "passed": actual >= max_score * 0.7,
            "notes": notes,
        }

    def _check_data_freshness(self, ctx) -> tuple[int, str]:
        qc = ctx.quality_check or {}
        score = qc.get("completeness_score", 0)
        if score >= 0.95:
            return 15, "データ鮮度良好"
        elif score >= 0.8:
            return 10, f"データ鮮度やや不足 (completeness={score:.0%})"
        return 5, f"データ鮮度に問題あり (completeness={score:.0%})"

    def _check_data_completeness(self, ctx) -> tuple[int, str]:
        issues = (ctx.quality_check or {}).get("issues", [])
        critical = [i for i in issues if i.get("severity") == "critical"]
        if not critical:
            return 10, "欠損なし"
        return 4, f"critical問題{len(critical)}件あり"

    def _check_analysis_clarity(self, ctx) -> tuple[int, str]:
        analysis = ctx.analysis or {}
        probs = analysis.get("probabilities", [])
        factors = analysis.get("key_factors", [])
        if len(probs) >= 8 and len(factors) >= 1:
            return 15, "分析根拠十分"
        elif len(probs) >= 5:
            return 10, "分析根拠はあるが不十分"
        return 5, "分析根拠が弱い"

    def _check_web_reliability(self, ctx) -> tuple[int, str]:
        wr = ctx.web_research or {}
        intel = wr.get("horse_intel", [])
        covered = len(intel)
        total = (ctx.features or {}).get("field_size", 0)
        if covered >= total * 0.8:
            return 10, f"Web調査カバレッジ{covered}/{total}"
        elif covered >= total * 0.5:
            return 7, f"Web調査カバレッジ{covered}/{total}、やや不足"
        return 4, "Web調査が不十分"

    def _check_odds_evaluation(self, ctx) -> tuple[int, str]:
        ae = ctx.actual_odds_eval or {}
        pe = ctx.predicted_odds_eval or {}
        if ae.get("evaluations") and pe.get("evaluations"):
            return 15, "予想オッズ・実オッズ双方の評価あり"
        elif ae.get("evaluations") or pe.get("evaluations"):
            return 10, "いずれかのオッズ評価あり"
        return 5, "オッズ評価が不足"

    def _check_backtest(self, ctx) -> tuple[int, str]:
        bt = ctx.backtest or {}
        races = bt.get("total_races", 0)
        if races >= 15:
            return 15, f"バックテスト{races}レース実施"
        elif races >= 5:
            return 10, f"バックテスト{races}レース（やや不足）"
        return 5, "バックテストデータ不足"

    def _check_prediction_validity(self, ctx) -> tuple[int, str]:
        pred = ctx.prediction_actual or {}
        n_bets = sum(1 for k in ["win_prediction", "place_prediction", "quinella_prediction", "trifecta_prediction"] if pred.get(k))
        if pred.get("skip_recommended"):
            return 10, "見送り判定が適切に出されている"
        elif 1 <= n_bets <= 4:
            return 8, f"{n_bets}券種の予想あり"
        elif n_bets > 4:
            return 5, "買い目が多すぎる"
        return 3, "予想が不十分"

    def _check_note_readability(self, ctx) -> tuple[int, str]:
        note = ctx.note_article or {}
        wc = note.get("word_count", 0)
        sections = len(note.get("structure_used", []))
        if wc > 500 and sections >= 5:
            return 10, f"記事{wc}文字・{sections}セクション"
        elif wc > 200:
            return 7, f"記事{wc}文字（やや短い）"
        return 4, "記事が不十分"

    def _check_prohibited_words(self, ctx) -> tuple[int, str]:
        note = ctx.note_article or {}
        violations = note.get("prohibited_word_violations", [])
        if not violations:
            return 10, "禁止表現なし"
        return 0, f"禁止表現検出: {', '.join(violations)}"

    def _check_risk_disclosure(self, ctx) -> tuple[int, str]:
        note = ctx.note_article or {}
        body = note.get("body_markdown", "")
        risk_markers = ["自己責任", "免責", "保証するものではありません", "リスク"]
        found = sum(1 for m in risk_markers if m in body)
        if found >= 3:
            return 10, f"リスク説明十分（{found}箇所）"
        elif found >= 1:
            return 6, f"リスク説明あり（{found}箇所）"
        return 2, "リスク説明不足"

    def _determine_route_back(self, criteria: list[dict]) -> str:
        failed = [c for c in criteria if not c["passed"]]
        if not failed:
            return None
        worst = min(failed, key=lambda c: c["actual_score"] / max(c["max_score"], 1))
        name = worst["criterion_name"]
        routing = {
            "データ鮮度": "historical_data_manager",
            "データ欠損チェック": "data_quality_checker",
            "分析根拠の明確さ": "python_analyzer",
            "Web調査の信頼性": "web_researcher",
            "オッズ期待値": "actual_odds_evaluator",
            "バックテスト結果": "backtester",
            "券種別予想の妥当性": "prediction_generator",
            "Noteの読みやすさ": "note_writer",
            "誇大表現の排除": "note_writer",
            "リスク説明": "note_writer",
        }
        return routing.get(name, "python_analyzer")

    def _generate_feedback(self, total: int, criteria: list[dict]) -> str:
        passed_count = sum(1 for c in criteria if c["passed"])
        failed_names = [c["criterion_name"] for c in criteria if not c["passed"]]
        if total >= 100:
            return f"品質チェック通過（{total}/120点、{passed_count}/10項目合格）"
        return f"品質チェック未達（{total}/120点）。要改善: {', '.join(failed_names)}"
