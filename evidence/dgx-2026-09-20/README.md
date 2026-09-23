# DGX live evidence — 2026-09-20

> **Superseded — do not quote these numbers.** In this run the baseline system
> prompt did not include the output format, while the rubric only checked the
> contract's field names. The 23.6% → 100% "improvement" therefore measured
> whether the model was told the field names, not whether the skill helped.
> The fair re-run, with ground-truth scoring and a baseline that receives the
> same output format, is in `evidence/dgx-2026-09-23/`. This snapshot is kept
> unchanged as a historical record.

This directory is the immutable evidence snapshot from the successful live
SkillSmith run on the competition DGX Spark.

## Result

- Hardware: NVIDIA GB10
- Runtime: vLLM 0.22.1, loopback-only OpenAI-compatible endpoint
- Model: `Qwen/Qwen3.6-35B-A3B`
- End-to-end time after model readiness: **78 seconds**
- Security gate: **PASS**, with zero findings
- Trigger accuracy: **100%**
- Baseline contract score: **23.6%**
- With-Skill contract score: **100%**
- Improvement: **+76.4 percentage points**
- New-input replay contract: **PASS**

The A/B captures used the same endpoint, model, prompt, and image for each
case. The only intended variable was whether the generated Skill instructions
were supplied as the system message.

## Files

- `DEMO_EVIDENCE.json`: machine-readable run summary.
- `live-fixtures/CAPTURE.json`: model identity and per-request latency.
- `live-fixtures/*.txt`: unedited baseline and With-Skill model outputs.
- `generated/retail-shelf-audit/BENCHMARK.md`: deterministic rubric result.
- `generated/retail-shelf-audit/SECURITY_REPORT.json`: security gate result.
- `generated/retail-shelf-audit/SKILL.md`: generated Skill evaluated in the run.
- `replay/result.json`: contract-valid result on the second, occluded image.

The evidence archive transferred from the DGX was
`dgx-evidence-20260920.tar.gz`, SHA-256
`7335bd7b95d08746dab003357c25dda6706660581cc7b538854f4749fee21465`.
It contains no API key, login material, source spreadsheet, or node access
document.
