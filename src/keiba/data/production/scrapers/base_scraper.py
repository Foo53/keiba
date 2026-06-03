"""スクレイパ基底クラス"""

import logging
from abc import ABC, abstractmethod

from keiba.utils.http_client import RateLimitedHttpClient


class BaseScraper(ABC):
    """全サイト別スクレイパの基底クラス"""

    def __init__(self, http_client: RateLimitedHttpClient):
        self.client = http_client
        self.logger = logging.getLogger(f"keiba.{self.__class__.__name__}")

    @property
    @abstractmethod
    def base_url(self) -> str:
        """対象サイトのルート URL"""
        ...

    def fetch_page(self, path: str, cache_ttl: int | None = None) -> str:
        """ページを取得して HTML テキストを返す。

        レート制限・キャッシュ・robots.txt は RateLimitedHttpClient が処理。
        """
        url = f"{self.base_url}{path}"
        response = self.client.get(url, cache_ttl=cache_ttl)
        response.encoding = self.encoding
        return response.text

    @property
    def encoding(self) -> str:
        """ページの文字エンコーディング（サブクラスで上書き可）"""
        return "utf-8"

    @abstractmethod
    def health_check(self) -> bool:
        """サイトがアクセス可能か確認"""
        ...
