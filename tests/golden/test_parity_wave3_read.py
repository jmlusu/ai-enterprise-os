"""Golden parity tests (risk R3), wave 3 — read rows: CLI output == API JSON.

Extends the parity seed (``test_parity_read.py``, ``test_parity_status.py``,
``test_parity_wave2b.py``) across the read rows not yet golden-tested:

- ``registry show`` (vision + board)
- ``exec org-chart`` (Mermaid)
- ``memory list / get / search / show / stats / snapshots``
- ``report generate summary / detailed / health``
- ``company board-report``
- ``orchestrate status / history``
- ``runtime health / metrics / diagnostics``

Same invariant as the seed: the facade (ADR 0003) is the single shared
surface, so CLI output and API JSON derive from the same engines and cannot
drift without a red test.

Hermeticity: memory and orchestration tests chdir into ``tmp_path`` so their
cwd-relative stores (``memory/store.jsonl``, ``memory/snapshots``) stay out of
the repo tree. Runtime tests boot real runtimes with a state dir isolated to
``tmp_path`` (see ``test_parity_status.py``). No test dispatches a subprocess
or writes into the repo tree.
"""

from __future__ import annotations

import re
import shutil
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

_ANSI = re.compile(r"\x1b\[[0-9;]*m")

_REPO = Path(__file__).resolve().parents[2]
_RUNTIME_CONFIG_DIR = _REPO / "config" / "runtime"


def _strip_ansi(text: str) -> str:
    """Remove ANSI styling (CI sets FORCE_COLOR, wrapping rich tokens)."""
    return _ANSI.sub("", text)


def _cli(args: list[str]) -> str:
    """Run a CLI command from the current working directory and return stdout."""
    result = runner.invoke(cli_app, args, catch_exceptions=False)
    assert result.exit_code == 0, f"{args} exited {result.exit_code}: {result.stdout}"
    return _strip_ansi(result.stdout)


def _int_match(text: str, pattern: str) -> int:
    m = re.search(pattern, text)
    assert m, f"pattern {pattern!r} not found in CLI output: {text[:400]}"
    return int(m.group(1))


def _collapse_ws(text: str) -> str:
    """Collapse runs of whitespace — rich soft-wrap adds line breaks."""
    return re.sub(r"\s+", " ", text).strip()


# ── plain loopback client (repo cwd — registry/report rows) ────────────────


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


# ── isolated-cwd client (memory / orchestration rows) ───────────────────────


@pytest.fixture()
def iso_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A facade + API client constructed inside a tmp cwd.

    Memory and orchestration engines resolve their cwd-relative storage
    (``config/memory/memory.yaml`` else ``memory/store.jsonl``,
    ``memory/snapshots``) at call time, so building the surfaces after
    ``chdir`` keeps every write inside ``tmp_path`` — hermetic.
    """
    monkeypatch.chdir(tmp_path)
    instance = EventBus(
        storage_path=str(tmp_path / "events.jsonl"),
        dead_letter_path=str(tmp_path / "dead_letter.jsonl"),
    )
    instance.start()
    runtime = create_runtime(config_dir=_MISSING_CONFIG, event_bus=instance)
    facade = RuntimeFacade(config_dir=_MISSING_CONFIG, runtime=runtime)
    app = create_app(facade=facade, auto_start=False)
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        yield facade, test_client
    instance.stop()


# ── registry show ───────────────────────────────────────────────────────────


def test_parity_registry_show_vision(client: TestClient) -> None:
    out = _cli(["registry", "show", "vision"])
    cli_name = re.search(r"^\s*Name: (.+)$", out, re.MULTILINE)
    cli_company = re.search(r"^\s*Company: (.+)$", out, re.MULTILINE)
    assert cli_name and cli_company, f"unexpected vision output: {out[:400]}"

    api = client.get("/api/registry/vision").json()
    assert api["success"] is True
    entry = api["entry"]
    assert entry["name"] == cli_name.group(1).strip()
    assert entry["company_name"] == cli_company.group(1).strip() or (
        not entry["company_name"] and cli_company.group(1).strip() == ""
    )


def test_parity_registry_show_board(client: TestClient) -> None:
    out = _cli(["registry", "show", "board"])
    cli_names = re.findall(r"^\s*-\s*(.+?)\s+\((.+)\)\s*$", out, re.MULTILINE)
    assert cli_names, f"no board lines in: {out[:400]}"

    api = client.get("/api/registry/board").json()
    assert api["success"] is True
    entry = api["entry"]
    assert len(entry) == len(cli_names)
    api_names = {b.get("name") for b in entry}
    assert {name for name, _ in cli_names} <= api_names


def test_parity_exec_org_chart(
    tmp_path: Path, iso_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``exec org-chart`` Mermaid == ``GET /api/org-chart`` mermaid.

    Runs in an isolated cwd with the registry copied in so the CLI's
    ``generated/org_chart.md`` write stays inside tmp_path.
    """
    shutil.copytree(_REPO / "company", tmp_path / "company")
    shutil.copytree(_REPO / "config" / "company", tmp_path / "config" / "company")
    facade, client = iso_client

    out = _cli(["exec", "org-chart"])
    start = out.index("```mermaid")
    end = out.index("```", start + len("```mermaid")) + 3
    cli_chart = out[start:end]

    api = client.get("/api/org-chart").json()
    assert api["success"] is True
    # Rich soft-wraps the long mermaid lines at the console width, so the CLI
    # render differs from the canonical string only by whitespace/newlines.
    assert _collapse_ws(api["mermaid"]) == _collapse_ws(cli_chart)
    assert "graph TD" in api["mermaid"]


# ── memory (isolated cwd, deterministic store) ──────────────────────────────


def _seed_memory(facade: RuntimeFacade, client: TestClient) -> dict[str, str]:
    """Save two entries via the facade; return their ids.

    The default engine keeps snapshots in-memory only (``MemorySnapshot`` is
    wired without a snapshot dir), so a fresh engine instance — the CLI and the
    facade create one per call — never lists snapshots; the parity test for
    ``memory snapshots`` therefore asserts the honest empty case.
    """
    e1 = facade.memory_save(
        content={"text": "golden alpha memory"},
        memory_type="system",
        namespace="global",
        tags=["golden"],
        source="cli",
        importance=0.8,
    )
    e2 = facade.memory_save(
        content={"text": "golden beta memory"},
        memory_type="executive",
        namespace="executive",
        tags=["golden", "exec"],
        source="cli",
        importance=0.6,
    )
    assert e1["success"] and e2["success"], (e1, e2)
    return {
        "id1": e1["entry"]["id"],
        "id2": e2["entry"]["id"],
    }


def test_parity_memory_list(iso_client) -> None:
    facade, client = iso_client
    ids = _seed_memory(facade, client)

    out = _cli(["memory", "list"])
    cli_ids = {m.group(1) for m in re.finditer(r"^\s{2}(\S+)\s+", out, re.MULTILINE)}
    assert {ids["id1"], ids["id2"]} <= cli_ids

    api = client.get("/api/memory").json()
    assert api["success"] is True
    api_ids = {e["id"] for e in api["entries"]}
    assert {ids["id1"], ids["id2"]} <= api_ids
    assert cli_ids <= api_ids


def test_parity_memory_get(iso_client) -> None:
    facade, client = iso_client
    ids = _seed_memory(facade, client)

    out = _cli(["memory", "get", ids["id1"]])
    cli_type = re.search(r"^\s*Type: (\S+)$", out, re.MULTILINE)
    cli_summary = re.search(r"^\s*Summary: (.*)$", out, re.MULTILINE)
    assert cli_type and cli_summary

    api = client.get(f"/api/memory/{ids['id1']}").json()
    assert api["success"] is True
    entry = api["entry"]
    assert entry["id"] == ids["id1"]
    assert entry["memory_type"] == cli_type.group(1).strip()
    # The engine's summary carries a "[<ns>] [<type>] " prefix; rich consumes
    # those "[...]" tokens as markup on the CLI, so the rendered line equals
    # the API summary with the prefix removed.
    prefix = f"[{entry['namespace']}] [{entry['memory_type']}] "
    api_summary = entry["summary"]
    api_summary = api_summary.removeprefix(prefix)
    assert api_summary.strip() == cli_summary.group(1).strip()


def test_parity_memory_search(iso_client) -> None:
    facade, client = iso_client
    ids = _seed_memory(facade, client)

    out = _cli(["memory", "search", "beta"])
    cli_ids = {
        m.group(1) for m in re.finditer(r"^\s{2}\d+\.\s+(\S+)", out, re.MULTILINE)
    }
    assert ids["id2"] in cli_ids

    api = client.get("/api/memory/search", params={"query": "beta"}).json()
    assert api["success"] is True
    api_ids = {r["id"] for r in api["results"]}
    assert ids["id2"] in api_ids
    assert cli_ids == api_ids


def test_parity_memory_show(iso_client) -> None:
    facade, client = iso_client
    _seed_memory(facade, client)

    out = _cli(["memory", "show"])
    cli_total = _int_match(out, r"Total entries: (\d+)")
    cli_archived = _int_match(out, r"Archived: (\d+)")
    cli_snapshots = _int_match(out, r"Snapshots: (\d+)")
    cli_avg = float(re.search(r"Average importance: ([0-9.]+)", out).group(1))

    api = client.get("/api/memory/stats").json()
    assert api["success"] is True
    stats = api["stats"]
    assert stats["total_memories"] == cli_total
    assert stats["total_archived"] == cli_archived
    assert stats["total_snapshots"] == cli_snapshots
    assert abs(stats["average_importance"] - cli_avg) < 1e-3


def test_parity_memory_stats(iso_client) -> None:
    facade, client = iso_client
    _seed_memory(facade, client)

    out = _cli(["memory", "stats"])
    # Only the "By Type:" block is parsed — later summary lines (Embeddings:,
    # Avg importance:, Total size:) are not per-type counts.
    block = out.split("By Type:", 1)[1].split("By Namespace:", 1)[0]
    cli_by_type = {
        m.group(1): int(m.group(2))
        for m in re.finditer(r"^\s{2}(\S+)\s*:\s*(\d+)\s*$", block, re.MULTILINE)
    }

    api = client.get("/api/memory/stats").json()
    stats = api["stats"]
    assert stats["by_type"] == cli_by_type


def test_parity_memory_snapshots(iso_client) -> None:
    facade, client = iso_client
    _seed_memory(facade, client)

    # The default engine keeps snapshots in-memory per instance, so both the
    # CLI and the API (each booting a fresh engine) report the empty state.
    out = _cli(["memory", "snapshots"])
    assert "No snapshots found." in out

    api = client.get("/api/memory/snapshots").json()
    assert api["success"] is True
    assert api["snapshots"] == []


# ── reports ─────────────────────────────────────────────────────────────────


def test_parity_report_summary(client: TestClient) -> None:
    out = _cli(["report", "generate", "summary"])
    cli = {
        "departments": _int_match(out, r"Departments: (\d+)"),
        "roles": _int_match(out, r"Roles: (\d+)"),
        "board": _int_match(out, r"Board members: (\d+)"),
        "workflows": _int_match(out, r"Workflows: (\d+)"),
    }

    api = client.get("/api/reports/summary").json()
    assert api["success"] is True
    assert api["departments"] == cli["departments"]
    assert api["roles"] == cli["roles"]
    assert api["board"] == cli["board"]
    assert api["workflows"] == cli["workflows"]


def test_parity_report_detailed(client: TestClient) -> None:
    out = _cli(["report", "generate", "detailed"])

    api = client.get("/api/reports/detailed").json()
    assert api["success"] is True

    for dept_name in api["departments"]:
        for role in api["departments"][dept_name]["roles"]:
            title = role["title"]
            desc = role.get("description") or ""
            assert re.search(re.escape(f"- {title}: {desc}"), out, re.MULTILINE), (
                f"CLI report missing role {title!r}"
            )

    api_board = {b.get("name") for b in api["board"]}
    if api_board:
        # Parse only the Board section — the Executives section below it has
        # the same "- name (title)" shape.
        board_block = out.split("  Board:", 1)[1].partition("  Executives:")[0]
        cli_board = {
            m.group(1)
            for m in re.finditer(r"^\s+- (.+?) \(.+\)\s*$", board_block, re.MULTILINE)
        }
        assert {n for n in cli_board if n != "(unnamed)"} == api_board


def test_parity_report_health(client: TestClient) -> None:
    out = _cli(["report", "generate", "health"])
    cli_pass = len(re.findall(r"\bPASS\b", out))

    api = client.get("/api/reports/health").json()
    assert api["success"] is True
    validation = api["validation"]
    reports = validation["reports"]
    assert cli_pass == sum(1 for r in reports if r["passed"])


# ── company board-report ────────────────────────────────────────────────────


def test_parity_company_board_report(client: TestClient) -> None:
    out = _cli(["company", "board-report"])
    cli_count = _int_match(out, r"Board Members: (\d+)")
    cli_names = {
        m.group(1)
        for m in re.finditer(r"^\s+-\s+(.+?)\s+\((.+)\)\s*$", out, re.MULTILINE)
    }

    api = client.get("/api/registry/board").json()
    assert api["success"] is True
    entry = api["entry"]
    assert len(entry) == cli_count
    assert {b.get("name") for b in entry} == cli_names


# ── orchestration (isolated cwd) ────────────────────────────────────────────


def test_parity_orchestrate_status(iso_client) -> None:
    facade, client = iso_client

    out = _cli(["orchestrate", "status"])
    cli_name = re.search(r"^\s*Name: (.+) \(v(.+)\)$", out, re.MULTILINE)
    cli_running = re.search(r"^\s*Running: (True|False)$", out, re.MULTILINE)
    cli_active = re.search(r"^\s*Active plans: (\d+)$", out, re.MULTILINE)
    cli_health = re.search(r"^\s*Health: (\d+) probe\(s\)$", out, re.MULTILINE)
    assert cli_name and cli_running and cli_active and cli_health

    api = client.get("/api/orchestrate/status").json()
    assert api["success"] is True
    engine = api["engine"]
    assert engine["name"] == cli_name.group(1).strip()
    assert engine["version"] == cli_name.group(2).strip()
    assert engine["running"] == (cli_running.group(1) == "True")
    assert engine["active_plans"] == int(cli_active.group(1))
    assert len(engine["health"]) == int(cli_health.group(1))


def test_parity_orchestrate_history_empty(iso_client) -> None:
    facade, client = iso_client

    out = _cli(["orchestrate", "history"])
    assert "No execution history found." in out

    api = client.get("/api/orchestrate/history").json()
    assert api["success"] is True
    assert api["count"] == 0
    assert api["records"] == []


# ── runtime (hermetic runtime on both surfaces) ─────────────────────────────


@pytest.fixture()
def rt_facade(tmp_path: Path, bus: EventBus) -> RuntimeFacade:
    """A runtime whose state_dir is isolated to ``tmp_path`` (as status test)."""
    cfg = tmp_path / "runtime-config"
    shutil.copytree(_RUNTIME_CONFIG_DIR, cfg / "runtime")
    runtime_yaml = cfg / "runtime" / "runtime.yaml"
    state_dir = str(tmp_path / "state").replace("\\", "/")
    runtime_yaml.write_text(
        re.sub(
            r'state_dir:\s*"[^"]*"',
            f'state_dir: "{state_dir}"',
            runtime_yaml.read_text(encoding="utf-8"),
            count=1,
        ),
        encoding="utf-8",
    )
    runtime = create_runtime(config_dir=str(cfg), event_bus=bus)
    yield RuntimeFacade(config_dir=str(cfg), runtime=runtime)
    try:
        runtime.stop(reason="test-teardown")
    except Exception:
        pass


@pytest.fixture()
def rt_client(rt_facade: RuntimeFacade) -> TestClient:
    app = create_app(facade=rt_facade, auto_start=False)
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        yield test_client


def test_parity_runtime_health(rt_client: TestClient, rt_facade: RuntimeFacade) -> None:
    """Both surfaces report the same health-check set for the same config."""
    rt_facade.ensure_running()
    api = rt_client.get("/api/health").json()
    api_checks = api["checks"]

    out = _cli(["runtime", "health"])
    cli_checks = re.findall(
        r"^  \S+ +([\w-]+) +(healthy|degraded|unhealthy)(?: \(\d+ms\))?\s*$",
        out,
        re.MULTILINE,
    )
    assert len(cli_checks) == len(api_checks)
    summary = re.search(
        r"Summary: (\d+) healthy / (\d+) degraded / (\d+) unhealthy", out
    )
    assert summary, f"no summary line in: {out[:400]}"
    healthy, degraded, unhealthy = (int(g) for g in summary.groups())
    assert healthy + degraded + unhealthy == len(api_checks)
    assert healthy == sum(1 for c in api_checks if c["status"] == "healthy")


def test_parity_runtime_metrics(
    rt_client: TestClient, rt_facade: RuntimeFacade
) -> None:
    """Engine-count facts agree across surfaces (live counters stay shape-only)."""
    rt_facade.ensure_running()
    api = rt_client.get("/api/metrics").json()

    out = _cli(["runtime", "metrics"])
    engines = re.search(
        r"Engines: active=(\d+) healthy=(\d+) degraded=(\d+) failed=(\d+)", out
    )
    assert engines, f"no engines line in: {out[:400]}"
    active, healthy, degraded, failed = (int(g) for g in engines.groups())
    assert active == api["active_engines"]
    assert healthy + degraded + failed == active
    assert api["active_engines"] >= 0
    assert api["jobs_executed"] >= 0


def test_parity_runtime_diagnostics(
    rt_client: TestClient, rt_facade: RuntimeFacade
) -> None:
    """Diagnostic shape (engines / health checks / config sections) agrees."""
    rt_facade.ensure_running()
    api = rt_client.get("/api/diagnostics").json()

    out = _cli(["runtime", "diagnostics"])
    sizes = re.search(r"Engines: (\d+) \| Health checks: (\d+)", out)
    assert sizes, f"no sizes line in: {out[:400]}"
    engines, health_checks = (int(g) for g in sizes.groups())
    assert engines == len(api["engines"])
    assert health_checks == len(api["health_checks"])
    sections = _int_match(out, r"Config sections: (\d+)")
    assert sections == len(api["config_sections"])
