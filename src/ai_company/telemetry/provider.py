"""Provider usage instrumentation (risk R5 closure).

Audit finding #4: ``CompletionResult.usage`` is computed by the providers but
never persisted, so "Model Usage" has zero upstream data. This module provides
the capture path — a fail-open JSONL log at ``runtime/provider_usage.jsonl`` —
plus read/summary helpers for the dashboard panels.

Every completed (or failed) provider call is recorded once through
:func:`record_provider_usage`:

- ``timestamp`` — UTC ISO-8601
- ``provider`` — provider class name (e.g. ``OllamaProvider``)
- ``model`` — model identifier from the completion result
- ``usage`` — the provider-reported token usage dict (prompt/completion/total)
- ``latency_seconds`` — call wall time
- ``ok`` — whether the call succeeded

:func:`provider_usage_summary` aggregates by model: request counts, summed
token usage, average latency, and error counts — the Model Usage panel data
source. The instrumentation wrapper itself lives in
:mod:`ai_company.providers.usage` (``UsageTrackingProvider``) so every
provider created through the factory is tracked without touching individual
provider implementations.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PROVIDER_USAGE_RELATIVE_PATH = Path("runtime") / "provider_usage.jsonl"


def provider_usage_path() -> Path:
    """Return the provider usage log path (relative to the working directory)."""
    return PROVIDER_USAGE_RELATIVE_PATH


def record_provider_usage(
    *,
    provider: str,
    model: str,
    usage: dict[str, int] | None = None,
    latency_seconds: float | None = None,
    ok: bool = True,
    error: str = "",
) -> None:
    """Append one provider call record to the usage log (fail-open).

    Never raises: instrumentation must not break the provider call path.
    """
    try:
        record: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "provider": provider,
            "model": model,
            "usage": dict(usage or {}),
            "latency_seconds": latency_seconds,
            "ok": ok,
            "error": error,
        }
        path = provider_usage_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.debug("Provider usage write failed: %s", exc)


def read_provider_usage(limit: int = 500) -> list[dict[str, Any]]:
    """Return the last ``limit`` provider usage records."""
    path = provider_usage_path()
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.debug("Skipping corrupt provider usage line")
    except OSError as exc:
        logger.debug("Provider usage read failed: %s", exc)
        return []
    return records[-limit:]


def provider_usage_summary(limit: int = 500) -> dict[str, Any]:
    """Aggregate usage records by model for the Model Usage panel.

    Returns per-model rows (requests, successes, errors, prompt/completion/
    total tokens, average latency) plus overall totals and the record count.
    """
    records = read_provider_usage(limit=limit)
    if not records:
        return {
            "persistence_enabled": True,
            "records": 0,
            "models": [],
            "totals": {
                "requests": 0,
                "successes": 0,
                "errors": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        }

    by_model: dict[str, dict[str, Any]] = {}
    totals: dict[str, Any] = {
        "requests": 0,
        "successes": 0,
        "errors": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    for record in records:
        model = record.get("model") or "(unknown)"
        ok = bool(record.get("ok", True))
        usage = record.get("usage") or {}
        prompt = int(usage.get("prompt_tokens", 0))
        completion = int(usage.get("completion_tokens", 0))
        total = int(usage.get("total_tokens", 0) or (prompt + completion))
        latency = record.get("latency_seconds")

        row = by_model.setdefault(
            model,
            {
                "model": model,
                "requests": 0,
                "successes": 0,
                "errors": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "latency_sum": 0.0,
                "latency_count": 0,
            },
        )
        row["requests"] += 1
        if ok:
            row["successes"] += 1
        else:
            row["errors"] += 1
        row["prompt_tokens"] += prompt
        row["completion_tokens"] += completion
        row["total_tokens"] += total
        if latency is not None:
            row["latency_sum"] += float(latency)
            row["latency_count"] += 1

        totals["requests"] += 1
        if ok:
            totals["successes"] += 1
        else:
            totals["errors"] += 1
        totals["prompt_tokens"] += prompt
        totals["completion_tokens"] += completion
        totals["total_tokens"] += total

    models = sorted(by_model.values(), key=lambda m: m["total_tokens"], reverse=True)
    for row in models:
        row["avg_latency_seconds"] = (
            round(row["latency_sum"] / row["latency_count"], 4)
            if row["latency_count"]
            else None
        )
        del row["latency_sum"]
        del row["latency_count"]

    return {
        "persistence_enabled": True,
        "records": len(records),
        "models": models,
        "totals": totals,
    }


__all__ = [
    "PROVIDER_USAGE_RELATIVE_PATH",
    "provider_usage_path",
    "provider_usage_summary",
    "read_provider_usage",
    "record_provider_usage",
]
