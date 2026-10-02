"""LLM-as-judge: score one test case at a time against a fixed rubric.

The judge sees the story and exactly one test case and returns four 1-5 scores plus a
one-line rationale. Pointwise scoring keeps every call independent and cheap, but a judge
is still a model: it can prefer whichever section it reads last, drift between calls, and
favour text written in its own style. Two guards are built in:

* every judgment records the prompt ``order`` it was produced with (story first by default);
* ``bias_check`` re-judges a sample with the sections swapped (case first) and reports the
  per-dimension score deltas, so position sensitivity is measured rather than assumed.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from statistics import mean
from typing import Any

from ..generate import extract_json, load_prompt
from ..providers.base import Provider
from ..schema import GeneratedSuite, Story, TestCase

DIMENSIONS = ("correctness", "completeness", "clarity", "independence")
ORDERS = ("story_first", "case_first")


@dataclass
class Judgment:
    story_id: str
    case_id: str
    order: str
    scores: dict[str, int] = field(default_factory=dict)
    rationale: str = ""
    parse_ok: bool = True
    latency_ms: float = 0.0
    cost_usd: float | None = None
    model: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_judge_prompt(story: Story, case: TestCase, order: str = "story_first") -> str:
    """Compose the judge's user turn in the requested section order."""
    if order not in ORDERS:
        raise ValueError(f"order must be one of {ORDERS}")
    story_block = "USER STORY:\n" + json.dumps(story.to_dict(), indent=2)
    case_block = "TEST CASE:\n" + json.dumps(case.to_dict(), indent=2)
    blocks = (story_block, case_block) if order == "story_first" else (case_block, story_block)
    return "\n\n".join(blocks) + "\n\nScore the test case."


def parse_judgment(text: str) -> tuple[dict[str, int], str]:
    """Pull the four integer scores and the rationale out of a judge reply."""
    data = extract_json(text)
    if not isinstance(data, dict):
        raise ValueError("judge reply is not a JSON object")
    scores: dict[str, int] = {}
    for dim in DIMENSIONS:
        value = data.get(dim)
        if not isinstance(value, int | float) or not 1 <= value <= 5:
            raise ValueError(f"{dim} missing or outside 1-5: {value!r}")
        scores[dim] = int(round(value))
    return scores, str(data.get("rationale", "")).strip()


def judge_case(
    provider: Provider,
    story: Story,
    case: TestCase,
    system: str | None = None,
    order: str = "story_first",
) -> Judgment:
    """Score one case. A reply that fails to parse yields ``parse_ok=False`` instead of raising."""
    system = system if system is not None else load_prompt("judge.md")
    judgment = Judgment(story.id, case.id, order, model=provider.model)
    try:
        completion = provider.generate(build_judge_prompt(story, case, order), system)
    except RuntimeError as exc:
        judgment.parse_ok = False
        judgment.error = str(exc)
        return judgment
    judgment.latency_ms = completion.latency_ms
    judgment.cost_usd = completion.cost_usd
    judgment.model = completion.model or judgment.model
    try:
        judgment.scores, judgment.rationale = parse_judgment(completion.text)
    except ValueError as exc:
        judgment.parse_ok = False
        judgment.error = str(exc)
    return judgment


def select_cases(
    stories: dict[str, Story],
    suites: list[GeneratedSuite],
    max_cases: int,
    seed: int = 0,
) -> list[tuple[Story, TestCase]]:
    """Pick up to ``max_cases`` valid cases, round-robin across stories so none is skipped."""
    rng = random.Random(seed)
    per_story: list[list[tuple[Story, TestCase]]] = []
    for suite in suites:
        story = stories.get(suite.story_id)
        if story is None or not suite.cases:
            continue
        cases = list(suite.cases)
        rng.shuffle(cases)
        per_story.append([(story, c) for c in cases])
    picked: list[tuple[Story, TestCase]] = []
    while len(picked) < max_cases and any(per_story):
        for bucket in per_story:
            if bucket and len(picked) < max_cases:
                picked.append(bucket.pop())
    return picked


def judge_suites(
    provider: Provider,
    stories: dict[str, Story],
    suites: list[GeneratedSuite],
    max_calls: int = 60,
    bias_check: int = 8,
    seed: int = 0,
    log: Any = None,
) -> dict[str, Any]:
    """Judge every case (sampling if needed) and re-judge ``bias_check`` of them case-first.

    Returns ``{"judgments": [...], "bias_check": [...], "sampled": bool, "total_cases": int}``.
    """
    total_cases = sum(len(s.cases) for s in suites)
    budget = max(0, max_calls - bias_check)
    selected = select_cases(stories, suites, budget, seed)
    judgments: list[Judgment] = []
    for i, (story, case) in enumerate(selected, 1):
        j = judge_case(provider, story, case, order="story_first")
        judgments.append(j)
        if log:
            log(f"  judge {i}/{len(selected)} {story.id}/{case.id} ok={j.parse_ok} {j.scores}")
    swapped: list[Judgment] = []
    for story, case in random.Random(seed + 1).sample(selected, min(bias_check, len(selected))):
        j = judge_case(provider, story, case, order="case_first")
        swapped.append(j)
        if log:
            log(f"  bias-check {story.id}/{case.id} ok={j.parse_ok} {j.scores}")
    return {
        "judgments": [j.to_dict() for j in judgments],
        "bias_check": [j.to_dict() for j in swapped],
        "sampled": len(selected) < total_cases,
        "total_cases": total_cases,
    }


def summarise_judgments(judge_run: dict[str, Any]) -> dict[str, Any]:
    """Mean score per dimension (overall and per story) and the position-bias deltas."""
    ok = [j for j in judge_run.get("judgments", []) if j.get("parse_ok")]
    by_story: dict[str, list[dict[str, Any]]] = {}
    for j in ok:
        by_story.setdefault(j["story_id"], []).append(j)

    def means(items: list[dict[str, Any]]) -> dict[str, float]:
        return (
            {d: round(mean(j["scores"][d] for j in items), 2) for d in DIMENSIONS} if items else {}
        )

    baseline = {(j["story_id"], j["case_id"]): j for j in ok}
    deltas: dict[str, list[int]] = {d: [] for d in DIMENSIONS}
    for j in judge_run.get("bias_check", []):
        base = baseline.get((j["story_id"], j["case_id"]))
        if j.get("parse_ok") and base:
            for d in DIMENSIONS:
                deltas[d].append(j["scores"][d] - base["scores"][d])
    n_pairs = len(deltas[DIMENSIONS[0]])
    summary: dict[str, Any] = {
        "judged": len(judge_run.get("judgments", [])),
        "parse_ok": len(ok),
        "sampled": judge_run.get("sampled", False),
        "total_cases": judge_run.get("total_cases", 0),
        "model": next((j["model"] for j in ok), ""),
        "mean_scores": means(ok),
        "overall_mean": round(mean(j["scores"][d] for j in ok for d in DIMENSIONS), 2)
        if ok
        else None,
        "per_story": {sid: means(items) for sid, items in sorted(by_story.items())},
        "position_bias": {
            "pairs": n_pairs,
            "mean_signed_delta": {d: round(mean(v), 2) if v else None for d, v in deltas.items()},
            "mean_abs_delta": {
                d: round(mean(abs(x) for x in v), 2) if v else None for d, v in deltas.items()
            },
            "pairs_with_any_change": sum(
                1 for i in range(n_pairs) if any(deltas[d][i] != 0 for d in DIMENSIONS)
            ),
        },
    }
    return summary
