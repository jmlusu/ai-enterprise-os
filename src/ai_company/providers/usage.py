"""Provider usage instrumentation wrapper (risk R5 closure).

Wraps any :class:`BaseProvider` and records each ``chat`` / ``complete`` /
``embed`` call through :func:`ai_company.telemetry.provider.record_provider_usage`
(fail-open JSONL) — the single choke point the initiative calls out: "one
choke point on BaseProvider.chat/complete/embed -> model.usage".

The wrapper is transparent: it delegates every call to the wrapped provider
and only observes the result. It is applied at construction time by
:class:`ProviderFactory` when ``track_usage=True`` is passed, so individual
provider implementations stay untouched.
"""

from __future__ import annotations

import time
from typing import Any

from ai_company.providers.base import BaseProvider, ChatMessage, CompletionResult
from ai_company.telemetry.provider import record_provider_usage


class UsageTrackingProvider(BaseProvider):
    """Transparent wrapper that records usage + latency for provider calls."""

    def __init__(self, provider: BaseProvider) -> None:
        self._wrapped = provider

    @property
    def wrapped(self) -> BaseProvider:
        """The wrapped provider instance."""
        return self._wrapped

    def _record(
        self,
        result: CompletionResult,
        started: float,
        ok: bool = True,
        error: str = "",
    ) -> CompletionResult:
        record_provider_usage(
            provider=self._wrapped.provider_name,
            model=result.model or self._wrapped.config.model,
            usage=result.usage,
            latency_seconds=round(time.monotonic() - started, 4),
            ok=ok,
            error=error,
        )
        return result

    def chat(self, messages: list[ChatMessage], **kwargs: Any) -> CompletionResult:
        started = time.monotonic()
        try:
            result = self._wrapped.chat(messages, **kwargs)
        except Exception as exc:
            self._record(
                CompletionResult(model=self._wrapped.config.model),
                started,
                ok=False,
                error=str(exc),
            )
            raise
        return self._record(result, started)

    def complete(self, prompt: str, **kwargs: Any) -> CompletionResult:
        started = time.monotonic()
        try:
            result = self._wrapped.complete(prompt, **kwargs)
        except Exception as exc:
            self._record(
                CompletionResult(model=self._wrapped.config.model),
                started,
                ok=False,
                error=str(exc),
            )
            raise
        return self._record(result, started)

    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        started = time.monotonic()
        try:
            result = self._wrapped.embed(texts, **kwargs)
        except Exception as exc:
            self._record(
                CompletionResult(model=self._wrapped.config.model),
                started,
                ok=False,
                error=str(exc),
            )
            raise
        record_provider_usage(
            provider=self._wrapped.provider_name,
            model=self._wrapped.config.model,
            usage={},
            latency_seconds=round(time.monotonic() - started, 4),
            ok=True,
        )
        return result

    def check_health(self) -> bool:
        return self._wrapped.check_health()

    def get_config(self) -> Any:
        return self._wrapped.get_config()

    def update_config(self, config: Any) -> None:
        self._wrapped.update_config(config)

    @property
    def provider_name(self) -> str:
        return self._wrapped.provider_name

    @property
    def is_healthy(self) -> bool:
        return self._wrapped.is_healthy


__all__ = ["UsageTrackingProvider"]
