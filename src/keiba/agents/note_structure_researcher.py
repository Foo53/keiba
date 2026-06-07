"""エージェント14: Note構成調査

人気競馬Note記事の共通パターンに基づき、無料/有料境界付きの最適な構成を提案する。
JRA-VAN DataLab利用規約に準拠（生データ・再配布可能な集計表は掲載しない）。
"""

from keiba.agents.base import BaseAgent
from keiba.models.note import PROHIBITED_WORDS, JRAVAN_ATTRIBUTION
from keiba.models.pipeline import PipelineContext


class NoteStructureResearcher(BaseAgent):
    """競馬Noteの構成を調査・提案するエージェント"""

    def validate_input(self, context: PipelineContext) -> bool:
        return context.current_race_data is not None

    def process(self, context: PipelineContext) -> PipelineContext:
        race = (context.current_race_data or {}).get("race", {})
        race_name = race.get("race_name", "重賞レース")
        grade = race.get("grade", "GI")
        race_date = race.get("race_date", "")
        year = race_date[:4] if race_date else ""

        context.note_suggestion = {
            "suggested_title": f"【{race_name}{year}】JRA-VANデータ×機械学習で導いた期待値◎｜危険な人気馬と勝負買い目",
            "structure": [
                # 無料部分
                "この記事で分かること（テイザー）",
                "レース概要",
                "今年のレースの見立て（展開予想）",
                "モデルの考え方（JRA-VAN安全化済み）",
                "有料部分で公開する内容（ティザー）",
                # 有料部分
                "最終結論（印一覧）",
                "モデル評価ランキング（S/A/B評価＋妙味ランク）",
                "◎本命（強み・懸念・買い条件）",
                "○対抗（強み・懸念・買い条件）",
                "▲単穴（強み・懸念・買い条件）",
                "☆評価馬（強み・懸念・買い条件・人気注意）",
                "危険な人気馬",
                "消し馬",
                "当日オッズ別の買い条件",
                "推奨買い目（本線・保険・高配当狙いの3段階）",
                "資金配分",
                "見送り条件",
                "免責事項",
            ],
            "tone": "reader_friendly_actionable",
            "successful_patterns": [
                "読者が馬券を買いやすい構成にする",
                "無料部分で具体馬名を出しすぎない",
                "期待値とオッズ条件で買い/見送りを明示する",
                "断定せず、条件付き判断を重視する",
                "JRA-VANの元データや集計表は掲載しない",
                "資金配分を具体的に示す",
            ],
            "ng_expressions": PROHIBITED_WORDS,
            "recommended_expressions": [
                "データからは〇〇の可能性が示唆されています",
                "期待値の観点からは〇〇と考えられます",
                "〇〇の条件なら買い",
                "今回は評価を下げる",
                "オッズ妙味に注目",
                "人気過熱に注意",
            ],
            "jravan_disclaimer": (
                "本記事は、JRA-VAN Data Labを用いて取得した過去データをもとに、"
                "筆者が独自に加工・学習・検証した機械学習モデルの出力を参考にした予想です。"
                "記事内では元データや再利用可能な集計表は掲載せず、独自の予測結果と見解のみを掲載します。"
            ),
        }
        self.logger.info(f"Note structure suggested for {race_name}")
        return context
