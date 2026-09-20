from __future__ import annotations

import shutil
from pathlib import Path


def install(skill_dir: str | Path, destination: str | Path, *, force: bool = False) -> Path:
    source = Path(skill_dir).resolve()
    if not (source / "SKILL.md").is_file():
        raise ValueError(f"not a skill directory: {source}")
    destination_root = Path(destination).resolve()
    destination_root.mkdir(parents=True, exist_ok=True)
    target = destination_root / source.name
    if target.exists():
        if not force:
            raise FileExistsError(f"installed skill exists: {target}; pass --force to replace it")
        shutil.rmtree(target)
    shutil.copytree(source, target)
    return target
