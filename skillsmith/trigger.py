"""Trigger evaluation through an agent-style skill router.

Agent harnesses such as Claude Code and OpenClaw load skills by progressive
disclosure: the model only sees each skill's name, description and location,
and decides on its own whether to read the full SKILL.md. This module
reproduces that decision with the real model: the skill under test sits in a
catalogue next to neighbouring skills, the model gets a ``read_file`` tool, and
a trigger is counted only when the model reads this skill's SKILL.md. Every
prompt is sampled several times so the result reports stability, not a single
lucky draw.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from .endpoint import post_chat, validate_endpoint

DISTRACTORS = Path(__file__).with_name("data") / "distractor_skills.json"
SKILLS_ROOT = "/workspace/skills"

ROUTER_SYSTEM = """You are a local agent running on an NVIDIA DGX Spark workstation.
Skills are instruction packages for specialised tasks. Only their names and descriptions are loaded below.
When a user request matches a skill's description, call read_file on that skill's SKILL.md location before doing anything else.
When no skill matches, answer the user directly without reading any skill.

<available_skills>
{skills}
</available_skills>"""

READ_TOOL = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Read a text file, such as a skill's SKILL.md.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Absolute file path"}},
            "required": ["path"],
        },
    },
}


def skill_frontmatter(skill_dir: Path) -> dict[str, str]:
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---", text, flags=re.DOTALL)
    if not match:
        raise ValueError("SKILL.md has no frontmatter")
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        value = value.strip()
        if value.startswith('"'):
            value = json.loads(value)
        fields[key.strip()] = value
    return fields


def catalogue(skill_dir: Path, distractors: list[dict[str, str]]) -> list[dict[str, str]]:
    own = skill_frontmatter(skill_dir)
    entries = [{"name": own["name"], "description": own["description"]}, *distractors]
    # Sort by name so the skill under test has no positional advantage.
    return sorted(
        ({**entry, "location": f"{SKILLS_ROOT}/{entry['name']}/SKILL.md"} for entry in entries),
        key=lambda entry: entry["name"],
    )


def render_catalogue(entries: list[dict[str, str]]) -> str:
    return "\n".join(
        "<skill>\n"
        f"  <name>{escape(entry['name'])}</name>\n"
        f"  <description>{escape(entry['description'])}</description>\n"
        f"  <location>{escape(entry['location'])}</location>\n"
        "</skill>"
        for entry in entries
    )


def _read_paths(message: dict[str, Any]) -> list[str]:
    paths = []
    for call in message.get("tool_calls") or []:
        function = call.get("function", {})
        if function.get("name") != "read_file":
            continue
        try:
            arguments = json.loads(function.get("arguments") or "{}")
        except json.JSONDecodeError:
            arguments = {}
        paths.append(str(arguments.get("path", "")))
    return paths


def selected_skill(paths: list[str]) -> str | None:
    for path in paths:
        match = re.search(rf"{re.escape(SKILLS_ROOT)}/([^/]+)/SKILL\.md", path)
        if match:
            return match.group(1)
    return None


def user_message(case: dict[str, Any]) -> str:
    """Output cases carry their image as an attachment, as they would in a real agent session."""
    if case.get("input"):
        return f"[附件: inbox/{Path(case['input']).name}] {case['prompt']}"
    return case["prompt"]


def evaluate_triggers(
    skill_dir: str | Path,
    output_dir: str | Path,
    *,
    base_url: str,
    model: str,
    api_key: str = "local",
    repeats: int = 3,
    temperature: float = 0.7,
    allow_remote: bool = False,
    timeout: float = 120,
) -> dict[str, Any]:
    root = Path(skill_dir).resolve()
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    endpoint = validate_endpoint(base_url, allow_remote=allow_remote)
    if not model:
        raise ValueError("model must be provided with --model or OPENAI_MODEL")
    if repeats < 1:
        raise ValueError("repeats must be at least 1")

    name = skill_frontmatter(root)["name"]
    distractors = json.loads(DISTRACTORS.read_text(encoding="utf-8"))["skills"]
    distractors = [entry for entry in distractors if entry["name"] != name]
    entries = catalogue(root, distractors)
    system = ROUTER_SYSTEM.format(skills=render_catalogue(entries))
    cases = json.loads((root / "evals/evals.json").read_text(encoding="utf-8"))["cases"]

    runs: list[dict[str, Any]] = []
    for case in cases:
        for attempt in range(1, repeats + 1):
            payload = {
                "model": model,
                "temperature": temperature,
                "top_p": 0.8,
                "max_tokens": 512,
                "chat_template_kwargs": {"enable_thinking": False},
                "tools": [READ_TOOL],
                "tool_choice": "auto",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_message(case)},
                ],
            }
            body, elapsed = post_chat(endpoint, api_key, payload, timeout)
            try:
                message = body["choices"][0]["message"]
            except (KeyError, IndexError, TypeError) as exc:
                raise RuntimeError("model endpoint returned an incompatible response") from exc
            paths = _read_paths(message)
            chosen = selected_skill(paths)
            triggered = chosen == name
            runs.append({
                "case_id": case["id"],
                "attempt": attempt,
                "should_trigger": case["should_trigger"],
                "triggered": triggered,
                "selected_skill": chosen,
                "read_paths": paths,
                "reply_preview": (message.get("content") or "")[:200],
                "elapsed_seconds": round(elapsed, 3),
            })

    positives = [run for run in runs if run["should_trigger"]]
    negatives = [run for run in runs if not run["should_trigger"]]
    result = {
        "method": "agent-router",
        "endpoint": endpoint,
        "model": model,
        "repeats": repeats,
        "temperature": temperature,
        "catalogue": [entry["name"] for entry in entries],
        "runs": len(runs),
        "accuracy": round(sum(run["triggered"] == run["should_trigger"] for run in runs) / len(runs), 3),
        "false_negative_rate": round(sum(not run["triggered"] for run in positives) / len(positives), 3) if positives else 0.0,
        "false_positive_rate": round(sum(run["triggered"] for run in negatives) / len(negatives), 3) if negatives else 0.0,
        "per_case": {
            case["id"]: {
                "should_trigger": case["should_trigger"],
                "triggered": sum(run["triggered"] for run in runs if run["case_id"] == case["id"]),
                "runs": repeats,
                "selected": sorted({str(run["selected_skill"]) for run in runs if run["case_id"] == case["id"]}),
            }
            for case in cases
        },
        "details": runs,
    }
    (output / "TRIGGER.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result
