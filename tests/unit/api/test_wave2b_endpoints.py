"""Integration tests for Phase 2 wave 2b operational endpoints.

Reads must expose generate/decision/telemetry/backup data; writes must follow
the exact ADR 0010 guard contract (token + CSRF + audit) established by wave
2a, and publish ``audit.write`` on success / ``audit.write_rejected`` on
failure. Facade write adapters are stubbed; the real adapters are covered in
``tests/unit/services/test_facade_wave2b.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from ai_company.api.app import create_app
from ai_company.api.auth import WriteTokenService
from ai_company.events import EventBus, EventType
from ai_company.runtime import create_runtime
from ai_company.services.runtime_facade import RuntimeFacade

_MISSING_CONFIG = "__missing__"
_TOKEN = "test-write-token-0123456789abcdef"
_CSRF = "test-csrf-token-0123456789abcdef"


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
def tokens(tmp_path: Path) -> WriteTokenService:
    token_file = tmp_path / "write_token"
    token_file.write_text(_TOKEN + "\n", encoding="utf-8")
    return WriteTokenService(token_file=token_file)


@pytest.fixture()
def client(facade: RuntimeFacade, tokens: WriteTokenService) -> TestClient:
    app = create_app(
        facade=facade,
        auto_start=False,
        tokens=tokens,
        csrf_token=_CSRF,
        require_loopback_token=False,
    )
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        yield test_client


@pytest.fixture()
def enforced_client(facade: RuntimeFacade, tokens: WriteTokenService) -> TestClient:
    """Client with loopback token enforcement (WS ?token= tests)."""
    app = create_app(
        facade=facade,
        auto_start=False,
        tokens=tokens,
        csrf_token=_CSRF,
        require_loopback_token=True,
    )
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        yield test_client


def _auth(token: str | None = None, csrf: str | None = _CSRF) -> dict[str, str]:
    headers: dict[str, str] = {}
    if csrf is not None:
        headers["X-CSRF-Token"] = csrf
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _stub(
    monkeypatch: pytest.MonkeyPatch,
    facade: RuntimeFacade,
    method: str,
    result: dict[str, Any],
) -> list[tuple[Any, ...]]:
    captured: list[tuple[Any, ...]] = []

    def _fake(*args: Any, **kwargs: Any) -> dict[str, Any]:
        captured.append((args, kwargs))
        return result

    monkeypatch.setattr(facade, method, _fake)
    return captured


def _audit_actions(client: TestClient) -> list[dict[str, Any]]:
    body = client.get("/api/audit/writes?limit=50").json()
    return [event["payload"] for event in body.get("events", [])]


# ── reads ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", ["/generate", "/decisions", "/telemetry"])
def test_wave2b_pages_render(client: TestClient, path: str) -> None:
    """The three new dashboard views render as HTML behind the page CSP."""
    resp = client.get(path)
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "content-security-policy" in resp.headers


def test_generate_runs_read(
    client: TestClient, facade: RuntimeFacade, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub(
        monkeypatch,
        facade,
        "generate_runs",
        {"success": True, "errors": [], "runs": []},
    )
    body = client.get("/api/generate/runs").json()
    assert body["success"] is True
    assert body["runs"] == []


def test_generate_run_404(
    client: TestClient, facade: RuntimeFacade, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub(
        monkeypatch,
        facade,
        "generate_run",
        {"success": False, "errors": ["run not found: nope"], "run": None},
    )
    assert client.get("/api/generate/runs/nope").status_code == 404


def test_decisions_read(
    client: TestClient, facade: RuntimeFacade, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub(
        monkeypatch,
        facade,
        "decisions_list",
        {"success": True, "errors": [], "decisions": [], "count": 0},
    )
    body = client.get("/api/decisions?status=pending").json()
    assert body["success"] is True


def test_validate_artifact_unknown_404(client: TestClient) -> None:
    assert client.get("/api/validate/not-an-artifact").status_code == 404


def test_telemetry_metrics_read(
    client: TestClient, facade: RuntimeFacade, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub(
        monkeypatch,
        facade,
        "metrics_history_summary",
        {"success": True, "errors": [], "summary": {"samples": 0}},
    )
    body = client.get("/api/telemetry/metrics").json()
    assert body["summary"]["samples"] == 0


def test_telemetry_providers_read(
    client: TestClient, facade: RuntimeFacade, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub(
        monkeypatch,
        facade,
        "provider_usage_summary",
        {"success": True, "errors": [], "summary": {"records": 0}},
    )
    body = client.get("/api/telemetry/providers").json()
    assert body["summary"]["records"] == 0


def test_backup_status_read(
    client: TestClient, facade: RuntimeFacade, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub(
        monkeypatch,
        facade,
        "backup_status",
        {"success": True, "errors": [], "backups": [], "total": 0},
    )
    body = client.get("/api/backup").json()
    assert body["total"] == 0


def test_company_files_read(
    client: TestClient, facade: RuntimeFacade, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub(
        monkeypatch,
        facade,
        "company_files",
        {"success": True, "errors": [], "files": ["departments.yaml"]},
    )
    body = client.get("/api/company").json()
    assert "departments.yaml" in body["files"]


# ── guarded writes ────────────────────────────────────────────────────────


def test_generate_start_requires_auth(
    enforced_client: TestClient, facade: RuntimeFacade, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With loopback token enforcement on, a missing bearer token is a 401."""
    _stub(
        monkeypatch,
        facade,
        "generate_start",
        {"success": True, "errors": [], "run": None},
    )
    resp = enforced_client.post("/api/generate", json={"target": "registry"})
    assert resp.status_code == 401
    assert _audit_actions(enforced_client)[-1]["action"] == "generate.start"


def test_generate_start_bad_csrf(
    client: TestClient, facade: RuntimeFacade, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub(
        monkeypatch,
        facade,
        "generate_start",
        {"success": True, "errors": [], "run": None},
    )
    resp = client.post(
        "/api/generate",
        json={"target": "registry"},
        headers=_auth(token=_TOKEN, csrf="wrong"),
    )
    assert resp.status_code == 403


def test_generate_start_audited(
    client: TestClient, facade: RuntimeFacade, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = _stub(
        monkeypatch,
        facade,
        "generate_start",
        {"success": True, "errors": [], "run": {"run_id": "g1", "status": "running"}},
    )
    resp = client.post(
        "/api/generate",
        json={"target": "registry", "reason": "wave 2b test"},
        headers=_auth(token=_TOKEN),
    )
    assert resp.status_code == 200
    assert resp.json()["run"]["run_id"] == "g1"
    assert captured[0][0][0] == "registry"  # facade.generate_start(target, reason)
    actions = _audit_actions(client)
    assert actions[-1]["action"] == "generate.start"
    assert actions[-1]["result"] == "ok"


def test_decision_create_guarded_and_audited(
    client: TestClient, facade: RuntimeFacade, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub(
        monkeypatch,
        facade,
        "decision_create",
        {
            "success": True,
            "errors": [],
            "decision": {"id": "decision_1", "title": "T"},
        },
    )
    resp = client.post(
        "/api/decisions",
        json={"title": "T", "description": "D", "category": "technical"},
        headers=_auth(token=_TOKEN),
    )
    assert resp.status_code == 200
    actions = _audit_actions(client)
    assert actions[-1]["action"] == "decision.create"


def test_decision_approve_409_on_failure(
    client: TestClient, facade: RuntimeFacade, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub(
        monkeypatch,
        facade,
        "decision_approve",
        {"success": False, "errors": ["decision already resolved: approved"]},
    )
    resp = client.post(
        "/api/decisions/decision_1/approve",
        json={"selected_option": "opt1", "rationale": "r"},
        headers=_auth(token=_TOKEN),
    )
    assert resp.status_code == 409


def test_decision_reject_requires_reason_in_audit(
    client: TestClient, facade: RuntimeFacade, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub(
        monkeypatch,
        facade,
        "decision_reject",
        {"success": True, "errors": [], "decision": {"id": "d1"}},
    )
    resp = client.post(
        "/api/decisions/d1/reject",
        json={"reason": "not now"},
        headers=_auth(token=_TOKEN),
    )
    assert resp.status_code == 200
    actions = _audit_actions(client)
    assert actions[-1]["action"] == "decision.reject"
    assert actions[-1]["reason"] == "not now"


def test_backup_create_guarded(
    client: TestClient, facade: RuntimeFacade, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub(
        monkeypatch,
        facade,
        "backup_create",
        {"success": True, "errors": [], "path": "backups/x.tar.gz"},
    )
    resp = client.post(
        "/api/backup",
        json={"dest_dir": "backups"},
        headers=_auth(token=_TOKEN),
    )
    assert resp.status_code == 200
    assert resp.json()["path"].endswith(".tar.gz")


def test_agents_sync_guarded(
    client: TestClient, facade: RuntimeFacade, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub(
        monkeypatch,
        facade,
        "agents_sync",
        {
            "success": True,
            "errors": [],
            "created": ["ceo"],
            "updated": [],
            "skipped": [],
            "conflicts": [],
        },
    )
    resp = client.post(
        "/api/agents/sync",
        json={"scope": "project"},
        headers=_auth(token=_TOKEN),
    )
    assert resp.status_code == 200
    assert resp.json()["created"] == ["ceo"]


def test_graph_export_guarded(
    client: TestClient, facade: RuntimeFacade, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub(
        monkeypatch,
        facade,
        "graph_export_write",
        {"success": True, "errors": [], "files": ["generated/org.md"]},
    )
    resp = client.post(
        "/api/graph/export",
        json={"output_dir": "generated"},
        headers=_auth(token=_TOKEN),
    )
    assert resp.status_code == 200


# ── WebSocket token enforcement (wave 2b) ─────────────────────────────────


def test_ws_rejects_without_token_when_enforced(enforced_client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect):
        with enforced_client.websocket_connect(
            "/api/ws", headers={"host": "127.0.0.1"}
        ):
            pass  # pragma: no cover — server closes before accept


def test_ws_accepts_with_valid_token(
    enforced_client: TestClient,
    facade: RuntimeFacade,
    bus: EventBus,
) -> None:
    with enforced_client.websocket_connect(
        "/api/ws?token=" + _TOKEN, headers={"host": "127.0.0.1"}
    ) as ws:
        bus.publish_event(
            event_type=EventType.SYSTEM_HEALTH_CHECK,
            payload={"ok": True},
            source="ws-token-test",
        )
        envelope = ws.receive_json()
        assert envelope["kind"] == "event"


def test_ws_rejects_bad_token_when_enforced(enforced_client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect):
        with enforced_client.websocket_connect(
            "/api/ws?token=wrong-token", headers={"host": "127.0.0.1"}
        ):
            pass  # pragma: no cover


def test_ws_allows_anonymous_on_plain_loopback(
    client: TestClient, bus: EventBus
) -> None:
    with client.websocket_connect("/api/ws", headers={"host": "127.0.0.1"}) as ws:
        bus.publish_event(
            event_type=EventType.MEMORY_SAVED,
            payload={"k": 1},
            source="ws-plain-test",
        )
        envelope = ws.receive_json()
        assert envelope["kind"] == "event"
