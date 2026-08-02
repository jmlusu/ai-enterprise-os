"""Golden parity test (risks R3 + R12) — ``runtime status`` CLI == API JSON.

The canonical status service (``services/status_service.py``) is the single
source of the four-state vocabulary (ok / watch / action / unknown) shared by
the CLI ``runtime status`` command and ``GET /api/status``. This test boots
the real runtime on both surfaces and cross-checks the canonical facts — so
the two interfaces cannot drift without a red test.
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

runner = CliRunner()

_ANSI = re.compile(r"\x1b\[[0-9;]*m")

_REPO = Path(__file__).resolve().parents[2]
_RUNTIME_CONFIG_DIR = _REPO / "config" / "runtime"


def _strip_ansi(text: str) -> str:
    """Remove ANSI styling (CI sets FORCE_COLOR, wrapping tokens)."""
    return _ANSI.sub("", text)


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
def facade(tmp_path: Path, bus: EventBus) -> RuntimeFacade:
    """A runtime whose state_dir is isolated to ``tmp_path``.

    Both surfaces boot real runtimes in this test; if they shared the
    default ``runtime/`` state dir, each construct-time read-model rebuild
    would drop/recreate the other instance's ``dashboard.db`` under it.
    Copying the runtime config with a patched ``state_dir`` keeps the two
    instances fully hermetic (production runs one runtime at a time).
    """
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
    # Teardown: never leave a booted runtime holding state files open.
    try:
        runtime.stop(reason="test-teardown")
    except Exception:
        pass


@pytest.fixture()
def client(facade: RuntimeFacade) -> TestClient:
    app = create_app(facade=facade, auto_start=False)
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        yield test_client


def _cli_status() -> str:
    """Run ``ai-company runtime status`` and return stripped stdout."""
    result = runner.invoke(cli_app, ["runtime", "status"], catch_exceptions=False)
    assert result.exit_code == 0, f"exit {result.exit_code}: {result.stdout}"
    return _strip_ansi(result.stdout)


def test_parity_runtime_status_running(
    client: TestClient, facade: RuntimeFacade
) -> None:
    """Both surfaces report the same canonical facts for a running runtime."""
    # Boot the API-side runtime (hermetic state dir) and capture its
    # canonical facts. The CLI then boots its own runtime instance.
    facade.ensure_running()
    api = client.get("/api/status").json()
    assert api["phase"] == "running"
    assert api["overall"] in ("ok", "watch", "action", "unknown")
    assert api["timestamp"], "R12: every status is time-stamped"
    health = client.get("/api/health").json()  # same vocabulary, same instance
    assert health["status"] == api["overall"]
    assert health["runtime_phase"] == api["phase"]

    out = _cli_status()  # boots its own runtime, reports, then stops it

    phase = re.search(r"Phase: (\w+)", out)
    overall = re.search(r"Overall: (\w+)", out)
    engines = re.search(r"Engines \((\d+)\):", out)
    active = re.search(
        r"Active: pipelines=(\d+) workflows=(\d+) decisions=(\d+) "
        r"meetings=(\d+) projects=(\d+) agents=(\d+)",
        out,
    )
    assert phase, f"no Phase line in: {out[:400]}"
    assert overall, f"no Overall line in: {out[:400]}"
    assert engines, f"no Engines line in: {out[:400]}"
    assert active, f"no Active line in: {out[:400]}"

    # Canonical facts agree across surfaces (same config + same service).
    assert phase.group(1) == api["phase"]
    assert overall.group(1) == api["overall"]
    assert int(engines.group(1)) == len(api["engines"])
    # Live counters are NOT parity facts: each surface snapshots its own
    # runtime instance, and a scheduled job may start/stop between snapshots.
    # Both surfaces must still expose the same counter *shape*.
    assert all(int(g) >= 0 for g in active.groups())
    for key in (
        "active_pipelines",
        "active_workflows",
        "active_decisions",
        "active_meetings",
        "active_projects",
        "active_agents",
    ):
        assert key in api and isinstance(api[key], int)


def test_parity_runtime_status_stopped(
    client: TestClient, facade: RuntimeFacade
) -> None:
    """A stopped runtime reads as ``watch``, never ``action`` (R12)."""
    api = client.get("/api/status").json()
    assert api["phase"] == "stopped"
    assert api["overall"] == "watch"  # stopped != broken

    health = client.get("/api/health").json()
    assert health["status"] == "watch"
    assert health["runtime_phase"] == "stopped"
