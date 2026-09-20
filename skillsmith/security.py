from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path


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


def report(findings: list[Finding]) -> dict[str, object]:
    counts = {level: sum(f.severity == level for f in findings) for level in ("critical", "high", "medium", "low")}
    verdict = "fail" if counts["critical"] or counts["high"] else "pass"
    return {"verdict": verdict, "counts": counts, "findings": [asdict(f) for f in findings]}
