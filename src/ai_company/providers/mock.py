"""Mock provider for testing AI Enterprise OS Provider Abstraction Layer."""

from __future__ import annotations

import logging
from typing import Any

from ai_company.providers.base import (
    BaseProvider,
    ChatMessage,
    CompletionResult,
    ProviderConfig,
)


class MockProvider(BaseProvider):
    """Mock provider for testing without real API calls."""

    def __init__(self, config: ProviderConfig | None = None) -> None:
        super().__init__(config)
        self.chat_calls: list[list[ChatMessage]] = []
        self.complete_calls: list[str] = []
        self.embed_calls: list[list[str]] = []
        self._mock_response = "This is a mock response."
        self._mock_embedding = [0.1, 0.2, 0.3]
        self.logger = logging.getLogger(self.__class__.__name__)

    def chat(self, messages: list[ChatMessage], **kwargs: Any) -> CompletionResult:
        self.chat_calls.append(messages)
        return CompletionResult(
            content=self._mock_response,
            model="mock-model",
            usage={"prompt_tokens": 10, "completion_tokens": 5},
            finish_reason="stop",
            latency=0.01,
        )

    def complete(self, prompt: str, **kwargs: Any) -> CompletionResult:
        self.complete_calls.append(prompt)
        return CompletionResult(
            content=self._mock_response,
            model="mock-model",
            usage={"prompt_tokens": 10, "completion_tokens": 5},
            finish_reason="stop",
            latency=0.01,
        )

    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        self.embed_calls.append(texts)
        return [self._mock_embedding for _ in texts]

    def check_health(self) -> bool:
        self._health_status = True
        return True

    def set_mock_response(self, response: str) -> None:
        self._mock_response = response

    def set_mock_embedding(self, embedding: list[float]) -> None:
        self._mock_embedding = embedding
