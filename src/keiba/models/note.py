"""Note記事モデル"""

from keiba.models.base import KeibaBaseModel


class NoteSuggestion(KeibaBaseModel):
    suggested_title: str
    structure: list[str]
    tone: str
    successful_patterns: list[str]
    ng_expressions: list[str] = []
    recommended_expressions: list[str] = []


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
