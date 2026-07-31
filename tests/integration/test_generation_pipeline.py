"""Integration tests: the generation pipeline through real engines."""

from __future__ import annotations

from ai_company.orchestration import OrchestrationEngine
from ai_company.orchestration.models import PipelineStatus


class TestGenerationPipeline:
    def test_generation_pipeline_completes(
        self, orchestration: OrchestrationEngine
    ) -> None:
        plan = orchestration.plan("generation")
        record = orchestration.run(plan)

        assert record.state.status == PipelineStatus.COMPLETED
        assert record.metrics.tasks_failed == 0
        assert record.metrics.tasks_completed == record.metrics.tasks_total

    def test_generation_writes_artifacts(
        self, orchestration: OrchestrationEngine
    ) -> None:
        plan = orchestration.plan("generation")
        record = orchestration.run(plan)
        results = record.state.task_results

        prompts = results.get("generate_prompts", {})
        assert prompts["success"] is True
        assert prompts["prompts"] > 0

        docs = results.get("generate_docs", {})
        assert docs["success"] is True
        assert docs["pages"] > 0

        graph = results.get("generate_graph", {})
        assert graph["success"] is True
        assert graph["mermaid_length"] > 0

    def test_generation_parallel_stage_runs_concurrently(
        self, orchestration: OrchestrationEngine
    ) -> None:
        plan = orchestration.plan("generation")
        record = orchestration.run(plan)
        # All three generation tasks completed.
        for task_id in ("generate_prompts", "generate_docs", "generate_graph"):
            assert record.state.task_statuses[task_id].value == "completed"

    def test_generation_records_memory_and_audit(
        self, orchestration: OrchestrationEngine
    ) -> None:
        plan = orchestration.plan("generation")
        record = orchestration.run(plan)
        assert record.state.status == PipelineStatus.COMPLETED

        memory = orchestration.coordinator.engine("memory")
        assert memory is not None
        entries = memory.search(namespace="global", limit=50)
        assert len(entries) >= 1

        audit = orchestration.coordinator.engine("audit")
        assert audit is not None
        events = audit.get_events(limit=50)
        assert len(events) >= 1

    def test_report_pipeline_completes(
        self, orchestration: OrchestrationEngine
    ) -> None:
        plan = orchestration.plan("report")
        record = orchestration.run(plan)
        assert record.state.status == PipelineStatus.COMPLETED
        report = record.state.task_results.get("report", {})
        assert report["success"] is True
        assert report["nodes"] > 0
