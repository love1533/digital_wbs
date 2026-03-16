"""LLM client abstraction supporting multiple providers."""

import time
import logging
from dataclasses import dataclass, field
from typing import Any, Iterator, Optional

logger = logging.getLogger(__name__)

SUPPORTED_PROVIDERS = ("openai", "anthropic", "cohere")


@dataclass
class Message:
    role: str  # "user" | "assistant" | "system"
    content: str

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


@dataclass
class CompletionResponse:
    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    raw: dict = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def cost_estimate_usd(self) -> float:
        """Rough cost estimate; pricing varies by provider/model."""
        # $0.002 per 1K tokens as a rough default
        return (self.total_tokens / 1000) * 0.002


class LLMError(Exception):
    """Base exception for LLM client errors."""


class RateLimitError(LLMError):
    """Raised when the provider returns a rate-limit response."""


class AuthenticationError(LLMError):
    """Raised when API credentials are invalid."""


class LLMClient:
    """
    Provider-agnostic LLM client with retry logic.

    Parameters
    ----------
    provider : str
        One of 'openai', 'anthropic', 'cohere'.
    api_key : str
        API key for the chosen provider.
    model : str
        Model identifier, e.g. 'gpt-4o' or 'claude-opus-4-6'.
    max_retries : int
        Maximum number of retries on transient errors.
    timeout : float
        Per-request timeout in seconds.
    """

    def __init__(
        self,
        provider: str,
        api_key: str,
        model: str,
        max_retries: int = 3,
        timeout: float = 30.0,
    ) -> None:
        if provider not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unsupported provider '{provider}'. "
                f"Choose from {SUPPORTED_PROVIDERS}."
            )
        if not api_key or not api_key.strip():
            raise ValueError("api_key must be a non-empty string.")
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0.")
        if timeout <= 0:
            raise ValueError("timeout must be > 0.")

        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.max_retries = max_retries
        self.timeout = timeout
        self._call_count = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def complete(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        stop: Optional[list[str]] = None,
    ) -> CompletionResponse:
        """
        Send a chat-completion request and return a structured response.

        Retries on transient errors with exponential back-off.
        """
        if not messages:
            raise ValueError("messages list must not be empty.")
        if not 0.0 <= temperature <= 2.0:
            raise ValueError("temperature must be between 0.0 and 2.0.")
        if max_tokens <= 0:
            raise ValueError("max_tokens must be > 0.")

        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                return self._send(messages, temperature, max_tokens, stop)
            except RateLimitError as exc:
                last_exc = exc
                wait = 2 ** attempt
                logger.warning("Rate limited; retrying in %ss (attempt %d)", wait, attempt + 1)
                time.sleep(wait)
            except AuthenticationError:
                raise  # never retry auth errors
            except LLMError as exc:
                last_exc = exc
                logger.warning("Transient error; retrying (attempt %d): %s", attempt + 1, exc)
                time.sleep(1)

        raise LLMError(f"Request failed after {self.max_retries + 1} attempts.") from last_exc

    def stream(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> Iterator[str]:
        """Yield response tokens as they arrive (streaming mode)."""
        raise NotImplementedError("Streaming is not yet implemented.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _send(
        self,
        messages: list[Message],
        temperature: float,
        max_tokens: int,
        stop: Optional[list[str]],
    ) -> CompletionResponse:
        """Dispatch to the provider-specific implementation."""
        self._call_count += 1
        dispatch = {
            "openai": self._send_openai,
            "anthropic": self._send_anthropic,
            "cohere": self._send_cohere,
        }
        return dispatch[self.provider](messages, temperature, max_tokens, stop)

    def _send_openai(self, messages, temperature, max_tokens, stop) -> CompletionResponse:
        raise NotImplementedError("OpenAI provider not wired in this stub.")

    def _send_anthropic(self, messages, temperature, max_tokens, stop) -> CompletionResponse:
        raise NotImplementedError("Anthropic provider not wired in this stub.")

    def _send_cohere(self, messages, temperature, max_tokens, stop) -> CompletionResponse:
        raise NotImplementedError("Cohere provider not wired in this stub.")
