"""パイプラインオーケストレータ"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from keiba.data.base_source import DataSource
from keiba.data.sample.sample_source import SampleDataSource
from keiba.models.pipeline import PipelineContext
from keiba.orchestration.pipeline import PipelineStage, build_pipeline
from keiba.utils.config import load_config
from keiba.utils.logging import get_agent_logger, setup_logging


class Orchestrator:
    """14エージェントパイプラインの実行管理"""

    def __init__(self, config: dict | None = None, data_source: DataSource | None = None):
        self.config = config or {}
        self.logger = get_agent_logger("Orchestrator")
        self.max_qa_retries = self.config.get("pipeline", {}).get("max_qa_retries", 3)

        # データソース解決
        if data_source:
            self.data_source = data_source
        else:
            active = self.config.get("data_source", {}).get("active", "sample")
            if active == "sample":
                self.data_source = SampleDataSource()
            elif active == "production":
                from keiba.data.production.production_source import ProductionDataSource
                self.data_source = ProductionDataSource(self.config)
            else:
                self.logger.warning(f"Data source '{active}' not recognized, falling back to sample")
                self.data_source = SampleDataSource()

        self.stages = build_pipeline(self.data_source)

    def run(self, race_id: str) -> PipelineContext:
        """パイプラインを実行"""
        context = PipelineContext(
            pipeline_id=str(uuid4()),
            race_id=race_id,
            started_at=datetime.now(),
            current_stage="initialized",
        )

        self.logger.info(f"Pipeline started: {race_id}")
        executed: dict[str, bool] = {}
        qa_retry_count = 0
        i = 0

        while i < len(self.stages):
            stage = self.stages[i]

            # 並列グループの検出
            if stage.parallel_group and stage.name not in executed:
                parallel_stages = [
                    s for s in self.stages[i:]
                    if s.parallel_group == stage.parallel_group and s.name not in executed
                ]
                if parallel_stages:
                    self._execute_parallel(context, parallel_stages, executed)
                    i += len(parallel_stages)
                    continue

            # 既に実行済み（リトライ時など）はスキップ
            if stage.name in executed:
                i += 1
                continue

            # 依存関係チェック
            for dep in stage.depends_on:
                if dep not in executed:
                    self.logger.error(f"Dependency {dep} not met for {stage.name}")
                    context.status = "failed"
                    return context

            # 実行
            context.current_stage = stage.name
            context = stage.agent.execute(context)

            if context.status == "failed":
                self.logger.error(f"Pipeline failed at {stage.name}")
                return context

            executed[stage.name] = True

            # QAゲート: 差し戻し判定
            if stage.name == "qa" and context.qa_report:
                if not context.qa_report.get("passed", False) and qa_retry_count < self.max_qa_retries:
                    route_to = context.qa_report.get("route_back_to", "")
                    qa_retry_count += 1
                    self.logger.warning(
                        f"QA failed ({context.qa_report['total_score']}/120). "
                        f"Routing back to {route_to}. Retry #{qa_retry_count}"
                    )
                    executed = self._reset_from(executed, route_to)
                    context.status = "running"
                    # ステージインデックスをリセット先に戻す
                    i = self._find_stage_index(route_to)
                    continue

            i += 1

        context.status = "completed"
        self.logger.info(f"Pipeline completed: {race_id}, agents={len(context.agent_results)}")
        return context

    def _execute_parallel(self, context: PipelineContext, stages: list[PipelineStage],
                          executed: dict[str, bool]) -> None:
        """並列ステージを実行"""
        self.logger.info(f"Running {len(stages)} stages in parallel: {[s.name for s in stages]}")

        with ThreadPoolExecutor(max_workers=len(stages)) as pool:
            # 各ステージにcontextのコピーを渡す
            futures = {}
            for stage in stages:
                ctx_copy = deepcopy(context)
                ctx_copy.current_stage = stage.name
                future = pool.submit(stage.agent.execute, ctx_copy)
                futures[future] = stage

            for future in as_completed(futures):
                stage = futures[future]
                try:
                    result_ctx = future.result()
                    # 結果をメインcontextにマージ
                    self._merge_context(context, result_ctx, stage.name)
                    executed[stage.name] = True
                    self.logger.info(f"Parallel stage {stage.name} completed")
                except Exception as e:
                    self.logger.error(f"Parallel stage {stage.name} failed: {e}")
                    context.status = "failed"

    def _merge_context(self, main: PipelineContext, result: PipelineContext, stage_name: str) -> None:
        """並列実行結果をメインcontextにマージ"""
        # 該当ステージの出力フィールドをコピー
        field_map = {
            "python_analysis": "analysis",
            "ml_analysis": "ml_analysis",
            "web_research": "web_research",
        }
        field = field_map.get(stage_name)
        if field:
            setattr(main, field, getattr(result, field, None))
        # このステージのagent_resultだけ追加（deepcopy由来の重複を避ける）
        if result.agent_results:
            main.agent_results.append(result.agent_results[-1])

    def _reset_from(self, executed: dict[str, bool], route_to: str) -> dict[str, bool]:
        """指定ステージ以降をリセット"""
        stage_names = [s.name for s in self.stages]
        if route_to not in stage_names:
            return executed
        start_idx = stage_names.index(route_to)
        for name in stage_names[start_idx:]:
            executed.pop(name, None)
        return executed

    def _find_stage_index(self, stage_name: str) -> int:
        """ステージ名からインデックスを検索"""
        for i, s in enumerate(self.stages):
            if s.name == stage_name:
                return i
        return 0

    def save_outputs(self, context: PipelineContext, output_dir: str = "output") -> None:
        """成果物を保存"""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        # JSON出力
        json_dir = out / "json"
        json_dir.mkdir(exist_ok=True)
        json_path = json_dir / f"{context.race_id}.json"
        json_path.write_text(context.model_dump_json(indent=2), encoding="utf-8")
        self.logger.info(f"JSON saved: {json_path}")

        # Markdown出力
        if context.note_article:
            md_dir = out / "markdown"
            md_dir.mkdir(exist_ok=True)
            md_path = md_dir / f"{context.race_id}.md"
            md_path.write_text(context.note_article.get("body_markdown", ""), encoding="utf-8")
            self.logger.info(f"Markdown saved: {md_path}")
