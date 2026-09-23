from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class SpecError(ValueError):
    """Raised when a workflow specification is invalid."""


@dataclass(frozen=True)
class WorkflowSpec:
    source: Path
    data: dict[str, Any]

    @property
    def name(self) -> str:
        return str(self.data["name"])

    @property
    def description(self) -> str:
        return str(self.data["description"])

    @property
    def reference_paths(self) -> list[Path]:
        return [(self.source.parent / item).resolve() for item in self.data.get("references", [])]

    @property
    def scorer_path(self) -> Path | None:
        scorer = self.data.get("scorer")
        return (self.source.parent / scorer).resolve() if scorer else None


def is_output_case(case: dict[str, Any]) -> bool:
    """Positive cases are output-scored unless they only test trigger selection."""
    return bool(case.get("should_trigger")) and case.get("kind", "output") == "output"


def _require_text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SpecError(f"{key!r} must be a non-empty string")
    return value.strip()


def _require_text_list(data: dict[str, Any], key: str, *, minimum: int = 1) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list) or len(value) < minimum:
        raise SpecError(f"{key!r} must contain at least {minimum} item(s)")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise SpecError(f"every item in {key!r} must be non-empty text")
    return [item.strip() for item in value]


def load_spec(path: str | Path) -> WorkflowSpec:
    source = Path(path).resolve()
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SpecError(f"workflow file does not exist: {source}") from exc
    except json.JSONDecodeError as exc:
        raise SpecError(f"workflow JSON is invalid: {exc}") from exc

    if not isinstance(data, dict):
        raise SpecError("workflow root must be a JSON object")
    if data.get("schema_version") != "1.0":
        raise SpecError("schema_version must be '1.0'")

    name = _require_text(data, "name")
    if len(name) > 64 or not NAME_RE.fullmatch(name):
        raise SpecError("name must be <=64 characters of lowercase letters, digits, and hyphens")
    _require_text(data, "description")
    _require_text(data, "successful_run_summary")
    _require_text_list(data, "triggers")
    _require_text_list(data, "negative_triggers")
    _require_text_list(data, "guardrails")

    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        raise SpecError("steps must contain at least one workflow step")
    for index, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            raise SpecError(f"step {index} must be an object")
        _require_text(step, "title")
        _require_text(step, "instruction")

    output = data.get("output_contract")
    if not isinstance(output, dict):
        raise SpecError("output_contract must be an object")
    if output.get("format") not in {"json", "markdown", "text"}:
        raise SpecError("output_contract.format must be json, markdown, or text")
    required_fields = output.get("required_fields", [])
    if not isinstance(required_fields, list) or any(not isinstance(x, str) for x in required_fields):
        raise SpecError("output_contract.required_fields must be a list of strings")
    if "schema_hint" in output and not isinstance(output["schema_hint"], str):
        raise SpecError("output_contract.schema_hint must be text")

    references = data.get("references", [])
    if not isinstance(references, list) or any(not isinstance(item, str) or not item for item in references):
        raise SpecError("references must be a list of relative file paths")
    names = set()
    for item in references:
        path = (source.parent / item).resolve()
        try:
            path.relative_to(source.parent)
        except ValueError as exc:
            raise SpecError(f"reference must stay beneath the workflow directory: {item}") from exc
        if not path.is_file():
            raise SpecError(f"reference does not exist: {path}")
        if path.name in names:
            raise SpecError(f"reference file names must be unique: {path.name}")
        names.add(path.name)

    scorer = data.get("scorer")
    if scorer is not None:
        if not isinstance(scorer, str) or not scorer.endswith(".py"):
            raise SpecError("scorer must be a relative path to a .py file")
        scorer_path = (source.parent / scorer).resolve()
        try:
            scorer_path.relative_to(source.parent)
        except ValueError as exc:
            raise SpecError("scorer must stay beneath the workflow directory") from exc
        if not scorer_path.is_file():
            raise SpecError(f"scorer does not exist: {scorer_path}")

    evals = data.get("evals")
    if not isinstance(evals, list) or len(evals) < 2:
        raise SpecError("evals must include at least one positive and one negative case")
    positives = negatives = 0
    seen: set[str] = set()
    for case in evals:
        if not isinstance(case, dict):
            raise SpecError("each eval case must be an object")
        case_id = _require_text(case, "id")
        if case_id in seen:
            raise SpecError(f"duplicate eval id: {case_id}")
        seen.add(case_id)
        _require_text(case, "prompt")
        if not isinstance(case.get("should_trigger"), bool):
            raise SpecError(f"eval {case_id}: should_trigger must be boolean")
        if "input" in case and (not isinstance(case["input"], str) or not case["input"].strip()):
            raise SpecError(f"eval {case_id}: input must be non-empty text when provided")
        if case.get("kind", "output") not in {"output", "trigger"}:
            raise SpecError(f"eval {case_id}: kind must be 'output' or 'trigger'")
        if "ground_truth" in case:
            if not isinstance(case["ground_truth"], dict):
                raise SpecError(f"eval {case_id}: ground_truth must be an object")
            if scorer is None:
                raise SpecError(f"eval {case_id}: ground_truth requires a top-level scorer")
        positives += int(case["should_trigger"])
        negatives += int(not case["should_trigger"])
    if not positives or not negatives:
        raise SpecError("evals must include both positive and negative trigger cases")

    return WorkflowSpec(source=source, data=data)
