# retail-shelf-audit benchmark

Both conditions receive the same user request, image, and output format. The with-skill condition adds only the
skill's workflow and guardrails, so any delta below comes from the skill's procedure, not from knowing field names.

| Dimension | Metric | Baseline | With skill | Delta |
| --- | --- | ---: | ---: | ---: |
| Contract | JSON + required fields | 100.0% | 100.0% | +0.0% |
| Correctness | Task score vs ground truth | 82.7% | 82.3% | -0.4% |
| Correctness | facing_accuracy | 98.2% | 97.4% | -0.8% |
| Correctness | gap_f1 | 50.0% | 50.0% | +0.0% |
| Correctness | occlusion_reported | 100.0% | 100.0% | +0.0% |
| Discoverability | Trigger accuracy (openclaw, 36 runs) | - | 100.0% | - |
| Discoverability | False-trigger rate on negatives | - | 0.0% | - |
| Discoverability | Missed-trigger rate on positives | - | 0.0% | - |
| Efficiency | Mean latency (s) | 15.0 | 14.9 | -0.1 |
| Efficiency | Mean completion tokens | 436 | 430 | -6 |

Primary metric: **task**. Verdict: **FAIL**

Live mode: raw outputs are in live-fixtures/ (CAPTURE.json has model, latency and tokens); trigger runs are in trigger-openclaw/.
