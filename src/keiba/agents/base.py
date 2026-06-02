"""エージェント抽象基底クラス"""

from abc import ABC, abstractmethod
from datetime import datetime

from keiba.models.pipeline import AgentResult, PipelineContext
from keiba.utils.logging import get_agent_logger


class BaseAgent(ABC):
    """全エージェントのテンプレートメソッドを定義"""

    def __init__(self):
        self.name: str = self.__class__.__name__
        self.logger = get_agent_logger(self.name)

    @abstractmethod
    def validate_input(self, context: PipelineContext) -> bool:
        """入力の前提条件を検証"""
        ...

    @abstractmethod
    def process(self, context: PipelineContext) -> PipelineContext:
        """エージェントのコアロジック"""
        ...

    def execute(self, context: PipelineContext) -> PipelineContext:
        """テンプレートメソッド: validate → process → 結果ラップ → ログ"""
        started = datetime.now()
        self.logger.info(
            f"Agent {self.name} starting",
            extra={
                "agent_name": self.name,
                "race_id": context.race_id,
                "pipeline_id": context.pipeline_id,
            },
        )
        try:
            if not self.validate_input(context):
                raise ValueError(f"Input validation failed for {self.name}")
            result = self.process(context)
            duration = (datetime.now() - started).total_seconds()
            agent_result = AgentResult(
                agent_name=self.name,
                success=True,
                started_at=started,
                completed_at=datetime.now(),
                duration_seconds=duration,
                output={"stage": context.current_stage},
            )
            result.agent_results.append(agent_result.model_dump())
            self.logger.info(f"Agent {self.name} completed in {duration:.2f}s")
            return result
        except Exception as e:
            duration = (datetime.now() - started).total_seconds()
            agent_result = AgentResult(
                agent_name=self.name,
                success=False,
                started_at=started,
                completed_at=datetime.now(),
                duration_seconds=duration,
                output={},
                error=str(e),
            )
            context.agent_results.append(agent_result.model_dump())
            self.logger.error(f"Agent {self.name} failed: {e}", exc_info=True)
            context.status = "failed"
            return context

    def describe(self) -> str:
        return f"{self.name}: {self.__doc__ or 'No description'}"
