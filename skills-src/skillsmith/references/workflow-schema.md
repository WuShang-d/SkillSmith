# Workflow schema

Use UTF-8 JSON with `schema_version` set to `1.0`.

Required top-level fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `name` | string | Lowercase hyphenated skill name, at most 64 characters |
| `description` | string | Narrow capability statement |
| `successful_run_summary` | string | Evidence that the source workflow worked |
| `triggers` | string[] | Requests that should load the skill |
| `negative_triggers` | string[] | Nearby requests that must not load it |
| `steps` | object[] | Ordered objects with `title` and `instruction` |
| `guardrails` | string[] | Domain and safety constraints |
| `output_contract` | object | `format` plus optional `required_fields` |
| `evals` | object[] | Cases with `id`, `prompt`, and boolean `should_trigger` |

For positive evaluations, optional `expected_contains` and `forbidden_contains` arrays add deterministic output checks. Fixture files are named `<id>.baseline.txt` and `<id>.skill.txt`.

Optional fields that make the A/B evaluation meaningful:

| Field | Type | Meaning |
| --- | --- | --- |
| `output_contract.schema_hint` | string | Output shape given to **both** conditions, so the baseline is not penalised for not knowing field names |
| `scorer` | string | Relative path to a Python file defining `score(output, ground_truth) -> {metric: float in [0, 1]}`; copied into the skill as `evals/scorer.py` and security-scanned before it runs |
| `evals[].ground_truth` | object | Annotated answer for a positive case, passed to the scorer; requires `scorer` |
| `evals[].kind` | `"output"` or `"trigger"` | `trigger` cases only test skill selection and need no fixture or image; default `output` |

When ground truth exists, the release gate uses the task score (correctness against ground truth), not contract adherence. Add many `trigger` cases, including near-miss negatives, because `trigger-eval` samples each one several times through an agent router or a real OpenClaw agent.

For live DGX capture, every positive case also needs `input`, resolved beneath the explicitly selected input root. Relative paths cannot escape that root.

Optional fields include `display_name` and `license`.

Never place credentials in the workflow JSON. Generated runners read endpoint configuration from `OPENAI_BASE_URL`, `OPENAI_MODEL`, and `OPENAI_API_KEY` at runtime.
