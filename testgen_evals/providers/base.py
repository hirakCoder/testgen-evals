"""Provider interface: every LLM backend exposes ``generate(prompt, system) -> Completion``."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class Completion:
    """One model response plus the bookkeeping we need for metrics."""

    text: str
    latency_ms: float
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None


class Provider(ABC):
    """Base class for LLM backends. Subclasses implement ``_call``; ``generate`` times it."""

    name: str = "base"

    def __init__(self, model: str | None = None) -> None:
        self.model = model or self.default_model

    @property
    @abstractmethod
    def default_model(self) -> str: ...

    @abstractmethod
    def _call(self, prompt: str, system: str) -> Completion: ...

    def generate(self, prompt: str, system: str = "") -> Completion:
        """Send one prompt and return the completion with wall-clock latency filled in."""
        start = time.perf_counter()
        completion = self._call(prompt, system)
        if not completion.latency_ms:
            completion.latency_ms = (time.perf_counter() - start) * 1000
        return completion


class FakeProvider(Provider):
    """Deterministic provider for tests: returns canned responses in order.

    Used by the pytest suite so metrics, retries and the judge can be exercised offline.
    """

    name = "fake"

    def __init__(self, responses: list[str] | Callable[[str, str], str], model: str = "fake-1"):
        super().__init__(model)
        self._responses = responses
        self._i = 0
        self.calls: list[tuple[str, str]] = []

    @property
    def default_model(self) -> str:
        return "fake-1"

    def _call(self, prompt: str, system: str) -> Completion:
        self.calls.append((prompt, system))
        if callable(self._responses):
            text = self._responses(prompt, system)
        else:
            text = self._responses[min(self._i, len(self._responses) - 1)]
            self._i += 1
        return Completion(
            text=text, latency_ms=1.0, model=self.model, input_tokens=0, output_tokens=0
        )


def get_provider(name: str, model: str | None = None) -> Provider:
    """Instantiate a provider by CLI name. Imports lazily so optional SDKs stay optional."""
    if name == "claude-cli":
        from .claude_cli import ClaudeCliProvider

        return ClaudeCliProvider(model)
    if name == "anthropic":
        from .anthropic_api import AnthropicProvider

        return AnthropicProvider(model)
    if name == "openai":
        from .openai_api import OpenAIProvider

        return OpenAIProvider(model)
    raise ValueError(f"unknown provider {name!r}; expected one of: claude-cli, anthropic, openai")
