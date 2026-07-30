"""Gemini provider implementation for AI Enterprise OS."""

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


class GeminiProvider(BaseProvider):
    """Google Gemini API provider implementation."""

    def __init__(self, config: ProviderConfig | None = None) -> None:
        super().__init__(config)
        self.logger = logging.getLogger(self.__class__.__name__)

    def chat(self, messages: list[ChatMessage], **kwargs: Any) -> CompletionResult:
        self._check_api_key()
        start = time.time()
        try:
            import google.generativeai as genai

            genai.configure(api_key=self.config.api_key)
            model = genai.GenerativeModel(
                kwargs.get("model", self.config.model or "gemini-1.5-pro")
            )

            contents = []
            for m in messages:
                if m.role == "system":
                    contents.append({"role": "user", "parts": [m.content]})
                else:
                    contents.append({"role": m.role, "parts": [m.content]})

            response = model.generate_content(contents)
            latency = time.time() - start

            return CompletionResult(
                content=response.text or "",
                model=response.model_id if hasattr(response, "model_id") else "gemini",
                usage={
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                },
                finish_reason=str(response.candidates[0].finish_reason)
                if response.candidates
                else "",
                latency=latency,
            )
        except Exception as e:
            self.logger.error(f"Gemini chat failed: {e}")
            raise

    def complete(self, prompt: str, **kwargs: Any) -> CompletionResult:
        return self.chat([ChatMessage(role="user", content=prompt)], **kwargs)

    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        self._check_api_key()
        try:
            import google.generativeai as genai

            genai.configure(api_key=self.config.api_key)
            result = genai.embed_content(
                model=kwargs.get("model", "models/embedding-001"),
                content=texts,
            )
            embedding = result.get("embedding", [])
            return embedding if isinstance(embedding, list) else []
        except Exception as e:
            self.logger.error(f"Gemini embed failed: {e}")
            raise

    def check_health(self) -> bool:
        try:
            import google.generativeai as genai

            genai.configure(api_key=self.config.api_key)
            genai.list_models()
            self._health_status = True
            return True
        except Exception:
            self._health_status = False
            return False

    def _check_api_key(self) -> None:
        if not self.config.api_key:
            raise ValueError("Gemini API key not configured")
