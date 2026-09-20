---
name: skillsmith
description: Turn a demonstrated successful multimodal agent workflow into a reusable Agent Skill package with trigger boundaries, an executable runner, security checks, A/B evaluations, and installation. Use when users want to productize, package, verify, or reproduce an agent workflow as a skill; not for ordinary one-off task execution.
---

# SkillSmith

Forge the user's validated workflow without inventing missing technical facts. Preserve the successful path, make its inputs and outputs explicit, and keep credentials outside generated files.

## Workflow

1. Collect or reconstruct a workflow JSON conforming to [references/workflow-schema.md](references/workflow-schema.md). A successful run summary, positive triggers, negative triggers, steps, guardrails, output contract, and positive plus negative evaluations are required.
2. Validate and generate the candidate skill:

   ```bash
   python3 -m skillsmith.cli forge WORKFLOW.json --output GENERATED_DIR
   ```

3. Run the security gate. Treat critical or high findings as release blockers; correct the source workflow or generated implementation instead of suppressing them.

   ```bash
   python3 -m skillsmith.cli scan GENERATED_DIR/SKILL_NAME
   ```

4. Evaluate trigger selection and output-contract adherence with distinct baseline and with-skill results. Fixture mode proves pipeline mechanics only; before judging, replace fixtures with outputs captured from the DGX model endpoint.

   ```bash
   python3 -m skillsmith.cli evaluate GENERATED_DIR/SKILL_NAME --fixtures FIXTURE_DIR
   ```

   On DGX Spark, use `live-pipeline` to capture both conditions from the same local model before scoring. Read [references/workflow-schema.md](references/workflow-schema.md) and add an `input` path to each positive case. Non-local endpoints are rejected unless the user explicitly authorizes image transmission.

5. Install only after both gates pass. Use a project-local workspace destination unless the user explicitly chooses a global agent directory.

   ```bash
   python3 -m skillsmith.cli install GENERATED_DIR/SKILL_NAME --destination WORKSPACE_SKILLS_DIR
   ```

For a repeatable demo, prefer the atomic `pipeline` command. It stops before installation if scanning or evaluation fails.

## Boundaries

- Do not include API keys, tokens, passwords, private input data, or absolute user-home paths in a generated skill.
- Do not claim NVIDIA verification or cryptographic signing. SkillSmith's local scan and benchmark are distinct from NVIDIA's official publication pipeline.
- Do not infer steps that were not evidenced by the successful run. Record unresolved gaps and ask for missing facts.
- Keep official third-party skills unchanged; put environment adaptations and business orchestration in the new skill.
- Always include at least one negative trigger case whose correct behavior is not invoking the skill.
