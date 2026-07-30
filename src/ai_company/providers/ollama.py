"""Ollama provider implementation for AI Enterprise OS."""

from __future__ import annotations

import json
import logging
import time
import urllib.request
from typing import Any

from ai_company.providers.base import (
    BaseProvider,
    ChatMessage,
    CompletionResult,
    ProviderConfig,
)


class OllamaProvider(BaseProvider):
    """Ollama local provider implementation."""

    def __init__(self, config: ProviderConfig | None = None) -> None:
        super().__init__(config)
        self.base_url = (
            config.base_url if config and config.base_url else "http://localhost:11434"
        )
        self.logger = logging.getLogger(self.__class__.__name__)

    def chat(self, messages: list[ChatMessage], **kwargs: Any) -> CompletionResult:
        start = time.time()
        try:
            payload = {
                "model": kwargs.get("model", self.config.model or "llama3.2"),
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "stream": False,
            }
            data = json.dumps(payload).encode()
            req = urllib.request.Request(
                f"{self.base_url}/api/chat",
                data=data,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
                result = json.loads(resp.read().decode())

            latency = time.time() - start
            return CompletionResult(
                content=result.get("message", {}).get("content", ""),
                model=result.get("model", ""),
                usage={"total_duration": result.get("total_duration", 0)},
                finish_reason=result.get("done_reason", ""),
                latency=latency,
            )
        except Exception as e:
            self.logger.error(f"Ollama chat failed: {e}")
            raise

    def complete(self, prompt: str, **kwargs: Any) -> CompletionResult:
        return self.chat([ChatMessage(role="user", content=prompt)], **kwargs)

    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        try:
            import ollama

            results = []
            for text in texts:
                resp = ollama.embeddings(
                    model=kwargs.get("model", "nomic-embed-text"),
                    prompt=text,
                )
                results.append(resp.get("embedding", []))
            return results
        except Exception as e:
            self.logger.error(f"Ollama embed failed: {e}")
            raise

    def check_health(self) -> bool:
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as resp:
                self._health_status = resp.status == 200
                return self._health_status
        except Exception:
            self._health_status = False
            return False
