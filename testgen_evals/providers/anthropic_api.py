"""Backend for the Anthropic Messages API via the official ``anthropic`` SDK.

Enabled when ``ANTHROPIC_API_KEY`` is set. Install with ``pip install "testgen-evals[anthropic]"``.
"""

from __future__ import annotations

import os

from .base import Completion, Provider

# USD per million tokens; used only to estimate cost in the report. Update when prices change.
_PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


class AnthropicProvider(Provider):
    name = "anthropic"

    @property
    def default_model(self) -> str:
        return os.environ.get("TESTGEN_ANTHROPIC_MODEL", "claude-sonnet-5")

    def _call(self, prompt: str, system: str) -> Completion:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - depends on optional install
            raise RuntimeError("install the optional dependency: pip install anthropic") from exc

        client = anthropic.Anthropic()
        response = client.messages.create(
            model=self.model,
            max_tokens=8000,
            system=system or anthropic.NOT_GIVEN,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        inp, out = response.usage.input_tokens, response.usage.output_tokens
        cost = None
        if self.model in _PRICES:
            pin, pout = _PRICES[self.model]
            cost = (inp * pin + out * pout) / 1_000_000
        return Completion(
            text=text,
            latency_ms=0.0,
            model=response.model,
            input_tokens=inp,
            output_tokens=out,
            cost_usd=cost,
        )
