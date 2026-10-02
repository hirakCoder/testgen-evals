# testgen-evals report - 20261002T191317Z

- Date: 2026-10-02
- Generator: `claude-cli` / `claude-sonnet-5`
- Stories file: `datasets/stories.jsonl`
- Generation retries: 0; median latency 15193 ms; max 18374 ms
- Tokens: 20466 in / 19129 out; reported cost: 0.2731 USD

## Overall

| Metric | Value |
|---|---|
| Stories | 10 (10 parsed OK) |
| Cases generated | 71 (71 schema-valid) |
| Schema-valid rate | 100.0% |
| AC coverage (explicit + fuzzy) | 100.0% (49/49) |
| AC coverage (explicit `covers` only) | 100.0% |
| Stories with every AC covered | 10/10 |
| Near-duplicate rate | 1.4% (1) |
| Case types | positive 24, negative 29, edge 18 |
| Negative-test ratio | 40.8% |
| Edge-test ratio | 25.4% |
| Mean steps per case | 2.5 (0 over the max) |
| Untestable steps | 0.0% (0/176) |

## Per story

| Story | Valid/produced | ACs covered | Dups | Neg/edge | Untestable |
|---|---|---|---|---|---|
| ST-001 Apply a discount code at checkout | 8/8 | 5/5 | 0 | 3/1 | 0/20 |
| ST-002 Reserve a library book via the API | 8/8 | 5/5 | 0 | 4/2 | 0/17 |
| ST-003 Cancel a booked ride | 6/6 | 4/4 | 0 | 3/2 | 0/18 |
| ST-004 Reset a forgotten password | 8/8 | 6/6 | 0 | 4/2 | 0/15 |
| ST-005 Upload an attachment to a support ticket | 7/7 | 5/5 | 0 | 3/2 | 0/18 |
| ST-006 Verify email after registration | 6/6 | 5/5 | 0 | 2/2 | 0/13 |
| ST-007 Update item quantity in the shopping cart | 7/7 | 4/4 | 0 | 2/3 | 0/18 |
| ST-008 Filter products by price range | 8/8 | 5/5 | 1 | 1/2 | 0/21 |
| ST-009 Enable two-factor authentication | 6/6 | 5/5 | 0 | 3/0 | 0/19 |
| ST-010 Request a return for a delivered order | 7/7 | 5/5 | 0 | 4/2 | 0/17 |

## LLM-as-judge

- Judge model: `claude-opus-5-5`; scored 52 of 71 cases (sampled round-robin per story); 52 replies parsed; reported cost 1.21 USD
- Overall mean: 4.01 / 5

| Dimension | Mean (1-5) |
|---|---|
| correctness | 4.29 |
| completeness | 3.38 |
| clarity | 3.92 |
| independence | 4.44 |

### Per story (mean)

| Story | correctness | completeness | clarity | independence |
|---|---|---|---|---|
| ST-001 | 4.83 | 3.67 | 4.5 | 4.83 |
| ST-002 | 4.17 | 3.5 | 4.17 | 4.33 |
| ST-003 | 4.2 | 3.8 | 3.6 | 4 |
| ST-004 | 4.4 | 3 | 4 | 4.4 |
| ST-005 | 4.2 | 3.6 | 4.2 | 4.6 |
| ST-006 | 4.6 | 3.6 | 4 | 4.2 |
| ST-007 | 4.8 | 3.2 | 4 | 4.8 |
| ST-008 | 4.2 | 3.6 | 3.4 | 4.2 |
| ST-009 | 4 | 3.2 | 3.8 | 4.2 |
| ST-010 | 3.4 | 2.6 | 3.4 | 4.8 |

### Position-bias check

8 cases were re-judged with the test case placed before the story. Delta = swapped score - original score.

| Dimension | Mean signed delta | Mean abs delta |
|---|---|---|
| correctness | -0.38 | 0.38 |
| completeness | 0.38 | 0.38 |
| clarity | 0 | 0.25 |
| independence | 0 | 0 |

Pairs where at least one score changed: 6/8
