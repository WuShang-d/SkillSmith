"""Sign and verify skill directories with OpenSSF model signing (OMS).

The signature is a detached ``skill.oms.sig`` inside the skill directory,
covering every other file, the same layout NVIDIA uses for verified skills.
SkillSmith shells out to the ``model_signing`` CLI (``pip install model-signing``)
rather than reimplementing any cryptography.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

SIGNATURE = "skill.oms.sig"


@dataclass(frozen=True)
class SigningIdentity:
    private_key: Path
    certificate: Path
    chain: Path

    @classmethod
    def from_pki_dir(cls, pki_dir: str | Path) -> "SigningIdentity":
        root = Path(pki_dir).expanduser().resolve()
        identity = cls(root / "signing-key.pem", root / "signing-cert.pem", root / "root-cert.pem")
        for path in (identity.private_key, identity.certificate, identity.chain):
            if not path.is_file():
                raise ValueError(f"missing PKI file: {path}; run scripts/init-signing-pki.sh")
        return identity


def model_signing_executable() -> str:
    executable = os.environ.get("SKILLSMITH_MODEL_SIGNING") or shutil.which("model_signing")
    if not executable:
        raise ValueError("model_signing not found; `pip install model-signing` or set SKILLSMITH_MODEL_SIGNING")
    return executable


def certificate_subject(certificate: Path) -> str:
    result = subprocess.run(
        ["openssl", "x509", "-in", str(certificate), "-noout", "-subject", "-nameopt", "RFC2253"],
        capture_output=True, text=True, check=False,
    )
    return result.stdout.strip().removeprefix("subject=") or certificate.name


def sign_skill(skill_dir: str | Path, identity: SigningIdentity) -> Path:
    root = Path(skill_dir).resolve()
    signature = root / SIGNATURE
    signature.unlink(missing_ok=True)
    result = subprocess.run(
        [model_signing_executable(), "sign", "certificate", str(root),
         "--signature", str(signature),
         "--ignore-paths", str(signature),
         "--private_key", str(identity.private_key),
         "--signing_certificate", str(identity.certificate),
         "--certificate_chain", str(identity.chain)],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0 or not signature.is_file():
        raise RuntimeError(f"signing failed: {(result.stderr or result.stdout).strip()[-500:]}")
    return signature


def verify_skill(skill_dir: str | Path, chain: str | Path) -> tuple[bool, str]:
    """Strict verification: any modified, missing or added file fails."""
    root = Path(skill_dir).resolve()
    signature = root / SIGNATURE
    if not signature.is_file():
        return False, f"no {SIGNATURE} in {root}"
    result = subprocess.run(
        [model_signing_executable(), "verify", "certificate", str(root),
         "--signature", str(signature),
         "--ignore-paths", str(signature),
         "--certificate_chain", str(Path(chain).expanduser().resolve())],
        capture_output=True, text=True, check=False,
    )
    output = (result.stdout + result.stderr).strip()
    if result.returncode == 0:
        return True, "signature verified"
    modified = re.findall(r"Hash mismatch for \\?'([^'\\]+)", output)
    if modified:
        return False, "modified since signing: " + ", ".join(sorted(set(modified)))
    lines = output.splitlines()
    return False, (lines[-1][:300] if lines else f"exit {result.returncode}")
