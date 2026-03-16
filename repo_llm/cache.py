"""Simple in-memory and disk-backed response cache."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Optional

from .client import CompletionResponse


def _make_key(provider: str, model: str, messages: list[dict], **kwargs) -> str:
    payload = json.dumps(
        {"provider": provider, "model": model, "messages": messages, **kwargs},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


class InMemoryCache:
    """LRU-style in-memory cache for :class:`~repo_llm.client.CompletionResponse`."""

    def __init__(self, max_size: int = 128, ttl_seconds: Optional[float] = None) -> None:
        if max_size <= 0:
            raise ValueError("max_size must be > 0.")
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._store: dict[str, tuple[CompletionResponse, float]] = {}

    def get(self, key: str) -> Optional[CompletionResponse]:
        entry = self._store.get(key)
        if entry is None:
            return None
        response, ts = entry
        if self.ttl_seconds is not None and (time.monotonic() - ts) > self.ttl_seconds:
            del self._store[key]
            return None
        # Move to end to mark as recently used
        self._store[key] = self._store.pop(key)
        return response

    def set(self, key: str, response: CompletionResponse) -> None:
        if key in self._store:
            del self._store[key]
        elif len(self._store) >= self.max_size:
            # Evict oldest
            oldest = next(iter(self._store))
            del self._store[oldest]
        self._store[key] = (response, time.monotonic())

    def invalidate(self, key: str) -> bool:
        """Remove a specific entry. Returns True if the key existed."""
        return self._store.pop(key, None) is not None

    def clear(self) -> None:
        self._store.clear()

    @property
    def size(self) -> int:
        return len(self._store)

    def __repr__(self) -> str:
        return f"InMemoryCache(size={self.size}/{self.max_size}, ttl={self.ttl_seconds})"


class DiskCache:
    """
    Persist cached responses as JSON files under *cache_dir*.

    Files are named ``<sha256_key>.json``.
    """

    def __init__(self, cache_dir: str | Path, ttl_seconds: Optional[float] = None) -> None:
        self.cache_dir = Path(cache_dir)
        self.ttl_seconds = ttl_seconds
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def get(self, key: str) -> Optional[CompletionResponse]:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if self.ttl_seconds is not None:
            age = time.time() - data.get("_cached_at", 0)
            if age > self.ttl_seconds:
                path.unlink(missing_ok=True)
                return None
        return CompletionResponse(
            text=data["text"],
            model=data["model"],
            prompt_tokens=data["prompt_tokens"],
            completion_tokens=data["completion_tokens"],
            latency_ms=data["latency_ms"],
            raw=data.get("raw", {}),
        )

    def set(self, key: str, response: CompletionResponse) -> None:
        data = {
            "text": response.text,
            "model": response.model,
            "prompt_tokens": response.prompt_tokens,
            "completion_tokens": response.completion_tokens,
            "latency_ms": response.latency_ms,
            "raw": response.raw,
            "_cached_at": time.time(),
        }
        self._path(key).write_text(json.dumps(data, indent=2), encoding="utf-8")

    def clear(self) -> None:
        for p in self.cache_dir.glob("*.json"):
            p.unlink(missing_ok=True)

    @property
    def size(self) -> int:
        return len(list(self.cache_dir.glob("*.json")))
