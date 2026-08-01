"""Unit tests for the dashboard write-auth infrastructure (ADR 0010, wave 2a).

Covers the bearer-token service (create/rotate/revoke/verify, hash-at-rest,
env override), the per-run CSRF synchronizer, the loopback Host allowlist,
and the mandatory write-audit helpers (``audit.write`` /
``audit.write_rejected``, fail-open to a JSONL file).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from ai_company.api.auth import (
    CsrfService,
    WriteTokenService,
    host_allowed,
    publish_write_audit,
    publish_write_rejected,
)
from ai_company.events import EventBus, ReplayRequest

# ── host allowlist (risk R9) ────────────────────────────────────────────────


def test_host_allowed_loopback_variants() -> None:
    for host in (
        "127.0.0.1",
        "127.0.0.1:8000",
        "localhost",
        "localhost:8000",
        "[::1]",
        "[::1]:8000",
    ):
        assert host_allowed(host), host


def test_host_allowed_rejects_non_loopback() -> None:
    for host in (
        "",
        "evil.example.com",
        "10.0.0.5",
        "192.168.1.10:8000",
        "127.0.0.2",
        "127.0.0.1.evil.com",
        "::1",  # RFC 3986: IPv6 Host headers use [::1], not bare ::1
    ):
        assert not host_allowed(host), host


# ── CSRF synchronizer (ADR 0010 §2) ─────────────────────────────────────────


def test_csrf_verify_roundtrip() -> None:
    service = CsrfService(token="fixed-token")
    assert service.token == "fixed-token"
    assert service.verify("fixed-token")
    assert not service.verify("wrong")
    assert not service.verify(None)
    assert not service.verify("")


def test_csrf_random_per_run() -> None:
    first, second = CsrfService(), CsrfService()
    assert first.token and second.token
    assert first.token != second.token
    assert first.verify(first.token)
    assert not second.verify(first.token)


# ── bearer token service (ADR 0010 §1) ──────────────────────────────────────


def test_token_create_returns_value_only_on_first_creation(tmp_path: Path) -> None:
    service = WriteTokenService(token_file=tmp_path / "tok")
    first = service.create()
    assert first is not None
    assert len(first) >= 32  # token_urlsafe(32) -> >= 256 bits of entropy
    assert service.has_token()
    assert service.verify(first)

    second = service.create()  # rotation never reveals the new value
    assert second is None
    assert not service.verify(first)  # rotation replaces the stored secret
    assert not service.verify("anything-else")


def test_token_verify_is_constant_time_and_env_managed(tmp_path: Path) -> None:
    service = WriteTokenService(token_file=tmp_path / "tok", env_token="env-secret")
    assert service.managed_by_env is True
    assert service.has_token()
    assert service.verify("env-secret")
    assert not service.verify("env-secret2")
    assert not service.verify(None)
    with pytest.raises(ValueError, match="managed by"):
        service.create()
    with pytest.raises(ValueError, match="managed by"):
        service.revoke()


def test_token_hash_at_rest(tmp_path: Path) -> None:
    path = tmp_path / "tok"
    service = WriteTokenService(token_file=path, hash_at_rest=True)
    created = service.create()
    assert created is not None
    stored = path.read_text(encoding="utf-8").strip()
    assert stored == hashlib.sha256(created.encode("utf-8")).hexdigest()
    assert stored != created

    reloaded = WriteTokenService(token_file=path, hash_at_rest=True)
    assert reloaded.verify(created)
    assert not reloaded.verify("wrong")
    assert not reloaded.verify(stored)  # digest is not itself the token


def test_token_revoke(tmp_path: Path) -> None:
    path = tmp_path / "tok"
    service = WriteTokenService(token_file=path)
    created = service.create()
    assert created is not None and service.has_token()
    service.revoke()
    assert not service.has_token()
    assert not path.exists()
    assert service.info()["created_at"] is None


def test_token_info_never_leaks_value(tmp_path: Path) -> None:
    path = tmp_path / "tok"
    service = WriteTokenService(token_file=path, hash_at_rest=True)
    created = service.create()
    assert created is not None
    info = service.info()
    assert info["path"] == str(path)
    assert info["hash_at_rest"] is True
    assert info["managed_by_env"] is False
    assert created not in json.dumps(info)


# ── write audit publishing (ADR 0010 §3) ────────────────────────────────────


@pytest.fixture()
def bus(tmp_path: Path) -> EventBus:
    instance = EventBus(
        storage_path=str(tmp_path / "events.jsonl"),
        dead_letter_path=str(tmp_path / "dead_letter.jsonl"),
    )
    instance.start()
    yield instance
    instance.stop()


def _replayed(bus: EventBus) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    bus.replay(
        ReplayRequest(limit=200),
        lambda event: collected.append(event.model_dump(mode="json")),
    )
    return collected


def test_publish_write_audit_and_rejected(bus: EventBus) -> None:
    publish_write_audit(
        bus, action="memory.save", result="ok", details={"memory_id": "m1"}
    )
    publish_write_rejected(
        bus, action="runtime.stop", reason="unauthorized", detail="invalid token"
    )
    events = _replayed(bus)
    types = [e["metadata"]["event_type"] for e in events]
    assert "audit.write" in types
    assert "audit.write_rejected" in types

    write_event = next(
        e for e in events if e["metadata"]["event_type"] == "audit.write"
    )
    assert write_event["payload"]["action"] == "memory.save"
    assert write_event["payload"]["result"] == "ok"
    assert write_event["payload"]["details"] == {"memory_id": "m1"}

    rejected = next(
        e for e in events if e["metadata"]["event_type"] == "audit.write_rejected"
    )
    assert rejected["payload"]["action"] == "runtime.stop"
    assert rejected["payload"]["reason"] == "unauthorized"
    # rejected payloads never carry the submitted token/CSRF fields
    assert "token" not in rejected["payload"]
    assert "csrf" not in rejected["payload"]


class _BoomBus:
    """An event bus whose publish always fails (fail-open exercise)."""

    def publish(self, event: Any) -> None:
        raise RuntimeError("event bus unavailable")


def test_audit_fail_open_appends_jsonl(tmp_path: Path) -> None:
    failed_path = tmp_path / "failed.jsonl"
    publish_write_audit(
        _BoomBus(),
        action="memory.save",
        result="ok",
        failed_path=failed_path,
    )
    lines = failed_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["metadata"]["event_type"] == "audit.write"
    assert data["payload"]["action"] == "memory.save"


def test_audit_fail_open_never_raises(tmp_path: Path) -> None:
    # publish failing AND the fail-open file being unwritable must not raise.
    publish_write_rejected(
        _BoomBus(),
        action="validate.run",
        reason="unauthorized",
        failed_path=tmp_path / "no" / "such" / "dir" / "failed.jsonl",
    )
