"""Conversation memory management with token-budget trimming."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from .client import Message


@dataclass
class TurnRecord:
    user: str
    assistant: str
    metadata: dict = field(default_factory=dict)


class ConversationMemory:
    """
    Maintains a sliding-window conversation history.

    Automatically trims old turns when the estimated token count exceeds
    ``max_tokens``.

    Parameters
    ----------
    max_tokens : int
        Soft cap on total tokens held in memory.  When exceeded, the oldest
        turn is dropped.
    token_counter : callable, optional
        A function ``(text: str) -> int`` used to estimate token counts.
        Defaults to a simple whitespace-split heuristic.
    system_prompt : str, optional
        A system message prepended to every :meth:`to_messages` call.
    """

    def __init__(
        self,
        max_tokens: int = 4096,
        token_counter: Optional[Callable[[str], int]] = None,
        system_prompt: Optional[str] = None,
    ) -> None:
        if max_tokens <= 0:
            raise ValueError("max_tokens must be > 0.")
        self.max_tokens = max_tokens
        self._token_counter = token_counter or _default_token_counter
        self.system_prompt = system_prompt
        self._turns: list[TurnRecord] = []

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add_turn(self, user: str, assistant: str, **metadata) -> None:
        """Append a completed exchange and enforce the token budget."""
        if not user.strip():
            raise ValueError("user message must not be blank.")
        if not assistant.strip():
            raise ValueError("assistant message must not be blank.")
        self._turns.append(TurnRecord(user=user, assistant=assistant, metadata=metadata))
        self._trim()

    def clear(self) -> None:
        """Remove all stored turns."""
        self._turns.clear()

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def to_messages(self) -> list[Message]:
        """Return the history as a flat list of :class:`Message` objects."""
        msgs: list[Message] = []
        if self.system_prompt:
            msgs.append(Message(role="system", content=self.system_prompt))
        for turn in self._turns:
            msgs.append(Message(role="user", content=turn.user))
            msgs.append(Message(role="assistant", content=turn.assistant))
        return msgs

    @property
    def turn_count(self) -> int:
        return len(self._turns)

    @property
    def token_count(self) -> int:
        """Estimate total tokens across all stored turns."""
        return sum(
            self._token_counter(t.user) + self._token_counter(t.assistant)
            for t in self._turns
        )

    def last_turn(self) -> Optional[TurnRecord]:
        return self._turns[-1] if self._turns else None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _trim(self) -> None:
        """Drop oldest turns until we are within the token budget."""
        while self._turns and self.token_count > self.max_tokens:
            self._turns.pop(0)

    def __repr__(self) -> str:
        return (
            f"ConversationMemory(turns={self.turn_count}, "
            f"tokens≈{self.token_count}/{self.max_tokens})"
        )


def _default_token_counter(text: str) -> int:
    """Heuristic: count whitespace-delimited words as a proxy for tokens."""
    return len(text.split())
