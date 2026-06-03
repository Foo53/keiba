"""本番データソース用の例外クラス"""


class DataSourceError(Exception):
    """データソース関連の基底例外"""


class RobotsTxtDisallowedError(DataSourceError):
    """robots.txt で禁止されている URL"""


class RateLimitExceededError(DataSourceError):
    """1日のリクエスト上限に到達"""


class ScraperError(DataSourceError):
    """スクレイパのパース・取得エラー"""


class AllSourcesFailedError(DataSourceError):
    """全データソースが失敗"""
