"""Anthropic provider implementation for AI Enterprise OS."""

from __future__ import annotations

import logging
import time
from typing import Any

from ai_company.providers.base import (
    BaseProvider,
    ChatMessage,
    CompletionResult,
    ProviderConfig,
)


class AnthropicProvider(BaseProvider):
    """Anthropic Claude API provider implementation."""

    def __init__(self, config: ProviderConfig | None = None) -> None:
        super().__init__(config)
        self.logger = logging.getLogger(self.__class__.__name__)

    def chat(self, messages: list[ChatMessage], **kwargs: Any) -> CompletionResult:
        self._check_api_key()
        start = time.time()

        try:
            import anthropic

            client = anthropic.Anthropic(api_key=self.config.api_key)
            response = client.messages.create(
                model=kwargs.get(
                    "model", self.config.model or "claude-3-5-sonnet-20241022"
                ),
                max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
                messages=[{"role": m.role, "content": m.content} for m in messages],
            )
            latency = time.time() - start
            return CompletionResult(
                content=response.content[0].text if response.content else "",
                model=response.model,
                usage={
                    "input_tokens": response.usage.input_tokens
                    if response.usage
                    else 0,
                    "output_tokens": response.usage.output_tokens
                    if response.usage
                    else 0,
                },
                finish_reason=response.stop_reason or "",
                latency=latency,
            )
        except Exception as e:
            self.logger.error(f"Anthropic chat failed: {e}")
            raise

    def complete(self, prompt: str, **kwargs: Any) -> CompletionResult:
        return self.chat([ChatMessage(role="user", content=prompt)], **kwargs)

    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        raise NotImplementedError("Anthropic does not support embeddings")

    def check_health(self) -> bool:
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=self.config.api_key)
            client.models.list()
            self._health_status = True
            return True
        except Exception:
            self._health_status = False
            return False

    def _check_api_key(self) -> None:
        if not self.config.api_key:
            raise ValueError("Anthropic API key not configured")
