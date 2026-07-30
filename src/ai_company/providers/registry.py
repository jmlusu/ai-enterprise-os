"""Provider registry for AI Enterprise OS Provider Abstraction Layer."""

from __future__ import annotations

import logging
from typing import Any

from ai_company.providers.base import BaseProvider, ProviderConfig
from ai_company.providers.factory import ProviderFactory


class ProviderRegistry:
    """Registry for managing multiple provider instances.

    Supports configuration-driven provider selection and dependency injection.
    """

    def __init__(self, factory: ProviderFactory | None = None) -> None:
        self.factory = factory or ProviderFactory()
        self._instances: dict[str, BaseProvider] = {}
        self._default_provider: str = ""
        self.logger = logging.getLogger(self.__class__.__name__)

    def register(
        self,
        name: str,
        provider: BaseProvider | str,
        config: ProviderConfig | dict[str, Any] | None = None,
        make_default: bool = False,
    ) -> BaseProvider:
        """Register a provider instance.

        Args:
            name: Name to register the provider under
            provider: Provider instance or provider type string
            config: Configuration (used only if provider is a string type)
            make_default: Whether to set as default provider

        Returns:
            Registered provider instance
        """
        if isinstance(provider, str):
            # Create from type string
            provider_instance = self.factory.create(provider, config)
        else:
            provider_instance = provider

        self._instances[name] = provider_instance

        if make_default or not self._default_provider:
            self._default_provider = name

        self.logger.info(
            f"Provider registered: {name} ({provider_instance.provider_name})"
        )
        return provider_instance

    def get(self, name: str | None = None) -> BaseProvider:
        """Get a provider by name, or default if None.

        Args:
            name: Provider name, or None for default

        Returns:
            Provider instance

        Raises:
            KeyError: If provider not found
        """
        provider_name = name or self._default_provider
        if not provider_name:
            raise KeyError("No providers registered")
        if provider_name not in self._instances:
            raise KeyError(
                f"Provider not found: '{provider_name}'. Registered: {list(self._instances.keys())}"
            )
        return self._instances[provider_name]

    def unregister(self, name: str) -> None:
        """Unregister a provider."""
        self._instances.pop(name, None)
        if self._default_provider == name:
            self._default_provider = (
                next(iter(self._instances.keys())) if self._instances else ""
            )

    def set_default(self, name: str) -> None:
        """Set the default provider."""
        if name not in self._instances:
            raise KeyError(f"Cannot set default: provider '{name}' not registered")
        self._default_provider = name

    def get_default_name(self) -> str:
        """Get the name of the default provider."""
        return self._default_provider

    def list_providers(self) -> dict[str, str]:
        """List all registered providers."""
        return {name: p.provider_name for name, p in self._instances.items()}

    def clear(self) -> None:
        """Clear all registered providers."""
        self._instances.clear()
        self._default_provider = ""

    def __len__(self) -> int:
        return len(self._instances)

    def __contains__(self, name: str) -> bool:
        return name in self._instances
