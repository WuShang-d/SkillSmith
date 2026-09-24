# retail-shelf-audit benchmark

All conditions receive the same user request, image, and output format. The with-skill condition adds the
skill's workflow and guardrails, so any delta below comes from the skill, not from knowing field names.

| Dimension | Metric | Baseline | With skill | Delta vs baseline |
| --- | --- | ---: | ---: | ---: |
| Contract | JSON + required fields | 100.0% | 100.0% | +0.0% |
| Correctness | Task score vs ground truth | 82.7% | 82.7% | +0.0% |
| Correctness | facing_accuracy | 98.2% | 98.5% | +0.3% |
| Correctness | gap_f1 | 50.0% | 50.0% | +0.0% |
| Correctness | occlusion_reported | 100.0% | 100.0% | +0.0% |
| Discoverability | Trigger accuracy (agent-router, 36 runs) | - | 100.0% | - |
| Discoverability | False-trigger rate on negatives | - | 0.0% | - |
| Discoverability | Missed-trigger rate on positives | - | 0.0% | - |
| Efficiency | Mean latency (s) | 14.2 | 15.5 | +1.4 |
| Efficiency | Mean completion tokens | 436 | 479 | +44 |

Primary metric: **task**. Verdict: **FAIL**

Live mode: raw outputs were captured from one configured model endpoint; see the adjacent CAPTURE.json for model, latency, and token evidence.
