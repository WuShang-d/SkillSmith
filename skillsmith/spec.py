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
        positives += int(case["should_trigger"])
        negatives += int(not case["should_trigger"])
    if not positives or not negatives:
        raise SpecError("evals must include both positive and negative trigger cases")

    return WorkflowSpec(source=source, data=data)
