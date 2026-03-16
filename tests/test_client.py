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

    def test_cost_estimate_usd(self):
        r = self._make(1000, 0)
        assert r.cost_estimate_usd == pytest.approx(0.002)

    def test_raw_defaults_to_empty_dict(self):
        r = self._make()
        assert r.raw == {}


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

    def test_negative_max_retries_raises(self):
        with pytest.raises(ValueError, match="max_retries"):
            LLMClient("openai", "sk-test", "gpt-4o", max_retries=-1)

    def test_zero_timeout_raises(self):
        with pytest.raises(ValueError, match="timeout"):
            LLMClient("openai", "sk-test", "gpt-4o", timeout=0)

    def test_negative_timeout_raises(self):
        with pytest.raises(ValueError, match="timeout"):
            LLMClient("openai", "sk-test", "gpt-4o", timeout=-5.0)

    def test_anthropic_provider(self):
        client = LLMClient("anthropic", "sk-ant-test", "claude-opus-4-6")
        assert client.provider == "anthropic"

    def test_cohere_provider(self):
        client = LLMClient("cohere", "co-test", "command-r")
        assert client.provider == "cohere"


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

    def test_temperature_below_zero_raises(self, client):
        with pytest.raises(ValueError, match="temperature"):
            client.complete([Message("user", "hi")], temperature=-0.1)

    @pytest.mark.parametrize("temp", [-0.1, 2.1, -100])
    def test_temperature_out_of_range(self, temp, client):
        with pytest.raises(ValueError, match="temperature"):
            client.complete([Message("user", "hi")], temperature=temp)

    def test_max_tokens_zero_raises(self, client):
        with pytest.raises(ValueError, match="max_tokens"):
            client.complete([Message("user", "hi")], max_tokens=0)

    def test_max_tokens_negative_raises(self, client):
        with pytest.raises(ValueError, match="max_tokens"):
            client.complete([Message("user", "hi")], max_tokens=-1)

    def test_rate_limit_retried(self, monkeypatch):
        client = LLMClient("openai", "sk-test", "gpt-4o", max_retries=2)
        good = CompletionResponse("ok", "m", 5, 10, 50.0)
        responses = [RateLimitError(), RateLimitError(), good]
        call_iter = iter(responses)

        def fake_send(*args, **kwargs):
            r = next(call_iter)
            if isinstance(r, Exception):
                raise r
            return r

        monkeypatch.setattr(client, "_send", fake_send)
        monkeypatch.setattr("time.sleep", lambda _: None)
        result = client.complete([Message("user", "hi")])
        assert result.text == "ok"

    def test_auth_error_not_retried(self, monkeypatch):
        client = LLMClient("openai", "sk-bad", "gpt-4o", max_retries=3)
        call_count = 0

        def fake_send(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise AuthenticationError("bad key")

        monkeypatch.setattr(client, "_send", fake_send)
        with pytest.raises(AuthenticationError):
            client.complete([Message("user", "hi")])
        assert call_count == 1

    def test_retries_exhausted_raises_llm_error(self, monkeypatch):
        client = LLMClient("openai", "sk-test", "gpt-4o", max_retries=2)

        def fake_send(*args, **kwargs):
            raise RateLimitError("always limited")

        monkeypatch.setattr(client, "_send", fake_send)
        monkeypatch.setattr("time.sleep", lambda _: None)
        with pytest.raises(LLMError):
            client.complete([Message("user", "hi")])

    def test_call_count_increments(self, monkeypatch):
        client = LLMClient("openai", "sk-test", "gpt-4o")
        good = CompletionResponse("ok", "m", 5, 10, 50.0)

        def fake_send_openai(*args, **kwargs):
            return good

        monkeypatch.setattr(client, "_send_openai", fake_send_openai)
        assert client._call_count == 0
        client.complete([Message("user", "first")])
        assert client._call_count == 1
        client.complete([Message("user", "second")])
        assert client._call_count == 2

    def test_transient_llm_error_retried(self, monkeypatch):
        client = LLMClient("openai", "sk-test", "gpt-4o", max_retries=2)
        good = CompletionResponse("ok", "m", 5, 10, 50.0)
        responses = [LLMError("transient"), good]
        call_iter = iter(responses)

        def fake_send(*args, **kwargs):
            r = next(call_iter)
            if isinstance(r, Exception):
                raise r
            return r

        monkeypatch.setattr(client, "_send", fake_send)
        monkeypatch.setattr("time.sleep", lambda _: None)
        result = client.complete([Message("user", "hi")])
        assert result.text == "ok"
