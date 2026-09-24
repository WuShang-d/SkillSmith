# planogram-compliance benchmark

All conditions receive the same user request, image, and output format. The with-skill condition adds the
skill's workflow and guardrails, so any delta below comes from the skill, not from knowing field names.
*Pasted data* is the same reference data given to a generic prompt without the skill's procedure.

| Dimension | Metric | Baseline | Pasted data | With skill | Delta vs baseline |
| --- | --- | ---: | ---: | ---: | ---: |
| Contract | JSON + required fields | 100.0% | 100.0% | 100.0% | +0.0% |
| Correctness | Task score vs ground truth | 11.1% | 72.6% | 78.4% | +67.3% |
| Correctness | status_accuracy | 0.0% | 77.4% | 87.1% | +87.1% |
| Correctness | deviation_f1 | 33.3% | 46.9% | 53.2% | +19.9% |
| Correctness | facing_exact | 0.0% | 93.5% | 95.0% | +95.0% |
| Discoverability | Trigger accuracy (agent-router, 36 runs) | - | - | 100.0% | - |
| Discoverability | False-trigger rate on negatives | - | - | 0.0% | - |
| Discoverability | Missed-trigger rate on positives | - | - | 0.0% | - |
| Efficiency | Mean latency (s) | 18.1 | 24.2 | 18.7 | +0.5 |
| Efficiency | Mean completion tokens | 558 | 748 | 568 | +11 |

Primary metric: **task**. Verdict: **PASS**

Live mode: raw outputs were captured from one configured model endpoint; see the adjacent CAPTURE.json for model, latency, and token evidence.
