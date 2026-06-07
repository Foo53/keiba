"""Note記事モデル"""

from typing import Optional

from keiba.models.base import KeibaBaseModel

# ── 共通禁止表現リスト（景品表示法・消費者契約法に基づく） ──
# NoteStructureResearcher / NoteWriter / QualityAssurance で共有
PROHIBITED_WORDS: list[str] = [
    # 断定的表現（景品表示法違反リスク）
    "絶対", "確定", "鉄板", "確実", "必勝",
    # 収益保証表現
    "必ず儲かる", "回収保証", "100%", "稼げる", "儲かる",
    # 射幸心を煽る表現
    "必ず当たる", "間違いなく", "間違いない",
    "これだけ買えば勝てる", "負けない", "ノーリスク", "安全",
]

# JRA-VAN DataLab 利用規約に基づく出典表記
JRAVAN_ATTRIBUTION = "出典: JRA-VAN DataLab（TARGET frontier JV）"


class NoteSuggestion(KeibaBaseModel):
    suggested_title: str
    structure: list[str]
    tone: str
    successful_patterns: list[str]
    ng_expressions: list[str] = PROHIBITED_WORDS
    recommended_expressions: list[str] = []
    jravan_data_used: bool = False  # JRA-VANデータを使用しているか


class NoteArticle(KeibaBaseModel):
    race_id: str
    race_name: str
    title: str
    structure_used: list[str]
    body_markdown: str
    summary_box: str
    key_prediction: str
    risk_warning: str
    word_count: int
    prohibited_word_violations: list[str] = []
    data_sources: Optional[str] = None  # JRA-VAN等の出典情報
