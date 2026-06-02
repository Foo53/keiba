"""パイプラインステージ定義"""

from keiba.data.base_source import DataSource
from keiba.agents.historical_data_manager import HistoricalDataManager
from keiba.agents.current_data_fetcher import CurrentDataFetcher
from keiba.agents.data_quality_checker import DataQualityChecker
from keiba.agents.feature_generator import FeatureGenerator
from keiba.agents.python_analyzer import PythonAnalyzer
from keiba.agents.web_researcher import WebResearcher
from keiba.agents.evidence_integrator import EvidenceIntegrator
from keiba.agents.predicted_odds_evaluator import PredictedOddsEvaluator
from keiba.agents.actual_odds_evaluator import ActualOddsEvaluator
from keiba.agents.prediction_generator import PredictionGenerator
from keiba.agents.backtester import Backtester
from keiba.agents.note_structure_researcher import NoteStructureResearcher
from keiba.agents.note_writer import NoteWriter
from keiba.agents.quality_assurance import QualityAssurance


class PipelineStage:
    """パイプラインの1ステージ"""

    def __init__(self, agent, name: str, depends_on: list[str] | None = None,
                 parallel_group: str | None = None):
        self.agent = agent
        self.name = name
        self.depends_on = depends_on or []
        self.parallel_group = parallel_group


def build_pipeline(data_source: DataSource) -> list[PipelineStage]:
    """全14ステージのパイプラインを構築"""
    return [
        PipelineStage(HistoricalDataManager(data_source), "historical_data", []),
        PipelineStage(CurrentDataFetcher(data_source), "current_data", ["historical_data"]),
        PipelineStage(DataQualityChecker(), "quality_check", ["current_data"]),
        PipelineStage(FeatureGenerator(), "feature_gen", ["quality_check"]),
        PipelineStage(PythonAnalyzer(), "python_analysis", ["feature_gen"], parallel_group="parallel_1"),
        PipelineStage(WebResearcher(data_source), "web_research", ["current_data"], parallel_group="parallel_1"),
        PipelineStage(EvidenceIntegrator(), "evidence", ["python_analysis", "web_research"]),
        PipelineStage(PredictedOddsEvaluator(), "predicted_odds", ["evidence"]),
        PipelineStage(ActualOddsEvaluator(), "actual_odds", ["predicted_odds"]),
        PipelineStage(PredictionGenerator(), "prediction", ["actual_odds"]),
        PipelineStage(Backtester(data_source), "backtest", ["prediction"]),
        PipelineStage(NoteStructureResearcher(), "note_research", ["prediction"]),
        PipelineStage(NoteWriter(), "note_write", ["note_research"]),
        PipelineStage(QualityAssurance(), "qa", ["note_write"]),
    ]
