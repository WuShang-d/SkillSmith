#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run this generated multimodal skill")
    parser.add_argument("--input", required=True, help="Absolute path to an image")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--model", help="Model name served by the local endpoint")
    parser.add_argument("--port", type=int, default=8000, help="Port of the OpenAI-compatible endpoint on 127.0.0.1")
    parser.add_argument("--mock-response", help="Offline JSON/text fixture used for deterministic tests")
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
        if not args.model:
            raise SystemExit("pass --model, or --mock-response for an offline run")
        if not 0 < args.port < 65536:
            raise SystemExit("--port must be a valid TCP port")
        # The destination is fixed to this machine; no flag or environment variable can redirect it.
        base_url = f"http://127.0.0.1:{args.port}/v1"
        model = args.model
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
            headers={"Content-Type": "application/json"},
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
