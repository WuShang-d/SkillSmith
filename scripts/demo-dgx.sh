#!/usr/bin/env bash
set -euo pipefail

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$project_dir"
export PYTHONPYCACHEPREFIX="${TMPDIR:-/tmp}/skillsmith-pycache"

: "${OPENAI_BASE_URL:?Set OPENAI_BASE_URL to the DGX-local OpenAI-compatible endpoint}"
: "${OPENAI_MODEL:?Set OPENAI_MODEL to the served multimodal model name}"

SECONDS=0
python3 -m skillsmith.cli live-pipeline \
  examples/retail-shelf-audit/workflow.json \
  --input-root examples/retail-shelf-audit \
  --capture-dir build/dgx/live-fixtures \
  --output build/dgx/generated \
  --destination build/dgx/workspace/skills \
  --force

python3 build/dgx/workspace/skills/retail-shelf-audit/scripts/run.py \
  --input examples/retail-shelf-audit/shelf-occluded.png \
  --output-dir build/dgx/replay

echo
echo "DGX demo completed in ${SECONDS}s"
echo "Capture:   build/dgx/live-fixtures/CAPTURE.json"
echo "Benchmark: build/dgx/generated/retail-shelf-audit/BENCHMARK.md"
echo "Security:  build/dgx/generated/retail-shelf-audit/SECURITY_REPORT.json"
echo "Replay:    build/dgx/replay/result.json"
