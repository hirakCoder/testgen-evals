"""Generate a test suite for a story with an LLM provider and validate the result.

The generator prompt lives in ``prompts/generate.md`` so it can be reviewed and versioned
like code. The model must answer with a JSON object; we tolerate markdown fences and leading
prose, retry once when the answer is not parseable JSON, and record latency, tokens and cost.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .providers.base import Provider
from .schema import GeneratedSuite, Story, parse_suite_payload

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def load_prompt(name: str) -> str:
    """Read a prompt template from the ``prompts/`` directory."""
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def extract_json(text: str) -> Any:
    """Parse the first JSON object or array in ``text``. Raises ``ValueError`` if none parses."""
    candidates = [m.group(1) for m in _FENCE.finditer(text)] + [text]
    for cand in candidates:
        cand = cand.strip()
        starts = [i for i in (cand.find("{"), cand.find("[")) if i >= 0]
        if not starts:
            continue
        start = min(starts)
        closer = "}" if cand[start] == "{" else "]"
        end = cand.rfind(closer)
        if end <= start:
            continue
        try:
            return json.loads(cand[start : end + 1])
        except json.JSONDecodeError:
            continue
    raise ValueError("no JSON object found in model output")


def build_user_prompt(story: Story) -> str:
    """The user turn: the story as JSON, nothing else, so the system prompt owns the rules."""
    return "User story:\n" + json.dumps(story.to_dict(), indent=2)


def generate_suite(
    provider: Provider,
    story: Story,
    system: str | None = None,
    raw_dir: Path | None = None,
) -> GeneratedSuite:
    """Ask ``provider`` for a suite for ``story``; retry once if the reply is not JSON."""
    system = system if system is not None else load_prompt("generate.md")
    prompt = build_user_prompt(story)
    suite = GeneratedSuite(story_id=story.id, provider=provider.name, model=provider.model)
    payload: Any = None
    for attempt in (1, 2):
        completion = provider.generate(prompt, system)
        suite.attempts = attempt
        suite.latency_ms += completion.latency_ms
        suite.model = completion.model or suite.model
        for field_name in ("input_tokens", "output_tokens", "cost_usd"):
            value = getattr(completion, field_name)
            if value is not None:
                setattr(suite, field_name, (getattr(suite, field_name) or 0) + value)
        if raw_dir is not None:
            raw_dir.mkdir(parents=True, exist_ok=True)
            (raw_dir / f"{story.id}.attempt{attempt}.txt").write_text(
                completion.text, encoding="utf-8"
            )
        try:
            payload = extract_json(completion.text)
            break
        except ValueError as exc:
            suite.schema_errors.append(f"attempt {attempt}: {exc}")
            prompt = (
                f"{prompt}\n\nYour previous reply was not valid JSON ({exc}). "
                "Reply with the JSON object only."
            )
    if payload is None:
        suite.parse_ok = False
        return suite
    suite.cases, suite.invalid_cases, errors = parse_suite_payload(payload)
    suite.schema_errors.extend(errors)
    return suite
