"""Trigger evaluation inside a real OpenClaw agent.

The skill is installed into an isolated OpenClaw profile's workspace next to
OpenClaw's own bundled skills. Each evaluation prompt runs as a fresh embedded
agent turn (``openclaw agent --local``) against the configured local model. A
trigger is counted when the agent's first skill read, taken from OpenClaw's own
session transcript, is this skill's SKILL.md.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import time
import uuid
import zlib
import struct
from pathlib import Path
from typing import Any

from .trigger import skill_frontmatter, user_message

SKILL_READ = re.compile(r"/skills/([^/]+)/SKILL\.md$")
ATTACHMENT = re.compile(r"inbox/([\w.\-]+\.(?:png|jpe?g|webp|mp4|csv))", re.IGNORECASE)


def profile_dir(profile: str) -> Path:
    return Path.home() / f".openclaw-{profile}"


def neutral_png(width: int = 64, height: int = 64) -> bytes:
    """A plain grey image, so a placeholder attachment cannot itself suggest a shelf."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    rows = b"".join(b"\x00" + b"\x80\x80\x80" * width for _ in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


def stage_attachments(case: dict[str, Any], message: str, inbox: Path, input_root: Path) -> None:
    """Put a file at every inbox/ path the message mentions so the agent is not stalled by a missing upload.

    Only the case's own input is a real image; every other attachment is a neutral placeholder,
    so the placeholder content cannot push the agent towards (or away from) the skill.
    """
    inbox.mkdir(parents=True, exist_ok=True)
    for name in ATTACHMENT.findall(message):
        target = inbox / name
        if target.exists():
            continue
        source = input_root / case["input"] if case.get("input") else None
        if source and source.name == name and source.is_file():
            shutil.copyfile(source, target)
        elif target.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            target.write_bytes(neutral_png())
        else:
            target.write_text("placeholder attachment for trigger evaluation\n", encoding="utf-8")


def skill_reads(profile: str, session_id: str) -> list[str]:
    """SKILL.md loads in order, whether via the read tool or OpenClaw's skill_workshop tool."""
    return transcript_skill_reads(profile_dir(profile) / "agents/main/agent/openclaw-agent.sqlite", session_id)


def transcript_skill_reads(database: Path, session_id: str) -> list[str]:
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "select event_json from transcript_events where session_id = ? order by seq", (session_id,)
        ).fetchall()
    finally:
        connection.close()
    paths = []
    for (raw,) in rows:
        event = json.loads(raw)
        message = event.get("message") or {}
        if message.get("role") != "assistant":
            continue
        for part in message.get("content") or []:
            if part.get("type") != "toolCall":
                continue
            arguments = part.get("arguments") or {}
            if part.get("name") == "read":
                path = str(arguments.get("path", ""))
                if SKILL_READ.search(path):
                    paths.append(path)
            elif part.get("name") == "skill_workshop" and arguments.get("action") == "read" and arguments.get("skill_name"):
                paths.append(f"skill_workshop:/skills/{arguments['skill_name']}/SKILL.md")
    return paths


def evaluate_openclaw_triggers(
    skill_dir: str | Path,
    output_dir: str | Path,
    *,
    input_root: str | Path,
    profile: str = "skillsmith-eval",
    openclaw: str = "openclaw",
    repeats: int = 3,
    timeout: int = 240,
) -> dict[str, Any]:
    root = Path(skill_dir).resolve()
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    inputs = Path(input_root).resolve()
    name = skill_frontmatter(root)["name"]
    workspace = profile_dir(profile) / "workspace"
    if not (profile_dir(profile) / "openclaw.json").is_file():
        raise ValueError(f"OpenClaw profile is not configured: {profile_dir(profile)}; run scripts/setup-openclaw-dgx.sh")
    installed = workspace / "skills" / name
    if installed.exists():
        shutil.rmtree(installed)
    shutil.copytree(root, installed)

    inbox = workspace / "inbox"
    if inbox.exists():
        shutil.rmtree(inbox)
    cases = json.loads((root / "evals/evals.json").read_text(encoding="utf-8"))["cases"]
    runs: list[dict[str, Any]] = []
    for case in cases:
        message = user_message(case)
        stage_attachments(case, message, inbox, inputs)
        for attempt in range(1, repeats + 1):
            session_id = f"skillsmith-{case['id']}-{attempt}-{uuid.uuid4().hex[:8]}"
            started = time.monotonic()
            completed = subprocess.run(
                [openclaw, "--profile", profile, "agent", "--local", "--json",
                 "--session-id", session_id, "--timeout", str(timeout), "--message", message],
                capture_output=True, text=True, timeout=timeout + 60, check=False,
                env={**os.environ, "NO_COLOR": "1"},
            )
            elapsed = time.monotonic() - started
            reads = skill_reads(profile, session_id)
            chosen = SKILL_READ.search(reads[0]).group(1) if reads else None
            runs.append({
                "case_id": case["id"],
                "attempt": attempt,
                "session_id": session_id,
                "should_trigger": case["should_trigger"],
                "triggered": chosen == name,
                "selected_skill": chosen,
                "read_paths": reads,
                "exit_code": completed.returncode,
                "elapsed_seconds": round(elapsed, 3),
            })

    positives = [run for run in runs if run["should_trigger"]]
    negatives = [run for run in runs if not run["should_trigger"]]
    version = subprocess.run([openclaw, "--version"], capture_output=True, text=True, check=False).stdout.strip()
    result = {
        "method": "openclaw",
        "harness": version,
        "profile": profile,
        "repeats": repeats,
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
    (output / "TRIGGER.openclaw.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result
