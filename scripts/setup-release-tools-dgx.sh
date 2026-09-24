#!/usr/bin/env bash
# Install the release-gate tools into an isolated venv (Python 3.12+ required by SkillSpector):
#   - NVIDIA SkillSpector (security scan, 68 patterns / 17 categories)
#   - OpenSSF model-signing (skill.oms.sig sign / verify)
# Then run scripts/init-signing-pki.sh once to create the signing identity.
set -euo pipefail

venv="${RELEASE_TOOLS_VENV:-$HOME/agent-tools/verify-venv}"
spector_ref="${SKILLSPECTOR_REF:-main}"

python3 -m venv "$venv"
"$venv/bin/pip" install --quiet --upgrade pip
"$venv/bin/pip" install --timeout 30 --retries 10 --quiet "model-signing>=1.1,<2"

src="$(mktemp -d)"
trap 'rm -rf "$src"' EXIT
curl -fsSL --retry 5 "https://codeload.github.com/NVIDIA/SkillSpector/tar.gz/$spector_ref" -o "$src/skillspector.tgz"
echo "SkillSpector source ($spector_ref) sha256: $(sha256sum "$src/skillspector.tgz" | cut -d' ' -f1)"
tar xzf "$src/skillspector.tgz" -C "$src"
"$venv/bin/pip" install --timeout 30 --retries 10 --quiet "$src"/SkillSpector-*/

"$venv/bin/skillspector" --version
"$venv/bin/model_signing" --version
echo "Add to PATH before running SkillSmith: export PATH=\"$venv/bin:\$PATH\""
