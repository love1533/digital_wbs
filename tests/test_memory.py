"""Tests for repo_llm.memory — partial coverage."""

import pytest

from repo_llm.memory import ConversationMemory, TurnRecord


class TestConversationMemory:
    def test_add_and_retrieve_turn(self):
        mem = ConversationMemory()
        mem.add_turn("hi", "hello back")
        assert mem.turn_count == 1
        assert mem.last_turn().user == "hi"

    def test_clear(self):
        mem = ConversationMemory()
        mem.add_turn("a", "b")
        mem.clear()
        assert mem.turn_count == 0
        assert mem.last_turn() is None

    def test_to_messages_without_system_prompt(self):
        mem = ConversationMemory()
        mem.add_turn("question", "answer")
        msgs = mem.to_messages()
        assert len(msgs) == 2
        assert msgs[0].role == "user"
        assert msgs[1].role == "assistant"

    def test_invalid_max_tokens(self):
        with pytest.raises(ValueError):
            ConversationMemory(max_tokens=0)

    # MISSING: to_messages() WITH system_prompt prepended
    # MISSING: token trimming — oldest turn dropped when budget exceeded
    # MISSING: custom token_counter is actually called
    # MISSING: blank user message raises ValueError
    # MISSING: blank assistant message raises ValueError
    # MISSING: metadata kwarg stored in TurnRecord
    # MISSING: token_count property returns correct value
    # MISSING: __repr__ smoke test
