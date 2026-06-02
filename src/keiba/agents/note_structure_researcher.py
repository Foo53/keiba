"""エージェント12: Note構成調査"""

from keiba.agents.base import BaseAgent
from keiba.models.pipeline import PipelineContext


class NoteStructureResearcher(BaseAgent):
    """競馬予想Noteの構成を調査・提案するエージェント"""

    def validate_input(self, context: PipelineContext) -> bool:
        return context.current_race_data is not None

    def process(self, context: PipelineContext) -> PipelineContext:
        race = (context.current_race_data or {}).get("race", {})
        race_name = race.get("race_name", "重賞レース")
        grade = race.get("grade", "GI")

        context.note_suggestion = {
            "suggested_title": f"【{grade}予想】{race_name} データ分析×期待値評価",
            "structure": [
                "導入：レース概要と注目ポイント",
                "出走馬一覧と簡単な見どころ",
                "データ分析結果（スコア・勝率推定）",
                "注目馬ピックアップ（本命・対抗・穴）",
                "期待値評価（予想オッズ vs 実オッズ）",
                "券種別買い目提案",
                "見送り判定とその理由",
                "リスク説明・免責事項",
                "まとめと当日更新チェックリスト",
            ],
            "tone": "analytical_calm",
            "successful_patterns": [
                "データ根拠を具体的に提示する",
                "見送り判断も含めて誠実に書く",
                "読者が自分で判断できる情報を提供する",
                "リスクを明記する",
            ],
            "ng_expressions": [
                "絶対当たる", "確定", "鉄板", "必ず儲かる", "回収保証",
                "これだけ買えば勝てる", "100%", "間違いなく", "間違いない",
            ],
            "recommended_expressions": [
                "データからは〇〇の可能性が示唆されています",
                "期待値の観点からは〇〇と考えられます",
                "あくまで予想であり、実際の結果とは異なる可能性があります",
                "自己責任でのご判断をお願いします",
            ],
        }
        self.logger.info(f"Note structure suggested for {race_name}")
        return context
