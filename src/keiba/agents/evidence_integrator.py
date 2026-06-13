"""エージェント7: 根拠統合"""

from datetime import datetime

from keiba.agents.base import BaseAgent
from keiba.models.pipeline import PipelineContext


class EvidenceIntegrator(BaseAgent):
    """Python分析結果とWeb調査結果を統合するエージェント"""

    MAX_WEB_ADJUSTMENT = 0.15  # Web証拠による確率調整の上限

    def validate_input(self, context: PipelineContext) -> bool:
        return context.analysis is not None and context.web_research is not None

    def process(self, context: PipelineContext) -> PipelineContext:
        probabilities = context.analysis.get("probabilities", [])
        horse_intel = {
            h["horse_id"]: h for h in context.web_research.get("horse_intel", [])
        }
        entries = (context.current_race_data or {}).get("entries", [])

        # entry_id → horse_id マッピング
        entry_to_horse = {}
        for e in entries:
            eid = e.get("entry_id", "")
            hid = e.get("horse", {}).get("horse_id", "")
            entry_to_horse[eid] = hid

        horses_evidence = []
        for prob in probabilities:
            entry_id = prob["entry_id"]
            horse_id = entry_to_horse.get(entry_id, "")
            intel = horse_intel.get(horse_id, {})
            horse_name = prob["horse_name"]

            strengths, weaknesses, concerns = self._extract_evidence(prob, intel)

            # Web証拠に基づく確率調整
            adjustment = self._compute_web_adjustment(intel)
            adjusted_win = max(0.01, min(0.99, prob["win_probability"] + adjustment))
            adjusted_place = max(0.05, min(0.99, prob["place_probability"] + adjustment * 0.5))

            # グレード判定
            grade = self._assign_grade(adjusted_win, strengths, weaknesses, concerns)

            # 総合評価テキスト
            assessment = self._write_assessment(horse_name, strengths, weaknesses, concerns)

            horses_evidence.append({
                "entry_id": entry_id,
                "horse_name": horse_name,
                "strengths": [s.model_dump() if hasattr(s, "model_dump") else s for s in strengths],
                "weaknesses": [w.model_dump() if hasattr(w, "model_dump") else w for w in weaknesses],
                "concerns": [c.model_dump() if hasattr(c, "model_dump") else c for c in concerns],
                "overall_assessment": assessment,
                "integrated_probability": round(adjusted_win, 4),
                "integrated_place_probability": round(adjusted_place, 4),
                "evidence_grade": grade,
                "web_adjustment": round(adjustment, 4),
            })

        context.evidence = {
            "race_id": context.race_id,
            "integrated_at": datetime.now().isoformat(),
            "horses": horses_evidence,
            "race_narrative": self._write_race_narrative(horses_evidence),
        }

        # ML予測のブレンド
        self._blend_ml_predictions(context, horses_evidence)

        self.logger.info(f"Integrated evidence for {len(horses_evidence)} horses")
        return context

    def _blend_ml_predictions(self, context: PipelineContext, horses_evidence: list[dict]) -> None:
        """ML予測とルールベース確率をブレンド（CodeWorks Parisの研究に基づく）。"""
        if not context.ml_analysis or not context.ml_analysis.get("probabilities"):
            return

        ml_probs = {
            p["entry_id"]: p["win_probability"]
            for p in context.ml_analysis["probabilities"]
        }
        ml_confidence = context.ml_analysis.get("model_confidence", 0)
        # モデル信頼度が高い場合はMLを重用、低い場合は控えめに
        ml_weight = 0.6 if ml_confidence > 0.6 else 0.3

        for he in horses_evidence:
            rule_prob = he["integrated_probability"]
            ml_prob = ml_probs.get(he["entry_id"], rule_prob)
            blended = rule_prob * (1 - ml_weight) + ml_prob * ml_weight
            he["integrated_probability"] = round(blended, 4)
            he["ml_contribution"] = round(ml_prob * ml_weight, 4)

        # 再正規化（確率の和を1に）
        total = sum(h["integrated_probability"] for h in horses_evidence)
        if total > 0:
            for h in horses_evidence:
                h["integrated_probability"] = round(h["integrated_probability"] / total, 4)

    def _extract_evidence(self, prob: dict, intel: dict) -> tuple:
        strengths, weaknesses, concerns = [], [], []

        # 統計根拠
        score = prob.get("composite_score", 50)
        rank = prob.get("rank_by_model", 5)
        if rank <= 2:
            strengths.append({"category": "model_ranking", "type": "strength", "description": f"モデル評価{rank}位（スコア{score:.1f}）", "confidence": 0.7, "source": "statistical"})
        if prob.get("win_probability", 0) > 0.15:
            strengths.append({"category": "win_probability", "type": "strength", "description": f"勝率推定{prob['win_probability']:.1%}", "confidence": 0.6, "source": "statistical"})

        # Web証拠
        for factor in intel.get("notable_factors", []):
            if any(w in factor for w in ["好調", "好時計", "勢い", "一流", "実績"]):
                strengths.append({"category": "web_info", "type": "strength", "description": factor, "confidence": 0.5, "source": "web_research"})
            elif any(w in factor for w in ["不安", "注意", "減少", "不足", "物足りない"]):
                concerns.append({"category": "web_info", "type": "concern", "description": factor, "confidence": 0.5, "source": "web_research"})
            else:
                weaknesses.append({"category": "web_info", "type": "weakness", "description": factor, "confidence": 0.4, "source": "web_research"})

        # トレーニングレポート
        for report in intel.get("training_reports", []):
            if any(w in report for w in ["好", "良好", "軽快", "改善", "上昇"]):
                strengths.append({"category": "training", "type": "strength", "description": f"調教: {report}", "confidence": 0.5, "source": "web_research"})
            elif any(w in report for w in ["普通", "軽め"]):
                weaknesses.append({"category": "training", "type": "weakness", "description": f"調教: {report}", "confidence": 0.4, "source": "web_research"})
            elif any(w in report for w in ["低下", "下降", "注意"]):
                concerns.append({"category": "training", "type": "concern", "description": f"調教: {report}", "confidence": 0.5, "source": "web_research"})

        # form_trend（調教推定由来）
        trend = intel.get("form_trend", "stable")
        if trend == "improving":
            strengths.append({"category": "form_trend", "type": "strength", "description": "近走高调入着傾向", "confidence": 0.6, "source": "web_research"})
        elif trend == "declining":
            concerns.append({"category": "form_trend", "type": "concern", "description": "近走成績下降傾向", "confidence": 0.6, "source": "web_research"})

        impact = intel.get("impact_on_prediction", "neutral")
        if impact == "positive":
            strengths.append({"category": "overall_web", "type": "strength", "description": "Web情報全体としてポジティブ", "confidence": 0.5, "source": "web_research"})
        elif impact == "negative":
            concerns.append({"category": "overall_web", "type": "concern", "description": "Web情報に懸念要素あり", "confidence": 0.6, "source": "web_research"})

        return strengths, weaknesses, concerns

    def _compute_web_adjustment(self, intel: dict) -> float:
        impact = intel.get("impact_on_prediction", "neutral")
        reliability = intel.get("reliability", "medium")
        rel_mult = {"high": 1.0, "medium": 0.6, "low": 0.3}.get(reliability, 0.5)
        adjustment = 0.0

        if impact == "positive":
            adjustment = self.MAX_WEB_ADJUSTMENT * rel_mult
        elif impact == "negative":
            adjustment = -self.MAX_WEB_ADJUSTMENT * rel_mult

        # fitness_score による微調整
        fitness = intel.get("fitness_score", 0.5)
        if fitness > 0.7:
            adjustment += 0.05 * rel_mult
        elif fitness < 0.3:
            adjustment -= 0.05 * rel_mult

        return max(-self.MAX_WEB_ADJUSTMENT, min(self.MAX_WEB_ADJUSTMENT, adjustment))

    def _assign_grade(self, win_prob: float, strengths, weaknesses, concerns) -> str:
        n_strengths = len(strengths)
        n_concerns = len(concerns)
        if win_prob > 0.20 and n_strengths >= 3 and n_concerns == 0:
            return "S"
        elif win_prob > 0.10 and n_strengths >= 2 and n_concerns <= 1:
            return "A"
        elif win_prob > 0.05 and n_concerns <= 2:
            return "B"
        return "C"

    def _write_assessment(self, name: str, strengths, weaknesses, concerns) -> str:
        parts = [f"{name}について"]
        if strengths:
            parts.append(f"強み: {', '.join(s['description'] for s in strengths[:3])}")
        if weaknesses:
            parts.append(f"留意点: {', '.join(w['description'] for w in weaknesses[:2])}")
        if concerns:
            parts.append(f"懸念: {', '.join(c['description'] for c in concerns[:2])}")
        return "。".join(parts)

    def _write_race_narrative(self, horses: list[dict]) -> str:
        top3 = sorted(horses, key=lambda h: h["integrated_probability"], reverse=True)[:3]
        names = [h["horse_name"] for h in top3]
        return f"レース概観: {', '.join(names)}の上位対決が想定される。データ分析とWeb調査の双方から根拠を確認できている。"
