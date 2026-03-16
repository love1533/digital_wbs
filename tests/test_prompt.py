"""Tests for repo_llm.prompt — partial coverage."""

import pytest

from repo_llm.prompt import PromptTemplate, load_template_from_file


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

    def test_partial_fills_known_variable(self):
        t = PromptTemplate("Hello {name}, speak {language}.")
        partial = t.partial(language="French")
        assert partial.render(name="Alice") == "Hello Alice, speak French."

    def test_partial_returns_prompt_template_instance(self):
        t = PromptTemplate("Hello {name}, speak {language}.")
        partial = t.partial(language="French")
        assert isinstance(partial, PromptTemplate)

    def test_partial_unknown_variable_raises(self):
        t = PromptTemplate("Hello {name}.")
        with pytest.raises(KeyError):
            t.partial(unknown_var="x")

    def test_eq_identical_templates(self):
        t1 = PromptTemplate("Hello {name}!")
        t2 = PromptTemplate("Hello {name}!")
        assert t1 == t2

    def test_eq_different_templates(self):
        t1 = PromptTemplate("Hello {name}!")
        t2 = PromptTemplate("Goodbye {name}!")
        assert t1 != t2

    def test_eq_non_template_returns_not_implemented(self):
        t = PromptTemplate("Hello {name}!")
        result = t.__eq__("not a template")
        assert result is NotImplemented

    def test_repr(self):
        t = PromptTemplate("Hello {name}!")
        r = repr(t)
        assert "PromptTemplate" in r
        assert "Hello {name}!" in r

    def test_load_template_from_file(self, tmp_path):
        p = tmp_path / "tpl.txt"
        p.write_text("Dear {recipient},\n{body}")
        t = load_template_from_file(str(p))
        assert t.render(recipient="Bob", body="Hi") == "Dear Bob,\nHi"

    def test_load_template_from_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_template_from_file("/nonexistent/path/template.txt")
