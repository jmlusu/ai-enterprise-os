"""Phase 2 (wave 2a) write endpoints — auth + CSRF + audit guarded (ADR 0010).

Every mutation endpoint:

1. passes the write guard dependency (bearer token per loopback policy +
   ``X-CSRF-Token`` synchronizer check), which publishes ``audit.write_rejected``
   on any failure (without exposing the submitted token/CSRF);
2. enforces the ADR reason requirement for high-impact actions;
3. calls the shared facade write adapter (ADR 0003) off the event loop; and
4. publishes an ``audit.write`` event on completion (fail-open).

Also registers the read helpers the operational dashboard needs:
``GET /api/write-csrf`` (synchronizer token) and
``GET /api/audit/writes`` (Write History panel data).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from ai_company.api.auth import (
    DEFAULT_AUDIT_FAILED_FILE,
    CsrfService,
    WriteTokenService,
    host_allowed,
    publish_write_audit,
    publish_write_rejected,
)
from ai_company.events import Event, EventType, ReplayRequest
from ai_company.services.runtime_facade import RuntimeFacade

__all__ = ["HIGH_IMPACT_ACTIONS", "register_write_endpoints"]

#: Actions that must carry a human-provided reason (ADR 0010 §5).
HIGH_IMPACT_ACTIONS: frozenset[str] = frozenset(
    {
        "runtime.stop",
        "runtime.restart",
        "runtime.recover",
        "runtime.unisolate",
        "orchestrate.rollback",
    }
)

_REASON_MAX = 500


# ── request bodies ─────────────────────────────────────────────────────────


class ReasonBody(BaseModel):
    """Optional reason attached to a write action."""

    reason: str | None = Field(default=None, max_length=_REASON_MAX)


class EngineActionBody(BaseModel):
    """Engine-scoped action (recover / un-isolate)."""

    engine: str = Field(..., min_length=1, max_length=200)
    reason: str | None = Field(default=None, max_length=_REASON_MAX)


class PlanBody(BaseModel):
    """Plan-scoped action."""

    plan_id: str = Field(..., min_length=1, max_length=200)


class PlanCreateBody(BaseModel):
    """Create an orchestration plan (exactly one of name/yaml_path/data)."""

    name: str | None = Field(default=None, max_length=200)
    yaml_path: str | None = Field(default=None, max_length=500)
    data: dict[str, Any] | None = None
    description: str = Field(default="", max_length=500)


class ResumeBody(BaseModel):
    """Resume a paused pipeline, optionally from a checkpoint."""

    plan_id: str = Field(..., min_length=1, max_length=200)
    checkpoint_id: str | None = Field(default=None, max_length=200)


class RollbackBody(BaseModel):
    """Roll back a pipeline (high-impact: reason required)."""

    plan_id: str = Field(..., min_length=1, max_length=200)
    reason: str = Field(default="manual rollback", max_length=_REASON_MAX)


class MemorySaveBody(BaseModel):
    """Save a memory entry."""

    content: dict[str, Any]
    memory_type: str | None = Field(default=None, max_length=50)
    namespace: str | None = Field(default=None, max_length=50)
    tags: list[str] = Field(default_factory=list)
    source: str = Field(default="dashboard", max_length=100)
    importance: float | None = Field(default=None, ge=0.0, le=1.0)


class MemoryUpdateBody(BaseModel):
    """Update a memory entry."""

    memory_id: str = Field(..., min_length=1, max_length=200)
    content: dict[str, Any] | None = None
    tags: list[str] | None = None
    importance: float | None = Field(default=None, ge=0.0, le=1.0)


class MemorySnapshotBody(BaseModel):
    """Create a memory snapshot."""

    name: str | None = Field(default=None, max_length=200)


class MemoryRestoreBody(BaseModel):
    """Restore memory from a snapshot."""

    snapshot_id: str = Field(..., min_length=1, max_length=200)


class ReportGenerateBody(BaseModel):
    """Generate a report on demand."""

    report_type: str = Field(default="summary", pattern="^(summary|detailed|health)$")


# ── registration ──────────────────────────────────────────────────────────


def register_write_endpoints(
    app: FastAPI,
    *,
    facade: RuntimeFacade,
    tokens: WriteTokenService,
    csrf: CsrfService,
    require_loopback_token: bool = False,
    audit_failed_file: Path = DEFAULT_AUDIT_FAILED_FILE,
) -> None:
    """Register Phase 2 (wave 2a) write endpoints on ``app``."""
    bus = facade.event_bus
    failed_path = audit_failed_file

    def _reject(action: str, reason: str, detail: str | None = None) -> None:
        if bus is not None:
            publish_write_rejected(
                bus,
                action=action,
                reason=reason,
                detail=detail,
                failed_path=failed_path,
            )

    def guard_factory(action: str) -> Callable[[Request], None]:
        """Build a dependency enforcing token + CSRF for ``action``."""

        def _require_write_auth(request: Request) -> None:
            host = request.headers.get("host", "")
            loopback = host_allowed(host)
            token_required = (not loopback) or require_loopback_token
            auth_header = request.headers.get("authorization", "")
            token = (
                auth_header[7:].strip()
                if auth_header.lower().startswith("bearer ")
                else None
            )
            if token is not None:
                if not tokens.verify(token):
                    _reject(action, "unauthorized", "invalid token")
                    raise HTTPException(status_code=401, detail="invalid write token")
            elif token_required:
                _reject(action, "unauthorized", "missing token")
                raise HTTPException(status_code=401, detail="write token required")
            csrf_value = request.headers.get("x-csrf-token")
            if not csrf.verify(csrf_value):
                _reject(action, "csrf_mismatch", "missing or invalid CSRF token")
                raise HTTPException(status_code=403, detail="invalid CSRF token")

        return _require_write_auth

    def _require_reason(action: str, reason: str | None) -> None:
        if action in HIGH_IMPACT_ACTIONS and (not reason or not reason.strip()):
            if bus is not None:
                publish_write_rejected(
                    bus,
                    action=action,
                    reason="missing_reason",
                    detail="reason is required for high-impact action",
                    failed_path=failed_path,
                )
            raise HTTPException(
                status_code=422,
                detail=f"reason is required for high-impact action: {action}",
            )

    def _audited(
        result: dict[str, Any],
        action: str,
        reason: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if bus is not None:
            status = "ok" if result.get("success") else "failed"
            details: dict[str, Any] = dict(extra or {})
            errors = result.get("errors")
            if errors:
                details["errors"] = errors
            publish_write_audit(
                bus,
                action=action,
                result=status,
                reason=reason,
                details=details or None,
                failed_path=failed_path,
            )
        return result

    # ── synchronizer token + write history (read helpers) ────────────────

    @app.get("/api/write-csrf", tags=["write"])
    async def write_csrf() -> dict[str, str]:
        """Per-run CSRF synchronizer token (ADR 0010 §2 — no auth required)."""
        return {"csrf_token": csrf.token}

    @app.get("/api/audit/writes", tags=["write"])
    async def audit_writes(
        limit: int = Query(default=50, ge=1, le=500),
    ) -> dict[str, Any]:
        """Recent write audit events (Write History panel data source)."""
        if bus is None or getattr(bus, "persistence", None) is None:
            return {"events": [], "persistence_enabled": False}
        collected: list[dict[str, Any]] = []

        def _collect(event: Event) -> None:
            if event.metadata.event_type in (
                EventType.AUDIT_WRITE,
                EventType.AUDIT_WRITE_REJECTED,
            ):
                collected.append(event.model_dump(mode="json"))

        replay_limit = max(limit * 10, 200)
        request = ReplayRequest(limit=replay_limit)
        await run_in_threadpool(bus.replay, request, _collect)
        return {
            "events": collected[-limit:],
            "persistence_enabled": True,
            "total": len(collected[-limit:]),
        }

    # ── runtime control (high-impact ops require a reason) ────────────────

    @app.post("/api/runtime/start", tags=["runtime", "write"])
    async def runtime_start(
        body: ReasonBody,
        _: None = Depends(guard_factory("runtime.start")),
    ) -> dict[str, Any]:
        """Start the runtime (auth + audit, ADR 0010)."""
        result = await run_in_threadpool(facade.runtime_start)
        return _audited(result, "runtime.start", reason=body.reason)

    @app.post("/api/runtime/stop", tags=["runtime", "write"])
    async def runtime_stop(
        body: ReasonBody,
        _: None = Depends(guard_factory("runtime.stop")),
    ) -> dict[str, Any]:
        """Stop the runtime (high-impact — reason required)."""
        _require_reason("runtime.stop", body.reason)
        result = await run_in_threadpool(facade.runtime_stop, body.reason or "manual")
        return _audited(result, "runtime.stop", reason=body.reason)

    @app.post("/api/runtime/restart", tags=["runtime", "write"])
    async def runtime_restart(
        body: ReasonBody,
        _: None = Depends(guard_factory("runtime.restart")),
    ) -> dict[str, Any]:
        """Restart the runtime (high-impact — reason required)."""
        _require_reason("runtime.restart", body.reason)
        result = await run_in_threadpool(
            facade.runtime_restart, body.reason or "manual"
        )
        return _audited(result, "runtime.restart", reason=body.reason)

    @app.post("/api/runtime/reload", tags=["runtime", "write"])
    async def runtime_reload(
        body: ReasonBody,
        _: None = Depends(guard_factory("runtime.reload")),
    ) -> dict[str, Any]:
        """Hot-reload runtime configuration."""
        result = await run_in_threadpool(facade.runtime_reload)
        return _audited(result, "runtime.reload", reason=body.reason)

    @app.post("/api/runtime/recover", tags=["runtime", "write"])
    async def runtime_recover(
        body: EngineActionBody,
        _: None = Depends(guard_factory("runtime.recover")),
    ) -> dict[str, Any]:
        """Recover one engine (high-impact — reason required)."""
        _require_reason("runtime.recover", body.reason)
        result = await run_in_threadpool(
            facade.runtime_recover, body.engine, body.reason or "manual"
        )
        return _audited(
            result, "runtime.recover", reason=body.reason, extra={"engine": body.engine}
        )

    @app.post("/api/runtime/unisolate", tags=["runtime", "write"])
    async def runtime_unisolate(
        body: EngineActionBody,
        _: None = Depends(guard_factory("runtime.unisolate")),
    ) -> dict[str, Any]:
        """Un-isolate an engine (high-impact — reason required)."""
        _require_reason("runtime.unisolate", body.reason)
        result = await run_in_threadpool(facade.runtime_unisolate, body.engine)
        return _audited(
            result,
            "runtime.unisolate",
            reason=body.reason,
            extra={"engine": body.engine},
        )

    # ── orchestration ─────────────────────────────────────────────────────

    @app.post("/api/orchestrate/plan", tags=["orchestration", "write"])
    async def orchestrate_plan(
        body: PlanCreateBody,
        _: None = Depends(guard_factory("orchestrate.plan")),
    ) -> dict[str, Any]:
        """Create an orchestration plan from a catalog pipeline, YAML, or dict."""
        result = await run_in_threadpool(
            facade.orchestrate_plan,
            body.name,
            body.yaml_path,
            body.data,
            body.description,
        )
        return _audited(result, "orchestrate.plan")

    @app.post("/api/orchestrate/start", tags=["orchestration", "write"])
    async def orchestrate_start(
        body: PlanBody,
        _: None = Depends(guard_factory("orchestrate.start")),
    ) -> dict[str, Any]:
        """Start a planned pipeline."""
        result = await run_in_threadpool(facade.orchestrate_start, body.plan_id)
        return _audited(result, "orchestrate.start", extra={"plan_id": body.plan_id})

    @app.post("/api/orchestrate/resume", tags=["orchestration", "write"])
    async def orchestrate_resume(
        body: ResumeBody,
        _: None = Depends(guard_factory("orchestrate.resume")),
    ) -> dict[str, Any]:
        """Resume a paused pipeline."""
        result = await run_in_threadpool(
            facade.orchestrate_resume, body.plan_id, body.checkpoint_id
        )
        return _audited(result, "orchestrate.resume", extra={"plan_id": body.plan_id})

    @app.post("/api/orchestrate/retry", tags=["orchestration", "write"])
    async def orchestrate_retry(
        body: PlanBody,
        _: None = Depends(guard_factory("orchestrate.retry")),
    ) -> dict[str, Any]:
        """Retry a failed pipeline."""
        result = await run_in_threadpool(facade.orchestrate_retry, body.plan_id)
        return _audited(result, "orchestrate.retry", extra={"plan_id": body.plan_id})

    @app.post("/api/orchestrate/rollback", tags=["orchestration", "write"])
    async def orchestrate_rollback(
        body: RollbackBody,
        _: None = Depends(guard_factory("orchestrate.rollback")),
    ) -> dict[str, Any]:
        """Roll back a pipeline (high-impact — reason required)."""
        _require_reason("orchestrate.rollback", body.reason)
        result = await run_in_threadpool(
            facade.orchestrate_rollback, body.plan_id, body.reason
        )
        return _audited(
            result,
            "orchestrate.rollback",
            reason=body.reason,
            extra={"plan_id": body.plan_id},
        )

    # ── memory writes ─────────────────────────────────────────────────────

    @app.post("/api/memory/save", tags=["memory", "write"])
    async def memory_save(
        body: MemorySaveBody,
        _: None = Depends(guard_factory("memory.save")),
    ) -> dict[str, Any]:
        """Save a new memory entry."""
        result = await run_in_threadpool(
            facade.memory_save,
            body.content,
            body.memory_type,
            body.namespace,
            body.tags,
            body.source,
            body.importance,
        )
        return _audited(result, "memory.save")

    @app.post("/api/memory/update", tags=["memory", "write"])
    async def memory_update(
        body: MemoryUpdateBody,
        _: None = Depends(guard_factory("memory.update")),
    ) -> dict[str, Any]:
        """Update a memory entry."""
        result = await run_in_threadpool(
            facade.memory_update,
            body.memory_id,
            body.content,
            body.tags,
            body.importance,
        )
        return _audited(result, "memory.update", extra={"memory_id": body.memory_id})

    @app.post("/api/memory/snapshot", tags=["memory", "write"])
    async def memory_snapshot(
        body: MemorySnapshotBody,
        _: None = Depends(guard_factory("memory.snapshot")),
    ) -> dict[str, Any]:
        """Create a memory snapshot."""
        result = await run_in_threadpool(facade.memory_snapshot, body.name)
        return _audited(result, "memory.snapshot")

    @app.post("/api/memory/restore", tags=["memory", "write"])
    async def memory_restore(
        body: MemoryRestoreBody,
        _: None = Depends(guard_factory("memory.restore")),
    ) -> dict[str, Any]:
        """Restore memory from a snapshot."""
        result = await run_in_threadpool(facade.memory_restore, body.snapshot_id)
        return _audited(
            result, "memory.restore", extra={"snapshot_id": body.snapshot_id}
        )

    @app.post("/api/memory/export", tags=["memory", "write"])
    async def memory_export(
        body: ReasonBody,
        _: None = Depends(guard_factory("memory.export")),
    ) -> dict[str, Any]:
        """Export memory to a JSON file (default generated/exports/)."""
        result = await run_in_threadpool(facade.memory_export)
        return _audited(result, "memory.export", reason=body.reason)

    @app.post("/api/memory/{key}/archive", tags=["memory", "write"])
    async def memory_archive(
        key: str,
        body: ReasonBody,
        _: None = Depends(guard_factory("memory.archive")),
    ) -> dict[str, Any]:
        """Archive one memory entry."""
        result = await run_in_threadpool(facade.memory_archive, key)
        return _audited(result, "memory.archive", extra={"memory_id": key})

    @app.post("/api/memory/{key}/unarchive", tags=["memory", "write"])
    async def memory_unarchive(
        key: str,
        body: ReasonBody,
        _: None = Depends(guard_factory("memory.unarchive")),
    ) -> dict[str, Any]:
        """Un-archive one memory entry."""
        result = await run_in_threadpool(facade.memory_unarchive, key)
        return _audited(result, "memory.unarchive", extra={"memory_id": key})

    # ── validation / reports / build / bootstrap ──────────────────────────

    @app.post("/api/validate", tags=["validation", "write"])
    async def validate_run(
        body: ReasonBody,
        _: None = Depends(guard_factory("validate.run")),
    ) -> dict[str, Any]:
        """Run the validation gate as an audited operator action."""
        result = await run_in_threadpool(facade.validate_run)
        return _audited(result, "validate.run", reason=body.reason)

    @app.post("/api/reports/generate", tags=["reports", "write"])
    async def report_generate(
        body: ReportGenerateBody,
        _: None = Depends(guard_factory("reports.generate")),
    ) -> dict[str, Any]:
        """Generate a report on demand (summary/detailed/health)."""
        result = await run_in_threadpool(facade.report_generate_write, body.report_type)
        return _audited(
            result, "reports.generate", extra={"report_type": body.report_type}
        )

    @app.post("/api/build", tags=["build", "write"])
    async def build(
        body: ReasonBody,
        _: None = Depends(guard_factory("build.run")),
    ) -> dict[str, Any]:
        """Run the artifact build pipeline (parity with ``ai-company build``)."""
        result = await run_in_threadpool(facade.build_run)
        return _audited(result, "build.run", reason=body.reason)

    @app.post("/api/bootstrap", tags=["build", "write"])
    async def bootstrap(
        body: ReasonBody,
        _: None = Depends(guard_factory("bootstrap.run")),
    ) -> dict[str, Any]:
        """Scaffold + generate the full company (parity with ``bootstrap``)."""
        result = await run_in_threadpool(facade.bootstrap_run)
        return _audited(result, "bootstrap.run", reason=body.reason)
