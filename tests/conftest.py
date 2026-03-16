"""Shared pytest fixtures for repo_llm tests."""

import pytest

from repo_llm.client import CompletionResponse


def make_response(text="ok", model="m", prompt_tokens=5, completion_tokens=10, latency_ms=50.0):
    return CompletionResponse(
        text=text,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
    )


@pytest.fixture
def mock_response():
    """Return a factory for CompletionResponse objects."""
    return make_response


@pytest.fixture
def tmp_cache_dir(tmp_path):
    """Return a temporary directory suitable for DiskCache."""
    return tmp_path / "cache"
