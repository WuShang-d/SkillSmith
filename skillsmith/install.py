from __future__ import annotations

import shutil
from pathlib import Path

from .sign import verify_skill


def install(
    skill_dir: str | Path,
    destination: str | Path,
    *,
    force: bool = False,
    verify_chain: str | Path | None = None,
) -> Path:
    source = Path(skill_dir).resolve()
    if not (source / "SKILL.md").is_file():
        raise ValueError(f"not a skill directory: {source}")
    if verify_chain is not None:
        ok, message = verify_skill(source, verify_chain)
        if not ok:
            raise ValueError(f"refusing to install {source.name}: signature verification failed: {message}")
    destination_root = Path(destination).resolve()
    destination_root.mkdir(parents=True, exist_ok=True)
    target = destination_root / source.name
    if target.exists():
        if not force:
            raise FileExistsError(f"installed skill exists: {target}; pass --force to replace it")
        shutil.rmtree(target)
    shutil.copytree(source, target)
    if verify_chain is not None:
        ok, message = verify_skill(target, verify_chain)
        if not ok:
            shutil.rmtree(target)
            raise ValueError(f"installed copy failed signature verification and was removed: {message}")
    return target
