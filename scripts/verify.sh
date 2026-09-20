#!/usr/bin/env bash
set -euo pipefail

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$project_dir"

export PYTHONPYCACHEPREFIX="${TMPDIR:-/tmp}/skillsmith-pycache"

python3 -m unittest discover -s tests -v
bash -n scripts/start-vllm-dgx.sh scripts/wait-vllm-dgx.sh scripts/demo-dgx.sh
python3 -m skillsmith.cli pipeline \
  examples/retail-shelf-audit/workflow.json \
  --fixtures examples/retail-shelf-audit/fixtures \
  --output build/verify/generated \
  --destination build/verify/workspace/skills \
  --force
python3 build/verify/workspace/skills/retail-shelf-audit/scripts/run.py \
  --input examples/retail-shelf-audit/shelf-clear.png \
  --output-dir build/verify/replay \
  --mock-response examples/retail-shelf-audit/fixtures/clear-shelf.skill.txt

python3 -c 'import json, pathlib; p=pathlib.Path("build/verify/replay/result.json"); d=json.loads(p.read_text()); required={"image_quality","sku_facings","empty_gaps","uncertainties"}; assert required <= d.keys(); print("replay contract: PASS")'
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git diff --check
fi

echo "SkillSmith verification: PASS"
