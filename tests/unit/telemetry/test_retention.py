"""Unit tests for telemetry retention + rollup (sprint 5.4 T2).

Covers the rollup-then-truncate contract: expired raw records are aggregated
into hourly/daily rollups before truncation; raw is never truncated before
rollup succeeds; rollup is idempotent; everything is fail-open.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai_company.telemetry import retention as retention_module
from ai_company.telemetry.retention import (
    apply_retention,
    bucket_key,
    load_policies,
    read_rollups,
    retention_summary,
    rollup_summary,
)

NOW = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)


@pytest.fixture()
def sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, tuple[Path, Path]]:
    """Point every telemetry source at tmp files for hermetic tests."""
    paths: dict[str, tuple[Path, Path]] = {}
    for key in retention_module.SOURCE_PATHS:
        raw = tmp_path / f"{key}.jsonl"
        rollup = tmp_path / f"rollup_{key}.jsonl"
        paths[key] = (raw, rollup)
        monkeypatch.setitem(retention_module.SOURCE_PATHS, key, (raw, rollup))
    return paths


def _ts(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


def _append(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _metrics_record(days_ago: float, cpu: float, healthy: int = 6) -> dict:
    return {
        "timestamp": _ts(days_ago),
        "snapshot": {"cpu_percent": cpu, "engine_healthy": healthy},
    }


# ── policies ───────────────────────────────────────────────────────


def test_load_policies_defaults() -> None:
    policies = load_policies({})
    assert policies["metrics_history"]["days"] == 7
    assert policies["provider_usage"]["days"] == 90
    assert policies["cli_telemetry"]["days"] == 180
    assert policies["session_telemetry"]["days"] == 180
    assert policies["action_telemetry"]["days"] == 180
    # rollup sources are the aggregated history logs; session/action checkpoints
    # are truncated by age without rollup (per-session/per-action records, not
    # time series).
    assert {k for k, v in policies.items() if v["rollup"]} == {
        "metrics_history",
        "provider_usage",
        "cli_telemetry",
    }
    assert policies["session_telemetry"]["rollup"] is False
    assert policies["action_telemetry"]["rollup"] is False


def test_load_policies_merges_config_section() -> None:
    policies = load_policies(
        {"retention": {"metrics_history": {"days": 2, "rollup": False}}}
    )
    assert policies["metrics_history"]["days"] == 2
    assert policies["metrics_history"]["rollup"] is False
    # untouched sources keep defaults
    assert policies["provider_usage"]["days"] == 90


def test_load_policies_ignores_unknown_sources() -> None:
    policies = load_policies({"retention": {"bogus_source": {"days": 1}}})
    assert "bogus_source" not in policies
    assert set(policies) == {
        "metrics_history",
        "provider_usage",
        "cli_telemetry",
        "session_telemetry",
        "action_telemetry",
    }


def test_load_policies_reads_config_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "telemetry.yaml"
    config.write_text(
        "retention:\n  metrics_history:\n    days: 3\n    rollup: false\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(retention_module, "telemetry_config_path", lambda: config)
    policies = load_policies()
    assert policies["metrics_history"]["days"] == 3
    assert policies["metrics_history"]["rollup"] is False


def test_bucket_keys() -> None:
    ts = datetime(2026, 8, 2, 10, 30, 15, tzinfo=UTC)
    assert bucket_key(ts, "hourly") == "2026-08-02T10:00:00+00:00"
    assert bucket_key(ts, "daily") == "2026-08-02"


# ── dry-run / summary ──────────────────────────────────────────────


def test_retention_summary_counts_expired(
    sources: dict[str, tuple[Path, Path]], tmp_path: Path
) -> None:
    raw, _ = sources["metrics_history"]
    _append(raw, _metrics_record(days_ago=8.0, cpu=10.0))  # expired
    _append(raw, _metrics_record(days_ago=9.0, cpu=12.0))  # expired
    _append(raw, _metrics_record(days_ago=0.1, cpu=14.0))  # kept

    summary = retention_summary(policies=load_policies({}), now=NOW)
    metrics = next(s for s in summary["sources"] if s["key"] == "metrics_history")
    assert metrics["raw_records"] == 3
    assert metrics["expired_records"] == 2
    assert metrics["keep_records"] == 1
    assert metrics["would_rollup"] == 2
    assert metrics["rollup_records"] == 0
    assert summary["total_expired"] == 2
    assert summary["applied"] is False


def test_dry_run_never_mutates(
    sources: dict[str, tuple[Path, Path]], tmp_path: Path
) -> None:
    raw, rollup = sources["metrics_history"]
    _append(raw, _metrics_record(days_ago=8.0, cpu=10.0))
    before = raw.read_text(encoding="utf-8")
    result = apply_retention(policies=load_policies({}), dry_run=True, now=NOW)
    assert result["applied"] is False
    assert raw.read_text(encoding="utf-8") == before
    assert not rollup.exists()


# ── rollup-then-truncate ───────────────────────────────────────────


def test_apply_metrics_rollup_then_truncate(
    sources: dict[str, tuple[Path, Path]],
) -> None:
    raw, rollup = sources["metrics_history"]
    # Two expired records in the same hour; last-value-wins for gauges.
    _append(raw, _metrics_record(days_ago=8.0, cpu=10.0, healthy=6))
    _append(raw, _metrics_record(days_ago=8.0, cpu=12.0, healthy=6))
    _append(raw, _metrics_record(days_ago=0.1, cpu=14.0, healthy=7))  # kept

    result = apply_retention(policies=load_policies({}), dry_run=False, now=NOW)

    metrics = next(s for s in result["sources"] if s["key"] == "metrics_history")
    assert metrics["expired_records"] == 2
    assert metrics["truncated"] == 2
    assert metrics["rolled_up"] == 2  # hourly + daily rows

    kept = [json.loads(line) for line in raw.read_text(encoding="utf-8").splitlines()]
    assert len(kept) == 1
    assert kept[0]["snapshot"]["cpu_percent"] == 14.0

    rows = read_rollups(source="metrics_history")
    by_granularity = {row["granularity"]: row for row in rows}
    assert set(by_granularity) == {"hourly", "daily"}
    for row in by_granularity.values():
        assert row["records"] == 2
        # last sample in the bucket wins for gauges
        assert row["metrics"]["cpu_percent"] == 12.0
        assert row["metrics"]["engine_healthy"] == 6
    assert by_granularity["hourly"]["timestamp"] == "2026-07-25T12:00:00+00:00"


def test_apply_provider_usage_math(sources: dict[str, tuple[Path, Path]]) -> None:
    raw, _ = sources["provider_usage"]
    # 100 days ago is beyond the 90-day provider_usage window (expired).
    for days, usage, ok, latency in (
        (100.0, {"prompt_tokens": 100, "completion_tokens": 50}, True, 1.5),
        (100.0, {"prompt_tokens": 200, "completion_tokens": 100}, True, 2.5),
        (100.0, {}, False, None),
    ):
        _append(
            raw,
            {
                "timestamp": _ts(days),
                "provider": "ollama",
                "model": "llama3.1:8b",
                "usage": usage,
                "latency_seconds": latency,
                "ok": ok,
            },
        )

    apply_retention(policies=load_policies({}), dry_run=False, now=NOW)

    rows = read_rollups(source="provider_usage", granularity="daily")
    assert len(rows) == 1
    metrics = rows[0]["metrics"]
    assert rows[0]["key"] == "llama3.1:8b"
    assert metrics["requests"] == 3
    assert metrics["successes"] == 2
    assert metrics["errors"] == 1
    assert metrics["prompt_tokens"] == 300
    assert metrics["completion_tokens"] == 150
    assert metrics["total_tokens"] == 450
    assert metrics["avg_latency_seconds"] == 2.0
    assert rows[0]["records"] == 3


def test_apply_cli_telemetry_math(sources: dict[str, tuple[Path, Path]]) -> None:
    raw, _ = sources["cli_telemetry"]
    # 200 days ago is beyond the 180-day cli_telemetry window (expired).
    for days, duration in ((200.0, 1.0), (200.0, 3.0)):
        _append(
            raw,
            {
                "timestamp": _ts(days),
                "command": "generate",
                "argv": ["generate", "bootstrap"],
                "duration_seconds": duration,
            },
        )

    apply_retention(policies=load_policies({}), dry_run=False, now=NOW)

    rows = read_rollups(source="cli_telemetry", granularity="daily")
    assert len(rows) == 1
    assert rows[0]["key"] == "generate"
    assert rows[0]["metrics"]["invocations"] == 2
    assert rows[0]["metrics"]["avg_duration_seconds"] == 2.0


def test_apply_is_idempotent(sources: dict[str, tuple[Path, Path]]) -> None:
    raw, rollup = sources["metrics_history"]
    _append(raw, _metrics_record(days_ago=8.0, cpu=10.0))

    first = apply_retention(policies=load_policies({}), dry_run=False, now=NOW)
    second = apply_retention(policies=load_policies({}), dry_run=False, now=NOW)

    assert first["sources"][0]["rolled_up"] == 2
    assert second["sources"][0]["rolled_up"] == 0  # nothing left to roll up
    assert second["sources"][0]["truncated"] == 0
    assert len(read_rollups(source="metrics_history")) == 2  # no duplicates
    assert rollup.exists()


def test_apply_rollup_disabled_truncates_without_rollup(
    sources: dict[str, tuple[Path, Path]],
) -> None:
    raw, rollup = sources["metrics_history"]
    _append(raw, _metrics_record(days_ago=8.0, cpu=10.0))
    _append(raw, _metrics_record(days_ago=0.1, cpu=12.0))

    policies = load_policies({})
    policies["metrics_history"]["rollup"] = False
    result = apply_retention(policies=policies, dry_run=False, now=NOW)

    metrics = next(s for s in result["sources"] if s["key"] == "metrics_history")
    assert metrics["rolled_up"] == 0
    assert metrics["truncated"] == 1
    assert not rollup.exists()  # rollup disabled → no rollup file
    kept = [json.loads(line) for line in raw.read_text(encoding="utf-8").splitlines()]
    assert len(kept) == 1


def test_apply_rollup_failure_keeps_raw(
    sources: dict[str, tuple[Path, Path]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raw is never truncated before rollup: a failed rollup write preserves it."""
    raw, _ = sources["metrics_history"]
    _append(raw, _metrics_record(days_ago=8.0, cpu=10.0))
    before = raw.read_text(encoding="utf-8")

    # Break the rollup path: its parent is a regular file.
    blocker = tmp_path / "blocker"
    blocker.write_text("not a dir", encoding="utf-8")
    monkeypatch.setitem(
        retention_module.SOURCE_PATHS,
        "metrics_history",
        (raw, blocker / "rollup.jsonl"),
    )

    result = apply_retention(policies=load_policies({}), dry_run=False, now=NOW)
    metrics = next(s for s in result["sources"] if s["key"] == "metrics_history")
    assert metrics["error"]  # fail-open: reported, never raised
    assert metrics["truncated"] == 0
    assert raw.read_text(encoding="utf-8") == before  # raw preserved


def test_apply_fail_open_missing_files(sources: dict[str, tuple[Path, Path]]) -> None:
    result = apply_retention(policies=load_policies({}), dry_run=False, now=NOW)
    assert result["applied"] is True
    assert result["total_expired"] == 0
    assert result["total_truncated"] == 0


def test_corrupt_timestamp_rows_never_truncated(
    sources: dict[str, tuple[Path, Path]],
) -> None:
    raw, _ = sources["metrics_history"]
    _append(raw, {"timestamp": "not-a-date", "snapshot": {"cpu_percent": 9.0}})
    _append(raw, _metrics_record(days_ago=8.0, cpu=10.0))

    apply_retention(policies=load_policies({}), dry_run=False, now=NOW)

    kept = [json.loads(line) for line in raw.read_text(encoding="utf-8").splitlines()]
    assert len(kept) == 1  # the unparseable row is kept, never truncated


# ── rollup-aware read path ─────────────────────────────────────────


def test_rollup_summary_counts(
    sources: dict[str, tuple[Path, Path]], tmp_path: Path
) -> None:
    _, rollup = sources["provider_usage"]
    _append(
        rollup,
        {
            "timestamp": "2026-08-01T10:00:00+00:00",
            "source": "provider_usage",
            "granularity": "hourly",
            "key": "ollama",
            "metrics": {},
            "records": 2,
        },
    )
    _append(
        rollup,
        {
            "timestamp": "2026-08-01",
            "source": "provider_usage",
            "granularity": "daily",
            "key": "ollama",
            "metrics": {},
            "records": 2,
        },
    )

    summary = rollup_summary()
    assert summary["records"] == 2
    provider = next(s for s in summary["per_source"] if s["source"] == "provider_usage")
    assert provider["hourly"] == 1
    assert provider["daily"] == 1


def test_read_rollups_filters(
    sources: dict[str, tuple[Path, Path]], tmp_path: Path
) -> None:
    _, rollup = sources["metrics_history"]
    _append(
        rollup,
        {
            "timestamp": "2026-08-01",
            "source": "metrics_history",
            "granularity": "daily",
            "key": "system",
            "metrics": {},
            "records": 1,
        },
    )
    assert read_rollups(source="provider_usage") == []
    assert len(read_rollups(source="metrics_history", granularity="daily")) == 1
    assert read_rollups(limit=0) == []
