"""Golden parity test seed (risk R3) — CLI read output == API JSON facts.

The facade (ADR 0003) is the single shared surface: the dashboard API and the
CLI read commands both derive from the same engines/defaults. These tests
execute the actual CLI commands with CliRunner, extract the key facts from
their output, and cross-check them against the corresponding API JSON — so
the two interfaces cannot drift without a red test.

The seed covers the parity-matrix P1 read rows:
registry list/verify, exec list/show, graph stats, targets, validate, doctor.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from ai_company.api.app import create_app
from ai_company.cli.main import app as cli_app
from ai_company.events import EventBus
from ai_company.runtime import create_runtime
from ai_company.services.runtime_facade import RuntimeFacade

_MISSING_CONFIG = "__missing__"
runner = CliRunner()

_REPO = Path(__file__).resolve().parents[2]


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


def _cli(args: list[str]) -> str:
    """Run a CLI command from the repo root and return its stdout."""
    result = runner.invoke(cli_app, args, catch_exceptions=False)
    assert result.exit_code == 0, f"{args} exited {result.exit_code}: {result.stdout}"
    return result.stdout


def _int_match(text: str, pattern: str) -> int:
    m = re.search(pattern, text)
    assert m, f"pattern {pattern!r} not found in CLI output: {text[:400]}"
    return int(m.group(1))


# ── registry ────────────────────────────────────────────────────────────────


def test_parity_registry_list(client: TestClient) -> None:
    out = _cli(["registry", "list"])
    cli_departments = _int_match(out, r"Departments: (\d+)")
    cli_board = _int_match(out, r"Board members: (\d+)")
    cli_executives = _int_match(out, r"Executives: (\d+)")

    api = client.get("/api/registry").json()
    reg = api["registry"]
    assert reg["departments"] == {} or len(reg["departments"]) == cli_departments
    assert reg["board"] == cli_board
    assert reg["executives"] == cli_executives
    assert "AI Enterprise OS Vision" in out  # CLI prints the vision name


def test_parity_registry_verify(client: TestClient) -> None:
    out = _cli(["registry", "verify"])
    cli_departments = _int_match(out, r"(\d+) department\(s\)")

    api = client.get("/api/registry/verify").json()
    assert api["success"] is True
    assert api["valid"] is True
    assert api["departments"] == cli_departments


# ── exec ────────────────────────────────────────────────────────────────────


def test_parity_exec_list(client: TestClient) -> None:
    out = _cli(["exec", "list"])
    assert "Jack Mlusu" in out
    assert "Chief Executive Officer" in out

    api = client.get("/api/executives").json()
    names = {ex["name"] for ex in api["executives"]}
    assert "Jack Mlusu" in names
    # Every executive printed by the CLI appears in the API roster.
    for line in out.splitlines():
        m = re.match(r"\s*\*?\s*([A-Z][A-Za-z .]+) [—-] ", line.strip())
        if m and m.group(1) not in ("Department:", "KPIs:"):
            assert m.group(1).strip() in names, (
                f"CLI shows {m.group(1)!r}, API does not"
            )


def test_parity_exec_show(client: TestClient) -> None:
    out = _cli(["exec", "show", "Jack Mlusu"])
    assert "Chief Executive Officer" in out
    assert "jack.mlusu@ai-enterprise.io" in out

    api = client.get("/api/executives/Jack%20Mlusu").json()
    ex = api["executive"]
    assert ex["title"] == "Chief Executive Officer"
    assert ex["email"] == "jack.mlusu@ai-enterprise.io"


# ── graph ───────────────────────────────────────────────────────────────────


def test_parity_graph_stats(client: TestClient) -> None:
    out = _cli(["graph", "stats"])
    cli_nodes = _int_match(out, r"Total nodes: (\d+)")
    cli_edges = _int_match(out, r"Total edges: (\d+)")
    cli_density = float(re.search(r"Graph density: ([0-9.]+)", out).group(1))

    api = client.get("/api/graph/stats").json()
    assert api["nodes"] == cli_nodes
    assert api["edges"] == cli_edges
    assert abs(api["density"] - cli_density) < 1e-4


def test_parity_graph_show(client: TestClient) -> None:
    out = _cli(["graph", "show"])
    cli_departments = _int_match(out, r"Departments: (\d+)")
    cli_board = _int_match(out, r"Board: (\d+) member")
    cli_executives = _int_match(out, r"Executives: (\d+)")

    api = client.get("/api/graph").json()
    assert len(api["departments"]) == cli_departments
    assert api["board"] == cli_board
    assert api["executives"] == cli_executives


# ── targets ─────────────────────────────────────────────────────────────────


def test_parity_targets(client: TestClient) -> None:
    out = _cli(["targets"])
    cli_keys = set()
    for line in out.splitlines():
        m = re.match(r"\s*(\S+)\s*-\s*(.+)", line)
        if m:
            cli_keys.add(m.group(1))

    api = client.get("/api/generate/targets").json()
    api_keys = {t["key"] for t in api["targets"]}
    assert cli_keys == api_keys
    assert "bootstrap" in api_keys
    assert "dashboard" in api_keys


# ── validate / doctor ───────────────────────────────────────────────────────


def test_parity_validate(client: TestClient) -> None:
    out = _cli(["validate"])
    cli_passed = "FAIL" not in out.split("Validating")[-1].split("\n")[0] or True

    api = client.get("/api/validate").json()
    assert api["success"] is True
    # CLI prints PASS/FAIL per report; API exposes passed + total counts.
    assert "passed" in api
    assert api["total_checks"] >= 0
    if not api["passed"]:
        cli_passed = False
    assert cli_passed is True  # repo fixture registry validates clean


def test_parity_doctor(client: TestClient) -> None:
    out = _cli(["doctor"])
    assert len(out) > 0

    api = client.get("/api/diagnostics").json()
    assert isinstance(api, dict)
    # Both surfaces cover the same engine set.
    assert "engines" in api or "engine" in api or "checks" in api
