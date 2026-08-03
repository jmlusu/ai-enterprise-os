"""Phase 2 (wave 2b) operational endpoints — reads + guarded writes.

Extends the v1 contract with the generate -> review -> validate -> approve
loop and the R5 telemetry surfaces:

Read (no auth, same as the rest of the GET contract):

- ``GET /api/generate/runs``, ``GET /api/generate/runs/{run_id}``,
  ``GET /api/generate/runs/{run_id}/log`` — generate run history + live logs
- ``GET /api/decisions``, ``GET /api/decisions/{decision_id}`` — approval inbox
- ``GET /api/validate/{artifact}`` — per-artifact validation passes
- ``GET /api/company`` — registry file list
- ``GET /api/telemetry/metrics``, ``GET /api/telemetry/providers`` — R5 panels
- ``GET /api/telemetry/sessions`` — OpenCode session checkpoints (sprint 5.5 P2)

Write (bearer token + CSRF + audit, identical contract to wave 2a via the
shared :class:`WriteGuard`):

- ``POST /api/generate``, ``POST /api/generate/{run_id}/cancel``
- ``POST /api/decisions``, ``POST /api/decisions/{decision_id}/approve``,
  ``.../reject``, ``.../escalate``, ``.../cancel``
- ``POST /api/graph/export``, ``POST /api/company/departments``,
  ``DELETE /api/company/departments/{name}``, ``PATCH /api/company/manifest``
- ``POST /api/agents/sync``, ``POST /api/backup``,
  ``POST /api/telemetry/metrics`` (snapshot persistence),
  ``POST /api/telemetry/session`` (OpenCode session checkpoint)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from ai_company.api.auth import (
    DEFAULT_AUDIT_FAILED_FILE,
    CsrfService,
    WriteTokenService,
)
from ai_company.api.guards import WriteGuard
from ai_company.services.runtime_facade import RuntimeFacade

__all__ = ["register_operational_endpoints"]

_REASON_MAX = 500


# ── request bodies ─────────────────────────────────────────────────────────


class GenerateStartBody(BaseModel):
    """Dispatch a generate run (target + optional operator reason)."""

    target: str = Field(..., min_length=1, max_length=100)
    reason: str | None = Field(default=None, max_length=_REASON_MAX)


class DecisionCreateBody(BaseModel):
    """Create a decision for the approval inbox."""

    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=4000)
    category: str = Field(default="operational", max_length=50)
    priority: str = Field(default="medium", max_length=20)
    requester: str = Field(default="dashboard", max_length=100)
    owner: str = Field(default="", max_length=100)
    options: list[dict[str, Any]] = Field(default_factory=list)


class DecisionApproveBody(BaseModel):
    """Approve a decision by selecting an option."""

    selected_option: str = Field(..., min_length=1, max_length=200)
    rationale: str = Field(..., min_length=1, max_length=2000)
    approved_by: str = Field(default="dashboard-operator", max_length=100)


class DecisionActionBody(BaseModel):
    """Reasoned decision action (reject / cancel)."""

    reason: str = Field(..., min_length=1, max_length=_REASON_MAX)


class DecisionEscalateBody(BaseModel):
    """Escalation note for a decision."""

    note: str = Field(default="", max_length=_REASON_MAX)


class DepartmentAddBody(BaseModel):
    """Add a department (role title + optional description)."""

    name: str = Field(..., min_length=1, max_length=100)
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=500)


class ManifestUpdateBody(BaseModel):
    """Update manifest metadata in ``config/company/company.yaml``."""

    name: str | None = Field(default=None, max_length=300)
    company_name: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=2000)


class AgentsSyncBody(BaseModel):
    """Agent sync options."""

    scope: str = Field(default="both", pattern="^(project|global|both)$")
    force: bool = False


class BackupBody(BaseModel):
    """Backup options."""

    dest_dir: str = Field(default="backups", max_length=500)


class GraphExportBody(BaseModel):
    """Graph export options."""

    output_dir: str = Field(default="generated", max_length=500)


class SessionTelemetryBody(BaseModel):
    """One OpenCode session checkpoint (sprint 5.5 P2 plugin payload).

    ``session_id`` is required; the rest are the plugin's captured counters
    (already non-negative) plus last-seen model/provider metadata. Numeric
    fields are clamped to their non-negative domain by validation.
    """

    session_id: str = Field(..., min_length=1, max_length=200)
    started_at: str | None = Field(default=None, max_length=64)
    updated_at: str | None = Field(default=None, max_length=64)
    end_reason: str = Field(default="checkpoint", max_length=50)
    title: str = Field(default="", max_length=500)
    directory: str = Field(default="", max_length=1000)
    project_id: str | None = Field(default=None, max_length=200)
    agent: str | None = Field(default=None, max_length=200)
    model_id: str | None = Field(default=None, max_length=200)
    provider_id: str | None = Field(default=None, max_length=200)
    messages_user: int = Field(default=0, ge=0)
    messages_assistant: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    commands_run: int = Field(default=0, ge=0)
    tools_used: dict[str, int] = Field(default_factory=dict)
    tokens_input: int = Field(default=0, ge=0)
    tokens_output: int = Field(default=0, ge=0)
    tokens_reasoning: int = Field(default=0, ge=0)
    cost: float = Field(default=0.0, ge=0.0)
    additions: int = Field(default=0, ge=0)
    deletions: int = Field(default=0, ge=0)
    files_changed: int = Field(default=0, ge=0)


# ── registration ──────────────────────────────────────────────────────────


def register_operational_endpoints(
    app: FastAPI,
    *,
    facade: RuntimeFacade,
    tokens: WriteTokenService,
    csrf: CsrfService,
    require_loopback_token: bool = False,
    audit_failed_file: Path = DEFAULT_AUDIT_FAILED_FILE,
) -> None:
    """Register Phase 2 (wave 2b) endpoints on ``app``."""
    guard = WriteGuard(
        tokens=tokens,
        csrf=csrf,
        bus=facade.event_bus,
        require_loopback_token=require_loopback_token,
        audit_failed_file=audit_failed_file,
    )

    # ── generate loop (reads) ──────────────────────────────────────────────

    @app.get("/api/generate/runs", tags=["generate"])
    async def generate_runs(
        limit: int = Query(default=50, ge=1, le=500),
    ) -> dict[str, Any]:
        """Recent generate runs (newest first)."""
        return await run_in_threadpool(facade.generate_runs, limit)

    @app.get("/api/generate/runs/{run_id}", tags=["generate"])
    async def generate_run(run_id: str) -> dict[str, Any]:
        """One generate run."""
        result = await run_in_threadpool(facade.generate_run, run_id)
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("errors", []))
        return result

    @app.get("/api/generate/runs/{run_id}/log", tags=["generate"])
    async def generate_log(
        run_id: str,
        max_lines: int = Query(default=400, ge=1, le=2000),
    ) -> dict[str, Any]:
        """Tail of a run's streamed log (live view)."""
        result = await run_in_threadpool(facade.generate_log, run_id, max_lines)
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("errors", []))
        return result

    # ── approval inbox (reads) ─────────────────────────────────────────────

    @app.get("/api/decisions", tags=["decisions"])
    async def decisions_list(
        status: str | None = Query(default=None),
        category: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict[str, Any]:
        """Decisions for the approval inbox (filterable)."""
        return await run_in_threadpool(facade.decisions_list, status, category, limit)

    @app.get("/api/decisions/{decision_id}", tags=["decisions"])
    async def decision_get(decision_id: str) -> dict[str, Any]:
        """One decision with its explainability summary."""
        result = await run_in_threadpool(facade.decision_get, decision_id)
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("errors", []))
        return result

    # ── per-artifact validation (reads) ────────────────────────────────────

    @app.get("/api/validate/{artifact}", tags=["validation"])
    async def validate_artifact(artifact: str) -> dict[str, Any]:
        """Run one validation pass (yaml|registry|templates|manifest|output|all)."""
        result = await run_in_threadpool(facade.validate_artifacts, artifact)
        if artifact not in (
            "all",
            "yaml",
            "registry",
            "templates",
            "manifest",
            "output",
        ):
            raise HTTPException(status_code=404, detail=result.get("errors", []))
        return result

    # ── company registry files (read) ──────────────────────────────────────

    @app.get("/api/company", tags=["company"])
    async def company_files() -> dict[str, Any]:
        """List the registry YAML files backing the company."""
        return await run_in_threadpool(facade.company_files)

    # ── R5 telemetry (reads) ───────────────────────────────────────────────

    @app.get("/api/telemetry/metrics", tags=["telemetry"])
    async def telemetry_metrics(
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict[str, Any]:
        """Persisted metrics history summary (KPI panel data)."""
        return await run_in_threadpool(facade.metrics_history_summary, limit)

    @app.get("/api/telemetry/providers", tags=["telemetry"])
    async def telemetry_providers(
        limit: int = Query(default=500, ge=1, le=5000),
    ) -> dict[str, Any]:
        """Provider usage aggregated by model (Model Usage panel data)."""
        return await run_in_threadpool(facade.provider_usage_summary, limit)

    @app.get("/api/alerts", tags=["telemetry"])
    async def alerts(
        limit: int = Query(default=200, ge=1, le=1000),
    ) -> dict[str, Any]:
        """Open isolation alerts + recent tail (System Health red chip data)."""
        return await run_in_threadpool(facade.alerts_summary, limit)

    @app.get("/api/telemetry/retention", tags=["telemetry"])
    async def telemetry_retention() -> dict[str, Any]:
        """Retention dry-run report (raw/expired/rollup counts per source)."""
        return await run_in_threadpool(facade.retention_status)

    @app.get("/api/telemetry/sessions", tags=["telemetry"])
    async def telemetry_sessions(
        limit: int = Query(default=200, ge=1, le=5000),
    ) -> dict[str, Any]:
        """OpenCode session checkpoints (Sessions panel data, sprint 5.5 P2)."""
        return await run_in_threadpool(facade.session_telemetry_summary, limit)

    @app.get("/api/backup", tags=["backup"])
    async def backup_status() -> dict[str, Any]:
        """Existing backup archives (newest first) for the R6 tile."""
        return await run_in_threadpool(facade.backup_status)

    # ── generate loop (writes) ─────────────────────────────────────────────

    @app.post("/api/generate", tags=["generate", "write"])
    async def generate_start(
        body: GenerateStartBody,
        _: None = Depends(guard.guard("generate.start")),
    ) -> dict[str, Any]:
        """Dispatch a generate run (streams via run history + log)."""
        result = await run_in_threadpool(
            facade.generate_start, body.target, body.reason or ""
        )
        return guard.audited(
            result, "generate.start", reason=body.reason, extra={"target": body.target}
        )

    @app.post("/api/generate/{run_id}/cancel", tags=["generate", "write"])
    async def generate_cancel(
        run_id: str,
        _: None = Depends(guard.guard("generate.cancel")),
    ) -> dict[str, Any]:
        """Cancel a running generate dispatch."""
        result = await run_in_threadpool(facade.generate_cancel, run_id)
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("errors", []))
        return guard.audited(result, "generate.cancel", extra={"run_id": run_id})

    # ── approval inbox (writes) ────────────────────────────────────────────

    @app.post("/api/decisions", tags=["decisions", "write"])
    async def decision_create(
        body: DecisionCreateBody,
        _: None = Depends(guard.guard("decision.create")),
    ) -> dict[str, Any]:
        """Create a decision for the approval inbox."""
        result = await run_in_threadpool(
            facade.decision_create,
            body.title,
            body.description,
            body.category,
            body.priority,
            body.requester,
            body.owner,
            body.options,
        )
        return guard.audited(result, "decision.create", extra={"title": body.title})

    @app.post("/api/decisions/{decision_id}/approve", tags=["decisions", "write"])
    async def decision_approve(
        decision_id: str,
        body: DecisionApproveBody,
        _: None = Depends(guard.guard("decision.approve")),
    ) -> dict[str, Any]:
        """Approve a decision by selecting an option."""
        result = await run_in_threadpool(
            facade.decision_approve,
            decision_id,
            body.selected_option,
            body.rationale,
            body.approved_by,
        )
        if not result.get("success"):
            raise HTTPException(status_code=409, detail=result.get("errors", []))
        return guard.audited(
            result, "decision.approve", extra={"decision_id": decision_id}
        )

    @app.post("/api/decisions/{decision_id}/reject", tags=["decisions", "write"])
    async def decision_reject(
        decision_id: str,
        body: DecisionActionBody,
        _: None = Depends(guard.guard("decision.reject")),
    ) -> dict[str, Any]:
        """Reject a pending decision (reason required)."""
        result = await run_in_threadpool(
            facade.decision_reject, decision_id, body.reason
        )
        if not result.get("success"):
            raise HTTPException(status_code=409, detail=result.get("errors", []))
        return guard.audited(
            result,
            "decision.reject",
            reason=body.reason,
            extra={"decision_id": decision_id},
        )

    @app.post("/api/decisions/{decision_id}/escalate", tags=["decisions", "write"])
    async def decision_escalate(
        decision_id: str,
        body: DecisionEscalateBody,
        _: None = Depends(guard.guard("decision.escalate")),
    ) -> dict[str, Any]:
        """Escalate a decision to the next approval level."""
        result = await run_in_threadpool(
            facade.decision_escalate, decision_id, body.note
        )
        if not result.get("success"):
            raise HTTPException(status_code=409, detail=result.get("errors", []))
        return guard.audited(
            result, "decision.escalate", extra={"decision_id": decision_id}
        )

    @app.post("/api/decisions/{decision_id}/cancel", tags=["decisions", "write"])
    async def decision_cancel(
        decision_id: str,
        body: DecisionActionBody,
        _: None = Depends(guard.guard("decision.cancel")),
    ) -> dict[str, Any]:
        """Cancel a pending decision (reason required)."""
        result = await run_in_threadpool(
            facade.decision_cancel, decision_id, body.reason
        )
        if not result.get("success"):
            raise HTTPException(status_code=409, detail=result.get("errors", []))
        return guard.audited(
            result,
            "decision.cancel",
            reason=body.reason,
            extra={"decision_id": decision_id},
        )

    # ── graph export / company CRUD / agents / backup (writes) ─────────────

    @app.post("/api/graph/export", tags=["graph", "write"])
    async def graph_export(
        body: GraphExportBody,
        _: None = Depends(guard.guard("graph.export")),
    ) -> dict[str, Any]:
        """Export the company graph (Mermaid + JSON) to disk."""
        result = await run_in_threadpool(facade.graph_export_write, body.output_dir)
        return guard.audited(
            result, "graph.export", extra={"output_dir": body.output_dir}
        )

    @app.post("/api/company/departments", tags=["company", "write"])
    async def company_department_add(
        body: DepartmentAddBody,
        _: None = Depends(guard.guard("company.department.add")),
    ) -> dict[str, Any]:
        """Add a department (registry YAML + manifest)."""
        result = await run_in_threadpool(
            facade.company_department_add, body.name, body.title, body.description
        )
        if not result.get("success"):
            raise HTTPException(status_code=409, detail=result.get("errors", []))
        return guard.audited(
            result, "company.department.add", extra={"name": body.name}
        )

    @app.delete("/api/company/departments/{name}", tags=["company", "write"])
    async def company_department_remove(
        name: str,
        request: Request,
        _: None = Depends(guard.guard("company.department.remove")),
    ) -> dict[str, Any]:
        """Remove a department (registry YAML + manifest)."""
        reason = request.query_params.get("reason", "")
        result = await run_in_threadpool(facade.company_department_remove, name)
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("errors", []))
        return guard.audited(
            result,
            "company.department.remove",
            reason=reason or None,
            extra={"name": name},
        )

    @app.patch("/api/company/manifest", tags=["company", "write"])
    async def company_manifest_update(
        body: ManifestUpdateBody,
        _: None = Depends(guard.guard("company.manifest.update")),
    ) -> dict[str, Any]:
        """Update manifest metadata."""
        result = await run_in_threadpool(
            facade.company_manifest_update,
            body.name,
            body.company_name,
            body.description,
        )
        return guard.audited(result, "company.manifest.update")

    @app.post("/api/agents/sync", tags=["agents", "write"])
    async def agents_sync(
        body: AgentsSyncBody,
        _: None = Depends(guard.guard("agents.sync")),
    ) -> dict[str, Any]:
        """Sync persona agents into opencode (project/global/both)."""
        result = await run_in_threadpool(facade.agents_sync, body.scope, body.force)
        return guard.audited(result, "agents.sync", extra={"scope": body.scope})

    @app.post("/api/backup", tags=["backup", "write"])
    async def backup_create(
        body: BackupBody,
        _: None = Depends(guard.guard("backup.create")),
    ) -> dict[str, Any]:
        """Create a timestamped backup archive."""
        result = await run_in_threadpool(facade.backup_create, body.dest_dir)
        return guard.audited(result, "backup.create", extra={"dest_dir": body.dest_dir})

    @app.post("/api/telemetry/metrics", tags=["telemetry", "write"])
    async def telemetry_metrics_persist(
        _: None = Depends(guard.guard("telemetry.metrics.persist")),
    ) -> dict[str, Any]:
        """Snapshot current runtime metrics into the persisted history."""
        result = await run_in_threadpool(facade.metrics_persist)
        return guard.audited(result, "telemetry.metrics.persist")

    @app.post("/api/telemetry/session", tags=["telemetry", "write"])
    async def telemetry_session_persist(
        body: SessionTelemetryBody,
        _: None = Depends(guard.guard("telemetry.session.persist")),
    ) -> dict[str, Any]:
        """Persist one OpenCode session checkpoint (sprint 5.5 P2 plugin).

        Not a high-impact action (ADR 0010 §5) — no reason is required — but
        it rides the same bearer-token + CSRF + audit guard as every other
        mutation and publishes ``audit.write`` on success.
        """
        result = await run_in_threadpool(
            facade.session_telemetry_record, body.model_dump()
        )
        return guard.audited(
            result,
            "telemetry.session.persist",
            extra={"session_id": body.session_id, "end_reason": body.end_reason},
        )
