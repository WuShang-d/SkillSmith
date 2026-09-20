from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from .evaluate import benchmark_markdown, evaluate_fixtures
from .forge import forge
from .install import install
from .security import report, scan
from .spec import SpecError, load_spec


def _json(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def cmd_forge(args: argparse.Namespace) -> int:
    target = forge(load_spec(args.workflow), args.output, force=args.force)
    _json({"status": "ok", "skill": str(target)})
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    result = report(scan(args.skill))
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _json(result)
    return int(result["verdict"] != "pass")


def cmd_evaluate(args: argparse.Namespace) -> int:
    result = evaluate_fixtures(args.skill, args.fixtures)
    skill_name = Path(args.skill).resolve().name
    benchmark = benchmark_markdown(result, skill_name)
    output = Path(args.output) if args.output else Path(args.skill) / "BENCHMARK.md"
    output.write_text(benchmark, encoding="utf-8")
    _json(result)
    return int(result["verdict"] != "pass")


def cmd_install(args: argparse.Namespace) -> int:
    target = install(args.skill, args.destination, force=args.force)
    _json({"status": "ok", "installed": str(target)})
    return 0


def cmd_pipeline(args: argparse.Namespace) -> int:
    spec = load_spec(args.workflow)
    target = forge(spec, args.output, force=args.force)
    security_result = report(scan(target))
    (target / "SECURITY_REPORT.json").write_text(
        json.dumps(security_result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if security_result["verdict"] != "pass":
        _json({"status": "blocked", "stage": "security", **security_result})
        return 2
    evaluation = evaluate_fixtures(target, args.fixtures)
    (target / "BENCHMARK.md").write_text(benchmark_markdown(evaluation, spec.name), encoding="utf-8")
    if evaluation["verdict"] != "pass":
        _json({"status": "blocked", "stage": "evaluation", **evaluation})
        return 3
    installed = install(target, args.destination, force=args.force)
    _json({
        "status": "ok",
        "generated": str(target),
        "security": security_result["verdict"],
        "evaluation": evaluation["verdict"],
        "installed": str(installed),
    })
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skillsmith", description="Forge successful workflows into verified Agent Skills")
    sub = parser.add_subparsers(dest="command", required=True)

    forge_parser = sub.add_parser("forge", help="generate a skill from workflow JSON")
    forge_parser.add_argument("workflow")
    forge_parser.add_argument("--output", required=True)
    forge_parser.add_argument("--force", action="store_true")
    forge_parser.set_defaults(func=cmd_forge)

    scan_parser = sub.add_parser("scan", help="scan a generated skill")
    scan_parser.add_argument("skill")
    scan_parser.add_argument("--output")
    scan_parser.set_defaults(func=cmd_scan)

    eval_parser = sub.add_parser("evaluate", help="run deterministic A/B fixture evaluation")
    eval_parser.add_argument("skill")
    eval_parser.add_argument("--fixtures", required=True)
    eval_parser.add_argument("--output")
    eval_parser.set_defaults(func=cmd_evaluate)

    install_parser = sub.add_parser("install", help="install a verified skill into an agent workspace")
    install_parser.add_argument("skill")
    install_parser.add_argument("--destination", required=True)
    install_parser.add_argument("--force", action="store_true")
    install_parser.set_defaults(func=cmd_install)

    pipeline = sub.add_parser("pipeline", help="forge, scan, evaluate, and install")
    pipeline.add_argument("workflow")
    pipeline.add_argument("--fixtures", required=True)
    pipeline.add_argument("--output", required=True)
    pipeline.add_argument("--destination", required=True)
    pipeline.add_argument("--force", action="store_true")
    pipeline.set_defaults(func=cmd_pipeline)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (SpecError, ValueError, FileExistsError, OSError, json.JSONDecodeError) as exc:
        print(f"skillsmith: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
