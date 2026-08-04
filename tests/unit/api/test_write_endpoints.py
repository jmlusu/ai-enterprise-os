"""Integration tests for the Phase 2 guarded write endpoints (ADR 0010).

Every mutation endpoint must pass the bearer-token + CSRF guard, enforce the
reason requirement for high-impact actions, publish ``audit.write`` on
completion, and publish ``audit.write_rejected`` on auth failures — without
ever executing a real engine write (facade write adapters are stubbed; the
facade itself stays an honest mirror of the CLI, tested elsewhere).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ai_company.api.app import create_app
from ai_company.api.auth import WriteTokenService
from ai_company.events import EventBus
from ai_company.runtime import create_runtime
from ai_company.services.runtime_facade import RuntimeFacade

_MISSING_CONFIG = "__missing__"
_TOKEN = "test-write-token-0123456789abcdef"
_CSRF = "test-csrf-token-0123456789abcdef"


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the guarded-write action telemetry (P5 D5) out of the repo tree."""
    monkeypatch.chdir(tmp_path)


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


def _write_events(client: TestClient) -> list[dict[str, Any]]:
    body = client.get("/api/audit/writes").json()
    return body["events"]


# ── read helpers ────────────────────────────────────────────────────────────


def test_write_csrf_endpoint(client: TestClient) -> None:
    resp = client.get("/api/write-csrf")
    assert resp.status_code == 200
    assert resp.json() == {"csrf_token": _CSRF}


# ── guard: token policy (ADR 0010 §1) ───────────────────────────────────────


def test_loopback_write_without_token_succeeds(
    client: TestClient, facade: RuntimeFacade, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = _stub(
        monkeypatch, facade, "memory_save", {"success": True, "errors": []}
    )
    resp = client.post(
        "/api/memory/save",
        headers=_auth(),  # token optional on loopback
        json={"content": {"text": "hello"}},
    )
    assert resp.status_code == 200
    assert captured, "facade write adapter was not called"


def test_invalid_token_rejected(client: TestClient) -> None:
    resp = client.post(
        "/api/memory/save",
        headers=_auth(token="wrong-token"),
        json={"content": {"text": "hello"}},
    )
    assert resp.status_code == 401
    assert "write token" in resp.json()["detail"]


def test_non_loopback_host_blocked_by_middleware(client: TestClient) -> None:
    # The security middleware fails closed on non-loopback Host headers
    # before any write route (outer defense-in-depth layer, risk R9).
    resp = client.post(
        "/api/memory/save",
        headers={**_auth(token=_TOKEN), "host": "evil.example.com"},
        json={"content": {"text": "hello"}},
    )
    assert resp.status_code == 403
    assert b"Host header not allowed" in resp.content


# ── guard: CSRF synchronizer (ADR 0010 §2) ──────────────────────────────────


def test_missing_csrf_rejected(client: TestClient) -> None:
    resp = client.post(
        "/api/memory/save",
        headers=_auth(token=_TOKEN, csrf=None),
        json={"content": {"text": "hello"}},
    )
    assert resp.status_code == 403


def test_wrong_csrf_rejected(client: TestClient) -> None:
    resp = client.post(
        "/api/memory/save",
        headers=_auth(token=_TOKEN, csrf="wrong"),
        json={"content": {"text": "hello"}},
    )
    assert resp.status_code == 403


# ── high-impact actions require a reason (ADR 0010 §5) ──────────────────────


def test_high_impact_without_reason_rejected(
    client: TestClient, facade: RuntimeFacade, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = _stub(
        monkeypatch, facade, "runtime_stop", {"success": True, "errors": []}
    )
    resp = client.post(
        "/api/runtime/stop",
        headers=_auth(token=_TOKEN),
        json={},  # no reason
    )
    assert resp.status_code == 422
    assert "reason" in resp.json()["detail"]
    assert not captured, "facade must not be called when reason is missing"


def test_high_impact_with_reason_succeeds(
    client: TestClient, facade: RuntimeFacade, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = _stub(
        monkeypatch, facade, "runtime_stop", {"success": True, "errors": []}
    )
    resp = client.post(
        "/api/runtime/stop",
        headers=_auth(token=_TOKEN),
        json={"reason": "scheduled maintenance window"},
    )
    assert resp.status_code == 200
    assert captured
    args, _kwargs = captured[0]
    assert args == ("scheduled maintenance window",)


def test_blank_reason_rejected(client: TestClient) -> None:
    resp = client.post(
        "/api/runtime/restart",
        headers=_auth(token=_TOKEN),
        json={"reason": "   "},
    )
    assert resp.status_code == 422


# ── success path: facade adapter called + audited (ADR 0010 §3) ─────────────


def test_successful_write_audited(
    client: TestClient, facade: RuntimeFacade, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = _stub(
        monkeypatch,
        facade,
        "memory_save",
        {"success": True, "errors": [], "entry": {"id": "m1"}},
    )
    resp = client.post(
        "/api/memory/save",
        headers=_auth(token=_TOKEN),
        json={"content": {"text": "hello"}, "namespace": "ops"},
    )
    assert resp.status_code == 200
    assert resp.json()["entry"]["id"] == "m1"
    assert captured

    events = _write_events(client)
    assert any(e["metadata"]["event_type"] == "audit.write" for e in events)
    audit = next(e for e in events if e["metadata"]["event_type"] == "audit.write")
    assert audit["payload"]["action"] == "memory.save"
    assert audit["payload"]["result"] == "ok"


def test_failed_operation_audited_as_failed(
    client: TestClient, facade: RuntimeFacade, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub(
        monkeypatch,
        facade,
        "memory_save",
        {"success": False, "errors": ["storage unavailable"]},
    )
    resp = client.post(
        "/api/memory/save",
        headers=_auth(token=_TOKEN),
        json={"content": {"text": "hello"}},
    )
    assert resp.status_code == 200  # errors travel in the body, not HTTP

    events = _write_events(client)
    audit = next(e for e in events if e["metadata"]["event_type"] == "audit.write")
    assert audit["payload"]["result"] == "failed"
    assert audit["payload"]["details"]["errors"] == ["storage unavailable"]


def test_rejected_write_audited(
    client: TestClient, facade: RuntimeFacade, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub(monkeypatch, facade, "memory_save", {"success": True, "errors": []})
    resp = client.post(
        "/api/memory/save",
        headers=_auth(token="bad-token"),
        json={"content": {"text": "hello"}},
    )
    assert resp.status_code == 401

    events = _write_events(client)
    assert any(e["metadata"]["event_type"] == "audit.write_rejected" for e in events)
    rejected = next(
        e for e in events if e["metadata"]["event_type"] == "audit.write_rejected"
    )
    assert rejected["payload"]["action"] == "memory.save"
    assert rejected["payload"]["reason"] == "unauthorized"
    assert "bad-token" not in str(rejected["payload"])


# ── endpoint surface ────────────────────────────────────────────────────────


def test_memory_archive_path_route(
    client: TestClient, facade: RuntimeFacade, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = _stub(
        monkeypatch,
        facade,
        "memory_archive",
        {"success": True, "errors": [], "memory_id": "m_123", "archived": True},
    )
    resp = client.post(
        "/api/memory/m_123/archive", headers=_auth(token=_TOKEN), json={}
    )
    assert resp.status_code == 200
    args, _kwargs = captured[0]
    assert args == ("m_123",)


def test_report_generate_rejects_unknown_type(client: TestClient) -> None:
    resp = client.post(
        "/api/reports/generate",
        headers=_auth(token=_TOKEN),
        json={"report_type": "bogus"},
    )
    assert resp.status_code == 422


def test_orchestrate_plan_endpoint(
    client: TestClient, facade: RuntimeFacade, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = _stub(
        monkeypatch, facade, "orchestrate_plan", {"success": True, "errors": []}
    )
    resp = client.post(
        "/api/orchestrate/plan",
        headers=_auth(token=_TOKEN),
        json={"name": "weekly-report", "description": "from dashboard"},
    )
    assert resp.status_code == 200
    args, _kwargs = captured[0]
    assert args[0] == "weekly-report"


def test_validate_endpoint_requires_auth(client: TestClient) -> None:
    resp = client.post("/api/validate", headers=_auth(), json={})
    assert resp.status_code == 200  # token optional on loopback, CSRF ok
    # ... but a non-loopback write always requires the token (fail-closed):
    resp = client.post(
        "/api/validate",
        headers={**_auth(csrf=_CSRF), "host": "10.0.0.5"},
        json={},
    )
    assert resp.status_code == 403  # middleware: host not allowed


# ── require-loopback-token mode ─────────────────────────────────────────────


def test_require_loopback_token_enforced(
    facade: RuntimeFacade,
    tokens: WriteTokenService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app(
        facade=facade,
        auto_start=False,
        tokens=tokens,
        csrf_token=_CSRF,
        require_loopback_token=True,
    )
    with TestClient(app, base_url="http://127.0.0.1") as strict_client:
        resp = strict_client.post(
            "/api/memory/save",
            headers=_auth(),  # no token -> rejected under strict mode
            json={"content": {"text": "hello"}},
        )
        assert resp.status_code == 401

        captured = _stub(
            monkeypatch,
            facade,
            "runtime_start",
            {"success": True, "errors": []},
        )
        resp = strict_client.post(
            "/api/runtime/start",
            headers=_auth(token=_TOKEN),
            json={},
        )
        assert resp.status_code == 200
        assert captured
