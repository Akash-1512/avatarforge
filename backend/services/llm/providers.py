"""Azure OpenAI (primary) and OpenAI (fallback) providers.

Both use the official openai SDK async clients. Transient errors
(rate limits, connection drops, 5xx) are retried with exponential
backoff before being surfaced as a provider failure.
"""

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncAzureOpenAI,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from backend.config import Settings
from backend.services.llm.base import BaseLLMProvider, CompletionResult, LLMProviderError

_TRANSIENT = (RateLimitError, APIConnectionError, APITimeoutError, InternalServerError)

_retry_transient = retry(
    retry=retry_if_exception_type(_TRANSIENT),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)


class AzureOpenAIProvider(BaseLLMProvider):
    name = "azure_openai"

    def __init__(self, settings: Settings):
        self._settings = settings
        self._client: AsyncAzureOpenAI | None = None

    @property
    def available(self) -> bool:
        return bool(self._settings.azure_openai_api_key and self._settings.azure_openai_endpoint)

    def _get_client(self) -> AsyncAzureOpenAI:
        if self._client is None:
            self._client = AsyncAzureOpenAI(
                api_key=self._settings.azure_openai_api_key,
                azure_endpoint=self._settings.azure_openai_endpoint,
                api_version=self._settings.azure_openai_api_version,
            )
        return self._client

    @_retry_transient
    async def _call(self, system: str, user: str, max_tokens: int) -> CompletionResult:
        resp = await self._get_client().chat.completions.create(
            model=self._settings.azure_openai_deployment,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_object"},
            max_tokens=max_tokens,
            temperature=0.7,
        )
        return CompletionResult(
            content=resp.choices[0].message.content or "",
            model=resp.model,
            prompt_tokens=resp.usage.prompt_tokens if resp.usage else 0,
            completion_tokens=resp.usage.completion_tokens if resp.usage else 0,
        )

    async def complete_json(
        self, system: str, user: str, max_tokens: int = 1500
    ) -> CompletionResult:
        try:
            return await self._call(system, user, max_tokens)
        except Exception as exc:  # noqa: BLE001 — normalize all SDK errors
            raise LLMProviderError(self.name, exc) from exc


class OpenAIProvider(BaseLLMProvider):
    name = "openai"

    def __init__(self, settings: Settings, model: str = "gpt-4o-mini"):
        self._settings = settings
        self._model = model
        self._client: AsyncOpenAI | None = None

    @property
    def available(self) -> bool:
        return bool(self._settings.openai_api_key)

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(api_key=self._settings.openai_api_key)
        return self._client

    @_retry_transient
    async def _call(self, system: str, user: str, max_tokens: int) -> CompletionResult:
        resp = await self._get_client().chat.completions.create(
            model=self._model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_object"},
            max_tokens=max_tokens,
            temperature=0.7,
        )
        return CompletionResult(
            content=resp.choices[0].message.content or "",
            model=resp.model,
            prompt_tokens=resp.usage.prompt_tokens if resp.usage else 0,
            completion_tokens=resp.usage.completion_tokens if resp.usage else 0,
        )

    async def complete_json(
        self, system: str, user: str, max_tokens: int = 1500
    ) -> CompletionResult:
        try:
            return await self._call(system, user, max_tokens)
        except Exception as exc:  # noqa: BLE001
            raise LLMProviderError(self.name, exc) from exc
