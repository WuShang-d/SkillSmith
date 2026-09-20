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


LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


@dataclass(frozen=True)
class Capture:
    case_id: str
    mode: str
    elapsed_seconds: float
    output_path: str


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


def chat_completion(
    *,
    base_url: str,
    model: str,
    api_key: str,
    prompt: str,
    system: str,
    image: Path,
    timeout: float = 300,
) -> tuple[str, float]:
    mime = mimetypes.guess_type(image.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(image.read_bytes()).decode("ascii")
    payload = {
        "model": model,
        "temperature": 0,
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
    elapsed = time.monotonic() - started
    try:
        content = _content_text(body["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise RuntimeError("model endpoint returned an incompatible response") from exc
    return content.strip(), elapsed


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
    captures: list[Capture] = []

    for case in evals:
        if not case["should_trigger"]:
            continue
        relative_input = case.get("input")
        if not isinstance(relative_input, str) or not relative_input:
            raise ValueError(f"positive eval {case['id']} requires an input path for live capture")
        image = _input_path(inputs, relative_input)
        conditions = {
            "baseline": "You are a capable multimodal assistant. Answer the user's request using only visible evidence.",
            "skill": (
                "Follow the Agent Skill below exactly. Respect its trigger boundary, workflow, output contract, and guardrails.\n\n"
                + skill_md
                + "\n\nValidated workflow reference:\n"
                + workflow
            ),
        }
        for mode, system in conditions.items():
            text, elapsed = chat_completion(
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
            captures.append(Capture(case["id"], mode, round(elapsed, 3), str(path)))

    manifest = {
        "mode": "live",
        "endpoint": urllib.parse.urlsplit(endpoint)._replace(query="", fragment="").geturl(),
        "model": model,
        "captures": [asdict(item) for item in captures],
    }
    (output / "CAPTURE.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest
