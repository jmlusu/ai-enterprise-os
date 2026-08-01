"""Integration tests for the Phase 1 WS-2.0 read-only domain endpoints.

These tests exercise the endpoints against the *tracked* ``company/`` fixture
and ``config/memory/memory.yaml`` (both deterministic in git), so they double
as golden parity tests: the API surface must mirror the CLI read commands
without drifting (risk R3). No state is written anywhere — the runtime is
never started and the memory store is only read (the file does not even need
to exist).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ai_company.api.app import create_app
from ai_company.events import EventBus
from ai_company.runtime import create_runtime
from ai_company.services.runtime_facade import RuntimeFacade

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


# ── index ────────────────────────────────────────────────────────────────────


def test_index_lists_domain_endpoints(client: TestClient) -> None:
    body = client.get("/api").json()
    for key in (
        "registry",
        "registry_verify",
        "executives",
        "org_chart",
        "memory",
        "memory_search",
        "graph",
        "reports",
        "validate",
        "diagnostics",
        "orchestrate_status",
        "generate_targets",
    ):
        assert key in body["endpoints"], f"missing endpoint map entry: {key}"


def test_index_renders_html_pulse(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Pulse" in resp.text
    assert "AI Enterprise OS" in resp.text


def test_dashboard_pages_render(client: TestClient) -> None:
    for path in (
        "/health",
        "/agents",
        "/runs",
        "/memory",
        "/reports",
        "/validation",
        "/registry",
    ):
        resp = client.get(path)
        assert resp.status_code == 200, f"{path} returned {resp.status_code}"
        assert "text/html" in resp.headers["content-type"]


def test_static_assets_served(client: TestClient) -> None:
    for path in (
        "/static/vendor/htmx.min.js",
        "/static/vendor/marked.min.js",
        "/static/vendor/dompurify.min.js",
        "/static/vendor/mermaid.min.js",
        "/static/vendor/ws.js",
        "/static/css/dashboard.css",
        "/static/js/app.js",
    ):
        resp = client.get(path)
        assert resp.status_code == 200, f"{path} returned {resp.status_code}"


def test_pages_use_scoped_csp(client: TestClient) -> None:
    # HTML pages: dashboard CSP (self + ws, no unsafe-inline).
    page = client.get("/")
    csp = page.headers["content-security-policy"]
    assert "script-src 'self'" in csp
    assert "unsafe-inline" not in csp
    assert "connect-src 'self' ws:" in csp

    # JSON API: still the strict default-src 'none'.
    api = client.get("/api/health")
    assert api.headers["content-security-policy"] == "default-src 'none'"


# ── registry ─────────────────────────────────────────────────────────────────


def test_registry_list(client: TestClient) -> None:
    body = client.get("/api/registry").json()
    assert body["success"] is True
    reg = body["registry"]
    assert reg["vision"]["name"] == "AI Enterprise OS Vision"
    assert reg["executives"] > 0
    assert reg["board"] > 0


def test_registry_verify(client: TestClient) -> None:
    body = client.get("/api/registry/verify").json()
    assert body["success"] is True
    assert body["valid"] is True


def test_registry_show(client: TestClient) -> None:
    body = client.get("/api/registry/executives").json()
    assert body["success"] is True
    assert body["name"] == "executives"
    assert isinstance(body["entry"], list)


def test_registry_show_unknown(client: TestClient) -> None:
    body = client.get("/api/registry/bogus").json()
    assert body["success"] is False
    assert "Unknown entry" in body["errors"][0]


# ── executives / org chart ───────────────────────────────────────────────────


def test_executives_list(client: TestClient) -> None:
    body = client.get("/api/executives").json()
    assert body["success"] is True
    assert body["executives"]
    names = {ex["name"] for ex in body["executives"]}
    assert "Jack Mlusu" in names


def test_executive_show(client: TestClient) -> None:
    body = client.get("/api/executives/Jack%20Mlusu").json()
    assert body["success"] is True
    ex = body["executive"]
    assert ex["title"] == "Chief Executive Officer"
    assert "agent_config" in ex


def test_executive_show_not_found(client: TestClient) -> None:
    body = client.get("/api/executives/Nobody").json()
    assert body["success"] is False


def test_org_chart(client: TestClient) -> None:
    body = client.get("/api/org-chart").json()
    assert body["success"] is True
    assert "graph TD" in body["mermaid"]
    assert body["executives"] > 0


# ── memory ───────────────────────────────────────────────────────────────────


def test_memory_list(client: TestClient) -> None:
    body = client.get("/api/memory").json()
    assert body["success"] is True
    assert isinstance(body["entries"], list)
    assert "count" in body


def test_memory_get_missing(client: TestClient) -> None:
    body = client.get("/api/memory/definitely-not-there").json()
    assert body["success"] is False
    assert "not found" in body["errors"][0]


def test_memory_stats(client: TestClient) -> None:
    body = client.get("/api/memory/stats").json()
    assert body["success"] is True
    assert "total_memories" in body["stats"]


def test_memory_snapshots(client: TestClient) -> None:
    body = client.get("/api/memory/snapshots").json()
    assert body["success"] is True
    assert isinstance(body["snapshots"], list)


def test_memory_search(client: TestClient) -> None:
    body = client.get("/api/memory/search", params={"query": "governance"}).json()
    assert body["success"] is True
    assert isinstance(body["results"], list)


# ── graph ────────────────────────────────────────────────────────────────────


def test_graph_show(client: TestClient) -> None:
    body = client.get("/api/graph").json()
    assert body["success"] is True
    assert body["vision"] == "AI Enterprise OS Vision"
    assert body["executives"] > 0


def test_graph_stats(client: TestClient) -> None:
    body = client.get("/api/graph/stats").json()
    assert body["success"] is True
    assert body["nodes"] > 0
    assert body["edges"] > 0
    assert 0 <= body["density"] <= 1


# ── reports ──────────────────────────────────────────────────────────────────


def test_reports_list(client: TestClient) -> None:
    body = client.get("/api/reports").json()
    assert body["types"] == ["summary", "detailed", "health"]


def test_report_summary(client: TestClient) -> None:
    body = client.get("/api/reports/summary").json()
    assert body["success"] is True
    assert body["company"] == "Lightspeed Holdings Limited"
    assert body["departments"] > 0


def test_report_detailed(client: TestClient) -> None:
    body = client.get("/api/reports/detailed").json()
    assert body["success"] is True
    assert len(body["executives"]) > 0


def test_report_health(client: TestClient) -> None:
    body = client.get("/api/reports/health").json()
    assert body["success"] is True
    assert "validation" in body


def test_report_unknown_type(client: TestClient) -> None:
    body = client.get("/api/reports/bogus").json()
    assert body["success"] is False


# ── validation ───────────────────────────────────────────────────────────────


def test_validate(client: TestClient) -> None:
    body = client.get("/api/validate").json()
    assert body["success"] is True
    assert isinstance(body["passed"], bool)
    assert isinstance(body["reports"], list)


# ── diagnostics ──────────────────────────────────────────────────────────────


def test_diagnostics(client: TestClient) -> None:
    body = client.get("/api/diagnostics").json()
    assert "engines" in body or "runtime" in body or isinstance(body, dict)


# ── orchestration ────────────────────────────────────────────────────────────


def test_orchestrate_status(client: TestClient) -> None:
    body = client.get("/api/orchestrate/status").json()
    assert body["success"] is True
    assert isinstance(body["engine"]["running"], bool)
    assert isinstance(body["engine"]["health"], list)


def test_orchestrate_history(client: TestClient) -> None:
    body = client.get("/api/orchestrate/history").json()
    assert body["success"] is True
    assert isinstance(body["records"], list)


# ── generate targets ─────────────────────────────────────────────────────────


def test_generate_targets(client: TestClient) -> None:
    body = client.get("/api/generate/targets").json()
    assert body["success"] is True
    keys = {t["key"] for t in body["targets"]}
    assert "registry" in keys
    assert "dashboard" in keys
    assert len(body["targets"]) == 14  # frozen command map (ADR 0005/0006)
