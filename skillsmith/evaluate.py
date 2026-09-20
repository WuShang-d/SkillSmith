from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


TOKEN_RE = re.compile(r"[a-z0-9\u4e00-\u9fff]+", re.IGNORECASE)


def _tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for raw in TOKEN_RE.findall(text):
        token = raw.lower()
        if len(token) > 1:
            tokens.add(token)
        cjk = "".join(char for char in token if "\u4e00" <= char <= "\u9fff")
        tokens.update(cjk[index : index + 2] for index in range(max(0, len(cjk) - 1)))
    return tokens


def _similarity(left: str, right: str) -> float:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))


def predicts_trigger(prompt: str, triggers: list[str], negative_triggers: list[str]) -> bool:
    positive = max((_similarity(prompt, phrase) for phrase in triggers), default=0.0)
    negative = max((_similarity(prompt, phrase) for phrase in negative_triggers), default=0.0)
    return positive >= 0.15 and positive > negative


def _parse_output(text: str, output_format: str) -> Any:
    if output_format == "json":
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
        return json.loads(cleaned)
    return text.strip()


def score_output(text: str, case: dict[str, Any], contract: dict[str, Any]) -> tuple[float, list[str]]:
    checks: list[bool] = []
    notes: list[str] = []
    try:
        parsed = _parse_output(text, contract["format"])
        checks.append(True)
    except (json.JSONDecodeError, ValueError):
        parsed = None
        checks.append(False)
        notes.append("invalid output format")

    if contract["format"] == "json":
        for field in contract.get("required_fields", []):
            ok = isinstance(parsed, dict) and field in parsed
            checks.append(ok)
            if not ok:
                notes.append(f"missing field: {field}")

    lowered = text.lower()
    for phrase in case.get("expected_contains", []):
        ok = phrase.lower() in lowered
        checks.append(ok)
        if not ok:
            notes.append(f"missing expected phrase: {phrase}")
    for phrase in case.get("forbidden_contains", []):
        ok = phrase.lower() not in lowered
        checks.append(ok)
        if not ok:
            notes.append(f"contains forbidden phrase: {phrase}")
    return (sum(checks) / len(checks) if checks else 1.0), notes


def evaluate_fixtures(skill_dir: str | Path, fixture_dir: str | Path) -> dict[str, Any]:
    skill_root = Path(skill_dir).resolve()
    fixtures = Path(fixture_dir).resolve()
    evals = json.loads((skill_root / "evals/evals.json").read_text(encoding="utf-8"))["cases"]
    workflow = json.loads((skill_root / "references/workflow.json").read_text(encoding="utf-8"))
    trigger_hits = []
    positive_rows = []
    baseline_scores: list[float] = []
    skill_scores: list[float] = []
    for case in evals:
        predicted = predicts_trigger(case["prompt"], workflow["triggers"], workflow["negative_triggers"])
        trigger_hits.append(predicted == case["should_trigger"])
        row: dict[str, Any] = {
            "id": case["id"],
            "should_trigger": case["should_trigger"],
            "predicted_trigger": predicted,
        }
        if case["should_trigger"]:
            baseline_text = (fixtures / f"{case['id']}.baseline.txt").read_text(encoding="utf-8")
            skill_text = (fixtures / f"{case['id']}.skill.txt").read_text(encoding="utf-8")
            baseline, baseline_notes = score_output(baseline_text, case, workflow["output_contract"])
            with_skill, skill_notes = score_output(skill_text, case, workflow["output_contract"])
            baseline_scores.append(baseline)
            skill_scores.append(with_skill)
            row.update({
                "baseline_score": round(baseline, 3),
                "skill_score": round(with_skill, 3),
                "delta": round(with_skill - baseline, 3),
                "baseline_notes": baseline_notes,
                "skill_notes": skill_notes,
            })
        positive_rows.append(row)

    baseline = sum(baseline_scores) / len(baseline_scores) if baseline_scores else 0.0
    with_skill = sum(skill_scores) / len(skill_scores) if skill_scores else 0.0
    trigger_accuracy = sum(trigger_hits) / len(trigger_hits) if trigger_hits else 0.0
    return {
        "verdict": "pass" if trigger_accuracy >= 0.8 and with_skill > baseline else "fail",
        "trigger_accuracy": round(trigger_accuracy, 3),
        "baseline_score": round(baseline, 3),
        "skill_score": round(with_skill, 3),
        "improvement": round(with_skill - baseline, 3),
        "cases": positive_rows,
    }


def benchmark_markdown(result: dict[str, Any], skill_name: str) -> str:
    rows = [
        f"# {skill_name} benchmark",
        "",
        "| Metric | Baseline | With skill | Delta |",
        "| --- | ---: | ---: | ---: |",
        f"| Contract score | {result['baseline_score']:.1%} | {result['skill_score']:.1%} | {result['improvement']:+.1%} |",
        f"| Trigger accuracy | - | {result['trigger_accuracy']:.1%} | - |",
        "",
        f"Verdict: **{result['verdict'].upper()}**",
        "",
        "Fixture mode is deterministic and validates the evaluation pipeline. Replace fixtures with DGX endpoint runs before final judging.",
        "",
    ]
    return "\n".join(rows)
