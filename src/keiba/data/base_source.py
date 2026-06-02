"""データソース抽象基底クラス

外部サイトへの実アクセスは行わないこと。
本番実装時は対象サイトの利用規約・robots.txt・アクセス頻度制限を必ず確認すること。
MVPではSampleDataSourceのみ使用する。
"""

from abc import ABC, abstractmethod


class DataSource(ABC):
    """全データ取得の抽象インターフェース"""

    @abstractmethod
    def get_historical_data(self, race_id: str) -> dict:
        """過去レースデータを取得"""
        ...

    @abstractmethod
    def get_current_race_card(self, race_id: str) -> dict:
        """当日のレース出走情報を取得"""
        ...

    @abstractmethod
    def get_predicted_odds(self, race_id: str) -> dict:
        """予想オッズを取得"""
        ...

    @abstractmethod
    def get_actual_odds(self, race_id: str) -> dict:
        """実オッズを取得"""
        ...

    @abstractmethod
    def get_web_content(self, race_id: str, horse_ids: list[str]) -> dict:
        """Web調査コンテンツを取得"""
        ...

    @abstractmethod
    def get_backtest_data(self, config: dict) -> list[dict]:
        """バックテスト用過去データを取得"""
        ...
