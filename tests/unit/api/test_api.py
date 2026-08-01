"""Integration tests for the dashboard API (read-only contract v1, ADR 0009).

The runtime engine is constructed but never started (hermetic: no state
writes) and is wired to a started EventBus fixture so the WebSocket bridge
has a live feed to subscribe to. ``auto_start=False`` keeps the test driver
in control of the runtime lifecycle.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from ai_company.api.app import create_app
from ai_company.events import EventBus, EventType
from ai_company.runtime import create_runtime
from ai_company.services.runtime_facade import RuntimeFacade

#: Missing config dir: configuration is optional (required=False) and the
#: engine is never started, so no state is written anywhere.
_MISSING_CONFIG = "__missing__"


@pytest.fixture()
def bus(tmp_path: Path) -> EventBus:
    instance = EventBus(
        storage_path=str(tmp_path / "events.jsonl"),
        dead_letter_path=str(tmp_path / "dead_letter.jsonl"),
    )
    instance.start()
    yield instance
    instance.stop()


@pytest.fixture()
def facade(bus: EventBus) -> RuntimeFacade:
    runtime = create_runtime(config_dir=_MISSING_CONFIG, event_bus=bus)
    return RuntimeFacade(config_dir=_MISSING_CONFIG, runtime=runtime)


@pytest.fixture()
def client(facade: RuntimeFacade) -> TestClient:
    app = create_app(facade=facade, auto_start=False)
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        yield test_client


def test_index(client: TestClient) -> None:
    # WS-3.0: "/" is the HTML dashboard landing page; the JSON index moved
    # to /api so the API contract stays JSON-only (separate paths).
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]

    api = client.get("/api").json()
    assert api["read_only"] is True
    assert api["endpoints"]["websocket"].startswith("/api/ws")


def test_health_endpoint(client: TestClient) -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("ok", "degraded", "unhealthy")
    assert body["runtime_phase"] == "stopped"
    assert isinstance(body["checks"], list)
    assert body["checks"], "the system check always runs"
    assert "healthy" in body["summary"]


def test_status_metrics_engines(client: TestClient) -> None:
    status_body = client.get("/api/status").json()
    assert status_body["phase"] == "stopped"
    assert "name" in status_body

    metrics_body = client.get("/api/metrics").json()
    assert "uptime_seconds" in metrics_body
    assert "active_engines" in metrics_body

    engines_body = client.get("/api/engines").json()
    assert isinstance(engines_body, list)


def test_security_headers(client: TestClient) -> None:
    resp = client.get("/api/health")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["content-security-policy"] == "default-src 'none'"
    assert resp.headers["referrer-policy"] == "no-referrer"
    assert resp.headers["cache-control"] == "no-store"


def test_host_header_rejected(client: TestClient) -> None:
    resp = client.get("/api/status", headers={"host": "evil.example.com"})
    assert resp.status_code == 403
    assert b"Host header not allowed" in resp.content


def test_host_header_localhost_allowed(client: TestClient) -> None:
    resp = client.get("/api/status", headers={"host": "localhost"})
    assert resp.status_code == 200


def test_events_rest_replay(bus: EventBus, client: TestClient) -> None:
    bus.publish_event(EventType.MEMORY_SAVED, payload={"k": 1}, source="test")

    resp = client.get("/api/events")
    assert resp.status_code == 200
    body = resp.json()
    assert body["persistence_enabled"] is True
    types = [e["metadata"]["event_type"] for e in body["events"]]
    assert "memory.saved" in types
    assert any(e["payload"] == {"k": 1} for e in body["events"])


def test_events_rest_since_filter(bus: EventBus, client: TestClient) -> None:
    bus.publish_event(EventType.MEMORY_SAVED, payload={"k": 1}, source="test")
    time.sleep(0.01)
    mark = datetime.now(UTC)
    time.sleep(0.01)
    bus.publish_event(EventType.MEMORY_SAVED, payload={"k": 2}, source="test")

    url = "/api/events?since=" + quote(mark.isoformat())
    body = client.get(url).json()
    payloads = [e["payload"] for e in body["events"]]
    assert {"k": 2} in payloads
    assert {"k": 1} not in payloads


def test_websocket_live_feed(bus: EventBus, client: TestClient) -> None:
    with client.websocket_connect("/api/ws", headers={"host": "127.0.0.1"}) as ws:
        bus.publish_event(
            event_type=EventType.SYSTEM_HEALTH_CHECK,
            payload={"x": 1},
            source="test",
        )
        envelope = ws.receive_json()
        assert envelope["kind"] == "event"
        assert envelope["event"]["metadata"]["event_type"] == "system.health_check"
        assert envelope["event"]["payload"] == {"x": 1}


def test_websocket_replay_then_live(bus: EventBus, client: TestClient) -> None:
    bus.publish_event(EventType.MEMORY_SAVED, payload={"k": 1}, source="test")
    time.sleep(0.01)
    mark = datetime.now(UTC)
    time.sleep(0.01)
    bus.publish_event(EventType.MEMORY_SAVED, payload={"k": 2}, source="test")

    url = "/api/ws?since=" + quote(mark.isoformat())
    with client.websocket_connect(url, headers={"host": "127.0.0.1"}) as ws:
        replayed = ws.receive_json()
        assert replayed["event"]["payload"] == {"k": 2}

        bus.publish_event(EventType.MEMORY_SAVED, payload={"k": 3}, source="test")
        live = ws.receive_json()
        assert live["event"]["payload"] == {"k": 3}


def test_websocket_host_rejected(client: TestClient) -> None:
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/api/ws", headers={"host": "evil.example.com"}) as ws,
    ):
        ws.receive_json()
