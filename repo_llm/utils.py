"""Utility helpers: token counting, text chunking, output parsing."""

from __future__ import annotations

import json
import re
from typing import Any


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------

def estimate_tokens(text: str, model: str = "default") -> int:
    """
    Estimate token count for *text*.

    Uses the widely-cited heuristic of ~4 characters per token for English
    text.  For ``cl100k``-family models (GPT-4, Claude) this is within ~10 %
    for typical prose.

    Parameters
    ----------
    text : str
    model : str
        Reserved for future model-specific logic.

    Returns
    -------
    int
        Non-negative estimated token count.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


# ---------------------------------------------------------------------------
# Text chunking
# ---------------------------------------------------------------------------

def chunk_text(
    text: str,
    max_tokens: int,
    overlap_tokens: int = 0,
    model: str = "default",
) -> list[str]:
    """
    Split *text* into chunks that each fit within *max_tokens*.

    Parameters
    ----------
    text : str
    max_tokens : int
        Maximum estimated tokens per chunk.
    overlap_tokens : int
        Number of tokens to repeat from the end of one chunk at the start of
        the next (useful for sliding-window tasks).
    model : str
        Passed through to :func:`estimate_tokens`.

    Returns
    -------
    list[str]
        Ordered list of text chunks.
    """
    if max_tokens <= 0:
        raise ValueError("max_tokens must be > 0.")
    if overlap_tokens < 0:
        raise ValueError("overlap_tokens must be >= 0.")
    if overlap_tokens >= max_tokens:
        raise ValueError("overlap_tokens must be less than max_tokens.")
    if not text:
        return []

    words = text.split()
    chars_per_token = 4  # heuristic
    words_per_chunk = max(1, max_tokens * chars_per_token // max(1, sum(len(w) for w in words[:100]) // max(1, len(words[:100]))))
    overlap_words = max(0, overlap_tokens * chars_per_token // max(1, sum(len(w) for w in words[:100]) // max(1, len(words[:100]))))

    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = start + words_per_chunk
        chunks.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        start = end - overlap_words
    return chunks


# ---------------------------------------------------------------------------
# JSON output parsing
# ---------------------------------------------------------------------------

def extract_json(text: str) -> Any:
    """
    Extract the first JSON object or array found in *text*.

    Useful for parsing structured LLM responses that may include surrounding
    prose or markdown fences.

    Raises
    ------
    ValueError
        If no valid JSON block is found.
    """
    # Try code-fence extraction first
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
    if fence_match:
        candidate = fence_match.group(1)
        return json.loads(candidate)

    # Fall back to finding first { or [
    for start_char, end_char in (("{", "}"), ("[", "]")):
        idx = text.find(start_char)
        if idx == -1:
            continue
        # Walk forward to find the matching closing bracket
        depth = 0
        in_string = False
        escape_next = False
        for i, ch in enumerate(text[idx:], start=idx):
            if escape_next:
                escape_next = False
                continue
            if ch == "\\" and in_string:
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == start_char:
                depth += 1
            elif ch == end_char:
                depth -= 1
                if depth == 0:
                    candidate = text[idx : i + 1]
                    return json.loads(candidate)

    raise ValueError("No JSON object or array found in text.")


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

def truncate(text: str, max_chars: int, suffix: str = "…") -> str:
    """Truncate *text* to *max_chars*, appending *suffix* if truncated."""
    if max_chars <= 0:
        raise ValueError("max_chars must be > 0.")
    if len(text) <= max_chars:
        return text
    return text[: max_chars - len(suffix)] + suffix
