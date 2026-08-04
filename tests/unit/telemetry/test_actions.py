"""Unit tests for GUI/desktop action telemetry (sprint 5.5 P5, D5).

Covers the fail-open JSONL capture, the tail read, pruning, and the honest
D5 share computation: numerator = GUI + desktop (+ session commands/tool calls,
newest checkpoint per session) over the trailing window, denominator adds the
signed-off CLI baseline (``runtime/cli_telemetry.jsonl``).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from ai_company.telemetry.actions import (
    action_share_summary,
    read_action_records,
    record_action,
)


@pytest.fixture(autouse=True)
def _isolated_logs(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve all telemetry paths (actions/CLI/sessions) under ``tmp_path``."""
    monkeypatch.chdir(tmp_path)


def _action_line(
    source: str,
    action: str,
    timestamp: str,
    count: int = 1,
    session_id: str | None = None,
) -> str:
    record: dict[str, Any] = {
        "timestamp": timestamp,
        "source": source,
        "action": action,
        "count": count,
    }
    if session_id is not None:
        record["session_id"] = session_id
    return json.dumps(record) + "\n"


def _cli_line(timestamp: str, command: str = "serve") -> str:
    return (
        json.dumps(
            {
                "timestamp": timestamp,
                "command": command,
                "args": [],
                "working_dir": ".",
                "exit_code": 0,
                "duration_seconds": 1.0,
            }
        )
        + "\n"
    )


def _session_line(
    session_id: str,
    timestamp: str,
    commands_run: int,
    tool_calls: int,
) -> str:
    return (
        json.dumps(
            {
                "timestamp": timestamp,
                "session_id": session_id,
                "title": "P5 test",
                "commands_run": commands_run,
                "tool_calls": tool_calls,
                "end_reason": "idle",
            }
        )
        + "\n"
    )


class TestRecordAction:
    def test_roundtrip(self, tmp_path: Any) -> None:
        record_action("gui", "runtime.reload")
        record_action(
            "desktop",
            "review.submit",
            session_id="sess-1",
            duration_seconds=0.4,
        )
        record_action("gui", "runtime.reload", count=3)

        records = read_action_records()
        assert len(records) == 3
        gui = [r for r in records if r["action"] == "runtime.reload"]
        assert sum(int(r["count"]) for r in gui) == 4
        submit = next(r for r in records if r["action"] == "review.submit")
        assert submit["source"] == "desktop"
        assert submit["session_id"] == "sess-1"
        assert submit["duration_seconds"] == 0.4

    def test_read_limit(self, tmp_path: Any) -> None:
        for i in range(5):
            record_action("gui", "runtime.reload", count=1)
        records = read_action_records(limit=2)
        assert len(records) == 2
        assert len(read_action_records()) == 5

    def test_count_clamps_to_positive(self, tmp_path: Any) -> None:
        record_action("gui", "runtime.reload", count=0)
        record_action("gui", "runtime.reload", count=-3)
        records = read_action_records()
        assert all(int(r["count"]) == 1 for r in records)

    def test_prunes_to_max(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("ai_company.telemetry.actions._MAX_RECORDS", 3)
        for i in range(5):
            record_action("gui", "runtime.reload", count=1)
        records = read_action_records(limit=100)
        assert len(records) == 3
        path = tmp_path / "runtime" / "action_telemetry.jsonl"
        assert len(path.read_text(encoding="utf-8").splitlines()) == 3

    def test_fail_open_on_write_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boom() -> None:
            raise OSError("read-only volume")

        monkeypatch.setattr("ai_company.telemetry.actions.action_telemetry_path", _boom)
        record_action("gui", "runtime.reload")  # must not raise


class TestShareSummary:
    def test_empty_is_zero_share(self) -> None:
        summary = action_share_summary()
        assert summary["persistence_enabled"] is True
        assert summary["counts"] == {"cli": 0, "gui": 0, "desktop": 0}
        assert summary["desktop_session_actions"] == 0
        assert summary["actions_total"] == 0
        assert summary["share_pct"] == 0.0
        assert summary["at_target"] is False

    def test_gui_desktop_and_cli_share(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        now = datetime(2026, 8, 4, 12, 0, 0, tzinfo=UTC)
        monkeypatch.setattr(
            "ai_company.telemetry.actions.datetime",
            _FrozenDatetime(now),
        )
        runtime = tmp_path / "runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        (runtime / "cli_telemetry.jsonl").write_text(
            _cli_line("2026-08-01T10:00:00+00:00")
            + _cli_line("2026-08-03T10:00:00+00:00"),
            encoding="utf-8",
        )
        (runtime / "action_telemetry.jsonl").write_text(
            _action_line("gui", "runtime.reload", "2026-08-02T10:00:00+00:00")
            + _action_line(
                "desktop",
                "review.submit",
                "2026-08-03T10:00:00+00:00",
                session_id="sess-1",
            ),
            encoding="utf-8",
        )

        summary = action_share_summary()
        assert summary["counts"]["cli"] == 2
        assert summary["counts"]["gui"] == 1
        assert summary["counts"]["desktop"] == 1
        assert summary["desktop_session_actions"] == 0
        assert summary["gui_desktop_total"] == 2
        assert summary["actions_total"] == 4
        assert summary["share_pct"] == 50.0
        assert summary["at_target"] is False
        by_action = {
            (row["source"], row["action"]): row["count"] for row in summary["by_action"]
        }
        assert by_action[("gui", "runtime.reload")] == 1
        assert by_action[("desktop", "review.submit")] == 1

    def test_session_activity_dedupes_to_newest_checkpoint(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        now = datetime(2026, 8, 4, 12, 0, 0, tzinfo=UTC)
        monkeypatch.setattr(
            "ai_company.telemetry.actions.datetime",
            _FrozenDatetime(now),
        )
        runtime = tmp_path / "runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        (runtime / "session_telemetry.jsonl").write_text(
            _session_line(
                "sess-1", "2026-08-01T10:00:00+00:00", commands_run=1, tool_calls=2
            )
            + _session_line(
                "sess-1", "2026-08-02T10:00:00+00:00", commands_run=4, tool_calls=6
            )
            + _session_line(
                "sess-2", "2026-08-03T10:00:00+00:00", commands_run=0, tool_calls=3
            ),
            encoding="utf-8",
        )

        summary = action_share_summary()
        # sess-1 newest checkpoint only (4+6=10), plus sess-2 (0+3=3).
        assert summary["desktop_session_actions"] == 13
        assert summary["gui_desktop_total"] == 13
        assert summary["actions_total"] == 13
        assert summary["share_pct"] == 100.0
        assert summary["at_target"] is True

    def test_window_filters_old_records(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        now = datetime(2026, 8, 4, 12, 0, 0, tzinfo=UTC)
        monkeypatch.setattr(
            "ai_company.telemetry.actions.datetime",
            _FrozenDatetime(now),
        )
        runtime = tmp_path / "runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        (runtime / "cli_telemetry.jsonl").write_text(
            _cli_line("2026-07-01T10:00:00+00:00")
            + _cli_line("2026-08-02T10:00:00+00:00"),
            encoding="utf-8",
        )
        (runtime / "action_telemetry.jsonl").write_text(
            _action_line("gui", "runtime.reload", "2026-07-20T10:00:00+00:00")
            + _action_line("gui", "runtime.reload", "2026-08-01T10:00:00+00:00"),
            encoding="utf-8",
        )

        summary = action_share_summary(window_days=7)
        assert summary["counts"]["cli"] == 1
        assert summary["counts"]["gui"] == 1
        assert summary["actions_total"] == 2
        assert summary["share_pct"] == 50.0

    def test_target_pct_controls_at_target(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        now = datetime(2026, 8, 4, 12, 0, 0, tzinfo=UTC)
        monkeypatch.setattr(
            "ai_company.telemetry.actions.datetime",
            _FrozenDatetime(now),
        )
        runtime = tmp_path / "runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        (runtime / "action_telemetry.jsonl").write_text(
            _action_line("gui", "runtime.reload", "2026-08-01T10:00:00+00:00"),
            encoding="utf-8",
        )
        summary = action_share_summary(target_pct=90.0)
        assert summary["share_pct"] == 100.0
        assert summary["at_target"] is True

        summary = action_share_summary(target_pct=100.1)
        assert summary["at_target"] is False

    def test_corrupt_logs_are_skipped(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        now = datetime(2026, 8, 4, 12, 0, 0, tzinfo=UTC)
        monkeypatch.setattr(
            "ai_company.telemetry.actions.datetime",
            _FrozenDatetime(now),
        )
        runtime = tmp_path / "runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        (runtime / "cli_telemetry.jsonl").write_text(
            "not json\n" + _cli_line("2026-08-01T10:00:00+00:00") + "{\n",
            encoding="utf-8",
        )
        (runtime / "action_telemetry.jsonl").write_text(
            "garbage\n"
            + _action_line("gui", "runtime.reload", "2026-08-01T10:00:00+00:00"),
            encoding="utf-8",
        )

        summary = action_share_summary()
        assert summary["counts"]["cli"] == 1
        assert summary["counts"]["gui"] == 1
        assert summary["actions_total"] == 2

    def test_missing_logs_read_as_empty(self, tmp_path: Any) -> None:
        assert read_action_records() == []
        summary = action_share_summary()
        assert summary["actions_total"] == 0


class _FrozenDatetime:
    """``datetime`` shim that keeps ``now(UTC)`` pinned for share tests."""

    def __init__(self, pinned: datetime) -> None:
        self._pinned = pinned

    def now(self, tz: Any = None) -> datetime:
        return self._pinned

    @staticmethod
    def fromisoformat(value: str) -> datetime:
        return datetime.fromisoformat(value)
