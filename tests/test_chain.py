"""Tests for repo_llm.chain — full coverage."""

import pytest
from unittest.mock import MagicMock

from repo_llm.chain import Chain, ChainStep
from repo_llm.client import CompletionResponse
from repo_llm.prompt import PromptTemplate


def _mock_client(reply="ok"):
    client = MagicMock()
    client.complete.return_value = CompletionResponse(
        text=reply, model="m", prompt_tokens=5,
        completion_tokens=10, latency_ms=50.0,
    )
    return client


def _step(name="s1", template_str="Say hi to {name}", output_key="output"):
    return ChainStep(name, PromptTemplate(template_str), output_key=output_key)


class TestChainStep:
    def test_repr(self):
        step = ChainStep("greet", PromptTemplate("Hello {name}"), output_key="greeting")
        r = repr(step)
        assert "greet" in r
        assert "greeting" in r

    def test_default_output_key(self):
        step = ChainStep("s", PromptTemplate("hi"))
        assert step.output_key == "output"

    def test_transform_stored(self):
        fn = lambda x: x.upper()
        step = ChainStep("s", PromptTemplate("hi"), transform=fn)
        assert step.transform is fn


class TestChainInit:
    def test_empty_steps_raises(self):
        with pytest.raises(ValueError, match="at least one step"):
            Chain(_mock_client(), [])

    def test_valid_construction(self):
        chain = Chain(_mock_client(), [_step()])
        assert len(chain) == 1

    def test_verbose_default_false(self):
        chain = Chain(_mock_client(), [_step()])
        assert chain.verbose is False

    def test_repr(self):
        chain = Chain(_mock_client(), [_step("step_a")])
        assert "step_a" in repr(chain)


class TestChainRun:
    def test_single_step_happy_path(self):
        step = ChainStep("greet", PromptTemplate("Say hi to {name}"), output_key="greeting")
        chain = Chain(_mock_client("Hello, Alice!"), [step])
        result = chain.run(name="Alice")
        assert result["greeting"] == "Hello, Alice!"
        assert result["name"] == "Alice"

    def test_multi_step_variable_passing(self):
        step1 = ChainStep("s1", PromptTemplate("Topic: {topic}"), output_key="summary")
        step2 = ChainStep("s2", PromptTemplate("Expand: {summary}"), output_key="expanded")
        client = MagicMock()
        client.complete.side_effect = [
            CompletionResponse("Short summary", "m", 5, 10, 50.0),
            CompletionResponse("Long expansion", "m", 10, 20, 60.0),
        ]
        chain = Chain(client, [step1, step2])
        ctx = chain.run(topic="AI")
        assert ctx["summary"] == "Short summary"
        assert ctx["expanded"] == "Long expansion"

    def test_transform_applied(self):
        step = ChainStep(
            "shout",
            PromptTemplate("Say {word}"),
            output_key="result",
            transform=str.upper,
        )
        chain = Chain(_mock_client("quiet"), [step])
        result = chain.run(word="hello")
        assert result["result"] == "QUIET"

    def test_client_exception_propagates(self):
        from repo_llm.client import LLMError
        client = MagicMock()
        client.complete.side_effect = LLMError("boom")
        chain = Chain(client, [_step()])
        with pytest.raises(LLMError):
            chain.run(name="x")

    def test_verbose_prints(self, capsys):
        step = ChainStep("loud", PromptTemplate("hi {x}"), output_key="out")
        chain = Chain(_mock_client("response text"), [step], verbose=True)
        chain.run(x="world")
        captured = capsys.readouterr()
        assert "loud" in captured.out
        assert "response text" in captured.out

    def test_verbose_long_output_truncated(self, capsys):
        long_reply = "a" * 200
        step = ChainStep("s", PromptTemplate("hi {x}"), output_key="out")
        chain = Chain(_mock_client(long_reply), [step], verbose=True)
        chain.run(x="y")
        captured = capsys.readouterr()
        assert "..." in captured.out


class TestChainAddStep:
    def test_add_step_returns_self(self):
        chain = Chain(_mock_client(), [_step("s1")])
        result = chain.add_step(_step("s2"))
        assert result is chain

    def test_add_step_mutates_steps(self):
        chain = Chain(_mock_client(), [_step("s1")])
        chain.add_step(_step("s2"))
        assert len(chain) == 2
        assert chain.steps[1].name == "s2"
