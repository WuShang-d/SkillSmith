#!/usr/bin/env bash
# Roadshow flow on the DGX: the same release gate blocks one skill and ships another.
#   1. retail-shelf-audit   — safe and discoverable, but no better than the bare model  -> BLOCKED
#   2. planogram-compliance — carries store planogram + policy, beats the pasted data  -> INSTALLED
#   3. replay the installed skill on a held-out photo and score it against ground truth
set -euo pipefail

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$project_dir"
export PYTHONPYCACHEPREFIX="${TMPDIR:-/tmp}/skillsmith-pycache"

: "${OPENAI_BASE_URL:?Set OPENAI_BASE_URL to the DGX-local OpenAI-compatible endpoint}"
: "${OPENAI_MODEL:?Set OPENAI_MODEL to the served multimodal model name}"
repeats="${TRIGGER_REPEATS:-3}"
out=build/demo-dgx
mkdir -p "$out/retail" "$out/planogram"
SECONDS=0

echo "== 1/3 retail-shelf-audit: fair A/B against ground truth"
set +e
python3 -m skillsmith.cli live-pipeline examples/retail-shelf-audit/workflow.json \
  --input-root examples/retail-shelf-audit --capture-dir "$out/retail/live-fixtures" \
  --output "$out/retail/generated" --destination "$out/workspace/skills" \
  --trigger-repeats "$repeats" --force > "$out/retail/pipeline.json"
retail_status=$?
set -e
cat "$out/retail/generated/retail-shelf-audit/BENCHMARK.md"
if [[ $retail_status -eq 3 ]]; then
  echo ">> BLOCKED at evaluation: the skill does not beat the bare model, so it is not installed."
elif [[ $retail_status -ne 0 ]]; then
  echo "retail pipeline failed unexpectedly (exit $retail_status)" >&2
  exit "$retail_status"
fi

echo
echo "== 2/3 planogram-compliance: baseline vs pasted data vs skill"
python3 -m skillsmith.cli live-pipeline examples/planogram-compliance/workflow.json \
  --input-root examples/planogram-compliance --capture-dir "$out/planogram/live-fixtures" \
  --output "$out/planogram/generated" --destination "$out/workspace/skills" \
  --trigger-repeats "$repeats" --force > "$out/planogram/pipeline.json"
cat "$out/planogram/generated/planogram-compliance/BENCHMARK.md"
echo ">> INSTALLED: $out/workspace/skills/planogram-compliance"

echo
echo "== 3/3 replay the installed skill on a held-out photo"
installed="$out/workspace/skills/planogram-compliance"
python3 "$installed/scripts/run.py" \
  --input examples/planogram-compliance/scenes/replay-a12-evening.png \
  --output-dir "$out/replay"
python3 -m skillsmith.cli score "$installed" --result "$out/replay/result.json" \
  --ground-truth examples/planogram-compliance/scenes/held-out-ground-truth.json --key replay-a12-evening

echo
echo "DGX demo completed in ${SECONDS}s. Outputs under $out/"
