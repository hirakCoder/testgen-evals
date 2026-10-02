"""Optional backend for OpenAI-compatible chat models. Enabled when ``OPENAI_API_KEY`` is set."""

from __future__ import annotations

import os

from .base import Completion, Provider


class OpenAIProvider(Provider):
    name = "openai"

    @property
    def default_model(self) -> str:
        return os.environ.get("TESTGEN_OPENAI_MODEL", "gpt-4o-mini")

    def _call(self, prompt: str, system: str) -> Completion:
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is not set")
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - depends on optional install
            raise RuntimeError("install the optional dependency: pip install openai") from exc

        client = OpenAI()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = client.chat.completions.create(model=self.model, messages=messages)
        usage = response.usage
        return Completion(
            text=response.choices[0].message.content or "",
            latency_ms=0.0,
            model=response.model,
            input_tokens=usage.prompt_tokens if usage else None,
            output_tokens=usage.completion_tokens if usage else None,
        )
