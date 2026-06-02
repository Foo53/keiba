"""設定ローダー"""

from pathlib import Path
from typing import Any

import yaml

from keiba.models.base import KeibaBaseModel


class AppConfig(KeibaBaseModel):
    pipeline: dict[str, Any]
    data_source: dict[str, Any]
    logging: dict[str, Any]
    output: dict[str, Any]
    analysis: dict[str, Any]
    odds: dict[str, Any]
    quality: dict[str, Any]
    note: dict[str, Any]


def load_config(config_path: str | None = None) -> AppConfig:
    """YAMLから設定を読み込む"""
    defaults = Path(__file__).parent.parent.parent.parent / "config" / "default.yaml"
    path = Path(config_path) if config_path else defaults
    with open(path) as f:
        raw = yaml.safe_load(f)
    return AppConfig(**raw)
