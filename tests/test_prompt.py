"""Tests for repo_llm.prompt — partial coverage."""

import pytest

from repo_llm.prompt import PromptTemplate


class TestPromptTemplate:
    def test_render_single_variable(self):
        t = PromptTemplate("Hello, {name}!")
        assert t.render(name="World") == "Hello, World!"

    def test_render_multiple_variables(self):
        t = PromptTemplate("Translate '{text}' to {language}.")
        result = t.render(text="hello", language="French")
        assert result == "Translate 'hello' to French."

    def test_variables_property(self):
        t = PromptTemplate("{a} and {b} and {a}")
        # The regex findall returns all occurrences including duplicates
        assert t.variables == ["a", "b", "a"]

    def test_render_missing_variable_raises(self):
        t = PromptTemplate("Hello, {name}!")
        with pytest.raises(KeyError):
            t.render()

    def test_no_variables(self):
        t = PromptTemplate("Static text.")
        assert t.render() == "Static text."

    def test_non_string_template_raises(self):
        with pytest.raises(TypeError):
            PromptTemplate(123)  # type: ignore[arg-type]

    # MISSING: test partial() happy path
    # MISSING: test partial() with unknown variable raises KeyError
    # MISSING: test partial() returns a new PromptTemplate instance
    # MISSING: test __eq__ between identical and different templates
    # MISSING: test __repr__ output
    # MISSING: test load_template_from_file (needs tmp_path fixture)
    # MISSING: test extra kwargs passed to render() are silently ignored or raise
