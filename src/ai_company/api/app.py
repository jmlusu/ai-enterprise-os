"""Dashboard API — read contract v1 + guarded write surface (FastAPI + WebSocket).

ADR 0002: FastAPI + plain uvicorn (no uvloop — Windows-safe). ADR 0009:
contract v1 is REST + WebSocket push. Phase 2 (ADR 0010, wave 2a) adds the
write surface — every mutation is guarded by the bearer token, the per-run
CSRF synchronizer token, and mandatory ``audit.write`` / ``audit.write_rejected``
events. The runtime is thread-based, so every synchronous runtime call is
bridged through ``run_in_threadpool`` and never blocks on runtime locks
directly.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import (
    FastAPI,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ai_company.api.auth import CsrfService, WriteTokenService
from ai_company.api.operational_endpoints import register_operational_endpoints
from ai_company.api.write_endpoints import register_write_endpoints
from ai_company.events import Event, ReplayRequest
from ai_company.services.dashboard_events import DashboardEventBridge
from ai_company.services.runtime_facade import RuntimeFacade

__all__ = ["create_app"]

_SERVICE_NAME = "AI Enterprise OS - Dashboard API"
_SERVICE_VERSION = "1.0.0"

#: Package-relative template + static asset roots (ADR 0008: Jinja2 + htmx).
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_STATIC_DIR = Path(__file__).resolve().parent / "static"

#: Loopback hosts only — DNS-rebinding defense (risk R9, ADR 0009).
_ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})

#: API responses stay locked down (JSON only, nothing to execute).
_API_CSP = b"default-src 'none'"

#: HTML dashboard pages need same-origin scripts/styles plus a loopback
#: WebSocket for the live feed. No CDNs, no unsafe-inline (ADR 0008, R9).
_PAGE_CSP = (
    b"default-src 'self'; "
    b"script-src 'self'; "
    b"style-src 'self'; "
    b"img-src 'self' data:; "
    b"connect-src 'self' ws:; "
    b"font-src 'self'; "
    b"frame-ancestors 'none'; "
    b"base-uri 'none'; "
    b"form-action 'none'"
)

_SECURITY_HEADERS = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"content-security-policy", b"default-src 'none'"),
    (b"referrer-policy", b"no-referrer"),
    (b"cache-control", b"no-store"),
)

#: Application-level heartbeat cadence for idle WebSocket connections.
_WS_HEARTBEAT_SECONDS = 20.0


def _header_value(scope: Scope, name: str) -> str:
    for key, value in scope.get("headers", []):
        if key.decode("latin-1").lower() == name:
            return value.decode("latin-1")
    return ""


def _host_allowed(host: str) -> bool:
    """Return True only for loopback Host headers (with or without port)."""
    host = (host or "").strip().lower()
    if not host:
        return False
    if host.startswith("["):  # IPv6 literal, e.g. "[::1]:8000"
        return host.split("]", 1)[0] + "]" in _ALLOWED_HOSTS
    return host.split(":", 1)[0] in _ALLOWED_HOSTS


class _SecurityMiddleware:
    """Reject non-loopback Host headers and add hardening headers (R9)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        if not _host_allowed(_header_value(scope, "host")):
            if scope["type"] == "websocket":
                await send(
                    {
                        "type": "websocket.close",
                        "code": 1008,
                        "reason": "host header not allowed",
                    }
                )
            else:
                await Response("Host header not allowed", status_code=403)(
                    scope, receive, send
                )
            return

        if scope["type"] == "websocket":
            await self.app(scope, receive, send)
            return

        # Scoped CSP: JSON API stays at default-src 'none'; HTML pages get
        # the dashboard policy (same-origin scripts/styles + loopback ws).
        path = scope.get("path", "")
        page = not path.startswith("/api/")
        csp = _PAGE_CSP if page else _API_CSP
        headers = tuple(
            (b"content-security-policy", csp)
            if name == b"content-security-policy"
            else (name, value)
            for name, value in _SECURITY_HEADERS
        )

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                merged = list(message.get("headers", [])) + list(headers)
                message = {**message, "headers": merged}
            await send(message)

        await self.app(scope, receive, send_with_headers)


def _parse_since(value: str | None) -> datetime | None:
    """Parse an optional ISO-8601 timestamp (``?since=``)."""
    if value is None or value == "":
        return None
    try:
        # datetime.fromisoformat accepts "Z" since Python 3.11 (project >= 3.12).
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="since must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def create_app(
    facade: RuntimeFacade | None = None,
    config_dir: str = "config",
    auto_start: bool = True,
    *,
    tokens: WriteTokenService | None = None,
    csrf_token: str | None = None,
    require_loopback_token: bool = False,
) -> FastAPI:
    """Build the dashboard API application.

    Args:
        facade: Shared runtime facade (built from ``config_dir`` when omitted).
        config_dir: Directory containing ``config/runtime/*.yaml``.
        auto_start: Boot the runtime on startup and stop it on shutdown.
            Tests pass ``False`` and drive the runtime themselves.
        tokens: Write-token service (ADR 0010). Defaults to a service backed
            by ``runtime/.write_token`` (relative to the working directory).
        csrf_token: Fixed per-run CSRF synchronizer token (ADR 0010 §2).
            Tests pass a known value; production derives one at boot.
        require_loopback_token: Demand a valid bearer token even for loopback
            Host headers (ADR 0010 §1 opt-in; non-loopback hosts are always
            token-mandatory and fail closed).
    """
    facade = facade or RuntimeFacade(config_dir=config_dir)
    tokens = tokens or WriteTokenService()
    csrf = CsrfService(token=csrf_token)
    bridge_state: dict[str, DashboardEventBridge | None] = {"bridge": None}

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if auto_start:
            await run_in_threadpool(facade.ensure_running)
        bus = facade.event_bus
        if bus is None:
            raise RuntimeError(
                "Dashboard API requires a started runtime (event bus unavailable)"
            )
        bridge = DashboardEventBridge(bus)
        bridge.attach(asyncio.get_running_loop())
        bridge_state["bridge"] = bridge

        # R5: persist a runtime metrics snapshot on a cadence while the
        # runtime is up (fail-open; the telemetry module never raises).
        # The KPI panel reads this persisted history via /api/telemetry/metrics.
        # metrics_persist also syncs the SQLite read model (ADR 0004) from the
        # JSONL sources, so telemetry reads are served from a projection that
        # stays current during this session without a restart (T1).
        _metrics_interval = 30.0
        _stop_metrics = asyncio.Event()

        async def _persist_metrics() -> None:
            while not _stop_metrics.is_set():
                try:
                    await asyncio.wait_for(
                        _stop_metrics.wait(), timeout=_metrics_interval
                    )
                except TimeoutError:
                    pass
                if facade.is_running:
                    await run_in_threadpool(facade.metrics_persist)

        metrics_task = asyncio.create_task(_persist_metrics())
        try:
            yield
        finally:
            _stop_metrics.set()
            metrics_task.cancel()
            await bridge.close()
            if auto_start:
                await run_in_threadpool(facade.close)

    app = FastAPI(
        title=_SERVICE_NAME,
        version=_SERVICE_VERSION,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(_SecurityMiddleware)
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
    templates = Jinja2Templates(directory=_TEMPLATES_DIR)

    # ── WS-3.0/WS-4.0: server-rendered dashboard views (Jinja2) ──────────
    # Views are thin: they fetch the same facade data the JSON API exposes
    # and render it into the base template. JSON API remains the source of
    # truth; the HTML pages never call engines directly.

    def _view_context(request: Request, active: str, **data: Any) -> dict[str, Any]:
        context: dict[str, Any] = {"request": request, "active": active}
        context.update(data)
        return context

    async def _safe(fn: Any, *args: Any, default: Any = None) -> Any:
        """Run a facade call off the loop; return ``default`` on failure."""
        try:
            return await run_in_threadpool(fn, *args)
        except Exception:
            return default

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def pulse(request: Request) -> HTMLResponse:
        """Dashboard overview ("pulse") page."""
        health_data = await _safe(facade.health)
        summary = await _safe(facade.health_summary, default={}) or {}
        status = await _safe(facade.status, default={}) or {}
        engine_states = await _safe(facade.engine_states, default=[]) or []
        memory_stats = await _safe(facade.memory_stats, default={}) or {}
        backups = await _safe(facade.backup_status, default={}) or {}
        alerts = await _safe(facade.alerts_summary, default={}) or {}
        # Canonical four-state overall (R12) — never derive it inline here.
        overall = status.get("overall", "unknown") if status else "unknown"
        return templates.TemplateResponse(
            request,
            "views/pulse.html",
            _view_context(
                request,
                "pulse",
                status=status,
                checks=health_data,
                health_summary=summary,
                health_overall=overall,
                health_overall_class=overall,
                engines=engine_states,
                running_engines=sum(
                    1 for e in engine_states if e.get("phase") == "running"
                ),
                memory_stats=memory_stats,
                backups=backups,
                alerts_summary=alerts.get("summary", {}),
            ),
        )

    @app.get("/health", response_class=HTMLResponse, include_in_schema=False)
    async def health_view(request: Request) -> HTMLResponse:
        """System health page."""
        checks = await _safe(facade.health, default=[]) or []
        summary = await _safe(facade.health_summary, default={}) or {}
        status = await _safe(facade.status, default={}) or {}
        engine_states = await _safe(facade.engine_states, default=[]) or []
        diagnostics = await _safe(facade.diagnostics, default=None)
        alerts = await _safe(facade.alerts_summary, default={}) or {}
        # Canonical four-state overall (R12) — never derive it inline here.
        overall = status.get("overall", "unknown") if status else "unknown"
        return templates.TemplateResponse(
            request,
            "views/health.html",
            _view_context(
                request,
                "health",
                checks=checks,
                health_summary=summary,
                health_overall=overall,
                health_overall_class=overall,
                status=status,
                engine_states=engine_states,
                diagnostics=diagnostics,
                alerts_summary=alerts.get("summary", {}),
            ),
        )

    @app.get("/agents", response_class=HTMLResponse, include_in_schema=False)
    async def agents_view(request: Request) -> HTMLResponse:
        """Agent roster + org chart page."""
        exec_data = await _safe(facade.executives_list, default={}) or {}
        org = await _safe(facade.org_chart, default={}) or {}
        return templates.TemplateResponse(
            request,
            "views/agents.html",
            _view_context(
                request,
                "agents",
                executives=exec_data.get("executives", []),
                org_chart=org,
            ),
        )

    @app.get("/runs", response_class=HTMLResponse, include_in_schema=False)
    async def runs_view(request: Request) -> HTMLResponse:
        """Runs & history page."""
        orch = await _safe(facade.orchestration_status, default=None)
        history = await _safe(facade.orchestration_history, default=None)
        return templates.TemplateResponse(
            request,
            "views/runs.html",
            _view_context(request, "runs", orch_status=orch, history=history),
        )

    @app.get("/memory", response_class=HTMLResponse, include_in_schema=False)
    async def memory_view(request: Request) -> HTMLResponse:
        """Memory (read) page."""
        stats = await _safe(facade.memory_stats, default={}) or {}
        listing = await _safe(facade.memory_list, default={}) or {}
        return templates.TemplateResponse(
            request,
            "views/memory.html",
            _view_context(
                request,
                "memory",
                memory_stats=stats,
                entries=listing.get("entries", []),
            ),
        )

    @app.get("/writes", response_class=HTMLResponse, include_in_schema=False)
    async def writes_view(request: Request) -> HTMLResponse:
        """Write History page (Phase 2, ADR 0010 — guarded operator actions)."""
        return templates.TemplateResponse(
            request,
            "views/writes.html",
            _view_context(request, "writes"),
        )

    @app.get("/generate", response_class=HTMLResponse, include_in_schema=False)
    async def generate_view(request: Request) -> HTMLResponse:
        """Generate panel (Phase 2 wave 2b — dispatch + live logs + history)."""
        targets = await _safe(facade.generate_targets, default={}) or {}
        return templates.TemplateResponse(
            request,
            "views/generate.html",
            _view_context(
                request,
                "generate",
                targets=targets.get("targets", []),
            ),
        )

    @app.get("/decisions", response_class=HTMLResponse, include_in_schema=False)
    async def decisions_view(request: Request) -> HTMLResponse:
        """Decision / approval inbox (Phase 2 wave 2b)."""
        inbox = await _safe(facade.decisions_list, default={}) or {}
        return templates.TemplateResponse(
            request,
            "views/decisions.html",
            _view_context(
                request,
                "decisions",
                decisions=inbox.get("decisions", []),
            ),
        )

    @app.get("/telemetry", response_class=HTMLResponse, include_in_schema=False)
    async def telemetry_view(request: Request) -> HTMLResponse:
        """Telemetry page (risk R5 — KPI / Model Usage / Sessions / Agent Health)."""
        metrics = await _safe(facade.metrics_history_summary, default={}) or {}
        providers = await _safe(facade.provider_usage_summary, default={}) or {}
        alerts = await _safe(facade.alerts_summary, default={}) or {}
        retention = await _safe(facade.retention_status, default={}) or {}
        sessions = await _safe(facade.session_telemetry_summary, default={}) or {}
        actions = await _safe(facade.action_telemetry_summary, default={}) or {}
        status = await _safe(facade.status, default={}) or {}
        metrics_summary = metrics.get("summary", {})
        return templates.TemplateResponse(
            request,
            "views/telemetry.html",
            _view_context(
                request,
                "telemetry",
                metrics_summary=metrics_summary,
                trend=metrics_summary.get("trend", {}),
                providers=providers.get("summary", {}),
                alerts_summary=alerts.get("summary", {}),
                retention_summary=retention.get("summary", {}),
                sessions_summary=sessions.get("summary", {}),
                actions_summary=actions.get("summary", {}),
                status=status,
            ),
        )

    @app.get("/reports", response_class=HTMLResponse, include_in_schema=False)
    async def reports_view(request: Request) -> HTMLResponse:
        """Reports page."""
        summary = await _safe(facade.report_generate_read, "summary", default=None)
        validation = await _safe(facade.validate_read, default=None)
        report_types = await _safe(facade.reports_list, default={}) or {}
        return templates.TemplateResponse(
            request,
            "views/reports.html",
            _view_context(
                request,
                "reports",
                summary=summary,
                validation=validation,
                report_types=report_types.get("types", []),
            ),
        )

    @app.get("/validation", response_class=HTMLResponse, include_in_schema=False)
    async def validation_view(request: Request) -> HTMLResponse:
        """Validation gate page."""
        validation = await _safe(facade.validate_read, default=None)
        return templates.TemplateResponse(
            request,
            "views/validation.html",
            _view_context(request, "validation", validation=validation),
        )

    @app.get("/registry", response_class=HTMLResponse, include_in_schema=False)
    async def registry_view(request: Request) -> HTMLResponse:
        """Registry & org graph page."""
        registry = await _safe(facade.registry_list, default=None)
        graph = await _safe(facade.graph_stats, default=None)
        org = await _safe(facade.org_chart, default={}) or {}
        return templates.TemplateResponse(
            request,
            "views/registry.html",
            _view_context(
                request,
                "registry",
                registry=registry,
                graph=graph,
                org_chart=org,
            ),
        )

    @app.get("/api", tags=["meta"])
    async def api_index() -> dict[str, Any]:
        """Service index with the v1 endpoint map (HTML landing page at /)."""
        return {
            "service": _SERVICE_NAME,
            "version": _SERVICE_VERSION,
            "read_only": False,
            "write": {
                "csrf": "/api/write-csrf",
                "audit_history": "/api/audit/writes?limit=<n>",
                "runtime": "/api/runtime/{start|stop|restart|reload|recover|unisolate}",
                "orchestrate": "/api/orchestrate/{plan|start|resume|retry|rollback}",
                "memory": "/api/memory/{save|update|snapshot|restore|export|{key}/archive|{key}/unarchive}",
                "validate": "/api/validate",
                "reports": "/api/reports/generate",
                "build": "/api/build",
                "bootstrap": "/api/bootstrap",
                "generate": "/api/generate + /api/generate/{run_id}/cancel",
                "decisions": "/api/decisions + /api/decisions/{id}/{approve|reject|escalate|cancel}",
                "graph_export": "/api/graph/export",
                "company": "/api/company/departments + /api/company/manifest",
                "agents_sync": "/api/agents/sync",
                "backup": "/api/backup",
                "telemetry_metrics": "/api/telemetry/metrics",
                "telemetry_session": "/api/telemetry/session",
                "review_submit": "/api/review/submit",
            },
            "endpoints": {
                "health": "/api/health",
                "status": "/api/status",
                "metrics": "/api/metrics",
                "engines": "/api/engines",
                "events": "/api/events?since=<iso8601>&limit=<n>",
                "registry": "/api/registry",
                "registry_show": "/api/registry/{name}",
                "registry_verify": "/api/registry/verify",
                "executives": "/api/executives",
                "executive_show": "/api/executives/{name}",
                "org_chart": "/api/org-chart",
                "memory": "/api/memory",
                "memory_search": "/api/memory/search",
                "memory_stats": "/api/memory/stats",
                "memory_snapshots": "/api/memory/snapshots",
                "graph": "/api/graph",
                "graph_stats": "/api/graph/stats",
                "reports": "/api/reports",
                "report_generate": "/api/reports/{type}",
                "validate": "/api/validate",
                "validate_artifact": "/api/validate/{artifact}",
                "diagnostics": "/api/diagnostics",
                "orchestrate_status": "/api/orchestrate/status",
                "orchestrate_history": "/api/orchestrate/history",
                "generate_targets": "/api/generate/targets",
                "generate_runs": "/api/generate/runs",
                "generate_run": "/api/generate/runs/{run_id}",
                "generate_log": "/api/generate/runs/{run_id}/log",
                "decisions": "/api/decisions",
                "decision_get": "/api/decisions/{decision_id}",
                "review_submit": "/api/review/submit",
                "company_files": "/api/company",
                "telemetry_metrics": "/api/telemetry/metrics",
                "telemetry_providers": "/api/telemetry/providers",
                "telemetry_sessions": "/api/telemetry/sessions",
                "telemetry_actions": "/api/telemetry/actions",
                "websocket": "/api/ws?since=<iso8601>",
                "docs": "/api/docs",
            },
            "auth": (
                "Write endpoints require the bearer token (mandatory on "
                "non-loopback hosts; optional on loopback unless "
                "--require-loopback-token) plus the per-run CSRF token from "
                "GET /api/write-csrf echoed in X-CSRF-Token (ADR 0010)."
            ),
            "reconnect": (
                "WebSocket clients pass ?since=<iso8601>; the server replays "
                "matching events then streams live (deduplicate by event_id)."
            ),
        }

    @app.get("/api/health", tags=["runtime"])
    async def health() -> dict[str, Any]:
        """Aggregated runtime health — canonical four-state overall (R12)."""
        status = await run_in_threadpool(facade.status)
        checks = await run_in_threadpool(facade.health)
        return {
            "status": status.get("overall", "unknown"),
            "runtime_phase": status.get("phase", "unknown"),
            "summary": status.get("health_summary", {}),
            "checks": checks,
            "timestamp": status.get("timestamp"),
        }

    @app.get("/api/status", tags=["runtime"])
    async def status() -> dict[str, Any]:
        """Runtime status view (phase, engines, processes, active counts)."""
        return await run_in_threadpool(facade.status)

    @app.get("/api/metrics", tags=["runtime"])
    async def metrics() -> dict[str, Any]:
        """Runtime metrics snapshot (gauges, counters, timers)."""
        return await run_in_threadpool(facade.metrics)

    @app.get("/api/engines", tags=["runtime"])
    async def engines() -> list[dict[str, Any]]:
        """Lifecycle + health state of every registered engine."""
        return await run_in_threadpool(facade.engine_states)

    @app.get("/api/events", tags=["events"])
    async def events(
        since: str | None = Query(default=None, description="ISO-8601 timestamp"),
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> dict[str, Any]:
        """REST replay of persisted events (REST fallback for the WebSocket feed)."""
        bus = facade.event_bus
        if bus is None or getattr(bus, "persistence", None) is None:
            return {"events": [], "persistence_enabled": False}
        collected: list[dict[str, Any]] = []

        def _collect(event: Event) -> None:
            collected.append(event.model_dump(mode="json"))

        request = ReplayRequest(since=_parse_since(since), limit=limit)
        session = await run_in_threadpool(bus.replay, request, _collect)
        return {
            "events": collected,
            "persistence_enabled": True,
            "replayed": session.succeeded,
            "total": session.total_events,
        }

    # ── Phase 1 WS-2.0: read-only domain endpoints (parity P1) ──────────
    # Note: literal path segments ("verify", "search", "stats", ...) are
    # registered BEFORE the {name}/{type} parameter routes so FastAPI matches
    # the literal first.

    @app.get("/api/registry", tags=["registry"])
    async def registry_list() -> dict[str, Any]:
        """Registry summary (vision, departments, counts)."""
        return await run_in_threadpool(facade.registry_list)

    @app.get("/api/registry/verify", tags=["registry"])
    async def registry_verify() -> dict[str, Any]:
        """Verify the registry loads cleanly (parity with ``registry verify``)."""
        return await run_in_threadpool(facade.registry_verify)

    @app.get("/api/registry/{name}", tags=["registry"])
    async def registry_show(name: str) -> dict[str, Any]:
        """Show one registry entry (vision, departments, board, ...)."""
        return await run_in_threadpool(facade.registry_show, name)

    @app.get("/api/executives", tags=["executives"])
    async def executives_list() -> dict[str, Any]:
        """Executive roster (name, title, department, status)."""
        return await run_in_threadpool(facade.executives_list)

    @app.get("/api/executives/{name}", tags=["executives"])
    async def executive_show(name: str) -> dict[str, Any]:
        """Executive profile with KPIs, budget, and agent config."""
        return await run_in_threadpool(facade.executive_show, name)

    @app.get("/api/org-chart", tags=["executives"])
    async def org_chart() -> dict[str, Any]:
        """Organization chart as Mermaid source (client-side render)."""
        return await run_in_threadpool(facade.org_chart)

    @app.get("/api/memory", tags=["memory"])
    async def memory_list(
        memory_type: str | None = Query(default=None),
        namespace: str | None = Query(default=None),
        limit: int = Query(default=20, ge=1, le=500),
    ) -> dict[str, Any]:
        """Memory entries, optionally filtered by type/namespace."""
        return await run_in_threadpool(
            facade.memory_list, memory_type, namespace, limit
        )

    @app.get("/api/memory/search", tags=["memory"])
    async def memory_search(
        query: str = Query(default=""),
        memory_type: str | None = Query(default=None),
        namespace: str | None = Query(default=None),
        tags: str = Query(default=""),
        limit: int = Query(default=20, ge=1, le=500),
        min_importance: float = Query(default=0.0, ge=0.0, le=1.0),
        include_archived: bool = Query(default=False),
    ) -> dict[str, Any]:
        """Search memory entries (read-only)."""
        return await run_in_threadpool(
            facade.memory_search,
            query,
            memory_type,
            namespace,
            tags,
            limit,
            min_importance,
            include_archived,
        )

    @app.get("/api/memory/stats", tags=["memory"])
    async def memory_stats() -> dict[str, Any]:
        """Memory statistics (totals by type/namespace)."""
        return await run_in_threadpool(facade.memory_stats)

    @app.get("/api/memory/snapshots", tags=["memory"])
    async def memory_snapshots() -> dict[str, Any]:
        """List available memory snapshots."""
        return await run_in_threadpool(facade.memory_snapshots)

    @app.get("/api/memory/{key}", tags=["memory"])
    async def memory_get(key: str) -> dict[str, Any]:
        """Fetch one memory entry by key (read-only)."""
        return await run_in_threadpool(facade.memory_get, key)

    @app.get("/api/graph", tags=["graph"])
    async def graph_show() -> dict[str, Any]:
        """Organizational graph view (departments, roles, edges)."""
        return await run_in_threadpool(facade.graph_show)

    @app.get("/api/graph/stats", tags=["graph"])
    async def graph_stats() -> dict[str, Any]:
        """Graph statistics (nodes, edges, density)."""
        return await run_in_threadpool(facade.graph_stats)

    @app.get("/api/reports", tags=["reports"])
    async def reports_list() -> dict[str, Any]:
        """Available report types."""
        return await run_in_threadpool(facade.reports_list)

    @app.get("/api/reports/{report_type}", tags=["reports"])
    async def report_generate(report_type: str) -> dict[str, Any]:
        """Generate one report (summary/detailed/health) — read-only."""
        return await run_in_threadpool(facade.report_generate_read, report_type)

    @app.get("/api/validate", tags=["validation"])
    async def validate() -> dict[str, Any]:
        """Run the validation gate (parity with ``ai-company validate``)."""
        return await run_in_threadpool(facade.validate_read)

    @app.get("/api/diagnostics", tags=["runtime"])
    async def diagnostics() -> dict[str, Any]:
        """Full runtime diagnostic report."""
        return await run_in_threadpool(facade.diagnostics)

    @app.get("/api/orchestrate/status", tags=["orchestration"])
    async def orchestrate_status() -> dict[str, Any]:
        """Orchestration engine status (parity with ``orchestrate status``)."""
        return await run_in_threadpool(facade.orchestration_status)

    @app.get("/api/orchestrate/history", tags=["orchestration"])
    async def orchestrate_history(
        plan_id: str | None = Query(default=None),
        limit: int = Query(default=20, ge=1, le=500),
    ) -> dict[str, Any]:
        """Execution history (parity with ``orchestrate history``)."""
        return await run_in_threadpool(facade.orchestration_history, plan_id, limit)

    @app.get("/api/generate/targets", tags=["generate"])
    async def generate_targets() -> dict[str, Any]:
        """Generation targets from the command map (parity with ``targets``)."""
        return await run_in_threadpool(facade.generate_targets)

    @app.websocket("/api/ws")
    async def websocket_endpoint(
        ws: WebSocket,
        since: str | None = Query(default=None, description="ISO-8601 timestamp"),
        token: str | None = Query(default=None, description="write token (ADR 0010)"),
    ) -> None:
        """Live event feed: replay (``?since=``) then stream, with heartbeats.

        The feed is read-only, but every event is business telemetry — on
        non-loopback hosts (or when loopback enforcement is on) a valid write
        token is required via ``?token=`` so the event stream is never exposed
        to anonymous clients (Wave 2b WS token enforcement).
        """
        host = ws.headers.get("host", "")
        token_required = (not _host_allowed(host)) or require_loopback_token
        if token_required and (token is None or not tokens.verify(token)):
            await ws.close(code=1008)
            return
        bridge = bridge_state["bridge"]
        if bridge is None:
            await ws.close(code=1011)
            return
        try:
            since_dt = _parse_since(since)
        except HTTPException:
            await ws.close(code=1008)
            return
        await ws.accept()
        client_id = f"ws-{uuid4().hex[:12]}"
        queue = await bridge.subscribe_client(client_id, since=since_dt)
        try:
            while True:
                try:
                    envelope = await asyncio.wait_for(
                        queue.get(), timeout=_WS_HEARTBEAT_SECONDS
                    )
                except TimeoutError:
                    await ws.send_json(
                        {"kind": "ping", "timestamp": datetime.now(UTC).isoformat()}
                    )
                    continue
                await ws.send_json(envelope)
        except (WebSocketDisconnect, RuntimeError):
            pass  # client went away; teardown below
        finally:
            bridge.unsubscribe_client(client_id)

    # ── Phase 2 (WS-2.1, ADR 0010): guarded write surface ─────────────────
    # Bearer token + per-run CSRF synchronizer + mandatory audit events.
    # Registered last: the read-only routes above keep their paths, and the
    # mutation routes use POST (no method collisions with the GET contract).
    register_write_endpoints(
        app,
        facade=facade,
        tokens=tokens,
        csrf=csrf,
        require_loopback_token=require_loopback_token,
    )

    # ── Phase 2 (WS-2.2, wave 2b): operational endpoints ──────────────────
    # Generate loop, approval inbox, validators, company CRUD, agent sync,
    # backup, and R5 telemetry — same guard/audit contract as wave 2a.
    register_operational_endpoints(
        app,
        facade=facade,
        tokens=tokens,
        csrf=csrf,
        require_loopback_token=require_loopback_token,
    )

    # Expose the auth services on app.state for tests and operational checks.
    app.state.write_tokens = tokens
    app.state.csrf_token = csrf.token
    app.state.require_loopback_token = require_loopback_token

    return app
