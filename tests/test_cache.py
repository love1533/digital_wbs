"""Tests for repo_llm.cache — partial coverage."""

import time

import pytest

from repo_llm.cache import InMemoryCache
from repo_llm.client import CompletionResponse


def _response(text="hi", model="m", pt=5, ct=10, lat=50.0):
    return CompletionResponse(
        text=text, model=model, prompt_tokens=pt,
        completion_tokens=ct, latency_ms=lat,
    )


class TestInMemoryCache:
    def test_set_and_get(self):
        cache = InMemoryCache()
        cache.set("k1", _response("hello"))
        result = cache.get("k1")
        assert result is not None
        assert result.text == "hello"

    def test_miss_returns_none(self):
        cache = InMemoryCache()
        assert cache.get("nonexistent") is None

    def test_clear(self):
        cache = InMemoryCache()
        cache.set("k", _response())
        cache.clear()
        assert cache.size == 0

    def test_max_size_evicts_oldest(self):
        cache = InMemoryCache(max_size=2)
        cache.set("a", _response("a"))
        cache.set("b", _response("b"))
        cache.set("c", _response("c"))
        assert cache.size == 2
        # "a" should have been evicted
        assert cache.get("a") is None
        assert cache.get("b") is not None

    # MISSING: max_size <= 0 raises ValueError
    # MISSING: TTL expiry — entry returned as None after ttl_seconds elapses
    # MISSING: TTL not expired — entry still returned
    # MISSING: invalidate() returns True when key existed, False otherwise
    # MISSING: LRU promotion — recently accessed key survives eviction over stale key
    # MISSING: DiskCache.get / .set / .clear (entire class untested)
    # MISSING: DiskCache TTL expiry
    # MISSING: DiskCache handles corrupted JSON gracefully
