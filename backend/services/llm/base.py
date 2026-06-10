"""LLM provider contract. Every provider returns the same shape so the
service layer can fall back between them without caring which is which."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CompletionResult:
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int


class LLMProviderError(Exception):
    """Normalized provider failure — wraps SDK-specific exceptions."""

    def __init__(self, provider: str, original: Exception):
        self.provider = provider
        self.original = original
        super().__init__(f"{provider}: {type(original).__name__}: {original}")


class AllProvidersFailedError(Exception):
    """Every configured provider failed or was circuit-broken."""


class BaseLLMProvider(ABC):
    name: str = "base"

    @property
    @abstractmethod
    def available(self) -> bool:
        """True when this provider has credentials configured."""

    @abstractmethod
    async def complete_json(
        self, system: str, user: str, max_tokens: int = 1500
    ) -> CompletionResult:
        """Run a chat completion that must return a JSON object."""
