"""Deterministic metrics for a generated suite. No LLM involved; every number is reproducible.

Metrics computed per story (suite) and aggregated across stories:

* schema validity rate      - cases that met the contract / cases the model produced
* acceptance-criteria coverage - ACs referenced by at least one valid case (explicit ``covers``
  ids first, then a fuzzy token-overlap fallback for cases that forgot to tag)
* near-duplicate rate       - cases whose normalised token set has Jaccard >= 0.8 with an
  earlier case
* negative-test ratio       - share of cases typed ``negative`` (and ``edge``, reported separately)
* step-count sanity         - mean steps per case and cases outside [1, MAX_STEPS]
* untestable steps          - steps with no verifiable expected result
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from statistics import mean
from typing import Any

from ..schema import CASE_TYPES, MAX_STEPS, GeneratedSuite, Step, Story, TestCase

DUPLICATE_THRESHOLD = 0.8
FUZZY_COVERAGE_THRESHOLD = 0.5

_STOPWORDS = frozenset(
    """a an and are as at be by for from has have if in into is it its of on or that the then
    this to was when with will should user users can click clicks enter enters verify verifies
    check checks system displays displayed shown shows page""".split()
)
_VAGUE_EXPECTED = re.compile(
    r"^\s*(it\s+)?(works?|succeeds?|passes?|ok|okay|done|n/?a|as\s+expected|"
    r"works?\s+(correctly|fine|as\s+expected)|should\s+work|no\s+errors?|"
    r"(the\s+)?(system|app|page)\s+(works|responds)(\s+correctly)?)\s*\.?\s*$",
    re.IGNORECASE,
)
_TOKEN = re.compile(r"[a-z0-9]+(?:[-'][a-z0-9]+)*")


def tokens(text: str) -> set[str]:
    """Lower-case content tokens with stop-words removed. Used by Jaccard and fuzzy coverage."""
    return {t for t in _TOKEN.findall(text.lower()) if len(t) > 1 and t not in _STOPWORDS}


def jaccard(a: set[str], b: set[str]) -> float:
    """Token-set Jaccard similarity; 0.0 when both sets are empty."""
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def find_duplicates(
    cases: list[TestCase], threshold: float = DUPLICATE_THRESHOLD
) -> list[tuple[str, str, float]]:
    """Return (earlier_id, later_id, similarity) for every pair at or above ``threshold``."""
    toks = [tokens(c.text()) for c in cases]
    pairs: list[tuple[str, str, float]] = []
    for j in range(len(cases)):
        for i in range(j):
            sim = jaccard(toks[i], toks[j])
            if sim >= threshold:
                pairs.append((cases[i].id, cases[j].id, round(sim, 3)))
    return pairs


def is_untestable(step: Step) -> bool:
    """A step is untestable when its expected result is missing, vague, or too thin to verify."""
    expected = step.expected.strip()
    if not expected or _VAGUE_EXPECTED.match(expected):
        return True
    return len(tokens(expected)) < 3


@dataclass
class CoverageResult:
    covered_explicit: list[str]
    covered_fuzzy: list[str]
    uncovered: list[str]
    unknown_refs: list[str]


def ac_coverage(
    story: Story, cases: list[TestCase], fuzzy_threshold: float = FUZZY_COVERAGE_THRESHOLD
) -> CoverageResult:
    """Which acceptance criteria are covered, explicitly (``covers``) or by fuzzy text overlap.

    Fuzzy matching only rescues criteria that no case tagged explicitly. A criterion counts as
    fuzzy-covered when at least ``fuzzy_threshold`` of its content tokens appear in one case.
    """
    known = set(story.ac_ids)
    explicit = {ac for c in cases for ac in c.covers if ac in known}
    unknown = sorted({ac for c in cases for ac in c.covers if ac not in known})
    fuzzy: list[str] = []
    case_tokens = [tokens(c.text()) for c in cases]
    for ac in story.acceptance_criteria:
        if ac.id in explicit:
            continue
        ac_toks = tokens(ac.text)
        if not ac_toks:
            continue
        best = max((len(ac_toks & ct) / len(ac_toks) for ct in case_tokens), default=0.0)
        if best >= fuzzy_threshold:
            fuzzy.append(ac.id)
    uncovered = [ac for ac in story.ac_ids if ac not in explicit and ac not in fuzzy]
    return CoverageResult(sorted(explicit), fuzzy, uncovered, unknown)


@dataclass
class SuiteMetrics:
    """All deterministic numbers for one story's generated suite."""

    story_id: str
    parse_ok: bool
    cases_produced: int
    cases_valid: int
    schema_valid_rate: float
    ac_total: int
    ac_covered_explicit: int
    ac_covered_fuzzy: int
    ac_coverage: float
    ac_coverage_explicit: float
    uncovered_acs: list[str]
    unknown_ac_refs: list[str]
    duplicate_pairs: list[tuple[str, str, float]]
    duplicate_rate: float
    type_counts: dict[str, int]
    negative_ratio: float
    edge_ratio: float
    mean_steps: float
    cases_over_max_steps: int
    total_steps: int
    untestable_steps: int
    untestable_step_rate: float
    untestable_examples: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_suite_metrics(story: Story, suite: GeneratedSuite) -> SuiteMetrics:
    """Score one generated suite against its story."""
    cases = suite.cases
    produced = len(cases) + len(suite.invalid_cases)
    n = len(cases)
    cov = ac_coverage(story, cases)
    dups = find_duplicates(cases)
    dup_later_ids = {later for _, later, _ in dups}
    type_counts = {t: sum(1 for c in cases if c.type == t) for t in CASE_TYPES}
    steps = [s for c in cases for s in c.steps]
    untestable = [(c.id, s) for c in cases for s in c.steps if is_untestable(s)]
    ac_total = len(story.acceptance_criteria)
    covered = len(cov.covered_explicit) + len(cov.covered_fuzzy)
    return SuiteMetrics(
        story_id=story.id,
        parse_ok=suite.parse_ok,
        cases_produced=produced,
        cases_valid=n,
        schema_valid_rate=n / produced if produced else 0.0,
        ac_total=ac_total,
        ac_covered_explicit=len(cov.covered_explicit),
        ac_covered_fuzzy=len(cov.covered_fuzzy),
        ac_coverage=covered / ac_total if ac_total else 0.0,
        ac_coverage_explicit=len(cov.covered_explicit) / ac_total if ac_total else 0.0,
        uncovered_acs=cov.uncovered,
        unknown_ac_refs=cov.unknown_refs,
        duplicate_pairs=dups,
        duplicate_rate=len(dup_later_ids) / n if n else 0.0,
        type_counts=type_counts,
        negative_ratio=type_counts["negative"] / n if n else 0.0,
        edge_ratio=type_counts["edge"] / n if n else 0.0,
        mean_steps=mean(len(c.steps) for c in cases) if cases else 0.0,
        cases_over_max_steps=sum(1 for c in cases if len(c.steps) > MAX_STEPS),
        total_steps=len(steps),
        untestable_steps=len(untestable),
        untestable_step_rate=len(untestable) / len(steps) if steps else 0.0,
        untestable_examples=[f"{cid}: {s.action!r} -> {s.expected!r}" for cid, s in untestable[:5]],
    )


def aggregate(metrics: list[SuiteMetrics]) -> dict[str, Any]:
    """Pool suite metrics into overall rates. Rates are case/step-weighted, not story-averaged."""
    produced = sum(m.cases_produced for m in metrics)
    valid = sum(m.cases_valid for m in metrics)
    ac_total = sum(m.ac_total for m in metrics)
    ac_covered = sum(m.ac_covered_explicit + m.ac_covered_fuzzy for m in metrics)
    ac_explicit = sum(m.ac_covered_explicit for m in metrics)
    dup_cases = sum(len({later for _, later, _ in m.duplicate_pairs}) for m in metrics)
    steps = sum(m.total_steps for m in metrics)
    untestable = sum(m.untestable_steps for m in metrics)
    types = {t: sum(m.type_counts.get(t, 0) for m in metrics) for t in CASE_TYPES}
    return {
        "stories": len(metrics),
        "stories_parse_ok": sum(1 for m in metrics if m.parse_ok),
        "cases_produced": produced,
        "cases_valid": valid,
        "schema_valid_rate": valid / produced if produced else 0.0,
        "ac_total": ac_total,
        "ac_covered": ac_covered,
        "ac_coverage": ac_covered / ac_total if ac_total else 0.0,
        "ac_coverage_explicit": ac_explicit / ac_total if ac_total else 0.0,
        "stories_with_full_coverage": sum(1 for m in metrics if not m.uncovered_acs),
        "duplicate_cases": dup_cases,
        "duplicate_rate": dup_cases / valid if valid else 0.0,
        "type_counts": types,
        "negative_ratio": types["negative"] / valid if valid else 0.0,
        "edge_ratio": types["edge"] / valid if valid else 0.0,
        "mean_steps": mean(m.mean_steps for m in metrics if m.cases_valid) if valid else 0.0,
        "cases_over_max_steps": sum(m.cases_over_max_steps for m in metrics),
        "total_steps": steps,
        "untestable_steps": untestable,
        "untestable_step_rate": untestable / steps if steps else 0.0,
    }
