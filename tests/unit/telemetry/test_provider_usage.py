"""Unit tests for provider usage instrumentation (risk R5)."""

from __future__ import annotations

from typing import Any

import pytest

from ai_company.providers.base import CompletionResult
from ai_company.providers.factory import ProviderFactory
from ai_company.telemetry.provider import (
    provider_usage_summary,
    read_provider_usage,
    record_provider_usage,
)


@pytest.fixture(autouse=True)
def _isolated_log(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the provider usage log at a temp file per test."""
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "runtime" / "provider_usage.jsonl"
    monkeypatch.setattr(
        "ai_company.telemetry.provider.PROVIDER_USAGE_RELATIVE_PATH",
        target.relative_to(tmp_path),
    )


def test_record_and_read_provider_usage(tmp_path: Any) -> None:
    record_provider_usage(
        provider="MockProvider",
        model="mock-model",
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        latency_seconds=0.25,
        ok=True,
    )
    records = read_provider_usage()
    assert len(records) == 1
    assert records[0]["model"] == "mock-model"
    assert records[0]["usage"]["total_tokens"] == 15
    assert records[0]["ok"] is True


def test_provider_usage_summary_aggregates_by_model(tmp_path: Any) -> None:
    record_provider_usage(
        provider="MockProvider",
        model="alpha",
        usage={"prompt_tokens": 10, "completion_tokens": 5},
        latency_seconds=0.2,
    )
    record_provider_usage(
        provider="MockProvider",
        model="alpha",
        usage={"prompt_tokens": 20, "completion_tokens": 10},
        latency_seconds=0.4,
    )
    record_provider_usage(
        provider="MockProvider",
        model="beta",
        usage={"prompt_tokens": 100, "completion_tokens": 0},
        latency_seconds=1.0,
        ok=False,
        error="boom",
    )
    summary = provider_usage_summary()
    assert summary["records"] == 3
    assert summary["totals"]["requests"] == 3
    assert summary["totals"]["errors"] == 1
    by_model = {row["model"]: row for row in summary["models"]}
    assert by_model["alpha"]["requests"] == 2
    assert by_model["alpha"]["total_tokens"] == 45
    assert by_model["alpha"]["avg_latency_seconds"] == pytest.approx(0.3, abs=1e-4)
    assert by_model["beta"]["errors"] == 1


def test_usage_tracking_provider_records_calls(tmp_path: Any) -> None:
    factory = ProviderFactory()
    provider = factory.create("mock", track_usage=True)
    result = provider.complete("hello")
    assert isinstance(result, CompletionResult)
    records = read_provider_usage()
    assert len(records) == 1
    assert records[0]["ok"] is True
    assert records[0]["provider"] == "MockProvider"


def test_usage_summary_empty_without_records(tmp_path: Any) -> None:
    summary = provider_usage_summary()
    assert summary["records"] == 0
    assert summary["models"] == []
    assert summary["totals"]["requests"] == 0
