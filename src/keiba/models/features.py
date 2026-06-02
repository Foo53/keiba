"""特徴量モデル"""

from datetime import datetime
from typing import Optional

from keiba.models.base import KeibaBaseModel, RunningStyle


class HorseFeatures(KeibaBaseModel):
    """1頭分の特徴量"""
    entry_id: str
    horse_id: str
    # 距離適性
    distance_aptitude_score: float
    optimal_distance_min: int
    optimal_distance_max: int
    # 馬場適性
    track_turf_score: float
    track_dirt_score: float
    course_specific_score: dict
    # 脚質
    primary_style: RunningStyle
    style_consistency: float
    # 上がり
    average_last_3f: Optional[float] = None
    best_last_3f: Optional[float] = None
    closing_speed_rank: Optional[int] = None
    # 近走
    recent_3_runs: list
    recent_5_runs: list
    form_score: float
    # クラス・距離変更
    class_change: Optional[str] = None
    distance_change: Optional[str] = None
    # 馬体重
    weight_carried_change: Optional[float] = None
    horse_weight_trend: Optional[str] = None
    # 騎手・厩舎
    jockey_trainer_win_rate: Optional[float] = None
    jockey_course_win_rate: Optional[float] = None


class FeatureSet(KeibaBaseModel):
    """1レース分の特徴量セット"""
    race_id: str
    generated_at: datetime
    horse_features: list[HorseFeatures]
    field_size: int
