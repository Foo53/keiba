"""レート制限付き HTTP クライアント

robots.txt 検査、ドメインごとのレート制限、ファイルベースのキャッシュ、
1日リクエスト上限を備えた HTTP クライアント。
"""

import base64
import hashlib
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

from keiba.data.production.exceptions import (
    RateLimitExceededError,
    RobotsTxtDisallowedError,
)

logger = logging.getLogger("keiba.HttpClient")


class RateLimitedHttpClient:
    """レート制限・キャッシュ・robots.txt チェック付き HTTP クライアント"""

    def __init__(self, config: dict):
        self.config = config
        self.user_agent = config.get("user_agent", "keiba-prediction/0.1.0 (educational research)")
        self.min_interval = config.get("min_interval_seconds", 7)
        self.daily_budget = config.get("daily_request_budget", 500)
        self.timeout = config.get("timeout_seconds", 30)
        self.max_retries = config.get("max_retries", 2)

        cache_cfg = config.get("cache", {})
        self.cache_dir = Path(cache_cfg.get("directory", "data/store/cache"))
        self.default_ttl = cache_cfg.get("default_ttl_seconds", 3600)
        self.ttl_overrides: dict[str, int] = cache_cfg.get("ttl_overrides", {})

        # ドメインごとの前回リクエスト時刻
        self._last_request: dict[str, float] = {}
        # ドメインごとの1日リクエスト数 {domain: {date_str: count}}
        self._daily_counts: dict[str, dict[str, int]] = {}
        # robots.txt キャッシュ {domain: RobotFileParser}
        self._robots_cache: dict[str, RobotFileParser] = {}
        self._robots_fetched_at: dict[str, float] = {}

        # requests セッション
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": self.user_agent})

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    def get(self, url: str, cache_ttl: int | None = None) -> requests.Response:
        """URL を取得（レート制限・キャッシュ・robots.txt 適用）。

        Parameters
        ----------
        url : str
            取得対象 URL
        cache_ttl : int | None
            キャッシュ TTL（秒）。None なら default_ttl を使用。

        Returns
        -------
        requests.Response
            HTTP レスポンス（キャッシュヒット時はステータス 200 の擬似レスポンス）

        Raises
        ------
        RobotsTxtDisallowedError
            robots.txt で禁止されている場合
        RateLimitExceededError
            1日のリクエスト上限に到達した場合
        """
        domain = self._domain(url)

        # 1) robots.txt チェック
        if not self._check_robots(url, domain):
            raise RobotsTxtDisallowedError(f"robots.txt disallows: {url}")

        # 2) キャッシュチェック
        ttl = cache_ttl if cache_ttl is not None else self.default_ttl
        cached = self._read_cache(url, ttl)
        if cached is not None:
            logger.debug(f"Cache hit: {url}")
            return self._make_cached_response(cached)

        # 3) 1日リクエスト上限チェック
        self._check_daily_budget(domain)

        # 4) レート制限
        self._enforce_rate_limit(domain)

        # 5) HTTP リクエスト（リトライ付き）
        response = self._request_with_retry(url)

        # 6) キャッシュ保存
        if response.status_code == 200:
            self._write_cache(url, response)

        # 7) 1日リクエスト数カウント
        self._increment_daily_count(domain)

        return response

    def is_allowed_by_robots(self, url: str) -> bool:
        """URL が robots.txt で許可されているかを返す"""
        domain = self._domain(url)
        try:
            return self._check_robots(url, domain)
        except Exception:
            return True  # robots.txt が取得できなければ許可（ログ出力済み）

    def clear_cache(self, domain: str | None = None) -> int:
        """キャッシュをクリア。domain 指定時はそのドメインのみ。削除件数を返す。"""
        if domain:
            target = self.cache_dir / domain
        else:
            target = self.cache_dir

        count = 0
        if target.exists():
            for f in target.rglob("*.json"):
                if f.name != "daily_count.json":
                    f.unlink()
                    count += 1
        return count

    def get_cache_stats(self) -> dict[str, int]:
        """キャッシュの統計情報を返す"""
        stats: dict[str, int] = {}
        if not self.cache_dir.exists():
            return stats
        for domain_dir in self.cache_dir.iterdir():
            if domain_dir.is_dir():
                count = sum(1 for f in domain_dir.glob("*.json") if f.name != "daily_count.json")
                stats[domain_dir.name] = count
        return stats

    # ------------------------------------------------------------------
    # robots.txt
    # ------------------------------------------------------------------

    def _check_robots(self, url: str, domain: str) -> bool:
        """robots.txt を確認（24h キャッシュ）

        Python 標準 RobotFileParser.read() は一部サイトで
        パースに失敗するため、requests で取得してから parse() する。
        """
        now = time.time()
        cached_at = self._robots_fetched_at.get(domain, 0)

        if domain in self._robots_cache and (now - cached_at) < 86400:
            return self._robots_cache[domain].can_fetch(self.user_agent, url)

        robots_url = f"https://{domain}/robots.txt"
        rp = RobotFileParser()
        try:
            resp = self._session.get(robots_url, timeout=self.timeout)
            if resp.status_code == 404:
                # robots.txt がない = 全許可
                rp.allow_all = True
            else:
                resp.raise_for_status()
                # requests 経由で取得したテキストを手動パース
                lines = resp.text.strip().splitlines()
                rp.parse(lines)
            self._robots_cache[domain] = rp
            self._robots_fetched_at[domain] = now
            allowed = rp.can_fetch(self.user_agent, url)
            logger.info(f"robots.txt check for {domain}: {'allowed' if allowed else 'disallowed'}")
            return allowed
        except Exception as e:
            logger.warning(f"Could not fetch robots.txt for {domain}: {e}")
            # 取得できなければ許可する（ただし警告を記録）
            return True

    # ------------------------------------------------------------------
    # レート制限
    # ------------------------------------------------------------------

    def _enforce_rate_limit(self, domain: str) -> None:
        """ドメインごとの最小リクエスト間隔を強制"""
        last = self._last_request.get(domain, 0)
        elapsed = time.time() - last
        if elapsed < self.min_interval:
            wait = self.min_interval - elapsed
            logger.debug(f"Rate limit: waiting {wait:.1f}s for {domain}")
            time.sleep(wait)
        self._last_request[domain] = time.time()

    # ------------------------------------------------------------------
    # 1日リクエスト上限
    # ------------------------------------------------------------------

    def _check_daily_budget(self, domain: str) -> None:
        """1日のリクエスト上限をチェック"""
        count = self._get_daily_count(domain)
        if count >= self.daily_budget:
            raise RateLimitExceededError(
                f"Daily budget ({self.daily_budget}) exceeded for {domain}"
            )

    def _get_daily_count(self, domain: str) -> int:
        """当日のリクエスト数を取得"""
        today = datetime.now().strftime("%Y-%m-%d")
        return self._daily_counts.get(domain, {}).get(today, 0)

    def _increment_daily_count(self, domain: str) -> None:
        """当日のリクエスト数をインクリメント"""
        today = datetime.now().strftime("%Y-%m-%d")
        if domain not in self._daily_counts:
            self._daily_counts[domain] = {}
        self._daily_counts[domain][today] = self._daily_counts[domain].get(today, 0) + 1

    # ------------------------------------------------------------------
    # キャッシュ
    # ------------------------------------------------------------------

    def _cache_path(self, url: str) -> Path:
        """URL からキャッシュファイルパスを生成"""
        domain = self._domain(url)
        key = hashlib.sha256(url.encode()).hexdigest()[:32]
        return self.cache_dir / domain / f"{key}.json"

    def _read_cache(self, url: str, ttl: int) -> dict | None:
        """キャッシュを読み込み。TTL 内なら返す、それ以外は None。"""
        path = self._cache_path(url)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            fetched_at = datetime.fromisoformat(data["fetched_at"])
            elapsed = (datetime.now() - fetched_at).total_seconds()
            if elapsed <= ttl:
                return data
            # TTL 超過
            return None
        except Exception:
            return None

    def _write_cache(self, url: str, response: requests.Response) -> None:
        """レスポンスをキャッシュに保存（raw bytes を base64 で保存）"""
        path = self._cache_path(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "url": url,
            "fetched_at": datetime.now().isoformat(),
            "status_code": response.status_code,
            "body_b64": base64.b64encode(response.content).decode("ascii"),
        }
        path.write_text(json.dumps(data), encoding="utf-8")

    def _make_cached_response(self, cached: dict) -> requests.Response:
        """キャッシュデータから requests.Response 風のオブジェクトを生成"""
        resp = requests.Response()
        resp.status_code = cached.get("status_code", 200)
        if "body_b64" in cached:
            # 新形式: raw bytes を base64 から復元
            resp._content = base64.b64decode(cached["body_b64"])
        else:
            # 旧形式: テキストとして保存されていたデータ（文字化け可能性あり）
            resp._content = cached.get("body", "").encode("utf-8")
            resp.encoding = "utf-8"
        resp.url = cached.get("url", "")
        return resp

    # ------------------------------------------------------------------
    # HTTP リクエスト
    # ------------------------------------------------------------------

    def _request_with_retry(self, url: str) -> requests.Response:
        """リトライ付き HTTP GET"""
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self._session.get(url, timeout=self.timeout)
                response.raise_for_status()
                return response
            except requests.RequestException as e:
                last_exc = e
                if attempt < self.max_retries:
                    wait = 5 * (attempt + 1)
                    logger.warning(f"Request failed (attempt {attempt + 1}/{self.max_retries + 1}): {e}. Retrying in {wait}s")
                    time.sleep(wait)
        raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------
    # ユーティリティ
    # ------------------------------------------------------------------

    @staticmethod
    def _domain(url: str) -> str:
        """URL からドメイン名を抽出"""
        return urlparse(url).netloc
