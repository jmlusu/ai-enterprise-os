"""Base provider interface for AI Enterprise OS Provider Abstraction Layer."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderConfig:
    """Configuration for an AI provider."""

    api_key: str = ""
    base_url: str = ""
    model: str = "default"
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: int = 60
    extra_params: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatMessage:
    """A single message in a chat conversation."""

    role: str = "user"  # system, user, assistant
    content: str = ""
    name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompletionResult:
    """Result from a completion request."""

    content: str = ""
    model: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str = ""
    latency: float = 0.0
    raw_response: dict[str, Any] = field(default_factory=dict)


class BaseProvider(ABC):
    """Abstract base class for all AI providers.

    Defines the common interface that all providers must implement.
    Providers are injected into the orchestration layer through this interface.
    """

    def __init__(self, config: ProviderConfig | None = None) -> None:
        self.config = config or ProviderConfig()
        self._health_status: bool = False

    @abstractmethod
    def chat(self, messages: list[ChatMessage], **kwargs: Any) -> CompletionResult:
        """Send a chat completion request.

        Args:
            messages: List of chat messages
            **kwargs: Additional provider-specific parameters

        Returns:
            CompletionResult with the response
        """
        ...

    @abstractmethod
    def complete(self, prompt: str, **kwargs: Any) -> CompletionResult:
        """Send a text completion request.

        Args:
            prompt: Input text prompt
            **kwargs: Additional provider-specific parameters

        Returns:
            CompletionResult with the response
        """
        ...

    @abstractmethod
    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        """Generate embeddings for input texts.

        Args:
            texts: List of texts to embed
            **kwargs: Additional provider-specific parameters

        Returns:
            List of embedding vectors
        """
        ...

    @abstractmethod
    def check_health(self) -> bool:
        """Check if the provider is healthy and accessible.

        Returns:
            True if accessible, False otherwise
        """
        ...

    def get_config(self) -> ProviderConfig:
        """Get the current provider configuration."""
        return self.config

    def update_config(self, config: ProviderConfig) -> None:
        """Update provider configuration."""
        self.config = config

    @property
    def provider_name(self) -> str:
        """Get the name of this provider."""
        return self.__class__.__name__

    @property
    def is_healthy(self) -> bool:
        return self._health_status
