from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

from .spec import is_output_case


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
        cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()
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


def load_scorer(skill_root: Path) -> Callable[[dict[str, Any], dict[str, Any]], dict[str, float]] | None:
    path = skill_root / "evals/scorer.py"
    if not path.is_file():
        return None
    module_spec = importlib.util.spec_from_file_location(f"skillsmith_scorer_{skill_root.name}", path)
    if module_spec is None or module_spec.loader is None:
        raise ValueError(f"cannot load scorer: {path}")
    module = importlib.util.module_from_spec(module_spec)
    # Never leave compiled bytecode inside a skill that is about to be signed and shipped.
    previous, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        module_spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    if not callable(getattr(module, "score", None)):
        raise ValueError(f"scorer must define score(output, ground_truth): {path}")
    return module.score


def score_task(text: str, case: dict[str, Any], contract: dict[str, Any], scorer) -> dict[str, float]:
    try:
        parsed = _parse_output(text, contract["format"])
    except (json.JSONDecodeError, ValueError):
        parsed = None
    if not isinstance(parsed, dict):
        return {name: 0.0 for name in scorer({}, case["ground_truth"])}
    return {name: float(value) for name, value in scorer(parsed, case["ground_truth"]).items()}


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def efficiency_summary(fixtures: Path) -> dict[str, Any] | None:
    manifest_path = fixtures / "CAPTURE.json"
    if not manifest_path.is_file():
        return None
    captures = json.loads(manifest_path.read_text(encoding="utf-8")).get("captures", [])
    summary: dict[str, Any] = {}
    for mode in sorted({row.get("mode") for row in captures}):
        rows = [row for row in captures if row.get("mode") == mode]
        tokens = [row["completion_tokens"] for row in rows if isinstance(row.get("completion_tokens"), int)]
        summary[mode] = {
            "mean_latency_seconds": round(_mean([row["elapsed_seconds"] for row in rows]), 3),
            "mean_completion_tokens": round(_mean(tokens), 1) if tokens else None,
        }
    return summary


def evaluate_fixtures(
    skill_dir: str | Path,
    fixture_dir: str | Path,
    *,
    trigger_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    skill_root = Path(skill_dir).resolve()
    fixtures = Path(fixture_dir).resolve()
    evals = json.loads((skill_root / "evals/evals.json").read_text(encoding="utf-8"))["cases"]
    workflow = json.loads((skill_root / "references/workflow.json").read_text(encoding="utf-8"))
    contract = workflow["output_contract"]
    scorer = load_scorer(skill_root)
    lexical_hits = []
    rows = []
    output_cases = [case for case in evals if is_output_case(case)]
    # "reference" = same data pasted into a generic prompt; present when the skill ships reference files.
    modes = ["baseline", "skill"]
    if output_cases and all((fixtures / f"{case['id']}.reference.txt").is_file() for case in output_cases):
        modes.append("reference")
    contract_scores: dict[str, list[float]] = {mode: [] for mode in modes}
    task_scores: dict[str, list[float]] = {mode: [] for mode in modes}
    metric_scores: dict[str, dict[str, list[float]]] = {}
    for case in evals:
        predicted = predicts_trigger(case["prompt"], workflow["triggers"], workflow["negative_triggers"])
        lexical_hits.append(predicted == case["should_trigger"])
        if not is_output_case(case):
            continue
        row: dict[str, Any] = {"id": case["id"]}
        for mode in modes:
            text = (fixtures / f"{case['id']}.{mode}.txt").read_text(encoding="utf-8")
            value, notes = score_output(text, case, contract)
            contract_scores[mode].append(value)
            row[f"{mode}_contract"] = round(value, 3)
            row[f"{mode}_notes"] = notes
            if scorer and "ground_truth" in case:
                metrics = score_task(text, case, contract, scorer)
                task_scores[mode].append(_mean(list(metrics.values())))
                row[f"{mode}_task"] = round(_mean(list(metrics.values())), 3)
                row[f"{mode}_metrics"] = {name: round(v, 3) for name, v in metrics.items()}
                for name, v in metrics.items():
                    metric_scores.setdefault(name, {m: [] for m in modes})[mode].append(v)
        rows.append(row)

    contract_summary = {mode: round(_mean(values), 3) for mode, values in contract_scores.items()}
    has_task = bool(task_scores["skill"])
    task_summary = {mode: round(_mean(values), 3) for mode, values in task_scores.items()} if has_task else None
    primary = task_summary or contract_summary

    if trigger_result is not None:
        trigger = {
            "method": trigger_result["method"],
            "accuracy": trigger_result["accuracy"],
            "runs": trigger_result["runs"],
            "false_positive_rate": trigger_result["false_positive_rate"],
            "false_negative_rate": trigger_result["false_negative_rate"],
        }
    else:
        trigger = {"method": "lexical-estimate", "accuracy": round(_mean([float(x) for x in lexical_hits]), 3)}

    passed = (
        trigger["accuracy"] >= 0.8
        and primary["skill"] > primary["baseline"]
        and contract_summary["skill"] >= contract_summary["baseline"]
        and ("reference" not in primary or primary["skill"] >= primary["reference"])
    )
    return {
        "verdict": "pass" if passed else "fail",
        "primary_metric": "task" if has_task else "contract",
        "trigger_accuracy": trigger["accuracy"],
        "trigger": trigger,
        "baseline_score": primary["baseline"],
        "skill_score": primary["skill"],
        "improvement": round(primary["skill"] - primary["baseline"], 3),
        "improvement_over_reference": round(primary["skill"] - primary["reference"], 3) if "reference" in primary else None,
        "contract": contract_summary,
        "task": task_summary,
        "task_metrics": {
            name: {mode: round(_mean(values), 3) for mode, values in by_mode.items()}
            for name, by_mode in metric_scores.items()
        },
        "efficiency": efficiency_summary(fixtures),
        "cases": rows,
    }


def benchmark_markdown(result: dict[str, Any], skill_name: str, *, mode: str = "fixture") -> str:
    evidence_note = (
        "Live mode: raw outputs were captured from one configured model endpoint; see the adjacent CAPTURE.json for model, latency, and token evidence."
        if mode == "live"
        else "Fixture mode is deterministic and validates the evaluation pipeline only. Replace fixtures with DGX endpoint runs before final judging."
    )
    has_reference = "reference" in result["contract"]
    columns = ["baseline", "reference", "skill"] if has_reference else ["baseline", "skill"]

    def pct(value: float) -> str:
        return f"{value:.1%}"

    def row(dimension: str, metric: str, values: dict[str, float] | None, fmt=pct, delta=lambda d: f"{d:+.1%}") -> str:
        if values is None:
            cells = ["-"] * (len(columns) - 1)
            return f"| {dimension} | {metric} | " + " | ".join(cells) + " | - |"
        cells = [fmt(values[c]) for c in columns]
        return f"| {dimension} | {metric} | " + " | ".join(cells) + f" | {delta(values['skill'] - values['baseline'])} |"

    header = ["Baseline", "Pasted data", "With skill"] if has_reference else ["Baseline", "With skill"]
    rows = [
        f"# {skill_name} benchmark",
        "",
        "All conditions receive the same user request, image, and output format. The with-skill condition adds the",
        "skill's workflow and guardrails, so any delta below comes from the skill, not from knowing field names.",
    ]
    if has_reference:
        rows.append("*Pasted data* is the same reference data given to a generic prompt without the skill's procedure.")
    rows += [
        "",
        "| Dimension | Metric | " + " | ".join(header) + " | Delta vs baseline |",
        "| --- | --- | " + " | ".join("---:" for _ in header) + " | ---: |",
        row("Contract", "JSON + required fields", result["contract"]),
    ]
    if result["task"]:
        rows.append(row("Correctness", "Task score vs ground truth", result["task"]))
        for name, values in result["task_metrics"].items():
            rows.append(row("Correctness", name, values))
    trigger = result["trigger"]
    blank = " | ".join("-" for _ in columns[:-1])
    if trigger["method"] == "lexical-estimate":
        rows.append(f"| Discoverability | Trigger accuracy (offline lexical estimate, not an agent run) | {blank} | {pct(trigger['accuracy'])} | - |")
    else:
        rows.append(f"| Discoverability | Trigger accuracy ({trigger['method']}, {trigger['runs']} runs) | {blank} | {pct(trigger['accuracy'])} | - |")
        rows.append(f"| Discoverability | False-trigger rate on negatives | {blank} | {pct(trigger['false_positive_rate'])} | - |")
        rows.append(f"| Discoverability | Missed-trigger rate on positives | {blank} | {pct(trigger['false_negative_rate'])} | - |")
    efficiency = result.get("efficiency")
    if efficiency and all(c in efficiency for c in columns):
        latency = {c: efficiency[c]["mean_latency_seconds"] for c in columns}
        rows.append(row("Efficiency", "Mean latency (s)", latency, fmt=lambda v: f"{v:.1f}", delta=lambda d: f"{d:+.1f}"))
        if all(efficiency[c]["mean_completion_tokens"] is not None for c in columns):
            tokens = {c: efficiency[c]["mean_completion_tokens"] for c in columns}
            rows.append(row("Efficiency", "Mean completion tokens", tokens, fmt=lambda v: f"{v:.0f}", delta=lambda d: f"{d:+.0f}"))
    rows += [
        "",
        f"Primary metric: **{result['primary_metric']}**. Verdict: **{result['verdict'].upper()}**",
        "",
        evidence_note,
        "",
    ]
    return "\n".join(rows)
