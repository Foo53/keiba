"""パイプライン統合テスト"""

import pytest
from keiba.orchestration.orchestrator import Orchestrator
from keiba.data.sample.sample_source import SampleDataSource


class TestFullPipeline:
    def test_pipeline_completes(self):
        orch = Orchestrator(data_source=SampleDataSource())
        ctx = orch.run("20260607-Tokyo-11")
        assert ctx.status == "completed"
        assert len(ctx.agent_results) == 16

    def test_all_outputs_present(self, full_context):
        ctx = full_context
        assert ctx.historical_data is not None
        assert ctx.current_race_data is not None
        assert ctx.quality_check is not None
        assert ctx.features is not None
        assert ctx.analysis is not None
        assert ctx.web_research is not None
        assert ctx.evidence is not None
        assert ctx.predicted_odds_eval is not None
        assert ctx.actual_odds_eval is not None
        assert ctx.prediction_actual is not None
        assert ctx.backtest is not None
        assert ctx.note_suggestion is not None
        assert ctx.note_article is not None
        assert ctx.qa_report is not None

    def test_qa_passes(self, full_context):
        assert full_context.qa_report["passed"] is True
        assert full_context.qa_report["total_score"] >= 100

    def test_no_prohibited_words(self, full_context):
        violations = full_context.note_article.get("prohibited_word_violations", [])
        assert violations == []

    def test_eda_images_generated(self, full_context):
        assert full_context.eda_images is not None
        assert len(full_context.eda_images) > 0

    def test_markdown_contains_chart_references(self, full_context):
        if full_context.eda_images:
            body = full_context.note_article.get("body_markdown", "")
            assert "![" in body

    def test_json_output_saved(self, full_context, tmp_path):
        orch = Orchestrator(data_source=SampleDataSource())
        orch.save_outputs(full_context, str(tmp_path))
        import json
        json_path = tmp_path / "json" / "20260607-Tokyo-11.json"
        assert json_path.exists()
        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert data["race_id"] == "20260607-Tokyo-11"

    def test_markdown_output_saved(self, full_context, tmp_path):
        orch = Orchestrator(data_source=SampleDataSource())
        orch.save_outputs(full_context, str(tmp_path))
        md_path = tmp_path / "markdown" / "20260607-Tokyo-11.md"
        assert md_path.exists()
        content = md_path.read_text(encoding="utf-8")
        assert "自己責任" in content
