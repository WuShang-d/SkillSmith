from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .evaluate import benchmark_markdown, evaluate_fixtures
from .endpoint import capture_ab
from .forge import forge
from .install import install
from .security import report, scan
from .openclaw_trigger import evaluate_openclaw_triggers
from .trigger import evaluate_triggers
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


def _load_trigger(path: str | None) -> dict[str, object] | None:
    return json.loads(Path(path).read_text(encoding="utf-8")) if path else None


def cmd_evaluate(args: argparse.Namespace) -> int:
    result = evaluate_fixtures(args.skill, args.fixtures, trigger_result=_load_trigger(args.trigger_result))
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


def _capture(args: argparse.Namespace, skill: str | Path, output: str | Path) -> dict[str, object]:
    return capture_ab(
        skill,
        args.input_root,
        output,
        base_url=args.base_url or os.environ.get("OPENAI_BASE_URL", ""),
        model=args.model or os.environ.get("OPENAI_MODEL", ""),
        api_key=os.environ.get("OPENAI_API_KEY", "local"),
        allow_remote=args.allow_remote_endpoint,
        timeout=args.timeout,
    )


def _triggers(args: argparse.Namespace, skill: str | Path, output: str | Path) -> dict[str, object]:
    if getattr(args, "harness", "router") == "openclaw":
        if not args.input_root:
            raise ValueError("--harness openclaw requires --input-root to stage attachments")
        return evaluate_openclaw_triggers(
            skill,
            output,
            input_root=args.input_root,
            profile=args.openclaw_profile,
            repeats=args.trigger_repeats,
        )
    return evaluate_triggers(
        skill,
        output,
        base_url=args.base_url or os.environ.get("OPENAI_BASE_URL", ""),
        model=args.model or os.environ.get("OPENAI_MODEL", ""),
        api_key=os.environ.get("OPENAI_API_KEY", "local"),
        repeats=args.trigger_repeats,
        allow_remote=args.allow_remote_endpoint,
    )


def cmd_trigger_eval(args: argparse.Namespace) -> int:
    result = _triggers(args, args.skill, args.output)
    _json({key: value for key, value in result.items() if key != "details"})
    return 0


def cmd_capture(args: argparse.Namespace) -> int:
    _json(_capture(args, args.skill, args.output))
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


def cmd_live_pipeline(args: argparse.Namespace) -> int:
    spec = load_spec(args.workflow)
    target = forge(spec, args.output, force=args.force)
    security_result = report(scan(target))
    (target / "SECURITY_REPORT.json").write_text(
        json.dumps(security_result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if security_result["verdict"] != "pass":
        _json({"status": "blocked", "stage": "security", **security_result})
        return 2
    capture = _capture(args, target, args.capture_dir)
    triggers = _triggers(args, target, args.capture_dir)
    evaluation = evaluate_fixtures(target, args.capture_dir, trigger_result=triggers)
    (target / "BENCHMARK.md").write_text(benchmark_markdown(evaluation, spec.name, mode="live"), encoding="utf-8")
    if evaluation["verdict"] != "pass":
        _json({"status": "blocked", "stage": "evaluation", "capture": capture, **evaluation})
        return 3
    installed = install(target, args.destination, force=args.force)
    _json({
        "status": "ok",
        "generated": str(target),
        "security": security_result["verdict"],
        "capture": capture,
        "evaluation": evaluation,
        "installed": str(installed),
    })
    return 0


def _add_endpoint_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input-root", required=True)
    parser.add_argument("--base-url")
    parser.add_argument("--model")
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--allow-remote-endpoint", action="store_true")


def _add_trigger_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--harness",
        choices=("router", "openclaw"),
        default="router",
        help="router: model decides from a skill catalogue via tool calls; openclaw: full OpenClaw agent turns",
    )
    parser.add_argument("--input-root", help="directory holding eval inputs (openclaw harness)")
    parser.add_argument("--openclaw-profile", default="skillsmith-eval")
    parser.add_argument("--base-url")
    parser.add_argument("--model")
    parser.add_argument("--trigger-repeats", type=int, default=3)
    parser.add_argument("--allow-remote-endpoint", action="store_true")


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
    eval_parser.add_argument("--trigger-result", help="TRIGGER.json from trigger-eval; otherwise a lexical estimate is reported")
    eval_parser.set_defaults(func=cmd_evaluate)

    trigger_parser = sub.add_parser("trigger-eval", help="measure skill selection with the real model behind an agent-style router")
    trigger_parser.add_argument("skill")
    trigger_parser.add_argument("--output", required=True)
    _add_trigger_arguments(trigger_parser)
    trigger_parser.set_defaults(func=cmd_trigger_eval)

    install_parser = sub.add_parser("install", help="install a verified skill into an agent workspace")
    install_parser.add_argument("skill")
    install_parser.add_argument("--destination", required=True)
    install_parser.add_argument("--force", action="store_true")
    install_parser.set_defaults(func=cmd_install)

    capture_parser = sub.add_parser("capture", help="capture live baseline and with-skill model outputs")
    capture_parser.add_argument("skill")
    capture_parser.add_argument("--output", required=True)
    _add_endpoint_arguments(capture_parser)
    capture_parser.set_defaults(func=cmd_capture)

    pipeline = sub.add_parser("pipeline", help="forge, scan, evaluate fixture outputs, and install")
    pipeline.add_argument("workflow")
    pipeline.add_argument("--fixtures", required=True)
    pipeline.add_argument("--output", required=True)
    pipeline.add_argument("--destination", required=True)
    pipeline.add_argument("--force", action="store_true")
    pipeline.set_defaults(func=cmd_pipeline)

    live = sub.add_parser("live-pipeline", help="forge, scan, capture live A/B outputs, evaluate, and install")
    live.add_argument("workflow")
    live.add_argument("--capture-dir", required=True)
    live.add_argument("--output", required=True)
    live.add_argument("--destination", required=True)
    live.add_argument("--force", action="store_true")
    live.add_argument("--trigger-repeats", type=int, default=3)
    _add_endpoint_arguments(live)
    live.set_defaults(func=cmd_live_pipeline)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (SpecError, ValueError, RuntimeError, FileExistsError, OSError, json.JSONDecodeError) as exc:
        print(f"skillsmith: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
