# DGX live evidence — 2026-09-23 (fair A/B + real-agent triggering)

Supersedes `evidence/dgx-2026-09-20/`, whose baseline was not told the output
format while the rubric only checked field names.

## Setup

- Hardware: NVIDIA DGX Spark (GB10), competition node
- Model: `Qwen/Qwen3.6-35B-A3B`, vLLM (`vllm/vllm-openai:latest`) on loopback,
  started by `scripts/start-vllm-dgx.sh` with tool calling enabled
  (`--tool-call-parser qwen3_coder`, 64K context)
- Agent harness for triggering: OpenClaw 2026.9.5, isolated profile
  (`scripts/setup-openclaw-dgx.sh`), 23 eligible skills incl. OpenClaw's bundled ones

## What was measured

**Correctness (A/B).** Same model, image and user request in both conditions,
and **both receive the same output format** (`output_contract.schema_hint`).
The with-skill condition adds only the skill's workflow and guardrails. Outputs
are scored against hand-annotated ground truth (front-row facings per shelf,
empty gaps, occlusion) by `examples/retail-shelf-audit/scorer.py`.

**Discoverability.** Every eval prompt (6 positive, 6 negative incl. near
misses: customer faces, shelf video, promo poster, sales CSV) was sent 3× as a
fresh OpenClaw agent turn. A trigger is counted only when OpenClaw's own session
transcript shows the agent loading this skill's SKILL.md.

## Result

| Dimension | Baseline | With skill |
| --- | ---: | ---: |
| Contract (JSON + fields) | 100% | 100% |
| Task score vs ground truth | 82.7% | 82.3% |
| — facing accuracy | 98.2% | 97.4% |
| — gap F1 | 50% | 50% |
| — occlusion reported | 100% | 100% |
| OpenClaw trigger accuracy (36 runs) | – | 100% (0 missed, 0 false) |
| Mean latency / completion tokens | 15.0 s / 436 | 14.9 s / 430 |

**Verdict: FAIL — the release gate correctly blocked installation.** On these
two images Qwen3.6 already audits the shelf as well without the skill; the
skill is discoverable and safe, but does not measurably improve correctness.
Both conditions miss the top-right gap in the occluded image.

Trigger stability note: an earlier OpenClaw pass (before two harness fixes —
detecting OpenClaw's `skill_workshop` load path, and using neutral placeholder
attachments instead of a shelf photo) recorded one genuine miss:
`trigger-stockout` attempt 1 answered from `view_image` without loading the
skill. Three repeats per prompt is therefore not proof of perfect stability.

The agent-router trigger evaluation (`live-fixtures/TRIGGER.json`, 60 runs,
9 neighbouring skills) also scored 100%.

## Files

- `live-fixtures/CAPTURE.json` — model, per-request latency and token usage
- `live-fixtures/*.txt` — unedited baseline and with-skill outputs
- `live-fixtures/TRIGGER.json` — agent-router trigger runs
- `trigger-openclaw/TRIGGER.openclaw.json` — OpenClaw trigger runs
- `trigger-openclaw/openclaw-transcripts.jsonl.gz` — full OpenClaw session transcripts for those runs
- `generated/retail-shelf-audit/` — the evaluated SKILL.md, security report, router-based BENCHMARK.md
- `BENCHMARK.openclaw.md` — benchmark with OpenClaw trigger results
- `live-pipeline.json` — pipeline output (`status: blocked`, `stage: evaluation`)

Re-score locally without a model: forge the example, then
`python3 -m skillsmith.cli evaluate <skill> --fixtures live-fixtures --trigger-result trigger-openclaw/TRIGGER.openclaw.json`.
