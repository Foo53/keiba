"""根拠統合モデル"""

from datetime import datetime

from keiba.models.base import ConfidenceGrade, KeibaBaseModel


class StrengthWeakness(KeibaBaseModel):
    category: str
    type: str  # "strength" | "weakness" | "concern"
    description: str
    confidence: float
    source: str  # "statistical" | "web_research" | "combined"


class HorseEvidence(KeibaBaseModel):
    entry_id: str
    horse_name: str
    strengths: list[StrengthWeakness]
    weaknesses: list[StrengthWeakness]
    concerns: list[StrengthWeakness]
    overall_assessment: str
    integrated_probability: float
    integrated_place_probability: float
    evidence_grade: ConfidenceGrade


class EvidenceProfile(KeibaBaseModel):
    race_id: str
    integrated_at: datetime
    horses: list[HorseEvidence]
    race_narrative: str
