from __future__ import annotations

import base64
import json
import mimetypes
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .forge import contract_instructions, reference_block
from .spec import is_output_case


LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


@dataclass(frozen=True)
class Capture:
    case_id: str
    mode: str
    elapsed_seconds: float
    output_path: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


def validate_endpoint(base_url: str, *, allow_remote: bool = False) -> str:
    parsed = urllib.parse.urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("base URL must be an absolute http(s) URL")
    if parsed.username or parsed.password:
        raise ValueError("credentials must not be embedded in the base URL")
    if parsed.hostname not in LOCAL_HOSTS and not allow_remote:
        raise ValueError(
            "refusing to transmit images to a non-local endpoint; pass --allow-remote-endpoint only with explicit authorization"
        )
    return base_url.rstrip("/")


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        if parts:
            return "\n".join(parts)
    raise ValueError("model response does not contain text content")


def post_chat(base_url: str, api_key: str, payload: dict[str, Any], timeout: float) -> tuple[dict[str, Any], float]:
    request = urllib.request.Request(
        base_url + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + api_key},
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read(2048).decode("utf-8", errors="replace")
        raise RuntimeError(f"model endpoint returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"model endpoint request failed: {exc.reason}") from exc
    return body, time.monotonic() - started


def chat_completion(
    *,
    base_url: str,
    model: str,
    api_key: str,
    prompt: str,
    system: str,
    image: Path,
    timeout: float = 300,
) -> tuple[str, float, dict[str, Any]]:
    mime = mimetypes.guess_type(image.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(image.read_bytes()).decode("ascii")
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 2048,
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}},
                ],
            },
        ],
    }
    body, elapsed = post_chat(base_url, api_key, payload, timeout)
    try:
        content = _content_text(body["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise RuntimeError("model endpoint returned an incompatible response") from exc
    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    return content.strip(), elapsed, usage


BASELINE_SYSTEM = "You are a capable multimodal assistant. Answer the user's request using only visible evidence."


def baseline_system(contract: dict[str, Any]) -> str:
    """Generic assistant that knows the output format but not the skill's workflow or guardrails."""
    return "\n".join([BASELINE_SYSTEM, "Output format:", *(f"- {line}" for line in contract_instructions(contract))])


def reference_system(contract: dict[str, Any], references: str) -> str:
    """What a user does without the skill: paste the same reference data into the prompt."""
    return baseline_system(contract) + "\n\nReference data provided by the user:\n\n" + references


def _input_path(input_root: Path, relative: str) -> Path:
    candidate = (input_root / relative).resolve()
    try:
        candidate.relative_to(input_root)
    except ValueError as exc:
        raise ValueError(f"eval input escapes input root: {relative}") from exc
    if not candidate.is_file():
        raise ValueError(f"eval input does not exist: {candidate}")
    return candidate


def capture_ab(
    skill_dir: str | Path,
    input_root: str | Path,
    output_dir: str | Path,
    *,
    base_url: str,
    model: str,
    api_key: str = "local",
    allow_remote: bool = False,
    timeout: float = 300,
) -> dict[str, Any]:
    root = Path(skill_dir).resolve()
    inputs = Path(input_root).resolve()
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    endpoint = validate_endpoint(base_url, allow_remote=allow_remote)
    if not model:
        raise ValueError("model must be provided with --model or OPENAI_MODEL")

    evals = json.loads((root / "evals/evals.json").read_text(encoding="utf-8"))["cases"]
    skill_md = (root / "SKILL.md").read_text(encoding="utf-8")
    workflow = (root / "references/workflow.json").read_text(encoding="utf-8")
    contract = json.loads(workflow)["output_contract"]
    references = reference_block(root, json.loads(workflow).get("references", []))
    captures: list[Capture] = []

    for case in evals:
        if not is_output_case(case):
            continue
        relative_input = case.get("input")
        if not isinstance(relative_input, str) or not relative_input:
            raise ValueError(f"positive eval {case['id']} requires an input path for live capture")
        image = _input_path(inputs, relative_input)
        conditions = {
            "baseline": baseline_system(contract),
            "skill": (
                "Follow the Agent Skill below exactly. Respect its trigger boundary, workflow, output contract, and guardrails.\n\n"
                + skill_md
                + "\n\nValidated workflow reference:\n"
                + workflow
                + (f"\n\nSkill reference files:\n\n{references}" if references else "")
            ),
        }
        if references:
            conditions["reference"] = reference_system(contract, references)
        for mode, system in conditions.items():
            text, elapsed, usage = chat_completion(
                base_url=endpoint,
                model=model,
                api_key=api_key,
                prompt=case["prompt"],
                system=system,
                image=image,
                timeout=timeout,
            )
            path = output / f"{case['id']}.{mode}.txt"
            path.write_text(text + "\n", encoding="utf-8")
            captures.append(Capture(
                case["id"], mode, round(elapsed, 3), str(path),
                usage.get("prompt_tokens"), usage.get("completion_tokens"),
            ))

    manifest = {
        "mode": "live",
        "endpoint": urllib.parse.urlsplit(endpoint)._replace(query="", fragment="").geturl(),
        "model": model,
        "captures": [asdict(item) for item in captures],
    }
    (output / "CAPTURE.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest
