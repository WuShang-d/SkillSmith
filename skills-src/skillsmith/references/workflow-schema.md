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

Optional fields include `display_name` and `license`.

Never place credentials in the workflow JSON. Generated runners read endpoint configuration from `OPENAI_BASE_URL`, `OPENAI_MODEL`, and `OPENAI_API_KEY` at runtime.
