"""エージェント3: データ品質チェック"""

from keiba.agents.base import BaseAgent
from keiba.models.pipeline import PipelineContext


class DataQualityChecker(BaseAgent):
    """取得データの欠損・異常を検出するエージェント"""

    def validate_input(self, context: PipelineContext) -> bool:
        return context.historical_data is not None and context.current_race_data is not None

    def process(self, context: PipelineContext) -> PipelineContext:
        issues = []
        anomalies = []

        entries = context.current_race_data.get("entries", [])
        historical = context.historical_data or {}
        past_perfs = historical.get("past_performances", {})

        # 出走馬ごとのチェック
        for entry in entries:
            horse_id = entry.get("horse", {}).get("horse_id", "")
            horse_name = entry.get("horse", {}).get("horse_name", "不明")

            # 過去成績の数
            pp_list = past_perfs.get(horse_id, [])
            if len(pp_list) < 3:
                issues.append({
                    "severity": "warning",
                    "horse": horse_name,
                    "type": "insufficient_past_performances",
                    "detail": f"過去成績が{len(pp_list)}走のみ（推奨3走以上）",
                })

            # 馬体重の大幅変動
            weight_change = entry.get("weight_change")
            if weight_change is not None and abs(weight_change) >= 10:
                anomalies.append({
                    "severity": "warning",
                    "horse": horse_name,
                    "type": "large_weight_change",
                    "detail": f"馬体重変動 {weight_change:+.0f}kg",
                })

            # 騎手・厩舎情報の有無
            if not entry.get("jockey"):
                issues.append({
                    "severity": "critical",
                    "horse": horse_name,
                    "type": "missing_jockey",
                    "detail": "騎手情報が未取得",
                })

        # レース基本情報チェック
        race = context.current_race_data.get("race", {})
        if not race.get("track_condition"):
            issues.append({
                "severity": "info",
                "horse": "-",
                "type": "track_condition_unavailable",
                "detail": "馬場状態が未確定",
            })

        # 完成度スコア計算
        total_checks = len(entries) * 3 + 1  # 馬ごと3項目 + レース1項目
        passed_checks = total_checks - len(issues) - len(anomalies)
        completeness_score = passed_checks / max(total_checks, 1)

        # critical問題がなければpassed
        has_critical = any(i["severity"] == "critical" for i in issues)

        context.quality_check = {
            "passed": not has_critical,
            "issues": issues,
            "anomalies": anomalies,
            "completeness_score": round(completeness_score, 3),
            "total_entries": len(entries),
        }
        self.logger.info(
            f"Quality check: passed={not has_critical}, "
            f"issues={len(issues)}, anomalies={len(anomalies)}, "
            f"completeness={completeness_score:.2%}"
        )
        return context
