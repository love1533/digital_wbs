"""Prompt templating with variable interpolation and validation."""

import re
from typing import Any


class PromptTemplate:
    """
    A simple Jinja-style prompt template.

    Variables are declared with ``{variable_name}`` placeholders.

    Examples
    --------
    >>> t = PromptTemplate("Translate '{text}' to {language}.")
    >>> t.render(text="hello", language="French")
    "Translate 'hello' to French."
    """

    # Matches {word} placeholders (alphanumeric + underscore, not whitespace)
    _VAR_RE = re.compile(r"\{(\w+)\}")

    def __init__(self, template: str) -> None:
        if not isinstance(template, str):
            raise TypeError("template must be a string.")
        self.template = template
        self.variables: list[str] = self._VAR_RE.findall(template)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render(self, **kwargs: Any) -> str:
        """
        Substitute variables and return the rendered string.

        Raises
        ------
        KeyError
            If a required variable is missing from ``kwargs``.
        """
        missing = set(self.variables) - set(kwargs)
        if missing:
            raise KeyError(f"Missing template variables: {sorted(missing)}")
        return self.template.format_map(kwargs)

    def partial(self, **kwargs: Any) -> "PromptTemplate":
        """Return a new template with some variables pre-filled."""
        unknown = set(kwargs) - set(self.variables)
        if unknown:
            raise KeyError(f"Unknown variables: {sorted(unknown)}")
        pre_rendered = self.template
        for key, value in kwargs.items():
            pre_rendered = pre_rendered.replace(f"{{{key}}}", str(value))
        return PromptTemplate(pre_rendered)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"PromptTemplate({self.template!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PromptTemplate):
            return NotImplemented
        return self.template == other.template


def load_template_from_file(path: str) -> PromptTemplate:
    """Load a :class:`PromptTemplate` from a plain-text file."""
    with open(path, encoding="utf-8") as fh:
        return PromptTemplate(fh.read())
