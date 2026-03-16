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

    def test_to_messages_with_system_prompt(self):
        mem = ConversationMemory(system_prompt="You are a helpful assistant.")
        mem.add_turn("hi", "hello")
        msgs = mem.to_messages()
        assert msgs[0].role == "system"
        assert msgs[0].content == "You are a helpful assistant."
        assert len(msgs) == 3  # system + user + assistant

    def test_trim_drops_oldest_when_budget_exceeded(self):
        # max_tokens=5, each turn costs ~2 words each side = ~4 tokens
        mem = ConversationMemory(max_tokens=5)
        mem.add_turn("one two", "three four")   # 4 tokens
        mem.add_turn("five six", "seven eight")  # 4 more → exceeds 5, trims first
        assert mem.turn_count == 1
        assert mem.last_turn().user == "five six"

    def test_custom_token_counter_is_called(self):
        counter_calls = []

        def counting_counter(text):
            counter_calls.append(text)
            return len(text)

        mem = ConversationMemory(max_tokens=10000, token_counter=counting_counter)
        mem.add_turn("hello", "world")
        assert len(counter_calls) > 0

    def test_blank_user_message_raises(self):
        mem = ConversationMemory()
        with pytest.raises(ValueError, match="user"):
            mem.add_turn("   ", "response")

    def test_blank_assistant_message_raises(self):
        mem = ConversationMemory()
        with pytest.raises(ValueError, match="assistant"):
            mem.add_turn("question", "   ")

    def test_metadata_stored_in_turn_record(self):
        mem = ConversationMemory()
        mem.add_turn("hi", "hello", source="test", timestamp=123)
        turn = mem.last_turn()
        assert turn.metadata["source"] == "test"
        assert turn.metadata["timestamp"] == 123

    def test_token_count_property(self):
        mem = ConversationMemory()
        mem.add_turn("hello world", "foo bar baz")
        # "hello world" = 2 words, "foo bar baz" = 3 words → 5 total
        assert mem.token_count == 5

    def test_repr(self):
        mem = ConversationMemory(max_tokens=100)
        mem.add_turn("hi", "hello")
        r = repr(mem)
        assert "ConversationMemory" in r
        assert "100" in r
