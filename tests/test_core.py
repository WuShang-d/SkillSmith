import json
import tempfile
import unittest
from pathlib import Path

from skillsmith.evaluate import evaluate_fixtures
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


if __name__ == "__main__":
    unittest.main()
