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


def test_generate_runs_deep_link_passthrough(
    client: TestClient, facade: RuntimeFacade, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The API serves the additive ``deep_link`` the facade enriches (P3)."""
    _stub(
        monkeypatch,
        facade,
        "generate_runs",
        {
            "success": True,
            "errors": [],
            "runs": [
                {
                    "run_id": "g1",
                    "target": "registry",
                    "deep_link": "opencode://new-session?directory=x&prompt=y",
                }
            ],
        },
    )
    body = client.get("/api/generate/runs").json()
    assert body["runs"][0]["deep_link"].startswith("opencode://new-session?")


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


def test_alerts_read(
    client: TestClient, facade: RuntimeFacade, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T3 — GET /api/alerts exposes the open-alert summary for the red chip."""
    _stub(
        monkeypatch,
        facade,
        "alerts_summary",
        {
            "success": True,
            "errors": [],
            "summary": {
                "persistence_enabled": True,
                "records": 1,
                "open_count": 1,
                "open_alerts": [
                    {
                        "component": "engine-a",
                        "opened_at": "2026-08-02T10:00:00+00:00",
                        "reason": "heartbeat_timeout",
                        "attempts": 2,
                        "source": "runtime.supervisor",
                    }
                ],
                "recent": [],
            },
        },
    )
    body = client.get("/api/alerts").json()
    assert body["summary"]["open_count"] == 1
    assert body["summary"]["open_alerts"][0]["component"] == "engine-a"
    assert body["summary"]["open_alerts"][0]["attempts"] == 2


def test_telemetry_retention_read(
    client: TestClient, facade: RuntimeFacade, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T2 — GET /api/telemetry/retention exposes the dry-run retention report."""
    _stub(
        monkeypatch,
        facade,
        "retention_status",
        {
            "success": True,
            "errors": [],
            "summary": {
                "persistence_enabled": True,
                "applied": False,
                "total_raw": 3,
                "total_expired": 2,
                "sources": [
                    {
                        "key": "metrics_history",
                        "days": 7,
                        "raw_records": 3,
                        "expired_records": 2,
                        "would_rollup": 2,
                    }
                ],
            },
        },
    )
    body = client.get("/api/telemetry/retention").json()
    assert body["summary"]["total_expired"] == 2
    assert body["summary"]["sources"][0]["key"] == "metrics_history"
    assert body["summary"]["applied"] is False


def test_telemetry_sessions_read(
    client: TestClient, facade: RuntimeFacade, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P2 — GET /api/telemetry/sessions exposes OpenCode session checkpoints."""
    _stub(
        monkeypatch,
        facade,
        "session_telemetry_summary",
        {
            "success": True,
            "errors": [],
            "summary": {
                "persistence_enabled": True,
                "records": 1,
                "sessions": 1,
                "recent": [
                    {
                        "session_id": "sess-1",
                        "title": "Sprint 5.5 P2",
                        "messages_user": 2,
                        "messages_assistant": 3,
                        "tool_calls": 4,
                        "end_reason": "deleted",
                    }
                ],
                "totals": {"tool_calls": 4},
            },
        },
    )
    body = client.get("/api/telemetry/sessions").json()
    assert body["summary"]["sessions"] == 1
    assert body["summary"]["recent"][0]["session_id"] == "sess-1"


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


def test_review_submit_guarded_and_audited(
    client: TestClient, facade: RuntimeFacade, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P4: a desktop submission is guarded, audited, and returns a deep link."""
    captured = _stub(
        monkeypatch,
        facade,
        "review_submit",
        {
            "success": True,
            "errors": [],
            "decision": {"id": "decision_9", "title": "T"},
            "review_link": "http://127.0.0.1/decisions?focus=decision_9",
        },
    )
    resp = client.post(
        "/api/review/submit",
        json={
            "title": "Review generated registry",
            "description": "Artifact from a desktop session.",
            "artifact_paths": ["generated/registry/company.yaml"],
            "session_id": "session-abc",
            "model": "deepseek-r1-64k:latest",
        },
        headers=_auth(token=_TOKEN),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["review_link"] == "http://127.0.0.1/decisions?focus=decision_9"
    assert captured[0][0][0] == "Review generated registry"
    actions = _audit_actions(client)
    assert actions[-1]["action"] == "review.submit"
    assert actions[-1]["details"]["session_id"] == "session-abc"


def test_review_submit_enforced_requires_token(
    enforced_client: TestClient,
) -> None:
    resp = enforced_client.post(
        "/api/review/submit",
        json={"title": "T", "description": "D"},
        headers=_auth(token=None),
    )
    assert resp.status_code == 401


def test_review_submit_missing_csrf_is_403(client: TestClient) -> None:
    resp = client.post(
        "/api/review/submit",
        json={"title": "T", "description": "D"},
        headers=_auth(token=_TOKEN, csrf=None),
    )
    assert resp.status_code == 403


def test_review_submit_validation_422(client: TestClient) -> None:
    resp = client.post(
        "/api/review/submit",
        json={"title": "", "description": ""},
        headers=_auth(token=_TOKEN),
    )
    assert resp.status_code == 422


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


def test_telemetry_session_persist_requires_auth(
    enforced_client: TestClient, facade: RuntimeFacade, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P2 — with loopback token enforcement on, a missing bearer is a 401."""
    _stub(
        monkeypatch,
        facade,
        "session_telemetry_record",
        {"success": True, "errors": [], "session_id": "sess-1"},
    )
    resp = enforced_client.post("/api/telemetry/session", json={"session_id": "sess-1"})
    assert resp.status_code == 401
    assert _audit_actions(enforced_client)[-1]["action"] == "telemetry.session.persist"


def test_telemetry_session_persist_bad_csrf(
    client: TestClient, facade: RuntimeFacade, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub(
        monkeypatch,
        facade,
        "session_telemetry_record",
        {"success": True, "errors": [], "session_id": "sess-1"},
    )
    resp = client.post(
        "/api/telemetry/session",
        json={"session_id": "sess-1"},
        headers=_auth(token=_TOKEN, csrf="wrong"),
    )
    assert resp.status_code == 403


def test_telemetry_session_persist_guarded_and_audited(
    client: TestClient, facade: RuntimeFacade, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P2 — guarded checkpoint post succeeds and publishes audit.write."""
    captured = _stub(
        monkeypatch,
        facade,
        "session_telemetry_record",
        {"success": True, "errors": [], "session_id": "sess-1"},
    )
    resp = client.post(
        "/api/telemetry/session",
        json={
            "session_id": "sess-1",
            "title": "Sprint 5.5 P2",
            "messages_user": 2,
            "messages_assistant": 3,
            "tool_calls": 4,
            "commands_run": 1,
            "tools_used": {"read": 2},
            "end_reason": "idle",
        },
        headers=_auth(token=_TOKEN),
    )
    assert resp.status_code == 200
    assert resp.json()["session_id"] == "sess-1"
    body = captured[0][0][0]  # facade.session_telemetry_record(record)
    assert body["session_id"] == "sess-1"
    assert body["tool_calls"] == 4
    actions = _audit_actions(client)
    assert actions[-1]["action"] == "telemetry.session.persist"
    assert actions[-1]["result"] == "ok"
    assert actions[-1]["details"]["session_id"] == "sess-1"


def test_telemetry_session_persist_rejects_negative_counts(
    client: TestClient, facade: RuntimeFacade, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P2 — the Pydantic body clamps counters to their non-negative domain."""
    _stub(
        monkeypatch,
        facade,
        "session_telemetry_record",
        {"success": True, "errors": [], "session_id": "sess-1"},
    )
    resp = client.post(
        "/api/telemetry/session",
        json={"session_id": "sess-1", "tool_calls": -1},
        headers=_auth(token=_TOKEN),
    )
    assert resp.status_code == 422


# ── WebSocket token enforcement (wave 2b) ─────────────────────────────────


def test_ws_rejects_without_token_when_enforced(enforced_client: TestClient) -> None:
    with (
        pytest.raises(WebSocketDisconnect),
        enforced_client.websocket_connect("/api/ws", headers={"host": "127.0.0.1"}),
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
    with (
        pytest.raises(WebSocketDisconnect),
        enforced_client.websocket_connect(
            "/api/ws?token=wrong-token", headers={"host": "127.0.0.1"}
        ),
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
