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

## Release chain (final run, `release/`)

The released skill differs from the A/B above only in SKILL.md: after
SkillSpector flagged the originally generated skill (score 100,
`DO_NOT_INSTALL`: `OPENAI_API_KEY` sent to the network, a compiled `.pyc` in the
skill, no declared tool scope — `release/skillspector-before-hardening.json`), the
runner got a fixed 127.0.0.1 destination, stopped reading environment variables,
and SKILL.md declares `allowed-tools` and `permissions`. SkillSpector 2.12.0
then scores it 3 (one LOW advisory asking to review the declared permissions).

That SKILL.md change cost accuracy: final task score **78.4%** (status 87.1%,
deviation F1 53.2%, facings 95.0%) vs pasted data 72.6% and baseline 11.1%;
reproduced in two consecutive runs. Held-out replay unchanged at 88.6%.
The OpenClaw trigger result (35/36) was measured before this change; the
skill's `description`, which the agent routes on, is identical, but the
frontmatter gained `allowed-tools` and `permissions` and was not re-run in OpenClaw.

`release/demo-dgx.log`: full `scripts/demo-dgx.sh` in 572 s — retail blocked;
planogram scanned, evaluated, carded, signed, verified and installed; replay
scored; one-word tamper refused with "modified since signing:
references/workflow.json". Also checked by hand: an added file fails ("Extra
files found … scripts/post_install.sh"), and a copy re-signed by another CA
fails against our root ("self-signed certificate in certificate chain").

Verify the archived release yourself (needs `pip install model-signing`):

```bash
python3 -m skillsmith.cli verify evidence/dgx-2026-09-24/release/planogram-compliance-signed \
  --certificate-chain evidence/dgx-2026-09-24/release/root-cert.pem
```

`root-cert.pem` is the public trust anchor; private keys never left `~/.skillsmith-pki` on the DGX.

## Files

- `planogram-compliance/live-fixtures/` — CAPTURE.json, 18 raw outputs, router TRIGGER.json
- `planogram-compliance/generated/` — evaluated SKILL.md, SECURITY_REPORT.json, BENCHMARK.md
- `planogram-compliance/live-pipeline.json` — pipeline output (`status: ok`)
- `planogram-compliance/replay/result.json` — held-out replay
- `planogram-compliance/trigger-openclaw/` — OpenClaw trigger runs and transcripts
