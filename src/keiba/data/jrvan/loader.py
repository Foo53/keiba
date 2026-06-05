"""JRA-VAN CSV → SQLite ローダー

race_horse_detail.csv を SQLite に変換し、インデックスを構築する。
2回目以降は SQLite を直接使用（CSV再読込スキップ）。
"""

import csv
import sqlite3
from pathlib import Path

CSV_DIR = Path("JRA_VAN_DATA")
DB_PATH = Path("data/store/jrvan.db")

# 競馬場コード → コース名
JYO_CODE_MAP = {
    "01": "札幌", "02": "函館", "03": "福島", "04": "新潟",
    "05": "東京", "06": "中山", "07": "中京", "08": "京都",
    "09": "阪神", "10": "小倉",
}

# トラックコード → トラック種別（芝/ダート）
TRACK_CODE_MAP = {
    "10": "芝", "11": "芝", "12": "芝", "13": "芝",
    "20": "ダート", "21": "ダート", "22": "ダート", "23": "ダート",
    "29": "ダート", "51": "障害", "52": "障害", "53": "障害",
    "60": "芝",  # 芝→ダート変更時等
}


def _infer_track_type(track_code: str) -> str:
    """track_code から芝/ダート/障害を判定"""
    if not track_code:
        return "芝"
    first = track_code[0] if len(track_code) >= 1 else "0"
    if first == "1" or first == "6":
        return "芝"
    elif first == "2":
        return "ダート"
    elif first == "5":
        return "障害"
    return TRACK_CODE_MAP.get(track_code, "芝")


class JrVanLoader:
    """JRA-VAN CSV → SQLite 変換"""

    def __init__(self, csv_dir: str | None = None, db_path: str | None = None):
        self.csv_dir = Path(csv_dir) if csv_dir else CSV_DIR
        self.db_path = Path(db_path) if db_path else DB_PATH

    def build_database(self) -> Path:
        """CSV → SQLite変換。DBが既存ならスキップ。"""
        if self.db_path.exists():
            return self.db_path

        csv_path = self.csv_dir / "race_horse_detail_keibadata_data.csv"
        if not csv_path.exists():
            csv_path = self.csv_dir / "race_horse_detail.csv"
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV not found: {csv_path}")

        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(self.db_path))
        try:
            self._load_race_horse_detail(conn, csv_path)
            self._load_code_tables(conn)
            self._create_indexes(conn)
            conn.execute("ANALYZE")
        finally:
            conn.close()

        return self.db_path

    def get_connection(self) -> sqlite3.Connection:
        """SQLiteコネクション取得（DBがなければ構築）"""
        self.build_database()
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def get_stats(self) -> dict:
        """DB内の件数等サマリ"""
        conn = self.get_connection()
        try:
            total = conn.execute("SELECT COUNT(*) FROM race_horse_detail").fetchone()[0]
            races = conn.execute("SELECT COUNT(DISTINCT race_id) FROM race_horse_detail").fetchone()[0]
            horses = conn.execute("SELECT COUNT(DISTINCT ketto_toroku_bango) FROM race_horse_detail").fetchone()[0]
            date_range = conn.execute(
                "SELECT MIN(race_date), MAX(race_date) FROM race_horse_detail"
            ).fetchone()
            return {
                "total_rows": total,
                "unique_races": races,
                "unique_horses": horses,
                "date_range": f"{date_range[0]} ~ {date_range[1]}",
                "db_path": str(self.db_path),
            }
        finally:
            conn.close()

    def _load_race_horse_detail(self, conn: sqlite3.Connection, csv_path: Path) -> None:
        """race_horse_detail.csv を SQLite にロード"""
        # BOM付きUTF-8対応
        with open(csv_path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            columns = reader.fieldnames
            if not columns:
                raise ValueError(f"No columns found in {csv_path}")

            cols_str = ", ".join(f'"{c}" TEXT' for c in columns)
            conn.execute(f"CREATE TABLE IF NOT EXISTS race_horse_detail ({cols_str})")

            placeholders = ", ".join("?" for _ in columns)
            insert_sql = f'INSERT INTO race_horse_detail VALUES ({placeholders})'

            batch = []
            for row in reader:
                batch.append(tuple(row.get(c, "") for c in columns))
                if len(batch) >= 5000:
                    conn.executemany(insert_sql, batch)
                    batch = []
            if batch:
                conn.executemany(insert_sql, batch)
            conn.commit()

    def _load_code_tables(self, conn: sqlite3.Connection) -> None:
        """コードテーブルをロード"""
        code_files = {
            "code_track": "jv_code_track.csv",
            "code_track_condition": "jv_code_track_condition.csv",
            "code_weather": "jv_code_weather.csv",
        }
        for table_name, filename in code_files.items():
            csv_path = self.csv_dir / filename
            if not csv_path.exists():
                continue
            with open(csv_path, encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                columns = reader.fieldnames
                if not columns:
                    continue
                cols_str = ", ".join(f'"{c}" TEXT' for c in columns)
                conn.execute(f"CREATE TABLE IF NOT EXISTS {table_name} ({cols_str})")
                placeholders = ", ".join("?" for _ in columns)
                insert_sql = f"INSERT INTO {table_name} VALUES ({placeholders})"
                rows = [tuple(row.get(c, "") for c in columns) for row in reader]
                conn.executemany(insert_sql, rows)
            conn.commit()

    def _create_indexes(self, conn: sqlite3.Connection) -> None:
        """検索用インデックス作成"""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_rhd_race_id ON race_horse_detail(race_id)",
            "CREATE INDEX IF NOT EXISTS idx_rhd_horse ON race_horse_detail(ketto_toroku_bango, race_date)",
            "CREATE INDEX IF NOT EXISTS idx_rhd_date ON race_horse_detail(race_date)",
            "CREATE INDEX IF NOT EXISTS idx_rhd_jockey ON race_horse_detail(jockey_code, race_date)",
            "CREATE INDEX IF NOT EXISTS idx_rhd_trainer ON race_horse_detail(trainer_code, race_date)",
        ]
        for sql in indexes:
            conn.execute(sql)
        conn.commit()
