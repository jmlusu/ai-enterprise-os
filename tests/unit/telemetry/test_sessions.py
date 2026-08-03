"""Unit tests for OpenCode session telemetry (sprint 5.5 P2).

Covers the fail-open JSONL capture, the tail read, and the newest-checkpoint-
per-session summary that powers the /telemetry Sessions panel.
"""

from __future__ import annotations

from typing import Any

import pytest

from ai_company.telemetry.sessions import (
    read_session_telemetry,
    record_session_telemetry,
    session_telemetry_summary,
)


@pytest.fixture(autouse=True)
def _isolated_log(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the session telemetry log at a temp file per test."""
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "runtime" / "session_telemetry.jsonl"
    monkeypatch.setattr(
        "ai_company.telemetry.sessions.SESSION_TELEMETRY_RELATIVE_PATH",
        target.relative_to(tmp_path),
    )


def _record(session_id: str, **overrides: Any) -> None:
    defaults: dict[str, Any] = {
        "session_id": session_id,
        "title": "session title",
        "messages_user": 1,
        "messages_assistant": 2,
        "tool_calls": 3,
        "commands_run": 1,
        "tools_used": {"read": 2, "bash": 1},
        "tokens_input": 100,
        "tokens_output": 50,
        "cost": 0.01,
        "end_reason": "idle",
    }
    defaults.update(overrides)
    record_session_telemetry(**defaults)


def test_record_and_read_session_telemetry(tmp_path: Any) -> None:
    _record("sess-1")
    records = read_session_telemetry()
    assert len(records) == 1
    assert records[0]["session_id"] == "sess-1"
    assert records[0]["messages_assistant"] == 2
    assert records[0]["tools_used"] == {"read": 2, "bash": 1}
    assert records[0]["timestamp"]  # capture time drives retention truncation


def test_read_missing_file_is_empty(tmp_path: Any) -> None:
    assert read_session_telemetry() == []


def test_summary_empty_without_records(tmp_path: Any) -> None:
    summary = session_telemetry_summary()
    assert summary["records"] == 0
    assert summary["sessions"] == 0
    assert summary["recent"] == []
    assert summary["totals"]["tool_calls"] == 0


def test_summary_dedups_checkpoints_to_newest_per_session(tmp_path: Any) -> None:
    _record("sess-1", end_reason="idle", messages_assistant=2)
    _record("sess-1", end_reason="idle", messages_assistant=3)
    _record("sess-1", end_reason="deleted", messages_assistant=4)
    _record("sess-2", end_reason="idle", messages_assistant=5, tool_calls=1)
    summary = session_telemetry_summary()
    assert summary["records"] == 4
    assert summary["sessions"] == 2
    assert len(summary["recent"]) == 2
    by_id = {r["session_id"]: r for r in summary["recent"]}
    assert by_id["sess-1"]["messages_assistant"] == 4
    assert by_id["sess-1"]["end_reason"] == "deleted"
    assert by_id["sess-2"]["tool_calls"] == 1
    assert summary["totals"]["assistant_messages"] == 9
    assert summary["totals"]["sessions"] == 2


def test_summary_recent_orders_by_capture_time(tmp_path: Any) -> None:
    _record("older")
    _record("newer")
    summary = session_telemetry_summary()
    assert summary["recent"][0]["session_id"] == "newer"


def test_summary_by_model_and_end_reason(tmp_path: Any) -> None:
    _record("sess-a", model_id="alpha", end_reason="idle")
    _record("sess-b", model_id="alpha", end_reason="deleted")
    _record("sess-c", end_reason="shutdown")
    summary = session_telemetry_summary()
    by_model = {row["model_id"]: row for row in summary["by_model"]}
    assert by_model["alpha"]["sessions"] == 2
    assert by_model["(unknown)"]["sessions"] == 1
    assert summary["by_end_reason"]["deleted"] == 1
    assert summary["by_end_reason"]["shutdown"] == 1


def test_record_fail_open_when_write_path_unusable(tmp_path: Any) -> None:
    # ``runtime`` exists as a plain file, so mkdir fails — the capture must
    # swallow the error and never raise (telemetry never breaks the caller).
    (tmp_path / "runtime").write_text("not a directory", encoding="utf-8")
    record_session_telemetry(session_id="s")
    assert read_session_telemetry() == []


def test_log_prunes_oversized_file(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai_company.telemetry import sessions as module

    monkeypatch.setattr(module, "_MAX_RECORDS", 3)
    for _ in range(5):
        _record("sess-x", title="x")
    records = read_session_telemetry()
    assert len(records) == 3  # newest kept after prune
    # Prune rewrote the file, so the log is bounded at the cap.
    with (tmp_path / "runtime" / "session_telemetry.jsonl").open(
        encoding="utf-8"
    ) as handle:
        lines = handle.readlines()
    assert len(lines) == 3
