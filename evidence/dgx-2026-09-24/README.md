# DGX live evidence — 2026-09-24 (planogram-compliance)

Same node, model and vLLM service as `../dgx-2026-09-23/`.

## A/B with a pasted-data control

`planogram-compliance` ships the bay A12 planogram, the SKU master and a store
policy. Three conditions, same image, request and output format:

- **baseline** — generic assistant
- **pasted data** — generic assistant + the same two reference files, no workflow or guardrails
- **skill** — generated SKILL.md, workflow and reference files

Six composed scenes with exact ground truth (see
`examples/planogram-compliance/ASSET_NOTES.md`).

| Metric | Baseline | Pasted data | With skill |
| --- | ---: | ---: | ---: |
| Task score | 11.1% | 72.6% | 81.4% |
| status_accuracy | 0% | 77.4% | 90.5% |
| deviation_f1 | 33.3% | 46.9% | 58.7% |
| facing_exact | 0% | 93.5% | 95.0% |
| Mean latency / completion tokens | 18.6 s / 558 | 24.6 s / 748 | 18.5 s / 544 |
| Agent-router triggering (60 runs) | – | – | 100% |
| OpenClaw triggering (36 runs, `retail-shelf-audit` installed alongside) | – | – | 97.2% (1 missed, 0 false) |

**Verdict: PASS**, installed. Where the gain comes from: with pasted data the
model flags anything below *target* as LOW; the skill's policy (OK once
`min_facings` is reached) removes those false alarms. Remaining errors in both
conditions: shelf-3 CHP-070 marked MISPLACED although it is planned there, and
one "equal to min" read as LOW. `deviation_f1` is 0 or 1 on the two scenes
without any deviation, so it is coarse there.

OpenClaw miss: `cola-low-chips-oos` attempt 1 (English prompt) loaded the
neighbouring `retail-shelf-audit` instead. On the count-only near miss the agent
loaded neither skill in all three runs, which is correct for this skill but
shows `retail-shelf-audit` is not always picked for its own task.

## Replay on a held-out photo

`scenes/replay-a12-evening.png` was never part of the evaluation.
`replay/result.json` found all three real deviations (cola LOW, water LOW, chips
OOS) plus one false LOW (tea 5 facings, min 4). Task score 88.6%.

## Full demo rehearsal

`demo-rehearsal.log`: `scripts/demo-dgx.sh` end to end in 580 s. Planogram
numbers and the held-out replay reproduced exactly; the retail skill tied
(82.7% vs 82.7%) and was blocked again, since the gate requires a strict gain.

## Files

- `planogram-compliance/live-fixtures/` — CAPTURE.json, 18 raw outputs, router TRIGGER.json
- `planogram-compliance/generated/` — evaluated SKILL.md, SECURITY_REPORT.json, BENCHMARK.md
- `planogram-compliance/live-pipeline.json` — pipeline output (`status: ok`)
- `planogram-compliance/replay/result.json` — held-out replay
- `planogram-compliance/trigger-openclaw/` — OpenClaw trigger runs and transcripts
