"""Golden parity tests (risk R3), wave 3 — write-row contract surfaces.

Every safe-write row in the parity matrix is ``1+2`` (Phase 2, ADR 0010): the
CLI command and the guarded API endpoint both exist. This file locks those
rows with the same *contract* style as wave 2b (``test_parity_generate_contract``,
``test_parity_backup_contract``): the CLI option surface and the OpenAPI
request-body schema must agree on the same semantic knob for each row.

Covered rows: ``memory save/update/snapshot/restore/archive/unarchive``,
``runtime start/stop/restart/reload``, ``orchestrate plan/start/resume/retry/
rollback``, ``report generate``, ``graph export``, ``bootstrap``, ``build``.

No test boots an engine, dispatches a subprocess, or writes into the repo tree
(``--help`` invocations only).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from ai_company.api.app import create_app
from ai_company.api.auth import WriteTokenService
from ai_company.cli.main import app as cli_app
from ai_company.events import EventBus
from ai_company.runtime import create_runtime
from ai_company.services.runtime_facade import RuntimeFacade

_MISSING_CONFIG = "__missing__"
_TOKEN = "test-write-token-0123456789abcdef"
_CSRF = "test-csrf-token-0123456789abcdef"

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")

runner = CliRunner()


def _strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE.sub("", text)


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


def _cli_help(args: list[str]) -> str:
    """Run ``ai-company <args> --help`` and return stripped stdout."""
    result = runner.invoke(cli_app, args + ["--help"], catch_exceptions=False)
    assert result.exit_code == 0, f"{args} --help exited {result.exit_code}"
    return _strip_ansi(result.stdout)


def _openapi(client: TestClient) -> dict[str, object]:
    return client.get("/api/openapi.json").json()


def _post_schema(openapi: dict[str, object], path: str) -> dict[str, object]:
    operation = openapi["paths"][path]["post"]
    content = operation["requestBody"]["content"]["application/json"]
    schema_ref = content["schema"]["$ref"].split("/")[-1]
    return openapi["components"]["schemas"][schema_ref]


def _assert_prop(schema: dict[str, object], name: str) -> None:
    assert name in schema["properties"], f"OpenAPI body missing {name!r}"


# ── memory write rows ───────────────────────────────────────────────────────


def test_parity_memory_save_contract(client: TestClient) -> None:
    help_out = _cli_help(["memory", "save"])
    for knob in ("--type", "--namespace", "--tags", "--source", "--importance"):
        assert knob in help_out, f"CLI memory save missing {knob}"

    schema = _post_schema(_openapi(client), "/api/memory/save")
    assert "content" in schema["required"]
    for prop in ("memory_type", "namespace", "tags", "source", "importance"):
        _assert_prop(schema, prop)


def test_parity_memory_update_contract(client: TestClient) -> None:
    help_out = _cli_help(["memory", "update"])
    for knob in ("--content", "--tags", "--importance"):
        assert knob in help_out, f"CLI memory update missing {knob}"

    schema = _post_schema(_openapi(client), "/api/memory/update")
    assert "memory_id" in schema["required"]
    for prop in ("content", "tags", "importance"):
        _assert_prop(schema, prop)


def test_parity_memory_snapshot_contract(client: TestClient) -> None:
    help_out = _cli_help(["memory", "snapshot"])
    assert "name" in help_out

    schema = _post_schema(_openapi(client), "/api/memory/snapshot")
    _assert_prop(schema, "name")


def test_parity_memory_restore_contract(client: TestClient) -> None:
    help_out = _cli_help(["memory", "restore"])
    assert "snapshot_id" in help_out

    schema = _post_schema(_openapi(client), "/api/memory/restore")
    assert "snapshot_id" in schema["required"]


def test_parity_memory_archive_contract(client: TestClient) -> None:
    help_out = _cli_help(["memory", "archive"])
    assert "memory_id" in help_out

    openapi = _openapi(client)
    schema = _post_schema(openapi, "/api/memory/{key}/archive")
    _assert_prop(schema, "reason")


def test_parity_memory_unarchive_contract(client: TestClient) -> None:
    help_out = _cli_help(["memory", "unarchive"])
    assert "memory_id" in help_out

    openapi = _openapi(client)
    schema = _post_schema(openapi, "/api/memory/{key}/unarchive")
    _assert_prop(schema, "reason")


# ── runtime write rows ──────────────────────────────────────────────────────


def test_parity_runtime_stop_contract(client: TestClient) -> None:
    help_out = _cli_help(["runtime", "stop"])
    assert "--reason" in help_out

    schema = _post_schema(_openapi(client), "/api/runtime/stop")
    _assert_prop(schema, "reason")


def test_parity_runtime_restart_contract(client: TestClient) -> None:
    help_out = _cli_help(["runtime", "restart"])
    assert "--reason" in help_out

    schema = _post_schema(_openapi(client), "/api/runtime/restart")
    _assert_prop(schema, "reason")


def test_parity_runtime_start_contract(client: TestClient) -> None:
    help_out = _cli_help(["runtime", "start"])
    assert "--config-dir" in help_out

    schema = _post_schema(_openapi(client), "/api/runtime/start")
    _assert_prop(schema, "reason")


def test_parity_runtime_reload_contract(client: TestClient) -> None:
    help_out = _cli_help(["runtime", "reload"])
    assert "--config-dir" in help_out

    schema = _post_schema(_openapi(client), "/api/runtime/reload")
    _assert_prop(schema, "reason")


# ── orchestrate write rows ──────────────────────────────────────────────────


def test_parity_orchestrate_plan_contract(client: TestClient) -> None:
    help_out = _cli_help(["orchestrate", "plan"])
    for knob in ("--file", "--schedule-mode"):
        assert knob in help_out, f"CLI orchestrate plan missing {knob}"

    schema = _post_schema(_openapi(client), "/api/orchestrate/plan")
    for prop in ("name", "yaml_path", "data", "description"):
        _assert_prop(schema, prop)


def test_parity_orchestrate_start_contract(client: TestClient) -> None:
    help_out = _cli_help(["orchestrate", "start"])
    assert "pipeline" in help_out

    schema = _post_schema(_openapi(client), "/api/orchestrate/start")
    assert "plan_id" in schema["required"]


def test_parity_orchestrate_resume_contract(client: TestClient) -> None:
    help_out = _cli_help(["orchestrate", "resume"])
    assert "--checkpoint-id" in help_out

    schema = _post_schema(_openapi(client), "/api/orchestrate/resume")
    assert "plan_id" in schema["required"]
    _assert_prop(schema, "checkpoint_id")


def test_parity_orchestrate_retry_contract(client: TestClient) -> None:
    help_out = _cli_help(["orchestrate", "retry"])
    assert "plan_id" in help_out

    schema = _post_schema(_openapi(client), "/api/orchestrate/retry")
    assert "plan_id" in schema["required"]


def test_parity_orchestrate_rollback_contract(client: TestClient) -> None:
    help_out = _cli_help(["orchestrate", "rollback"])
    assert "--reason" in help_out

    schema = _post_schema(_openapi(client), "/api/orchestrate/rollback")
    assert "plan_id" in schema["required"]
    _assert_prop(schema, "reason")


# ── reports / graph / top-level write rows ──────────────────────────────────


def test_parity_report_generate_contract(client: TestClient) -> None:
    help_out = _cli_help(["report", "generate"])
    assert "summary" in help_out
    assert "detailed" in help_out
    assert "health" in help_out

    schema = _post_schema(_openapi(client), "/api/reports/generate")
    assert schema["properties"]["report_type"]["default"] == "summary"
    assert "detailed" in schema["properties"]["report_type"]["pattern"]


def test_parity_graph_export_contract(client: TestClient) -> None:
    graph_help = _cli_help(["graph"])
    assert "export" in graph_help

    schema = _post_schema(_openapi(client), "/api/graph/export")
    assert schema["properties"]["output_dir"]["default"] == "generated"


def test_parity_bootstrap_contract(client: TestClient) -> None:
    top = _cli_help([])
    assert "bootstrap" in top

    schema = _post_schema(_openapi(client), "/api/bootstrap")
    _assert_prop(schema, "reason")


def test_parity_build_contract(client: TestClient) -> None:
    top = _cli_help([])
    assert "build" in top

    schema = _post_schema(_openapi(client), "/api/build")
    _assert_prop(schema, "reason")
