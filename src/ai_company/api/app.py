"""Dashboard API — read-only contract v1 (FastAPI + WebSocket bridge).

ADR 0002: FastAPI + plain uvicorn (no uvloop — Windows-safe). ADR 0009:
contract v1 is read-only REST + WebSocket push; write endpoints arrive in
Phase 2 with token auth, CSRF headers, and audit events. The runtime is
thread-based, so every synchronous runtime call is bridged through
``run_in_threadpool`` and never blocks on runtime locks directly.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ai_company.events import Event, ReplayRequest
from ai_company.services.dashboard_events import DashboardEventBridge
from ai_company.services.runtime_facade import RuntimeFacade

__all__ = ["create_app"]

_SERVICE_NAME = "AI Enterprise OS - Dashboard API"
_SERVICE_VERSION = "1.0.0"

#: Loopback hosts only — DNS-rebinding defense (risk R9, ADR 0009).
_ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})

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

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", [])) + list(_SECURITY_HEADERS)
                message = {**message, "headers": headers}
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
) -> FastAPI:
    """Build the dashboard API application.

    Args:
        facade: Shared runtime facade (built from ``config_dir`` when omitted).
        config_dir: Directory containing ``config/runtime/*.yaml``.
        auto_start: Boot the runtime on startup and stop it on shutdown.
            Tests pass ``False`` and drive the runtime themselves.
    """
    facade = facade or RuntimeFacade(config_dir=config_dir)
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
        try:
            yield
        finally:
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

    @app.get("/", tags=["meta"])
    async def index() -> dict[str, Any]:
        """Service index with the v1 endpoint map."""
        return {
            "service": _SERVICE_NAME,
            "version": _SERVICE_VERSION,
            "read_only": True,
            "endpoints": {
                "health": "/api/health",
                "status": "/api/status",
                "metrics": "/api/metrics",
                "engines": "/api/engines",
                "events": "/api/events?since=<iso8601>&limit=<n>",
                "websocket": "/api/ws?since=<iso8601>",
                "docs": "/api/docs",
            },
            "reconnect": (
                "WebSocket clients pass ?since=<iso8601>; the server replays "
                "matching events then streams live (deduplicate by event_id)."
            ),
        }

    @app.get("/api/health", tags=["runtime"])
    async def health() -> dict[str, Any]:
        """Aggregated runtime health (is the system healthy?)."""
        checks = await run_in_threadpool(facade.health)
        summary = await run_in_threadpool(facade.health_summary)
        overall = (
            "unhealthy"
            if summary.get("unhealthy", 0)
            else ("degraded" if summary.get("degraded", 0) else "ok")
        )
        return {
            "status": overall,
            "runtime_phase": facade.phase,
            "summary": summary,
            "checks": checks,
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

    @app.websocket("/api/ws")
    async def websocket_endpoint(
        ws: WebSocket,
        since: str | None = Query(default=None, description="ISO-8601 timestamp"),
    ) -> None:
        """Live event feed: replay (``?since=``) then stream, with heartbeats."""
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

    return app
