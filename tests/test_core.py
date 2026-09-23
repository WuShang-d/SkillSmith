import json
import base64
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skillsmith.evaluate import benchmark_markdown, evaluate_fixtures
from skillsmith.endpoint import validate_endpoint
from skillsmith.endpoint import capture_ab
from skillsmith.forge import forge
from skillsmith.install import install
from skillsmith.security import report, scan
from skillsmith.spec import SpecError, load_spec
from skillsmith.trigger import evaluate_triggers, user_message
from skillsmith.web import forge_submission


ROOT = Path(__file__).parents[1]
EXAMPLE = ROOT / "examples/retail-shelf-audit"


def web_spec() -> dict:
    """The guided UI has no scorer, so it submits one positive and one negative case."""
    spec = json.loads((EXAMPLE / "workflow.json").read_text(encoding="utf-8"))
    spec.pop("scorer")
    cases = {case["id"]: case for case in spec["evals"]}
    positive = {k: v for k, v in cases["clear-shelf"].items() if k != "ground_truth"}
    spec["evals"] = [positive, cases["marketing-copy"]]
    return spec


class SkillSmithTests(unittest.TestCase):
    def test_pipeline_components(self):
        spec = load_spec(EXAMPLE / "workflow.json")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            generated = forge(spec, tmp_path / "generated")
            self.assertTrue((generated / "SKILL.md").is_file())
            self.assertEqual(report(scan(generated))["verdict"], "pass")
            result = evaluate_fixtures(generated, EXAMPLE / "fixtures")
            self.assertEqual(result["verdict"], "pass")
            self.assertGreater(result["skill_score"], result["baseline_score"])
            installed = install(generated, tmp_path / "workspace/skills")
            self.assertTrue((installed / "SKILL.md").is_file())

    def test_scanner_blocks_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "SKILL.md").write_text("token = '123456789-secret'\n", encoding="utf-8")
            result = report(scan(root))
            self.assertEqual(result["verdict"], "fail")
            self.assertEqual(result["counts"]["high"], 1)

    def test_generated_runner_rejects_contract_violation(self):
        spec = load_spec(EXAMPLE / "workflow.json")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            generated = forge(spec, tmp_path / "generated")
            invalid = tmp_path / "invalid.json"
            invalid.write_text('{"renamed_field": []}', encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(generated / "scripts/run.py"),
                    "--input",
                    str(EXAMPLE / "shelf-clear.png"),
                    "--output-dir",
                    str(tmp_path / "result"),
                    "--mock-response",
                    str(invalid),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing fields", result.stderr)

    def test_requires_negative_eval(self):
        data = json.loads((EXAMPLE / "workflow.json").read_text(encoding="utf-8"))
        data["evals"] = [case for case in data["evals"] if case["should_trigger"]]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "invalid.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(SpecError):
                load_spec(path)

    def test_guided_web_submission(self):
        payload = {
            "spec": web_spec(),
            "fixtures": {
                "clear-shelf": {
                    "baseline": "The shelf looks mostly full. There may be a gap.",
                    "skill": (EXAMPLE / "fixtures/clear-shelf.skill.txt").read_text(encoding="utf-8"),
                }
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            result = forge_submission(payload, Path(tmp))
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["security"], "pass")
            self.assertEqual(result["evaluation"]["verdict"], "pass")
            self.assertTrue(Path(result["installed"]).is_dir())

    def test_endpoint_defaults_to_local_only(self):
        self.assertEqual(validate_endpoint("http://127.0.0.1:8000/v1"), "http://127.0.0.1:8000/v1")
        with self.assertRaises(ValueError):
            validate_endpoint("https://example.com/v1")
        self.assertEqual(
            validate_endpoint("https://example.com/v1", allow_remote=True),
            "https://example.com/v1",
        )
        with self.assertRaises(ValueError):
            validate_endpoint("https://secret@example.com/v1", allow_remote=True)

    def test_web_live_mode_rejects_remote_endpoint(self):
        payload = {
            "spec": web_spec(),
            "live": {
                "image": {
                    "name": "shelf.pgm",
                    "data": base64.b64encode((EXAMPLE / "shelf-clear.png").read_bytes()).decode("ascii"),
                },
                "base_url": "https://example.com/v1",
                "model": "example-model",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "non-local endpoint"):
                forge_submission(payload, Path(tmp))

    def test_live_capture_writes_baseline_and_skill_evidence(self):
        spec = load_spec(EXAMPLE / "workflow.json")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            generated = forge(spec, tmp_path / "generated")

            prompts = {case["prompt"]: case["id"] for case in spec.data["evals"]}
            systems = []

            def fake_urlopen(request, timeout):
                request_body = json.loads(request.data)
                system = request_body["messages"][0]["content"]
                systems.append(system)
                case_id = prompts[request_body["messages"][1]["content"][0]["text"]]
                mode = "skill" if system.startswith("Follow the Agent Skill") else "baseline"
                content = (EXAMPLE / f"fixtures/{case_id}.{mode}.txt").read_text(encoding="utf-8")
                body = {"choices": [{"message": {"content": content}}], "usage": {"prompt_tokens": 900, "completion_tokens": 300}}
                return io.BytesIO(json.dumps(body).encode("utf-8"))

            capture_dir = tmp_path / "capture"
            with patch("skillsmith.endpoint.urllib.request.urlopen", side_effect=fake_urlopen):
                manifest = capture_ab(
                    generated,
                    EXAMPLE,
                    capture_dir,
                    base_url="http://127.0.0.1:8000/v1",
                    model="local-test-model",
                )
            self.assertEqual(manifest["mode"], "live")
            self.assertEqual(len(manifest["captures"]), 4)
            self.assertTrue((capture_dir / "CAPTURE.json").is_file())
            baseline = next(system for system in systems if not system.startswith("Follow the Agent Skill"))
            for field in ("image_quality", "sku_facings", "empty_gaps", "uncertainties", "Shelf 1 is the top shelf"):
                self.assertIn(field, baseline)
            self.assertNotIn("最前排", baseline)
            self.assertEqual(manifest["captures"][0]["completion_tokens"], 300)
            result = evaluate_fixtures(generated, capture_dir)
            self.assertEqual(result["verdict"], "pass")
            self.assertEqual(result["primary_metric"], "task")
            self.assertEqual(result["efficiency"]["skill"]["mean_completion_tokens"], 300)
            self.assertIn("Live mode: raw outputs", benchmark_markdown(result, spec.name, mode="live"))

    def test_scorer_penalises_stacked_units_and_tote_items(self):
        spec = load_spec(EXAMPLE / "workflow.json")
        cases = {case["id"]: case for case in spec.data["evals"]}
        with tempfile.TemporaryDirectory() as tmp:
            generated = forge(spec, Path(tmp) / "generated")
            from skillsmith.evaluate import load_scorer
            score = load_scorer(generated)
        truth = cases["clear-shelf"]["ground_truth"]
        correct = json.loads((EXAMPLE / "fixtures/clear-shelf.skill.txt").read_text(encoding="utf-8"))
        self.assertEqual(score(correct, truth)["facing_accuracy"], 1.0)
        stacked = json.loads(json.dumps(correct))
        stacked["sku_facings"][0]["facings"] = 14
        self.assertLess(score(stacked, truth)["facing_accuracy"], 1.0)
        occluded = json.loads((EXAMPLE / "fixtures/occluded-shelf.skill.txt").read_text(encoding="utf-8"))
        occluded_truth = cases["occluded-shelf"]["ground_truth"]
        self.assertEqual(score(occluded, occluded_truth)["facing_accuracy"], 1.0)
        occluded["sku_facings"].append({"shelf": 3, "sku": "red can (in tote)", "facings": 2})
        self.assertLess(score(occluded, occluded_truth)["facing_accuracy"], 1.0)
        self.assertEqual(score(occluded, occluded_truth)["occlusion_reported"], 1.0)

    def test_trigger_eval_counts_only_reads_of_this_skill(self):
        spec = load_spec(EXAMPLE / "workflow.json")
        cases = {user_message(case): case for case in spec.data["evals"]}
        with tempfile.TemporaryDirectory() as tmp:
            generated = forge(spec, Path(tmp) / "generated")

            def fake_urlopen(request, timeout):
                request_body = json.loads(request.data)
                self.assertIn("tao-generate-image-grounding", request_body["messages"][0]["content"])
                case = cases[request_body["messages"][1]["content"]]
                if case["id"] == "negative-face":
                    target = "/workspace/skills/local-pedestrian-detector/SKILL.md"
                elif case["should_trigger"]:
                    target = "/workspace/skills/retail-shelf-audit/SKILL.md"
                else:
                    target = None
                message = {"role": "assistant", "content": None if target else "Direct answer."}
                if target:
                    message["tool_calls"] = [{
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": json.dumps({"path": target})},
                    }]
                return io.BytesIO(json.dumps({"choices": [{"message": message}]}).encode("utf-8"))

            with patch("skillsmith.endpoint.urllib.request.urlopen", side_effect=fake_urlopen):
                result = evaluate_triggers(
                    generated,
                    Path(tmp) / "trigger",
                    base_url="http://127.0.0.1:8000/v1",
                    model="local-test-model",
                    repeats=2,
                )
            self.assertEqual(result["runs"], 2 * len(cases))
            self.assertEqual(result["accuracy"], 1.0)
            self.assertEqual(result["per_case"]["negative-face"]["selected"], ["local-pedestrian-detector"])
            self.assertTrue((Path(tmp) / "trigger/TRIGGER.json").is_file())
            evaluation = evaluate_fixtures(generated, EXAMPLE / "fixtures", trigger_result=result)
            self.assertEqual(evaluation["trigger"]["method"], "agent-router")

    def test_openclaw_transcript_detects_both_skill_load_paths(self):
        import sqlite3
        from skillsmith.openclaw_trigger import SKILL_READ, stage_attachments, transcript_skill_reads

        def call(name, arguments):
            return json.dumps({"message": {"role": "assistant", "content": [
                {"type": "toolCall", "name": name, "arguments": arguments}]}})

        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "agent.sqlite"
            connection = sqlite3.connect(database)
            connection.execute("create table transcript_events (session_id text, seq int, event_json text)")
            connection.executemany("insert into transcript_events values (?, ?, ?)", [
                ("a", 1, call("view_image", {"path": "inbox/x.png"})),
                ("a", 2, call("skill_workshop", {"action": "read", "skill_name": "retail-shelf-audit"})),
                ("b", 1, call("read", {"path": "~/.openclaw-x/workspace/skills/weather/SKILL.md"})),
                ("b", 2, call("read", {"path": "notes.md"})),
            ])
            connection.commit()
            connection.close()
            first = transcript_skill_reads(database, "a")
            self.assertEqual(SKILL_READ.search(first[0]).group(1), "retail-shelf-audit")
            self.assertEqual(SKILL_READ.search(transcript_skill_reads(database, "b")[0]).group(1), "weather")

            inbox = Path(tmp) / "inbox"
            case = {"id": "negative-poster", "should_trigger": False}
            stage_attachments(case, "[附件: inbox/new-cola.png] 设计海报", inbox, EXAMPLE)
            staged = (inbox / "new-cola.png").read_bytes()
            self.assertTrue(staged.startswith(b"\x89PNG"))
            self.assertNotEqual(staged, (EXAMPLE / "shelf-clear.png").read_bytes())


if __name__ == "__main__":
    unittest.main()
