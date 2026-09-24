from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Finding:
    severity: str
    rule: str
    path: str
    line: int
    message: str


RULES: tuple[tuple[str, str, re.Pattern[str], str], ...] = (
    ("critical", "destructive-delete", re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f\b"), "destructive recursive deletion"),
    ("high", "shell-pipe-install", re.compile(r"(?:curl|wget)[^\n|]*\|\s*(?:sh|bash)\b"), "remote content piped to a shell"),
    ("high", "secret-literal", re.compile(r"(?i)(?:api[_-]?key|token|password)\s*[=:]\s*['\"][^'\"]{8,}['\"]"), "possible hard-coded credential"),
    ("high", "unsafe-eval", re.compile(r"\beval\s*\("), "dynamic eval execution"),
    ("medium", "shell-true", re.compile(r"shell\s*=\s*True"), "subprocess shell execution"),
    ("medium", "broad-home-write", re.compile(r"(?:Path\s*\(\s*['\"]~|\$HOME|/home/[^/\s]+/)"), "broad or user-home path reference"),
    ("medium", "unicode-control", re.compile(r"[\u202a-\u202e\u2066-\u2069]"), "bidirectional Unicode control character"),
)


def scan(skill_dir: str | Path) -> list[Finding]:
    root = Path(skill_dir).resolve()
    findings: list[Finding] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if path.stat().st_size > 1_000_000:
            findings.append(Finding("medium", "large-file", str(path.relative_to(root)), 0, "file exceeds 1 MB"))
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(lines, 1):
            for severity, rule, pattern, message in RULES:
                if pattern.search(line):
                    findings.append(Finding(severity, rule, str(path.relative_to(root)), number, message))
    return findings


def skillspector_executable() -> str | None:
    return os.environ.get("SKILLSMITH_SKILLSPECTOR") or shutil.which("skillspector")


def skillspector_scan(skill_dir: str | Path, executable: str, *, use_llm: bool = False, timeout: float = 600) -> dict[str, Any]:
    """Run NVIDIA SkillSpector and normalise its JSON report.

    Static analysis only by default (--no-llm); with use_llm, SkillSpector's own
    LLM configuration decides which endpoint performs the semantic pass.
    """
    root = Path(skill_dir).resolve()
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "skillspector.json"
        command = [executable, "scan", str(root), "-f", "json", "-o", str(output)]
        if not use_llm:
            command.append("--no-llm")
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        if completed.returncode == 2 or not output.is_file():
            detail = (completed.stderr or completed.stdout).strip()[-500:]
            raise RuntimeError(f"SkillSpector failed (exit {completed.returncode}): {detail}")
        raw = json.loads(output.read_text(encoding="utf-8"))
    assessment = raw.get("risk_assessment") or {}
    metadata = raw.get("metadata") or {}
    return {
        "engine": "skillspector",
        "version": metadata.get("skillspector_version"),
        "exit_code": completed.returncode,
        "score": assessment.get("score"),
        "severity": assessment.get("severity"),
        "recommendation": assessment.get("recommendation"),
        "llm_used": bool(metadata.get("llm_requested") and metadata.get("llm_available")),
        "issues": raw.get("issues", []),
    }


def report(findings: list[Finding], skillspector: dict[str, Any] | None = None) -> dict[str, object]:
    """Combine SkillSmith's rules with SkillSpector; either one can block installation."""
    counts = {level: sum(f.severity == level for f in findings) for level in ("critical", "high", "medium", "low")}
    blocked = bool(counts["critical"] or counts["high"])
    result: dict[str, object] = {"engines": ["skillsmith-rules"]}
    if skillspector is not None:
        result["engines"] = ["skillsmith-rules", "skillspector"]
        result["skillspector"] = skillspector
        blocked = blocked or skillspector["exit_code"] == 1 or skillspector["recommendation"] == "DO_NOT_INSTALL"
    return {"verdict": "fail" if blocked else "pass", "counts": counts, "findings": [asdict(f) for f in findings], **result}


def full_scan(skill_dir: str | Path, *, require_skillspector: bool = False, use_llm: bool = False) -> dict[str, object]:
    executable = skillspector_executable()
    if executable is None and require_skillspector:
        raise ValueError("SkillSpector is required but not installed; set SKILLSMITH_SKILLSPECTOR or put it on PATH")
    spector = skillspector_scan(skill_dir, executable, use_llm=use_llm) if executable else None
    return report(scan(skill_dir), spector)
