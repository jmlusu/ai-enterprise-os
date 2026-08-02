"""Provider factory for AI Enterprise OS Provider Abstraction Layer."""

from __future__ import annotations

import logging
from typing import Any

from ai_company.providers.anthropic import AnthropicProvider
from ai_company.providers.base import BaseProvider, ProviderConfig
from ai_company.providers.gemini import GeminiProvider
from ai_company.providers.mock import MockProvider
from ai_company.providers.ollama import OllamaProvider
from ai_company.providers.openai import OpenAIProvider
from ai_company.providers.usage import UsageTrackingProvider


class ProviderFactory:
    """Factory for creating provider instances.

    Configuration-driven selection of AI providers.
    Supports OpenAI, Anthropic, Ollama, Gemini, and Mock providers.
    """

    PROVIDERS: dict[str, type[BaseProvider]] = {
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "ollama": OllamaProvider,
        "gemini": GeminiProvider,
        "mock": MockProvider,
    }

    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)

    def create(
        self,
        provider_type: str,
        config: ProviderConfig | dict[str, Any] | None = None,
        track_usage: bool = False,
    ) -> BaseProvider:
        """Create a provider instance.

        Args:
            provider_type: Type of provider ("openai", "anthropic", "ollama", "gemini", "mock")
            config: Provider configuration (ProviderConfig instance or dict)
            track_usage: When True, wrap the provider in UsageTrackingProvider
                so every call is recorded to the provider usage telemetry log.

        Returns:
            Provider instance

        Raises:
            ValueError: If provider type is not supported
        """
        provider_type = provider_type.lower()
        if provider_type not in self.PROVIDERS:
            supported = ", ".join(sorted(self.PROVIDERS.keys()))
            raise ValueError(
                f"Unsupported provider: '{provider_type}'. Supported: {supported}"
            )

        # Convert dict config to ProviderConfig if needed
        if isinstance(config, dict):
            config = ProviderConfig(**config)
        elif config is None:
            config = ProviderConfig()

        provider_class = self.PROVIDERS[provider_type]
        provider: BaseProvider = provider_class(config)
        if track_usage:
            provider = UsageTrackingProvider(provider)
        self.logger.info(
            f"Created provider: {provider_type} ({provider_class.__name__})"
        )

        return provider

    def register_provider(self, name: str, provider_class: type[BaseProvider]) -> None:
        """Register a custom provider class."""
        self.PROVIDERS[name.lower()] = provider_class
        self.logger.info(f"Registered provider: {name} ({provider_class.__name__})")

    def list_supported(self) -> list[str]:
        """List supported provider types."""
        return list(self.PROVIDERS.keys())
