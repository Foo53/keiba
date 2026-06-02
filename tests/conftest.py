"""共通テストフィクスチャ"""

import pytest
from datetime import datetime
from keiba.models.pipeline import PipelineContext
from keiba.data.sample.sample_source import SampleDataSource


@pytest.fixture
def sample_race_id():
    return "20260607-Tokyo-11"


@pytest.fixture
def sample_data_source():
    return SampleDataSource()


@pytest.fixture
def fresh_context(sample_race_id):
    return PipelineContext(
        pipeline_id="test-001",
        race_id=sample_race_id,
        started_at=datetime.now(),
        current_stage="initialized",
    )


@pytest.fixture
def context_with_historical(fresh_context, sample_data_source):
    """過去データ済みのコンテキスト"""
    from keiba.agents.historical_data_manager import HistoricalDataManager
    agent = HistoricalDataManager(sample_data_source)
    return agent.execute(fresh_context)


@pytest.fixture
def context_with_current(context_with_historical, sample_data_source):
    """当日データ済みのコンテキスト"""
    from keiba.agents.current_data_fetcher import CurrentDataFetcher
    agent = CurrentDataFetcher(sample_data_source)
    return agent.execute(context_with_historical)


@pytest.fixture
def context_with_quality(context_with_current):
    """品質チェック済みのコンテキスト"""
    from keiba.agents.data_quality_checker import DataQualityChecker
    agent = DataQualityChecker()
    return agent.execute(context_with_current)


@pytest.fixture
def context_with_features(context_with_quality):
    """特徴量生成済みのコンテキスト"""
    from keiba.agents.feature_generator import FeatureGenerator
    agent = FeatureGenerator()
    return agent.execute(context_with_quality)


@pytest.fixture
def full_context(sample_data_source):
    """全エージェント実行済みのコンテキスト"""
    from keiba.orchestration.orchestrator import Orchestrator
    orch = Orchestrator(data_source=sample_data_source)
    return orch.run("20260607-Tokyo-11")
