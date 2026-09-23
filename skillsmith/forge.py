from __future__ import annotations

import json
import shutil
from pathlib import Path

from .spec import WorkflowSpec


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def contract_instructions(contract: dict) -> list[str]:
    """Output-format instructions shared by the baseline and the with-skill condition."""
    lines = [f"Return only valid {contract['format']}."]
    fields = contract.get("required_fields", [])
    if fields:
        lines.append("Use these exact top-level field names: " + ", ".join(fields) + ".")
        lines.append("Include every required field even when its value is empty or uncertain.")
    if contract.get("schema_hint"):
        lines.append("Shape: " + contract["schema_hint"])
    return lines


def reference_block(skill_root: Path, names: list[str]) -> str:
    """Reference files as an agent would see them after reading them."""
    return "\n\n".join(
        f"references/{name}:\n" + (skill_root / "references" / name).read_text(encoding="utf-8")
        for name in names
    )


def render_skill_md(spec: WorkflowSpec) -> str:
    d = spec.data
    reference_names = [path.name for path in spec.reference_paths]
    reference_section = (
        "\n## Reference data\n\nRead these before judging the input; they are the only source of codes, targets and policy data.\n\n"
        + "\n".join(f"- [references/{name}](references/{name})" for name in reference_names)
        + "\n"
        if reference_names
        else ""
    )
    triggers = "; ".join(d["triggers"])
    negatives = "; ".join(d["negative_triggers"])
    description = f"{d['description']} Use when: {triggers}. Do not use for: {negatives}."
    steps = "\n".join(
        f"{index}. **{step['title']}** — {step['instruction']}"
        for index, step in enumerate(d["steps"], 1)
    )
    fields = d["output_contract"].get("required_fields", [])
    field_text = ", ".join(f"`{field}`" for field in fields) if fields else "No fixed fields."
    hint = d["output_contract"].get("schema_hint")
    shape = f"- Shape: `{hint}`\n" if hint else ""
    return f"""---
name: {spec.name}
description: {json.dumps(description, ensure_ascii=False)}
license: {d.get('license', 'Apache-2.0')}
---

# {d.get('display_name', spec.name)}

Reproduce the validated workflow summarized in [references/workflow.json](references/workflow.json).
{reference_section}
## Trigger boundary

Use this skill when:
{_bullets(d['triggers'])}

Do not use this skill when:
{_bullets(d['negative_triggers'])}

If required input is missing, ask for it instead of guessing.

## Workflow

{steps}

## Output contract

- Format: `{d['output_contract']['format']}`
- Required fields: {field_text}
{shape}- Write generated artifacts only beneath the user-selected output directory.
- Separate visible evidence from inference and report uncertainty explicitly.

## Guardrails

{_bullets(d['guardrails'])}

## Execution

For a local OpenAI-compatible multimodal endpoint, run:

```bash
python3 scripts/run.py --input /absolute/path/to/input --output-dir /absolute/path/to/output
```

The runner reads `OPENAI_BASE_URL`, `OPENAI_MODEL`, and optionally `OPENAI_API_KEY`. Never print credentials.
"""


RUNNER = r'''#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run this generated multimodal skill")
    parser.add_argument("--input", required=True, help="Absolute path to an image")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--mock-response", help="Offline JSON/text fixture used for deterministic tests")
    parser.add_argument("--allow-remote-endpoint", action="store_true")
    args = parser.parse_args()

    source = Path(args.input).resolve()
    output_dir = Path(args.output_dir).resolve()
    if not source.is_file():
        raise SystemExit(f"input does not exist: {source}")
    output_dir.mkdir(parents=True, exist_ok=True)

    skill_root = Path(__file__).parents[1]
    workflow = json.loads((skill_root / "references/workflow.json").read_text())
    required_fields = workflow["output_contract"].get("required_fields", [])
    references = [
        f"references/{name}:\n" + (skill_root / "references" / name).read_text(encoding="utf-8")
        for name in workflow.get("references", [])
    ]
    system = "\n".join([
        "Execute the installed Agent Skill exactly as specified.",
        "Workflow:",
        *[f"{index}. {step['instruction']}" for index, step in enumerate(workflow["steps"], 1)],
        "Guardrails:",
        *[f"- {guardrail}" for guardrail in workflow["guardrails"]],
        "Output contract:",
        f"- Return only valid {workflow['output_contract']['format']}.",
        "- Use these exact top-level field names: " + ", ".join(required_fields) + ".",
        "- Include every required field even when its value is empty or uncertain.",
        *(["- Shape: " + workflow["output_contract"]["schema_hint"]] if workflow["output_contract"].get("schema_hint") else []),
        *(["Reference data:", *references] if references else []),
    ])
    prompt = "Apply the installed skill to this input image. Do not rename contract fields."

    if args.mock_response:
        content = Path(args.mock_response).read_text(encoding="utf-8")
    else:
        base_url = os.environ.get("OPENAI_BASE_URL", "").rstrip("/")
        model = os.environ.get("OPENAI_MODEL", "")
        if not base_url or not model:
            raise SystemExit("set OPENAI_BASE_URL and OPENAI_MODEL, or pass --mock-response")
        parsed = urllib.parse.urlparse(base_url)
        if parsed.hostname not in {"127.0.0.1", "localhost", "::1"} and not args.allow_remote_endpoint:
            raise SystemExit("refusing to transmit input to a non-local endpoint; explicit --allow-remote-endpoint is required")
        mime = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        encoded = base64.b64encode(source.read_bytes()).decode("ascii")
        payload = {
            "model": model,
            "temperature": 0,
            "max_tokens": 2048,
            "chat_template_kwargs": {"enable_thinking": False},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}},
                ]},
            ],
        }
        request = urllib.request.Request(
            base_url + "/chat/completions",
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + os.environ.get("OPENAI_API_KEY", "local"),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                body = json.load(response)
        except urllib.error.URLError as exc:
            raise SystemExit(f"model request failed: {exc}") from exc
        content = body["choices"][0]["message"]["content"]

    if workflow["output_contract"]["format"] == "json":
        cleaned = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL | re.IGNORECASE).strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
        try:
            parsed_content = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"model response violates JSON output contract: {exc}") from exc
        if not isinstance(parsed_content, dict):
            raise SystemExit("model response violates output contract: expected a JSON object")
        missing = [field for field in required_fields if field not in parsed_content]
        if missing:
            raise SystemExit("model response violates output contract; missing fields: " + ", ".join(missing))
        content = json.dumps(parsed_content, indent=2, ensure_ascii=False)

    suffix = ".json" if workflow["output_contract"]["format"] == "json" else ".txt"
    result_path = output_dir / ("result" + suffix)
    result_path.write_text(content.strip() + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "result": str(result_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def forge(spec: WorkflowSpec, output_root: str | Path, *, force: bool = False) -> Path:
    root = Path(output_root).resolve()
    target = root / spec.name
    if target.exists():
        if not force:
            raise FileExistsError(f"target already exists: {target}; pass --force to replace it")
        shutil.rmtree(target)
    (target / "scripts").mkdir(parents=True)
    (target / "references").mkdir()
    (target / "evals").mkdir()

    (target / "SKILL.md").write_text(render_skill_md(spec), encoding="utf-8")
    (target / "scripts/run.py").write_text(RUNNER, encoding="utf-8")
    (target / "scripts/run.py").chmod(0o755)
    workflow = dict(spec.data)
    evals = workflow.pop("evals")
    workflow.pop("scorer", None)
    workflow["references"] = [path.name for path in spec.reference_paths]
    for path in spec.reference_paths:
        shutil.copyfile(path, target / "references" / path.name)
    if spec.scorer_path:
        shutil.copyfile(spec.scorer_path, target / "evals/scorer.py")
    (target / "references/workflow.json").write_text(
        json.dumps(workflow, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (target / "evals/evals.json").write_text(
        json.dumps({"version": "1.0", "cases": evals}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target
