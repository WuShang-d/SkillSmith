# planogram-compliance benchmark

All conditions receive the same user request, image, and output format. The with-skill condition adds the
skill's workflow and guardrails, so any delta below comes from the skill, not from knowing field names.
*Pasted data* is the same reference data given to a generic prompt without the skill's procedure.

| Dimension | Metric | Baseline | Pasted data | With skill | Delta vs baseline |
| --- | --- | ---: | ---: | ---: | ---: |
| Contract | JSON + required fields | 100.0% | 100.0% | 100.0% | +0.0% |
| Correctness | Task score vs ground truth | 11.1% | 72.6% | 81.4% | +70.3% |
| Correctness | status_accuracy | 0.0% | 77.4% | 90.5% | +90.5% |
| Correctness | deviation_f1 | 33.3% | 46.9% | 58.7% | +25.4% |
| Correctness | facing_exact | 0.0% | 93.5% | 95.0% | +95.0% |
| Discoverability | Trigger accuracy (agent-router, 60 runs) | - | - | 100.0% | - |
| Discoverability | False-trigger rate on negatives | - | - | 0.0% | - |
| Discoverability | Missed-trigger rate on positives | - | - | 0.0% | - |
| Efficiency | Mean latency (s) | 18.6 | 24.6 | 18.5 | -0.1 |
| Efficiency | Mean completion tokens | 558 | 748 | 544 | -13 |

Primary metric: **task**. Verdict: **PASS**

Live mode: raw outputs were captured from one configured model endpoint; see the adjacent CAPTURE.json for model, latency, and token evidence.
