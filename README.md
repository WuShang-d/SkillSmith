# SkillSmith

**把 Agent 的一次成功，锻造成全公司都敢装的能力。** 第三届 NVIDIA DGX Spark Hackathon · Agent Skills 开发挑战赛参赛作品。

- 演示视频：[B 站观看](https://www.bilibili.com/video/BV1HaaG6QE3f/)
- 项目报告书：[docs/REPORT.md](docs/REPORT.md) · 参赛历程：[docs/JOURNEY.md](docs/JOURNEY.md)
- 在 DGX Spark 本地实测，同一道门禁拦下一个 Skill、放行一个：

| Skill | 不装 | 粘贴资料 | 装 Skill | 门禁 |
| --- | ---: | ---: | ---: | --- |
| 零售货架巡检 | 82.7% | – | 82.3% | 拦截，不安装 |
| 门店陈列合规 | 11.1% | 72.6% | 78.4% | 通过，签名后安装 |


SkillSmith turns one successful multimodal agent workflow into a reusable Agent Skill and enforces a release gate:

```text
successful workflow -> skill package -> security scan -> A/B evaluation -> install -> replay
```

The core has no third-party Python dependency. It is designed to run locally on NVIDIA DGX Spark and to call any OpenAI-compatible multimodal endpoint.

## Five-minute local proof

From this directory:

```bash
python3 -m skillsmith.cli pipeline \
  examples/retail-shelf-audit/workflow.json \
  --fixtures examples/retail-shelf-audit/fixtures \
  --output build/generated \
  --destination build/workspace/skills \
  --force
```

The command generates `retail-shelf-audit`, scans it, writes `BENCHMARK.md`, and installs it only if both gates pass.

For the guided local UI:

```bash
python3 -m skillsmith.web --host 127.0.0.1 --port 7860
```

Open `http://127.0.0.1:7860`. The browser form turns a successful run, trigger boundaries, workflow steps, guardrails, and A/B outputs into an installed project-local skill. The server never needs to expose credentials or upload business images.

Replay the generated skill without a model endpoint:

```bash
python3 build/workspace/skills/retail-shelf-audit/scripts/run.py \
  --input examples/retail-shelf-audit/shelf-clear.png \
  --output-dir build/replay \
  --mock-response examples/retail-shelf-audit/fixtures/clear-shelf.skill.txt
```

For DGX inference, omit `--mock-response` and set:

```bash
export OPENAI_BASE_URL=http://127.0.0.1:8000/v1
export OPENAI_MODEL=YOUR_LOCAL_MULTIMODAL_MODEL
export OPENAI_API_KEY=local
```

On the competition DGX Spark, start the preloaded Qwen3.6 model through the
loopback-only vLLM service, then wait for readiness:

```bash
./scripts/start-vllm-dgx.sh
./scripts/wait-vllm-dgx.sh
```

The launch script mounts the model read-only, exposes no network-facing port,
and keeps all inference on the DGX. Its image, model path, port, container name,
and memory utilization can be overridden with the documented environment
variables at the top of the script.

Do not commit real credentials. Fixture mode validates the pipeline mechanics, not model quality; the final competition benchmark must use captured DGX endpoint results.

## Live DGX A/B evidence

Each positive evaluation case can name an `input` image beneath an input root. The live pipeline sends the same prompt and image to the same local model twice: once with a generic baseline system message and once with the generated Skill. It records raw answers and latency before applying the same deterministic rubric.

```bash
export OPENAI_BASE_URL=http://127.0.0.1:8000/v1
export OPENAI_MODEL=Qwen/Qwen3.6-35B-A3B
export OPENAI_API_KEY=local

python3 -m skillsmith.cli live-pipeline \
  examples/retail-shelf-audit/workflow.json \
  --input-root examples/retail-shelf-audit \
  --capture-dir build/live-fixtures \
  --output build/live-generated \
  --destination build/live-workspace/skills \
  --force
```

Images are restricted to the declared input root. Endpoints are restricted to loopback addresses by default; using a remote endpoint requires the explicit `--allow-remote-endpoint` flag and user authorization.

## Project layout

- `skillsmith/`: forge, scan, evaluation, install, and CLI implementation.
- `skills-src/skillsmith/`: the reusable meta-skill that teaches an agent to run the pipeline.
- `examples/retail-shelf-audit/`: a skill that is safe and discoverable but does not beat the bare model — the gate blocks it.
- `examples/planogram-compliance/`: a skill that ships a store planogram, SKU master and policy; scenes are composed by `make_scenes.py` with exact ground truth.
- `tests/`: deterministic release-gate tests.
- `scripts/verify.sh`: full local verification; `scripts/start-vllm-dgx.sh` and
  `scripts/wait-vllm-dgx.sh`: reproducible DGX model service; `scripts/demo-dgx.sh`:
  live evidence path.
- `scripts/package.sh`: create a source archive from tracked Git content only, excluding ignored credentials and build outputs.
- `docs/ROADSHOW.md`: timed competition demo; `docs/COMPLETION_AUDIT.md`: honest requirement-by-requirement status.

The two shelf images are synthetic, brandless evaluation assets generated specifically for this project. Their prompts, provenance, and hashes are recorded in `examples/retail-shelf-audit/ASSET_NOTES.md`; they are not presented as real store data.

## Measuring triggering with a real agent

```bash
python3 -m skillsmith.cli trigger-eval GENERATED/retail-shelf-audit --output build/trigger          # agent router + neighbouring skills
./scripts/setup-openclaw-dgx.sh                                                                     # once, on the DGX
python3 -m skillsmith.cli trigger-eval GENERATED/retail-shelf-audit --output build/trigger-openclaw \
  --harness openclaw --input-root examples/retail-shelf-audit                                        # full OpenClaw agent turns
```

## Release chain: scanned, evaluated, documented, signed

Mirroring NVIDIA's Verified Skills (Scanned · Evaluated · Signed · Documented)
for an organisation's own skills, entirely on the DGX:

```bash
./scripts/setup-release-tools-dgx.sh     # NVIDIA SkillSpector + OpenSSF model-signing in a Python 3.12 venv
./scripts/init-signing-pki.sh            # local root CA + code-signing certificate, keys kept in ~/.skillsmith-pki
python3 -m skillsmith.cli live-pipeline WORKFLOW.json ... --require-skillspector --pki-dir ~/.skillsmith-pki
```

1. **Scanned** — SkillSmith's rules plus NVIDIA SkillSpector (`--no-llm` static pass); a
   `DO_NOT_INSTALL` recommendation or a fired gate blocks the release.
2. **Evaluated** — fair A/B against ground truth and real-agent triggering (below).
3. **Documented** — `skill-card.md` with NVIDIA's skill card sections plus the measured release evidence.
4. **Signed** — `skill.oms.sig` over the whole directory; `install` verifies it before and after copying,
   and `python3 -m skillsmith.cli verify SKILL --certificate-chain root-cert.pem` checks any copy.

SkillSpector found real problems in the skills SkillSmith originally generated (score 100, `DO_NOT_INSTALL`):
the runner forwarded `OPENAI_API_KEY` to the network, a compiled `.pyc` was left in the skill, and no tool
scope was declared. The runner now has a fixed loopback destination, reads no environment variables and
declares its permissions; the same scan scores 3 (one LOW advisory to review the declared permissions).

## Verified DGX results: one skill blocked, one shipped

Fair A/B on the competition DGX Spark (Qwen3.6-35B-A3B): all conditions get
the same image, request and output format; outputs are scored against exact
ground truth. Skills that ship reference data are also compared with simply
pasting that data into a generic prompt.

| Skill | Baseline | Pasted data | With skill | Triggering | Gate |
| --- | ---: | ---: | ---: | --- | --- |
| `retail-shelf-audit` | 82.7% | – | 82.3% | OpenClaw 36/36 | **BLOCKED** |
| `planogram-compliance` | 11.1% | 72.6% | 78.4% | OpenClaw 35/36 | **PASS → signed, installed** |

On a held-out photo the installed planogram skill found all three real
deviations with one false LOW (task score 88.6%). `./scripts/demo-dgx.sh` runs
the whole blocked → shipped → replay flow. Evidence: `evidence/dgx-2026-09-23/`
(retail) and `evidence/dgx-2026-09-24/` (planogram; `release/` holds the signed skill and its public
root certificate — verify it with `python3 -m skillsmith.cli verify evidence/dgx-2026-09-24/release/planogram-compliance-signed --certificate-chain evidence/dgx-2026-09-24/release/root-cert.pem`). The earlier
"23.6% → 100%" figure (`evidence/dgx-2026-09-20/`) is superseded: that
baseline was never told the output format.
