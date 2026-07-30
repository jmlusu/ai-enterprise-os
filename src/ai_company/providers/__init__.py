"""Provider Abstraction Layer for AI Enterprise OS.

Future-proofs the platform so it can use OpenAI, Anthropic, Ollama, Gemini,
or any compatible endpoint through a common interface with dependency injection.
"""

from .anthropic import AnthropicProvider
from .base import BaseProvider
from .factory import ProviderFactory
from .gemini import GeminiProvider
from .ollama import OllamaProvider
from .openai import OpenAIProvider
from .registry import ProviderRegistry

__all__ = [
    "AnthropicProvider",
    "BaseProvider",
    "GeminiProvider",
    "OllamaProvider",
    "OpenAIProvider",
    "ProviderFactory",
    "ProviderRegistry",
]
