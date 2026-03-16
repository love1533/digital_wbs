"""Tests for repo_llm.utils — partial coverage."""

import pytest

from repo_llm.utils import chunk_text, estimate_tokens, extract_json, truncate


class TestEstimateTokens:
    def test_empty_string(self):
        assert estimate_tokens("") == 0

    def test_short_text(self):
        # 8 chars → max(1, 8//4) = 2
        assert estimate_tokens("12345678") == 2

    def test_single_char_returns_one(self):
        assert estimate_tokens("a") == 1

    def test_long_string(self):
        text = "a" * 400
        assert estimate_tokens(text) == 100

    def test_model_parameter_no_effect(self):
        text = "hello world test"
        assert estimate_tokens(text, model="gpt-4") == estimate_tokens(text, model="default")


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

    def test_single_chunk_small_text(self):
        result = chunk_text("hello world", max_tokens=100)
        assert len(result) == 1
        assert "hello" in result[0]

    def test_multiple_chunks_for_long_text(self):
        # 200 words, max_tokens=2 → should produce multiple chunks
        text = " ".join(["word"] * 200)
        result = chunk_text(text, max_tokens=2)
        assert len(result) > 1

    def test_overlap_produces_repeated_words(self):
        text = " ".join([f"w{i}" for i in range(20)])
        chunks_with_overlap = chunk_text(text, max_tokens=3, overlap_tokens=1)
        chunks_no_overlap = chunk_text(text, max_tokens=3, overlap_tokens=0)
        # With overlap there should be more chunks (or at least same)
        assert len(chunks_with_overlap) >= len(chunks_no_overlap)
        # Words from end of one chunk should appear at start of the next
        if len(chunks_with_overlap) > 1:
            words_in_first = set(chunks_with_overlap[0].split())
            words_in_second = set(chunks_with_overlap[1].split())
            assert len(words_in_first & words_in_second) > 0


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

    def test_json_in_markdown_code_fence(self):
        text = '```json\n{"key": "value"}\n```'
        result = extract_json(text)
        assert result == {"key": "value"}

    def test_json_in_plain_code_fence(self):
        text = '```\n{"key": 42}\n```'
        result = extract_json(text)
        assert result == {"key": 42}

    def test_nested_json_object(self):
        text = '{"outer": {"inner": [1, 2, 3]}}'
        result = extract_json(text)
        assert result["outer"]["inner"] == [1, 2, 3]

    def test_escaped_quotes_in_json(self):
        text = '{"msg": "say \\"hello\\""}'
        result = extract_json(text)
        assert result["msg"] == 'say "hello"'

    def test_malformed_json_raises(self):
        import json
        with pytest.raises(json.JSONDecodeError):
            extract_json("{invalid: json}")


class TestTruncate:
    def test_short_text_unchanged(self):
        assert truncate("hello", max_chars=10) == "hello"

    def test_truncation_applied(self):
        result = truncate("hello world", max_chars=7)
        assert len(result) == 7
        assert result.endswith("…")

    def test_max_chars_zero_raises(self):
        with pytest.raises(ValueError, match="max_chars"):
            truncate("hello", max_chars=0)

    def test_max_chars_negative_raises(self):
        with pytest.raises(ValueError, match="max_chars"):
            truncate("hello", max_chars=-5)

    def test_custom_suffix(self):
        result = truncate("hello world", max_chars=8, suffix="...")
        assert result.endswith("...")
        assert len(result) == 8

    def test_text_exactly_at_max_chars_not_truncated(self):
        text = "hello"
        assert truncate(text, max_chars=5) == "hello"
