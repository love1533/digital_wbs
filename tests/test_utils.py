"""Tests for repo_llm.utils — partial coverage."""

import pytest

from repo_llm.utils import chunk_text, estimate_tokens, extract_json, truncate


class TestEstimateTokens:
    def test_empty_string(self):
        assert estimate_tokens("") == 0

    def test_short_text(self):
        # 8 chars → max(1, 8//4) = 2
        assert estimate_tokens("12345678") == 2

    # MISSING: very long string
    # MISSING: model parameter has no effect in current implementation (document/test)
    # MISSING: single-char string returns 1 (minimum)


class TestChunkText:
    def test_empty_text_returns_empty_list(self):
        assert chunk_text("", max_tokens=100) == []

    def test_invalid_max_tokens(self):
        with pytest.raises(ValueError):
            chunk_text("hello", max_tokens=0)

    def test_invalid_overlap_negative(self):
        with pytest.raises(ValueError):
            chunk_text("hello world", max_tokens=10, overlap_tokens=-1)

    def test_overlap_gte_max_raises(self):
        with pytest.raises(ValueError):
            chunk_text("hello world", max_tokens=10, overlap_tokens=10)

    # MISSING: single chunk (text fits in one chunk)
    # MISSING: multiple chunks produced for long text
    # MISSING: overlap_tokens > 0 causes words to repeat across adjacent chunks
    # MISSING: text with only whitespace


class TestExtractJson:
    def test_plain_json_object(self):
        result = extract_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_inside_prose(self):
        text = 'Here is your answer: {"score": 9, "label": "good"} — enjoy!'
        result = extract_json(text)
        assert result["score"] == 9

    def test_json_array(self):
        result = extract_json("[1, 2, 3]")
        assert result == [1, 2, 3]

    def test_no_json_raises(self):
        with pytest.raises(ValueError):
            extract_json("no json here at all")

    # MISSING: JSON in markdown code fence (```json ... ```)
    # MISSING: nested objects/arrays
    # MISSING: escaped quotes inside JSON strings
    # MISSING: malformed JSON that looks like JSON raises json.JSONDecodeError


class TestTruncate:
    def test_short_text_unchanged(self):
        assert truncate("hello", max_chars=10) == "hello"

    def test_truncation_applied(self):
        result = truncate("hello world", max_chars=7)
        assert len(result) == 7
        assert result.endswith("…")

    # MISSING: max_chars <= 0 raises ValueError
    # MISSING: custom suffix parameter
    # MISSING: text exactly at max_chars is not truncated
    # MISSING: suffix longer than max_chars edge case
