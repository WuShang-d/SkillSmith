#!/usr/bin/env bash
set -euo pipefail

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$project_dir"

export PYTHONPYCACHEPREFIX="${TMPDIR:-/tmp}/skillsmith-pycache"

python3 -m unittest discover -s tests -v
bash -n scripts/start-vllm-dgx.sh scripts/wait-vllm-dgx.sh scripts/demo-dgx.sh scripts/setup-openclaw-dgx.sh
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
python3 -m skillsmith.cli pipeline \
  examples/planogram-compliance/workflow.json \
  --fixtures examples/planogram-compliance/fixtures \
  --output build/verify/generated \
  --destination build/verify/workspace/skills \
  --force
python3 build/verify/workspace/skills/planogram-compliance/scripts/run.py \
  --input examples/planogram-compliance/scenes/mixed-deviations.png \
  --output-dir build/verify/replay-planogram \
  --mock-response examples/planogram-compliance/fixtures/mixed-deviations.skill.txt
python3 -m skillsmith.cli score build/verify/workspace/skills/planogram-compliance \
  --result build/verify/replay-planogram/result.json \
  --ground-truth <(python3 -c 'import json; print(json.dumps(next(c["ground_truth"] for c in json.load(open("examples/planogram-compliance/workflow.json"))["evals"] if c["id"] == "mixed-deviations")))')

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git diff --check
fi

echo "SkillSmith verification: PASS"
