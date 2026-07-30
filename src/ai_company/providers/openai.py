"""OpenAI provider implementation for AI Enterprise OS."""

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


class OpenAIProvider(BaseProvider):
    """OpenAI API provider implementation."""

    def __init__(self, config: ProviderConfig | None = None) -> None:
        super().__init__(config)
        self.logger = logging.getLogger(self.__class__.__name__)

    def chat(self, messages: list[ChatMessage], **kwargs: Any) -> CompletionResult:
        self._check_api_key()
        start = time.time()

        try:
            import openai

            client = openai.OpenAI(
                api_key=self.config.api_key, base_url=self.config.base_url or None
            )
            response = client.chat.completions.create(
                model=kwargs.get("model", self.config.model or "gpt-4o"),
                messages=[{"role": m.role, "content": m.content} for m in messages],
                temperature=kwargs.get("temperature", self.config.temperature),
                max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
            )
            latency = time.time() - start
            choice = response.choices[0]
            return CompletionResult(
                content=choice.message.content or "",
                model=response.model,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens
                    if response.usage
                    else 0,
                    "completion_tokens": response.usage.completion_tokens
                    if response.usage
                    else 0,
                    "total_tokens": response.usage.total_tokens
                    if response.usage
                    else 0,
                },
                finish_reason=choice.finish_reason or "",
                latency=latency,
            )
        except Exception as e:
            self.logger.error(f"OpenAI chat failed: {e}")
            raise

    def complete(self, prompt: str, **kwargs: Any) -> CompletionResult:
        return self.chat([ChatMessage(role="user", content=prompt)], **kwargs)

    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        self._check_api_key()
        try:
            import openai

            client = openai.OpenAI(
                api_key=self.config.api_key, base_url=self.config.base_url or None
            )
            model = kwargs.get("model", "text-embedding-3-small")
            response = client.embeddings.create(model=model, input=texts)
            return [data.embedding for data in response.data]
        except Exception as e:
            self.logger.error(f"OpenAI embed failed: {e}")
            raise

    def check_health(self) -> bool:
        try:
            import openai

            client = openai.OpenAI(
                api_key=self.config.api_key, base_url=self.config.base_url or None
            )
            client.models.list()
            self._health_status = True
            return True
        except Exception:
            self._health_status = False
            return False

    def _check_api_key(self) -> None:
        if not self.config.api_key:
            raise ValueError("OpenAI API key not configured")
