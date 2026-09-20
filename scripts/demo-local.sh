#!/usr/bin/env bash
set -euo pipefail

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$project_dir"
export PYTHONPYCACHEPREFIX="${TMPDIR:-/tmp}/skillsmith-pycache"

SECONDS=0
python3 -m skillsmith.cli pipeline \
  examples/retail-shelf-audit/workflow.json \
  --fixtures examples/retail-shelf-audit/fixtures \
  --output build/demo/generated \
  --destination build/demo/workspace/skills \
  --force

python3 build/demo/workspace/skills/retail-shelf-audit/scripts/run.py \
  --input examples/retail-shelf-audit/shelf-occluded.png \
  --output-dir build/demo/replay \
  --mock-response examples/retail-shelf-audit/fixtures/occluded-shelf.skill.txt

echo
echo "Demo completed in ${SECONDS}s"
echo "Benchmark: build/demo/generated/retail-shelf-audit/BENCHMARK.md"
echo "Security:  build/demo/generated/retail-shelf-audit/SECURITY_REPORT.json"
echo "Replay:    build/demo/replay/result.json"
