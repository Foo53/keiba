"""共通Enum・基底モデル定義"""

from enum import Enum

from pydantic import BaseModel, ConfigDict


class TrackType(str, Enum):
    TURF = "芝"
    DIRT = "ダート"
    OBSTACLE = "障害"


class TrackCondition(str, Enum):
    FIRM = "良"
    GOOD_TO_FIRM = "稍重"
    YIELDING = "重"
    SOFT = "不良"


class Weather(str, Enum):
    SUNNY = "晴"
    CLOUDY = "曇"
    RAIN = "雨"
    SNOW = "雪"


class RaceGrade(str, Enum):
    GI = "GI"
    GII = "GII"
    GIII = "GIII"
    LISTED = "L"


class BetType(str, Enum):
    WIN = "単勝"
    PLACE = "複勝"
    WIDE = "ワイド"
    QUINELLA = "馬連"
    EXACTA = "馬単"
    TRIO = "3連複"
    TRIFECTA = "3連単"


class ConfidenceGrade(str, Enum):
    S = "S"
    A = "A"
    B = "B"
    C = "C"


class RunningStyle(str, Enum):
    FRONT_RUNNER = "逃げ"
    STALKER = "先行"
    MIDPACK = "差し"
    CLOSER = "追込"


class Gender(str, Enum):
    COLT = "牡"
    FILLY = "牝"
    GELDING = "せん"


class KeibaBaseModel(BaseModel):
    model_config = ConfigDict(
        strict=False,
        populate_by_name=True,
        use_enum_values=True,
    )
