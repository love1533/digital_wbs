"""Sequential prompt chain that pipes outputs into subsequent steps."""

from __future__ import annotations

from typing import Any, Callable, Optional

from .client import LLMClient, Message
from .prompt import PromptTemplate


StepFn = Callable[[str], str]


class ChainStep:
    """A single step in a :class:`Chain`."""

    def __init__(
        self,
        name: str,
        template: PromptTemplate,
        output_key: str = "output",
        transform: Optional[StepFn] = None,
    ) -> None:
        self.name = name
        self.template = template
        self.output_key = output_key
        self.transform = transform  # post-process the raw LLM output

    def __repr__(self) -> str:
        return f"ChainStep(name={self.name!r}, output_key={self.output_key!r})"


class Chain:
    """
    Execute a sequence of LLM calls where each step can consume
    variables produced by earlier steps.

    Parameters
    ----------
    client : LLMClient
        The LLM client used to execute each step.
    steps : list[ChainStep]
        Ordered list of steps to run.
    verbose : bool
        If ``True``, log intermediate outputs.
    """

    def __init__(
        self,
        client: LLMClient,
        steps: list[ChainStep],
        verbose: bool = False,
    ) -> None:
        if not steps:
            raise ValueError("Chain requires at least one step.")
        self.client = client
        self.steps = steps
        self.verbose = verbose

    def run(self, **inputs: Any) -> dict[str, Any]:
        """
        Execute all steps and return a dict of all accumulated variables.

        Parameters
        ----------
        **inputs : Any
            Initial variables made available to the first step's template.

        Returns
        -------
        dict
            Merged dict containing all inputs and the output of each step.
        """
        context: dict[str, Any] = dict(inputs)

        for step in self.steps:
            prompt_text = step.template.render(**context)
            response = self.client.complete(
                messages=[Message(role="user", content=prompt_text)]
            )
            output = response.text
            if step.transform:
                output = step.transform(output)
            context[step.output_key] = output
            if self.verbose:
                print(f"[{step.name}] → {output[:80]}{'...' if len(output) > 80 else ''}")

        return context

    def add_step(self, step: ChainStep) -> "Chain":
        """Append a step and return self for chaining calls."""
        self.steps.append(step)
        return self

    def __len__(self) -> int:
        return len(self.steps)

    def __repr__(self) -> str:
        names = ", ".join(s.name for s in self.steps)
        return f"Chain(steps=[{names}])"
