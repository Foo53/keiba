"""構造化ログユーティリティ"""

import json
import logging
from datetime import datetime
from pathlib import Path


class StructuredFormatter(logging.Formatter):
    """JSON構造化ログフォーマッタ"""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "level": record.levelname,
            "agent": getattr(record, "agent_name", "system"),
            "race_id": getattr(record, "race_id", ""),
            "pipeline_id": getattr(record, "pipeline_id", ""),
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = str(record.exc_info[1])
        return json.dumps(log_entry, ensure_ascii=False)


def get_agent_logger(agent_name: str) -> logging.Logger:
    """エージェント専用ロガーを取得（親ロガーに伝播のみ、ハンドラは追加しない）"""
    logger = logging.getLogger(f"keiba.{agent_name}")
    logger.setLevel(logging.DEBUG)
    # propagate=True のまま、ハンドラは親(keiba)にだけ持たせる
    return logger


def setup_logging(config: dict) -> None:
    """設定に基づいてロギングを初期化"""
    root = logging.getLogger("keiba")
    level_name = config.get("level", "INFO")
    root.setLevel(getattr(logging, level_name))

    # コンソールハンドラ（親にだけ1つ追加）
    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler) for h in root.handlers):
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter(
            "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
        ))
        root.addHandler(console)

    # ファイルハンドラ（JSONL）
    if config.get("per_agent_files"):
        log_dir = Path(config.get("log_dir", "output/logs"))
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_dir / "pipeline.jsonl", encoding="utf-8")
        file_handler.setFormatter(StructuredFormatter())
        root.addHandler(file_handler)
