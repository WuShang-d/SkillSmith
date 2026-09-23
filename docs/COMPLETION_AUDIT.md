# Goal completion audit

This file tracks evidence against the actual competition objective. A checked item means the cited artifact or command has been verified; it is not a statement of intent.

| Requirement | Status | Authoritative evidence |
| --- | --- | --- |
| Generate an installable Agent Skill from a successful workflow | Verified locally | `skillsmith/forge.py`; `scripts/verify.sh` |
| Explicit positive and negative trigger boundaries | Verified locally | example `workflow.json` (6 positive, 6 negative incl. near misses) |
| Security gate blocks high-risk patterns before installation | Verified locally | `skillsmith/security.py`; `test_scanner_blocks_secret` |
| A/B evaluation of baseline versus with-Skill output | Verified; baseline now receives the same output format | `baseline_system` in `skillsmith/endpoint.py`; `test_live_capture_writes_baseline_and_skill_evidence` |
| Correctness scored against ground truth, not field names | Verified | `examples/retail-shelf-audit/scorer.py`; `ground_truth` in `workflow.json`; `test_scorer_penalises_stacked_units_and_tote_items` |
| Capture real A/B outputs from the same DGX-local model | Verified on DGX; **skill shows no gain (82.7% → 82.3%), install blocked** | `evidence/dgx-2026-09-23/` |
| Trigger measured with a real agent, not keyword overlap | Verified on DGX: OpenClaw 36/36, agent router 60/60 | `evidence/dgx-2026-09-23/trigger-openclaw/`; `skillsmith/openclaw_trigger.py` |
| Install only after security and evaluation pass | Verified locally | `cmd_pipeline`, `cmd_live_pipeline`, tests |
| Replay with a new input | Verified locally with mock response | generated runner and `scripts/verify.sh` |
| Replay with a new input on DGX multimodal inference | Verified on DGX | `evidence/dgx-2026-09-20/replay/result.json`; exact required fields validated by the runner |
| Non-technical browser workflow | Verified locally in a real browser | `skillsmith/web.py`; browser result showed PASS/READY |
| End-to-end duration under 10 minutes on DGX | Verified: 182 s for forge → scan → A/B → 60 router trigger runs | `evidence/dgx-2026-09-23/` (the OpenClaw trigger pass is separate, ~70 s per agent run) |
| A skill that passes the fair gate | Verified on DGX: `planogram-compliance` 81.4% vs pasted data 72.6% vs baseline 11.1% | `evidence/dgx-2026-09-24/planogram-compliance/` |
| Skill beats simply pasting its reference data | Verified on DGX (+8.8 pts, fewer tokens, lower latency) | same; gate rule in `evaluate_fixtures` |
| Replay on a held-out input, scored | Verified on DGX: 3/3 real deviations found, 1 false LOW, task score 88.6% | `evidence/dgx-2026-09-24/planogram-compliance/replay/` |
| Roadshow shows the gate blocking and shipping | Rehearsed on DGX end to end in 580 s | `evidence/dgx-2026-09-24/demo-rehearsal.log` |
| Reusable SkillSmith skill package | Verified structurally | `skills-src/skillsmith`; `quick_validate.py` |
| Stable roadshow narrative and fallback | Technically rehearsed on DGX | Two complete `scripts/demo-dgx.sh` runs; final evidence snapshot and `docs/ROADSHOW.md` |

The 2026-09-20 "23.6% → 100%" result is superseded: its baseline was never
told the output format, so it measured field-name knowledge, not the skill.
