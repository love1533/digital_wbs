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

    def test_max_size_zero_raises(self):
        with pytest.raises(ValueError, match="max_size"):
            InMemoryCache(max_size=0)

    def test_max_size_negative_raises(self):
        with pytest.raises(ValueError, match="max_size"):
            InMemoryCache(max_size=-1)

    def test_ttl_expiry_returns_none(self):
        cache = InMemoryCache(ttl_seconds=0.05)
        cache.set("k", _response())
        time.sleep(0.1)
        assert cache.get("k") is None

    def test_ttl_not_expired_returns_entry(self):
        cache = InMemoryCache(ttl_seconds=10.0)
        cache.set("k", _response("fresh"))
        result = cache.get("k")
        assert result is not None
        assert result.text == "fresh"

    def test_invalidate_existing_key_returns_true(self):
        cache = InMemoryCache()
        cache.set("k", _response())
        assert cache.invalidate("k") is True
        assert cache.get("k") is None

    def test_invalidate_missing_key_returns_false(self):
        cache = InMemoryCache()
        assert cache.invalidate("nonexistent") is False

    def test_lru_recently_accessed_survives_eviction(self):
        cache = InMemoryCache(max_size=2)
        cache.set("a", _response("a"))
        cache.set("b", _response("b"))
        # Access "a" so it becomes most recently used
        cache.get("a")
        # Adding "c" should evict "b" (oldest in insertion order now), not "a"
        cache.set("c", _response("c"))
        assert cache.get("a") is not None
        assert cache.get("b") is None
        assert cache.get("c") is not None

    def test_repr(self):
        cache = InMemoryCache(max_size=10, ttl_seconds=30.0)
        r = repr(cache)
        assert "InMemoryCache" in r


class TestDiskCache:
    def test_set_and_get_roundtrip(self, tmp_path):
        from repo_llm.cache import DiskCache
        cache = DiskCache(tmp_path)
        r = _response("disk-hit")
        cache.set("dk", r)
        result = cache.get("dk")
        assert result is not None
        assert result.text == "disk-hit"
        assert result.model == "m"
        assert result.prompt_tokens == 5

    def test_miss_returns_none(self, tmp_path):
        from repo_llm.cache import DiskCache
        cache = DiskCache(tmp_path)
        assert cache.get("missing") is None

    def test_clear_removes_all_files(self, tmp_path):
        from repo_llm.cache import DiskCache
        cache = DiskCache(tmp_path)
        cache.set("a", _response("a"))
        cache.set("b", _response("b"))
        assert cache.size == 2
        cache.clear()
        assert cache.size == 0

    def test_ttl_expiry_removes_stale_file(self, tmp_path):
        from repo_llm.cache import DiskCache
        cache = DiskCache(tmp_path, ttl_seconds=0.05)
        cache.set("stale", _response("old"))
        time.sleep(0.1)
        result = cache.get("stale")
        assert result is None

    def test_ttl_not_expired_returns_entry(self, tmp_path):
        from repo_llm.cache import DiskCache
        cache = DiskCache(tmp_path, ttl_seconds=10.0)
        cache.set("fresh", _response("new"))
        result = cache.get("fresh")
        assert result is not None
        assert result.text == "new"

    def test_corrupted_json_returns_none(self, tmp_path):
        from repo_llm.cache import DiskCache
        cache = DiskCache(tmp_path)
        (tmp_path / "badkey.json").write_text("NOT JSON")
        assert cache.get("badkey") is None

    def test_creates_directory_if_missing(self, tmp_path):
        from repo_llm.cache import DiskCache
        nested = tmp_path / "a" / "b" / "c"
        cache = DiskCache(nested)
        cache.set("k", _response())
        assert cache.get("k") is not None

    def test_size_property(self, tmp_path):
        from repo_llm.cache import DiskCache
        cache = DiskCache(tmp_path)
        assert cache.size == 0
        cache.set("k1", _response())
        cache.set("k2", _response())
        assert cache.size == 2
