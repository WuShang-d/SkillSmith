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
from skillsmith.web import forge_submission


ROOT = Path(__file__).parents[1]
EXAMPLE = ROOT / "examples/retail-shelf-audit"


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
        spec = json.loads((EXAMPLE / "workflow.json").read_text(encoding="utf-8"))
        spec["evals"] = [spec["evals"][0], spec["evals"][2]]
        payload = {
            "spec": spec,
            "fixtures": {
                "clear-shelf": {
                    "baseline": (EXAMPLE / "fixtures/clear-shelf.baseline.txt").read_text(encoding="utf-8"),
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
        spec = json.loads((EXAMPLE / "workflow.json").read_text(encoding="utf-8"))
        spec["evals"] = [spec["evals"][0], spec["evals"][2]]
        payload = {
            "spec": spec,
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

            def fake_urlopen(request, timeout):
                request_body = json.loads(request.data)
                system = request_body["messages"][0]["content"]
                if system.startswith("Follow the Agent Skill"):
                    content = json.dumps({
                        "image_quality": "clear",
                        "sku_facings": [],
                        "empty_gaps": [],
                        "uncertainties": [],
                    })
                else:
                    content = "The shelf looks mostly full."
                body = {"choices": [{"message": {"content": content}}]}
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
            result = evaluate_fixtures(generated, capture_dir)
            self.assertEqual(result["verdict"], "pass")
            self.assertIn("Live mode used raw outputs", benchmark_markdown(result, spec.name, mode="live"))


if __name__ == "__main__":
    unittest.main()
