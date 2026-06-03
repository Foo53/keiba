"""ProductionDataSource のテスト"""

import pytest
from unittest.mock import MagicMock, patch

from keiba.data.base_source import DataSource
from keiba.data.production.exceptions import AllSourcesFailedError
from keiba.data.production.production_source import ProductionDataSource


def _make_config():
    return {
        "data_source": {
            "production": {
                "http": {"min_interval_seconds": 0, "daily_request_budget": 100},
                "cache": {"directory": "/tmp/keiba_test_cache"},
            }
        }
    }


@pytest.fixture
def prod_source():
    """テスト用 ProductionDataSource（モックスクレイパ付き）"""
    config = _make_config()
    with patch("keiba.data.production.production_source.RateLimitedHttpClient"):
        source = ProductionDataSource(config)
    return source


class TestDataSourceConformance:
    def test_is_datasource_subclass(self):
        assert issubclass(ProductionDataSource, DataSource)

    def test_has_all_abstract_methods(self):
        methods = ["get_historical_data", "get_current_race_card",
                    "get_predicted_odds", "get_actual_odds",
                    "get_web_content", "get_backtest_data"]
        for m in methods:
            assert hasattr(ProductionDataSource, m)


class TestFallbackMechanism:
    def test_fetch_with_fallback_returns_none_on_error(self, prod_source):
        def failing():
            raise Exception("test error")
        result = prod_source._fetch_with_fallback(failing, "test")
        assert result is None

    def test_fetch_with_fallback_returns_result_on_success(self, prod_source):
        result = prod_source._fetch_with_fallback(lambda: {"ok": True}, "test")
        assert result == {"ok": True}

    def test_fetch_with_fallback_propagates_all_sources_failed(self, prod_source):
        def failing():
            raise AllSourcesFailedError("all failed")
        with pytest.raises(AllSourcesFailedError):
            prod_source._fetch_with_fallback(failing, "test")


class TestFormatOdds:
    def test_format_produces_correct_structure(self, prod_source):
        odds_list = [
            {"entry_id": "E1", "horse_name": "馬A", "win_odds": 2.5, "popularity_rank": 1},
            {"entry_id": "E2", "horse_name": "馬B", "win_odds": 5.0, "popularity_rank": 2},
        ]
        result = prod_source._format_odds(odds_list, "R001", is_provisional=True)
        assert result["race_id"] == "R001"
        assert result["is_provisional"] is True
        assert len(result["entries"]) == 2
        assert result["entries"][0]["win_odds"] == 2.5

    def test_format_actual_odds(self, prod_source):
        result = prod_source._format_odds([], "R001", is_provisional=False)
        assert result["is_provisional"] is False


class TestOrchestratorIntegration:
    def test_orchestrator_instantiates_production_source(self):
        """orchestrator が 'production' 設定時に ProductionDataSource を生成"""
        from keiba.orchestration.orchestrator import Orchestrator
        with patch("keiba.data.production.production_source.RateLimitedHttpClient"):
            config = {
                "data_source": {"active": "production", "production": {
                    "http": {"min_interval_seconds": 0, "daily_request_budget": 100},
                    "cache": {"directory": "/tmp/keiba_test"},
                }},
            }
            orch = Orchestrator(config=config)
            assert isinstance(orch.data_source, ProductionDataSource)

    def test_orchestrator_falls_back_for_unknown_source(self):
        """不明なソース名は sample にフォールバック"""
        from keiba.orchestration.orchestrator import Orchestrator
        from keiba.data.sample.sample_source import SampleDataSource

        config = {"data_source": {"active": "unknown"}}
        orch = Orchestrator(config=config)
        assert isinstance(orch.data_source, SampleDataSource)
