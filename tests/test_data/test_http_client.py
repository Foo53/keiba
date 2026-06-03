"""RateLimitedHttpClient のテスト"""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from keiba.data.production.exceptions import (
    RateLimitExceededError,
    RobotsTxtDisallowedError,
)
from keiba.utils.http_client import RateLimitedHttpClient


@pytest.fixture
def http_client(tmp_path):
    """テスト用 RateLimitedHttpClient（高速化のため min_interval=0）"""
    config = {
        "user_agent": "test-bot",
        "min_interval_seconds": 0,
        "daily_request_budget": 10,
        "timeout_seconds": 5,
        "max_retries": 1,
        "cache": {
            "directory": str(tmp_path / "cache"),
            "default_ttl_seconds": 3600,
        },
    }
    return RateLimitedHttpClient(config)


@pytest.fixture
def slow_client(tmp_path):
    """レート制限テスト用（min_interval=0.1秒）"""
    config = {
        "user_agent": "test-bot",
        "min_interval_seconds": 0.1,
        "daily_request_budget": 10,
        "timeout_seconds": 5,
        "max_retries": 0,
        "cache": {
            "directory": str(tmp_path / "cache"),
            "default_ttl_seconds": 3600,
        },
    }
    return RateLimitedHttpClient(config)


class TestCaching:
    def test_cache_returns_cached_response_within_ttl(self, http_client, tmp_path):
        """TTL 内はキャッシュを返す（HTTP リクエストしない）"""
        url = "https://example.com/page"
        cache_data = {
            "url": url,
            "fetched_at": "2099-01-01T00:00:00",  # far future
            "status_code": 200,
            "body": "<html>cached</html>",
        }
        cache_path = tmp_path / "cache" / "example.com"
        cache_path.mkdir(parents=True)
        key = __import__("hashlib").sha256(url.encode()).hexdigest()[:32]
        (cache_path / f"{key}.json").write_text(json.dumps(cache_data), encoding="utf-8")

        resp = http_client.get(url)
        assert resp.status_code == 200
        assert "cached" in resp.text

    def test_cache_makes_request_after_ttl_expiry(self, http_client, tmp_path):
        """TTL 超過後は HTTP リクエストする"""
        url = "https://example.com/page"
        cache_data = {
            "url": url,
            "fetched_at": "2000-01-01T00:00:00",  # expired
            "status_code": 200,
            "body": "<html>old</html>",
        }
        cache_path = tmp_path / "cache" / "example.com"
        cache_path.mkdir(parents=True)
        key = __import__("hashlib").sha256(url.encode()).hexdigest()[:32]
        (cache_path / f"{key}.json").write_text(json.dumps(cache_data), encoding="utf-8")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html>fresh</html>"
        mock_resp.raise_for_status = MagicMock()

        with patch.object(http_client._session, "get", return_value=mock_resp):
            resp = http_client.get(url)

        assert "fresh" in resp.text

    def test_cache_saves_response(self, http_client, tmp_path):
        """HTTP レスポンスをキャッシュに保存する"""
        url = "https://example.com/newpage"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html>response</html>"
        mock_resp.raise_for_status = MagicMock()

        with patch.object(http_client._session, "get", return_value=mock_resp):
            http_client.get(url)

        # キャッシュファイルが作成されている
        cache_path = tmp_path / "cache" / "example.com"
        key = __import__("hashlib").sha256(url.encode()).hexdigest()[:32]
        saved = cache_path / f"{key}.json"
        assert saved.exists()
        data = json.loads(saved.read_text(encoding="utf-8"))
        assert data["body"] == "<html>response</html>"

    def test_cache_ttl_override(self, http_client, tmp_path):
        """カスタム TTL でキャッシュヒット判定"""
        url = "https://example.com/page"
        # 60秒前にフェッチ → TTL=300秒ならヒット、TTL=1秒ならミス
        import datetime
        past = (datetime.datetime.now() - datetime.timedelta(seconds=60)).isoformat()
        cache_data = {
            "url": url,
            "fetched_at": past,
            "status_code": 200,
            "body": "<html>cached</html>",
        }
        cache_path = tmp_path / "cache" / "example.com"
        cache_path.mkdir(parents=True)
        key = __import__("hashlib").sha256(url.encode()).hexdigest()[:32]
        (cache_path / f"{key}.json").write_text(json.dumps(cache_data), encoding="utf-8")

        # TTL=300秒ならキャッシュヒット
        resp = http_client.get(url, cache_ttl=300)
        assert "cached" in resp.text


class TestRobotsTxt:
    def test_disallowed_url_raises_error(self, http_client):
        """robots.txt で禁止URLはエラー"""
        url = "https://example.com/disallowed"
        mock_rp = MagicMock()
        mock_rp.can_fetch.return_value = False
        mock_rp.read = MagicMock()

        with patch("keiba.utils.http_client.RobotFileParser", return_value=mock_rp):
            with pytest.raises(RobotsTxtDisallowedError):
                http_client.get(url)

    def test_allowed_url_proceeds(self, http_client):
        """robots.txt で許可URLはリクエストを続行"""
        url = "https://example.com/allowed"
        mock_rp = MagicMock()
        mock_rp.can_fetch.return_value = True
        mock_rp.read = MagicMock()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html>ok</html>"
        mock_resp.raise_for_status = MagicMock()

        with patch("keiba.utils.http_client.RobotFileParser", return_value=mock_rp):
            with patch.object(http_client._session, "get", return_value=mock_resp):
                resp = http_client.get(url)
                assert resp.status_code == 200

    def test_robots_txt_failure_allows_request(self, http_client):
        """robots.txt 取得失敗時はリクエストを許可"""
        url = "https://example.com/page"
        mock_rp = MagicMock()
        mock_rp.read.side_effect = Exception("network error")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html>ok</html>"
        mock_resp.raise_for_status = MagicMock()

        with patch("keiba.utils.http_client.RobotFileParser", return_value=mock_rp):
            with patch.object(http_client._session, "get", return_value=mock_resp):
                resp = http_client.get(url)
                assert resp.status_code == 200

    def test_is_allowed_by_robots(self, http_client):
        """is_allowed_by_robots は例外を投げない"""
        mock_rp = MagicMock()
        mock_rp.can_fetch.return_value = True
        mock_rp.read = MagicMock()

        with patch("keiba.utils.http_client.RobotFileParser", return_value=mock_rp):
            assert http_client.is_allowed_by_robots("https://example.com/page") is True


class TestRateLimiting:
    def test_enforces_min_interval(self, slow_client):
        """ドメインごとの最小リクエスト間隔を強制"""
        url = "https://example.com/page"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html>ok</html>"
        mock_resp.raise_for_status = MagicMock()

        with patch.object(slow_client._session, "get", return_value=mock_resp):
            start = time.time()
            slow_client.get(url, cache_ttl=0)  # TTL=0 でキャッシュ無効化
            slow_client.get(url, cache_ttl=0)
            elapsed = time.time() - start

        # 2回目のリクエストで min_interval(0.1s) 待機しているはず
        assert elapsed >= 0.08  # 許容誤差


class TestDailyBudget:
    def test_exceeds_daily_budget_raises_error(self, http_client):
        """1日のリクエスト上限到達でエラー"""
        url = "https://example.com/page"

        # 予めカウントを上限に設定
        today = time.strftime("%Y-%m-%d")
        http_client._daily_counts["example.com"] = {today: http_client.daily_budget}

        # キャッシュミスを強制
        with patch.object(http_client, "_read_cache", return_value=None):
            with pytest.raises(RateLimitExceededError):
                http_client.get(url)


class TestRetry:
    def test_retries_on_failure(self, http_client):
        """リクエスト失敗時にリトライする"""
        url = "https://example.com/page"
        import requests

        fail_resp = MagicMock()
        fail_resp.raise_for_status.side_effect = requests.RequestException("timeout")

        success_resp = MagicMock()
        success_resp.status_code = 200
        success_resp.text = "<html>ok</html>"
        success_resp.raise_for_status = MagicMock()

        with patch.object(http_client._session, "get", side_effect=[fail_resp, success_resp]):
            with patch("keiba.utils.http_client.time.sleep"):
                resp = http_client.get(url, cache_ttl=0)

        assert resp.status_code == 200


class TestCacheManagement:
    def test_clear_cache(self, http_client, tmp_path):
        """キャッシュクリア"""
        url = "https://example.com/page"
        cache_data = {
            "url": url,
            "fetched_at": "2099-01-01T00:00:00",
            "status_code": 200,
            "body": "<html>cached</html>",
        }
        cache_path = tmp_path / "cache" / "example.com"
        cache_path.mkdir(parents=True)
        key = __import__("hashlib").sha256(url.encode()).hexdigest()[:32]
        (cache_path / f"{key}.json").write_text(json.dumps(cache_data), encoding="utf-8")

        count = http_client.clear_cache("example.com")
        assert count == 1

    def test_get_cache_stats(self, http_client, tmp_path):
        """キャッシュ統計"""
        cache_path = tmp_path / "cache" / "example.com"
        cache_path.mkdir(parents=True)
        (cache_path / "abc.json").write_text("{}", encoding="utf-8")
        (cache_path / "def.json").write_text("{}", encoding="utf-8")

        stats = http_client.get_cache_stats()
        assert stats.get("example.com") == 2
