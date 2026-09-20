from __future__ import annotations

import json
import shutil
from pathlib import Path

from .spec import WorkflowSpec


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def render_skill_md(spec: WorkflowSpec) -> str:
    d = spec.data
    triggers = "; ".join(d["triggers"])
    negatives = "; ".join(d["negative_triggers"])
    description = f"{d['description']} Use when: {triggers}. Do not use for: {negatives}."
    steps = "\n".join(
        f"{index}. **{step['title']}** — {step['instruction']}"
        for index, step in enumerate(d["steps"], 1)
    )
    fields = d["output_contract"].get("required_fields", [])
    field_text = ", ".join(f"`{field}`" for field in fields) if fields else "No fixed fields."
    return f"""---
name: {spec.name}
description: {json.dumps(description, ensure_ascii=False)}
license: {d.get('license', 'Apache-2.0')}
---

# {d.get('display_name', spec.name)}

Reproduce the validated workflow summarized in [references/workflow.json](references/workflow.json).

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
- Write generated artifacts only beneath the user-selected output directory.
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

    workflow = json.loads((Path(__file__).parents[1] / "references/workflow.json").read_text())
    prompt = "\n".join(step["instruction"] for step in workflow["steps"])
    prompt += "\nReturn only " + workflow["output_contract"]["format"] + "."

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
            "chat_template_kwargs": {"enable_thinking": False},
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}},
            ]}],
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
    (target / "references/workflow.json").write_text(
        json.dumps(workflow, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (target / "evals/evals.json").write_text(
        json.dumps({"version": "1.0", "cases": evals}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target
