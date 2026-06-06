"""業務リーダーエージェント

社長（ユーザー）からの依頼をかみ砕き、適切な社員（エージェント）に業務を割り当てる。
対話型REPLでユーザーと相談しながら進める。
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime
from uuid import uuid4

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Confirm, Prompt

from keiba.data.base_source import DataSource
from keiba.models.pipeline import PipelineContext
from keiba.orchestration.pipeline import PipelineStage, build_pipeline
from keiba.utils.logging import get_agent_logger


# ワークフロー定義: (表示名, ステージ名リスト)
WORKFLOWS: dict[str, tuple[str, list[str]]] = {
    "full": (
        "完全予想パイプライン",
        [
            "historical_data", "current_data", "quality_check", "feature_gen",
            "python_analysis", "ml_analysis", "web_research", "evidence",
            "predicted_odds", "actual_odds", "prediction", "backtest",
            "visualization", "note_research", "note_write", "qa",
        ],
    ),
    "data": (
        "データ取得",
        ["historical_data", "current_data", "quality_check"],
    ),
    "features": (
        "特徴量生成",
        ["feature_gen"],
    ),
    "analysis": (
        "分析",
        ["python_analysis", "ml_analysis", "web_research", "evidence"],
    ),
    "odds": (
        "オッズ評価",
        ["predicted_odds", "actual_odds"],
    ),
    "prediction": (
        "予想生成",
        ["prediction", "backtest"],
    ),
    "publish": (
        "記事生成",
        ["visualization", "note_research", "note_write", "qa"],
    ),
}

# メニュー選択肢 → ワークフローキー
MENU_WORKFLOW_MAP = {
    "1": "full",
    "2": "data",
    "3": "features",
    "4": "analysis",
    "5": "odds",
    "6": "prediction",
    "7": "publish",
}


class LeaderAgent:
    """業務リーダー - 社長（ユーザー）の指示を社員（エージェント）に伝える"""

    def __init__(self, config: dict, data_source: DataSource, race_id: str):
        self.config = config
        self.data_source = data_source
        self.race_id = race_id
        self.logger = get_agent_logger("LeaderAgent")
        self.console = Console()

        # パイプラインステージ
        self.stages: list[PipelineStage] = build_pipeline(data_source)
        self.stage_map: dict[str, PipelineStage] = {s.name: s for s in self.stages}

        # 実行状態
        self.context = self._init_context(race_id)
        self.completed: set[str] = set()

    def run(self) -> None:
        """REPL メインループ"""
        self._greet()
        while True:
            choice = self._show_menu()
            if not self._handle_choice(choice):
                break
        self._farewell()

    # ----------------------------------------------------------------
    # メニュー
    # ----------------------------------------------------------------

    def _greet(self) -> None:
        self.console.print()
        self.console.print(Panel(
            "[bold]業務リーダーです。社長、よろしくお願いします。[/bold]",
            border_style="blue",
        ))

    def _farewell(self) -> None:
        self.console.print()
        self.console.print("[bold blue]お疲れ様でした。またよろしくお願いします。[/bold blue]")

    def _show_menu(self) -> str:
        done = len(self.completed)
        total = len(self.stages)
        self.console.print()
        self.console.rule(f"[bold]レース: {self.race_id}  完了: {done}/{total}[/bold]")
        self.console.print()
        self.console.print("何をお願いしますか？")
        self.console.print("  [1] 完全予想パイプライン  (全16エージェント)")
        self.console.print("  [2] データ取得            (Agent 1-3)")
        self.console.print("  [3] 特徴量生成            (Agent 4)")
        self.console.print("  [4] 分析                  (Agent 5-8)")
        self.console.print("  [5] オッズ評価            (Agent 9-10)")
        self.console.print("  [6] 予想生成              (Agent 11-12)")
        self.console.print("  [7] 記事生成              (Agent 13-16)")
        self.console.print("  [8] ML学習")
        self.console.print("  [s] 現在の状況確認")
        self.console.print("  [r] レース変更")
        self.console.print("  [q] 終了")
        return Prompt.ask("\n選択", choices=[
            "1", "2", "3", "4", "5", "6", "7", "8", "s", "r", "q",
        ], default="q")

    def _handle_choice(self, choice: str) -> bool:
        """選択肢を処理。False で終了。"""
        # ワークフロー系
        wf_key = MENU_WORKFLOW_MAP.get(choice)
        if wf_key:
            self._run_workflow(wf_key)
            return True

        # その他
        if choice == "8":
            self._run_training()
            return True
        if choice == "s":
            self._show_status()
            return True
        if choice == "r":
            self._change_race_prompt()
            return True
        if choice == "q":
            return False
        return True

    # ----------------------------------------------------------------
    # ワークフロー実行
    # ----------------------------------------------------------------

    def _run_workflow(self, workflow_key: str) -> None:
        """指定ワークフローを実行"""
        name, stage_names = WORKFLOWS[workflow_key]

        # 完了済みを除外
        pending = [n for n in stage_names if n not in self.completed]
        if not pending:
            self.console.print(f"\n[green]✅ 「{name}」は全ステージ完了済みです。[/green]")
            return

        # 前提チェック
        missing = self._collect_missing_prerequisites(pending)
        missing_outside = [m for m in missing if m not in set(pending)]
        if missing_outside:
            if not self._consult_on_prerequisites(missing_outside, name):
                return  # ユーザーが中止
            # 前提を先頭に追加
            pending = missing_outside + pending

        # 実行
        self.console.print(f"\n[bold]▶ 「{name}」を実行します ({len(pending)}ステージ)[/bold]")
        for stage_name in pending:
            if stage_name in self.completed:
                continue
            success = self._execute_stage(stage_name)
            if not success:
                self.console.print(f"[red]❌ ステージ {stage_name} で失敗しました。[/red]")
                return

        self.console.print(f"\n[bold green]✅ 「{name}」完了しました。[/bold green]")
        self._show_workflow_summary(workflow_key)

    def _execute_stage(self, stage_name: str) -> bool:
        """単一ステージを実行"""
        stage = self.stage_map.get(stage_name)
        if not stage:
            self.logger.error(f"Unknown stage: {stage_name}")
            return False

        # 並列グループ検出
        if stage.parallel_group and stage_name not in self.completed:
            peers = [
                s for s in self.stages
                if s.parallel_group == stage.parallel_group
                and s.name not in self.completed
            ]
            if len(peers) > 1:
                return self._execute_parallel_group(peers)

        # 単体実行
        self.console.print(f"  🏃 {stage_name} ...", end=" ")
        self.context.current_stage = stage_name
        self.context = stage.agent.execute(self.context)

        if self.context.status == "failed":
            self.console.print("[red]失敗[/red]")
            return False

        self.completed.add(stage_name)
        dur = self._last_duration()
        self.console.print(f"[green]完了[/green] ({dur:.1f}s)")

        # QAリトライ
        if stage_name == "qa" and self.context.qa_report:
            return self._handle_qa_result()

        return True

    def _execute_parallel_group(self, stages: list[PipelineStage]) -> bool:
        """並列ステージを実行"""
        names = [s.name for s in stages]
        self.console.print(f"  🏃 {' | '.join(names)} (並列) ...", end=" ")

        with ThreadPoolExecutor(max_workers=len(stages)) as pool:
            futures = {}
            for stage in stages:
                ctx_copy = deepcopy(self.context)
                ctx_copy.current_stage = stage.name
                future = pool.submit(stage.agent.execute, ctx_copy)
                futures[future] = stage

            for future in as_completed(futures):
                stage = futures[future]
                try:
                    result_ctx = future.result()
                    self._merge_context(result_ctx, stage.name)
                    self.completed.add(stage.name)
                except Exception as e:
                    self.logger.error(f"Parallel stage {stage.name} failed: {e}")
                    self.console.print(f"[red]失敗 ({stage.name})[/red]")
                    self.context.status = "failed"
                    return False

        self.console.print("[green]完了[/green]")
        return True

    def _merge_context(self, result: PipelineContext, stage_name: str) -> None:
        """並列実行結果をメインcontextにマージ"""
        field_map = {
            "python_analysis": "analysis",
            "ml_analysis": "ml_analysis",
            "web_research": "web_research",
        }
        field = field_map.get(stage_name)
        if field:
            setattr(self.context, field, getattr(result, field, None))
        if result.agent_results:
            self.context.agent_results.append(result.agent_results[-1])

    # ----------------------------------------------------------------
    # 前提チェック
    # ----------------------------------------------------------------

    def _collect_missing_prerequisites(self, stage_names: list[str]) -> list[str]:
        """指定ステージに必要な未完了前提を再帰的に収集（パイプライン順）"""
        needed = set(stage_names)
        # 前提を再帰的に展開
        changed = True
        while changed:
            changed = False
            for s in self.stages:
                if s.name in needed:
                    for dep in s.depends_on:
                        if dep not in needed:
                            needed.add(dep)
                            changed = True
        # パイプライン順で未完了のみ返す
        return [
            s.name for s in self.stages
            if s.name in needed and s.name not in self.completed
        ]

    def _consult_on_prerequisites(self, missing: list[str], workflow_name: str) -> bool:
        """前提不足をユーザーに相談"""
        self.console.print()
        self.console.print(Panel(
            f"⚠️ 「{workflow_name}」には以下のステージが未完了です:\n"
            + "\n".join(f"  • {m}" for m in missing),
            title="前提チェック",
            border_style="yellow",
        ))
        proceed = Confirm.ask("先に実行しますか？", default=True)
        if not proceed:
            self.console.print("[yellow]中止しました。[/yellow]")
        return proceed

    # ----------------------------------------------------------------
    # QAリトライ
    # ----------------------------------------------------------------

    def _handle_qa_result(self) -> bool:
        """QA結果を確認し、必要ならリトライ"""
        report = self.context.qa_report
        if report.get("passed", False):
            return True

        score = report.get("total_score", 0)
        route_to = report.get("route_back_to", "")
        self.console.print()
        self.console.print(Panel(
            f"QA不合格: {score}/120点\n"
            f"差し戻し先: {route_to}",
            border_style="red",
        ))

        if not Confirm.ask("リトライしますか？", default=True):
            return True  # リトライしないが失敗とはしない

        # 差し戻し先以降をリセット
        self._reset_from(route_to)
        return True

    def _reset_from(self, route_to: str) -> None:
        """指定ステージ以降をリセット"""
        stage_names = [s.name for s in self.stages]
        if route_to not in stage_names:
            return
        start_idx = stage_names.index(route_to)
        for name in stage_names[start_idx:]:
            self.completed.discard(name)
        self.context.status = "running"
        self.console.print(f"[yellow]🔄 {route_to} 以降をリセットしました。[/yellow]")

    # ----------------------------------------------------------------
    # 結果表示
    # ----------------------------------------------------------------

    def _show_workflow_summary(self, workflow_key: str) -> None:
        """ワークフロー完了後のサマリ表示"""
        ctx = self.context

        if workflow_key in ("full", "prediction") and ctx.prediction_actual:
            self._show_prediction_summary()

        if workflow_key in ("full", "prediction") and ctx.backtest:
            self._show_backtest_summary()

        if workflow_key in ("full", "publish") and ctx.qa_report:
            self._show_qa_summary()

        if workflow_key in ("full", "publish") and ctx.note_article:
            note = ctx.note_article
            self.console.print(f"\n📝 記事: {note.get('title', '')}")
            self.console.print(f"   文字数: {note.get('word_count', 0)}")

    def _show_prediction_summary(self) -> None:
        """予想サマリ表示"""
        pred = self.context.prediction_actual
        if not pred:
            return

        self.console.print()
        self.console.rule("[bold]🎯 予想サマリ[/bold]")

        if pred.get("skip_recommended"):
            self.console.print(f"  ⚠️ 見送り推奨: {pred.get('skip_reason', '')}")
            return

        for key in ["win_prediction", "place_prediction", "quinella_prediction", "trifecta_prediction"]:
            bet = pred.get(key)
            if bet:
                risk = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(bet.get("risk_level", "medium"), "🟡")
                horses = ", ".join(bet.get("horse_names", []))
                self.console.print(f"  {risk} {bet['bet_type']}: {horses}")

    def _show_backtest_summary(self) -> None:
        """バックテスト結果表示"""
        bt = self.context.backtest
        if not bt:
            return
        self.console.print(f"\n📈 バックテスト: {bt['total_races']}レース")
        self.console.print(f"   的中率: {bt['hit_rate']:.1%}")
        self.console.print(f"   ROI: {bt['roi']:.1%}")

    def _show_qa_summary(self) -> None:
        """QA結果表示"""
        report = self.context.qa_report
        if not report:
            return
        passed = "✅ 通過" if report.get("passed") else "❌ 不合格"
        self.console.print(f"\n🔍 QA採点: {report['total_score']}/120  {passed}")

    def _show_status(self) -> None:
        """現在の進捗を表示"""
        table = Table(title=f"進捗状況 - {self.race_id}")
        table.add_column("#", style="dim", width=3)
        table.add_column("ステージ", style="cyan")
        table.add_column("状態", width=6)
        table.add_column("出力", style="dim")

        output_fields = {
            "historical_data": "historical_data",
            "current_data": "current_race_data",
            "quality_check": "quality_check",
            "feature_gen": "features",
            "python_analysis": "analysis",
            "ml_analysis": "ml_analysis",
            "web_research": "web_research",
            "evidence": "evidence",
            "predicted_odds": "predicted_odds_eval",
            "actual_odds": "actual_odds_eval",
            "prediction": "prediction_actual",
            "backtest": "backtest",
            "visualization": "eda_images",
            "note_research": "note_suggestion",
            "note_write": "note_article",
            "qa": "qa_report",
        }

        for i, stage in enumerate(self.stages, 1):
            done = stage.name in self.completed
            status = "[green]✅[/green]" if done else "[dim]⬚[/dim]"
            field = output_fields.get(stage.name, "")
            has_output = bool(getattr(self.context, field, None)) if field else False
            output_str = "あり" if has_output else ""
            table.add_row(str(i), stage.name, status, output_str)

        self.console.print()
        self.console.print(table)

    # ----------------------------------------------------------------
    # セッション管理
    # ----------------------------------------------------------------

    def _change_race_prompt(self) -> None:
        """レース変更プロンプト"""
        new_id = Prompt.ask("新しいレースID", default=self.race_id)
        if new_id == self.race_id:
            return
        self.race_id = new_id
        self.context = self._init_context(new_id)
        self.completed.clear()
        self.console.print(f"[green]🔄 レースを {new_id} に変更しました。[/green]")

    def _run_training(self) -> None:
        """ML学習を実行"""
        source = Prompt.ask("データソース", choices=["sample", "production", "jrvan"], default="sample")
        trials = Prompt.ask("Optuna試行数", default="100")

        self.console.print(f"\n[bold]🏁 ML学習を開始します (source={source}, trials={trials})[/bold]")

        # データソース構築
        if source == "sample":
            from keiba.data.sample.sample_source import SampleDataSource
            ds = SampleDataSource()
        elif source == "jrvan":
            from keiba.data.jrvan.data_source import JrVanDataSource
            ds = JrVanDataSource(self.config)
        else:
            from keiba.data.production.production_source import ProductionDataSource
            ds = ProductionDataSource(self.config)

        from keiba.ml.trainer import LightGBMTrainer
        trainer = LightGBMTrainer(ds, self.config)

        try:
            report = trainer.train(optuna_trials=int(trials))
            self.console.print(f"\n[bold green]✅ 学習完了[/bold green]")
            self.console.print(f"  学習サンプル: {report['train_samples']:,}")
            self.console.print(f"  検証AUC: {report['val_auc']:.4f}")
            if report.get("test_auc"):
                self.console.print(f"  テストAUC: {report['test_auc']:.4f}")
        except Exception as e:
            self.console.print(f"\n[red]❌ 学習失敗: {e}[/red]")

    def _save_outputs(self, output_dir: str = "output") -> None:
        """成果物を保存"""
        from keiba.orchestration.orchestrator import Orchestrator
        orch = Orchestrator.__new__(Orchestrator)
        orch.config = self.config
        orch.logger = self.logger
        orch.save_outputs(self.context, output_dir)

    # ----------------------------------------------------------------
    # ヘルパー
    # ----------------------------------------------------------------

    def _init_context(self, race_id: str) -> PipelineContext:
        return PipelineContext(
            pipeline_id=str(uuid4()),
            race_id=race_id,
            started_at=datetime.now(),
            current_stage="initialized",
        )

    def _last_duration(self) -> float:
        """最後のエージェント結果から所要時間を取得"""
        if self.context.agent_results:
            return self.context.agent_results[-1].get("duration_seconds", 0.0)
        return 0.0
