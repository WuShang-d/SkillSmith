"""Generate skill-card.md, the human trust record that ships with a released skill.

Section order follows NVIDIA's skill card guidance (Description, Owner,
License/Terms of Use, Use Case, Deployment Geography for Use, Requirements /
Dependencies, Known Risks and Mitigations, References, Skill Output, Skill
Version, Ethical Considerations). A Release Evidence section records what the
gate measured, so a reviewer can accept the skill without reading its source.
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any

from . import __version__

DEFAULT_GEOGRAPHY = (
    "Global, on-premises only. The runner only talks to a loopback OpenAI-compatible endpoint on the "
    "local NVIDIA DGX Spark; inputs never leave the machine."
)


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- None"


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def _evidence(evaluation: dict[str, Any], security: dict[str, Any], capture: dict[str, Any] | None) -> str:
    lines = []
    engines = ", ".join(security.get("engines", ["skillsmith-rules"]))
    rule_findings = sum(security["counts"].values())
    lines.append(f"- Security gate ({engines}): **{security['verdict'].upper()}**; SkillSmith rules: {rule_findings} finding(s)")
    spector = security.get("skillspector")
    if spector:
        lines.append(
            f"- SkillSpector {spector.get('version') or ''}: recommendation **{spector.get('recommendation')}**, "
            f"risk score {spector.get('score')}, {len(spector.get('issues', []))} issue(s), LLM analysis "
            f"{'on' if spector.get('llm_used') else 'off'}"
        )
    if capture:
        lines.append(f"- Evaluated with model `{capture.get('model')}` on endpoint `{capture.get('endpoint')}`")
    score = evaluation.get("task") or evaluation.get("contract")
    label = "Task score vs ground truth" if evaluation.get("task") else "Contract score"
    parts = [f"baseline {_pct(score.get('baseline'))}"]
    if "reference" in score:
        parts.append(f"pasted reference data {_pct(score['reference'])}")
    parts.append(f"with skill {_pct(score.get('skill'))}")
    lines.append(f"- {label}: " + ", ".join(parts))
    for name, values in (evaluation.get("task_metrics") or {}).items():
        lines.append(f"  - {name}: " + ", ".join(f"{mode} {_pct(v)}" for mode, v in values.items()))
    trigger = evaluation["trigger"]
    if trigger["method"] == "lexical-estimate":
        lines.append(f"- Triggering: offline lexical estimate {_pct(trigger['accuracy'])} (not an agent run)")
    else:
        lines.append(
            f"- Triggering ({trigger['method']}, {trigger['runs']} runs): accuracy {_pct(trigger['accuracy'])}, "
            f"missed {_pct(trigger['false_negative_rate'])}, false triggers {_pct(trigger['false_positive_rate'])}"
        )
    efficiency = evaluation.get("efficiency")
    if efficiency and "skill" in efficiency:
        lines.append(
            f"- Efficiency with skill: {efficiency['skill']['mean_latency_seconds']:.1f} s mean latency, "
            f"{efficiency['skill']['mean_completion_tokens']} mean completion tokens"
        )
    lines.append(f"- Gate verdict: **{evaluation['verdict'].upper()}** (full table in BENCHMARK.md)")
    return "\n".join(lines)


def render_skill_card(
    skill_dir: str | Path,
    *,
    evaluation: dict[str, Any],
    security: dict[str, Any],
    capture: dict[str, Any] | None = None,
    signer: str | None = None,
    today: _dt.date | None = None,
) -> str:
    root = Path(skill_dir).resolve()
    workflow = json.loads((root / "references/workflow.json").read_text(encoding="utf-8"))
    name = root.name
    contract = workflow["output_contract"]
    references = [f"references/{item}" for item in workflow.get("references", [])]
    release_date = (today or _dt.date.today()).isoformat()
    risks = [
        ("Model misreads the input (miscounts, misidentifies items).",
         "Outputs are scored against ground truth before release (see Release Evidence); uncertain observations must be listed in `uncertainties` for human review."),
        ("Inputs leave the device.",
         "The runner's destination is fixed to 127.0.0.1; it reads no environment variables and handles no credentials."),
        ("Skill files are modified after review.",
         f"The directory is signed as `skill.oms.sig`; verify it before installation with `model_signing verify certificate {name} --signature {name}/skill.oms.sig --certificate_chain <root-cert.pem>`."),
        ("Skill loads for requests it should not handle.",
         "Negative trigger boundaries are in the description and were evaluated with repeated agent runs."),
    ] + [("Workflow guardrail", guardrail) for guardrail in workflow["guardrails"]]
    signature_line = (
        f"Signed by `{signer}` as `skill.oms.sig` (OpenSSF model signing, certificate chain)."
        if signer
        else "Not signed yet."
    )
    return f"""# Skill Card: {workflow.get('display_name', name)} (`{name}`)

## Description

{workflow['description']}

Proven workflow: {workflow['successful_run_summary']}

## Owner

{workflow.get('owner', 'Not specified — set `owner` in the workflow before release.')}

## License/Terms of Use

{workflow.get('license', 'Apache-2.0')}

## Use Case

Use when:
{_bullets(workflow['triggers'])}

Not for:
{_bullets(workflow['negative_triggers'])}

## Deployment Geography for Use

{workflow.get('deployment_geography', DEFAULT_GEOGRAPHY)}

## Requirements / Dependencies

- Requires API Key or External Credential: No
- Credential Type(s): None
- Runtime: Python 3.10+ standard library; an OpenAI-compatible multimodal endpoint on `127.0.0.1` (`--port`, `--model`)
- Agent tools: `Read`, `Bash(python3 scripts/run.py:*)` (declared as `allowed-tools`)
- Declared capabilities: network to the loopback model only, read of the input image and bundled references, write to the user-selected output directory
- Bundled reference data: {', '.join(f'`{item}`' for item in references) or 'None'}

## Known Risks and Mitigations

{chr(10).join(f"- Risk: {risk}{chr(10)}  Mitigation: {mitigation}" for risk, mitigation in risks)}

## References

- `SKILL.md`, `references/workflow.json`{''.join(f', `{item}`' for item in references)}
- `evals/evals.json` (positive and negative cases){', `evals/scorer.py`' if (root / 'evals/scorer.py').is_file() else ''}
- `BENCHMARK.md`, `SECURITY_REPORT.json`

## Skill Output

- Output type(s): structured report written to the user-selected output directory
- Output format: {contract['format']}
- Output parameters: {', '.join(f'`{field}`' for field in contract.get('required_fields', [])) or 'none fixed'}
- Other properties: {('shape `' + contract['schema_hint'] + '`') if contract.get('schema_hint') else 'none'}

## Skill Version

{workflow.get('version', '0.1.0')}, released {release_date}, generated by SkillSmith {__version__}. {signature_line}

## Ethical Considerations

The skill reports only what is visible in the input and must not identify people or infer personal attributes. Automated findings are decision support; a responsible person reviews them before acting.

## Release Evidence

{_evidence(evaluation, security, capture)}
"""


def write_skill_card(skill_dir: str | Path, **kwargs: Any) -> Path:
    path = Path(skill_dir).resolve() / "skill-card.md"
    path.write_text(render_skill_card(skill_dir, **kwargs), encoding="utf-8")
    return path
