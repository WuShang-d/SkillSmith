# SkillSmith

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
  --input examples/retail-shelf-audit/sample-shelf.pgm \
  --output-dir build/replay \
  --mock-response examples/retail-shelf-audit/fixtures/clear-shelf.skill.txt
```

For DGX inference, omit `--mock-response` and set:

```bash
export OPENAI_BASE_URL=http://127.0.0.1:8000/v1
export OPENAI_MODEL=YOUR_LOCAL_MULTIMODAL_MODEL
export OPENAI_API_KEY=local
```

Do not commit real credentials. Fixture mode validates the pipeline mechanics, not model quality; the final competition benchmark must use captured DGX endpoint results.

## Project layout

- `skillsmith/`: forge, scan, evaluation, install, and CLI implementation.
- `skills-src/skillsmith/`: the reusable meta-skill that teaches an agent to run the pipeline.
- `examples/retail-shelf-audit/`: a complete multimodal example with positive and negative evaluations.
- `tests/`: deterministic release-gate tests.
