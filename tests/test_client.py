"""Tests for repo_llm.client — partial coverage, several gaps intentional."""

import pytest

from repo_llm.client import (
    AuthenticationError,
    CompletionResponse,
    LLMClient,
    LLMError,
    Message,
    RateLimitError,
)


# ---------------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------------

class TestMessage:
    def test_to_dict(self):
        msg = Message(role="user", content="hello")
        assert msg.to_dict() == {"role": "user", "content": "hello"}

    # MISSING: no test for Message with role="system" or role="assistant"
    # MISSING: no test for empty content string


# ---------------------------------------------------------------------------
# CompletionResponse
# ---------------------------------------------------------------------------

class TestCompletionResponse:
    def _make(self, prompt=10, completion=20):
        return CompletionResponse(
            text="result",
            model="test-model",
            prompt_tokens=prompt,
            completion_tokens=completion,
            latency_ms=100.0,
        )

    def test_total_tokens(self):
        r = self._make(10, 20)
        assert r.total_tokens == 30

    # MISSING: no test for cost_estimate_usd
    # MISSING: no test that raw defaults to empty dict


# ---------------------------------------------------------------------------
# LLMClient construction
# ---------------------------------------------------------------------------

class TestLLMClientInit:
    def test_valid_construction(self):
        client = LLMClient("openai", "sk-test", "gpt-4o")
        assert client.provider == "openai"
        assert client.model == "gpt-4o"

    def test_invalid_provider(self):
        with pytest.raises(ValueError, match="Unsupported provider"):
            LLMClient("fakeprovider", "key", "model")

    def test_empty_api_key(self):
        with pytest.raises(ValueError, match="api_key"):
            LLMClient("openai", "", "model")

    def test_whitespace_api_key(self):
        with pytest.raises(ValueError, match="api_key"):
            LLMClient("openai", "   ", "model")

    # MISSING: test max_retries < 0 raises ValueError
    # MISSING: test timeout <= 0 raises ValueError
    # MISSING: tests for 'anthropic' and 'cohere' providers


# ---------------------------------------------------------------------------
# LLMClient.complete — validation layer only (no real HTTP)
# ---------------------------------------------------------------------------

class TestLLMClientComplete:
    @pytest.fixture
    def client(self):
        return LLMClient("openai", "sk-test", "gpt-4o")

    def test_empty_messages_raises(self, client):
        with pytest.raises(ValueError, match="empty"):
            client.complete([])

    def test_invalid_temperature_high(self, client):
        with pytest.raises(ValueError, match="temperature"):
            client.complete(
                [Message("user", "hi")],
                temperature=3.0,
            )

    # MISSING: temperature < 0 raises ValueError
    # MISSING: max_tokens <= 0 raises ValueError
    # MISSING: retry logic on RateLimitError (mock _send)
    # MISSING: AuthenticationError is NOT retried
    # MISSING: exhausting all retries raises LLMError
    # MISSING: call_count increments on each _send
