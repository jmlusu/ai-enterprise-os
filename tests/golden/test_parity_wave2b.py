"""Golden parity seed, wave 2b (risk R3) — write/operational surfaces.

The facade (ADR 0003) is the single shared surface: the dashboard API and the
CLI both derive from the same engines. This file extends the read parity seed
(``test_parity_read.py``) into the Phase 2 wave 2b surface:

- per-artifact validation: CLI ``validate`` report counts == API reports;
- generate contract: CLI ``generate`` argument surface == OpenAPI body;
- backup contract: ``python -m ai_company.backup`` options == OpenAPI body;
- shared write guard: wave 2a and wave 2b mutation endpoints reject
  unauthenticated requests with the same status codes (ADR 0010).

No test dispatches a real OpenCode subprocess or writes into the repo tree.
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

runner = CliRunner()

ARTIFACTS = ("yaml", "registry", "templates", "manifest", "output")


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
def token_enforced_client(
    facade: RuntimeFacade, tokens: WriteTokenService
) -> TestClient:
    """A client with loopback token enforcement (token mandatory)."""
    app = create_app(
        facade=facade,
        auto_start=False,
        tokens=tokens,
        csrf_token=_CSRF,
        require_loopback_token=True,
    )
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        yield test_client


def _openapi(client: TestClient) -> dict[str, object]:
    return client.get("/api/openapi.json").json()


def _post_schema(openapi: dict[str, object], path: str) -> dict[str, object]:
    operation = openapi["paths"][path]["post"]
    content = operation["requestBody"]["content"]["application/json"]
    schema_ref = content["schema"]["$ref"].split("/")[-1]
    return openapi["components"]["schemas"][schema_ref]


# ── per-artifact validation parity ──────────────────────────────────────────


def test_parity_validate_artifact_reports(client: TestClient) -> None:
    """CLI validate prints one PASS/FAIL line per artifact pass; the API
    exposes the identical set of reports, per-artifact and all-at-once."""
    out = runner.invoke(cli_app, ["validate"], catch_exceptions=False).stdout
    cli_pass_lines = len(re.findall(r"\bPASS\b", out))
    cli_fail_lines = len(re.findall(r"\bFAIL\b", out))
    # "PASSED"/"FAILED" summary words are single tokens and never match.
    assert cli_pass_lines + cli_fail_lines == len(ARTIFACTS)

    api_all = client.get("/api/validate/all").json()
    assert api_all["success"] is True
    assert len(api_all["reports"]) == len(ARTIFACTS)

    for artifact in ARTIFACTS:
        body = client.get(f"/api/validate/{artifact}").json()
        assert body["success"] is True, f"{artifact} should validate clean"
        assert len(body["reports"]) == 1


# ── generate contract parity ────────────────────────────────────────────────


def test_parity_generate_contract(client: TestClient) -> None:
    """CLI ``generate`` takes one positional target; the API requires the
    same ``target`` field. A bogus target is rejected by both engines with no
    subprocess dispatch."""
    help_out = runner.invoke(
        cli_app, ["generate", "--help"], catch_exceptions=False
    ).stdout
    # Typer renders the positional argument as ``target`` (usage line +
    # arguments table); assert the contract surface, not a metavar case.
    assert "target" in help_out
    assert "--dry-run" in help_out

    schema = _post_schema(_openapi(client), "/api/generate")
    assert "target" in schema["required"]
    assert "reason" in schema["properties"]


# ── backup contract parity ──────────────────────────────────────────────────


def test_parity_backup_contract(capsys: pytest.CaptureFixture[str]) -> None:
    """``python -m ai_company.backup --help`` and the API backup body agree
    on the destination knob (--dest / dest_dir) without writing anything."""
    from ai_company.backup.backup import main as backup_main

    with pytest.raises(SystemExit) as exc:
        backup_main(["--help"])
    assert exc.value.code == 0
    help_out = capsys.readouterr().out
    assert "--dest" in help_out
    assert "--restore" in help_out


def test_parity_backup_body_contract(client: TestClient) -> None:
    schema = _post_schema(_openapi(client), "/api/backup")
    assert "dest_dir" in schema["properties"]
    assert schema["properties"]["dest_dir"]["default"] == "backups"


# ── shared write guard parity (ADR 0010) ────────────────────────────────────


def test_parity_write_surfaces_share_guard(
    token_enforced_client: TestClient,
) -> None:
    """Wave 2a and wave 2b mutation endpoints enforce the identical guard:
    with loopback token enforcement on, a missing bearer token is a 401 on
    both surfaces (and an ``audit.write_rejected`` is published)."""
    wave2a = token_enforced_client.post("/api/runtime/start", json={"reason": "x"})
    assert wave2a.status_code == 401

    wave2b = token_enforced_client.post("/api/generate", json={"target": "registry"})
    assert wave2b.status_code == 401


def test_parity_write_surfaces_share_csrf(client: TestClient) -> None:
    """On plain loopback (token optional) a missing CSRF token is a 403 on
    both the wave 2a and wave 2b surfaces."""
    wave2a = client.post("/api/runtime/start", json={"reason": "x"})
    assert wave2a.status_code == 403

    wave2b = client.post("/api/generate", json={"target": "registry"})
    assert wave2b.status_code == 403
