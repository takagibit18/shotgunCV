from __future__ import annotations

import argparse
import io
from contextlib import redirect_stdout
from pathlib import Path
from typing import Callable

from shotguncv_core.pipeline import (
    analyze_run,
    evaluate_run,
    generate_run,
    ingest_run,
    plan_run,
    report_run,
)


COMMAND_DESCRIPTIONS = {
    "ingest": "Load candidate material and job descriptions into a run workspace.",
    "analyze": "Parse JDs and build candidate and cluster views.",
    "generate": "Create cluster and JD-specific resume variants.",
    "evaluate": "Run rules and judge-oriented evaluation passes.",
    "plan": "Produce ranked application strategy recommendations.",
    "report": "Render run artifacts into readable summaries.",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shotguncv",
        description="Pipeline-first Resume Ops CLI for high-volume applications.",
    )
    subparsers = parser.add_subparsers(dest="command", required=False)

    for command, description in COMMAND_DESCRIPTIONS.items():
        subparser = subparsers.add_parser(command, help=description, description=description)
        subparser.set_defaults(command_name=command)
        subparser.add_argument("--run-dir", type=Path, required=True, help="Workspace directory for staged artifacts.")
        if command == "ingest":
            subparser.add_argument("--candidate-id", required=True, help="Stable candidate identifier for the run.")
            subparser.add_argument("--candidate-resume", type=Path, required=True, help="Path to the base resume markdown.")
            subparser.add_argument(
                "--jd-file",
                dest="jd_files",
                action="append",
                type=Path,
                default=[],
                help="Path to a JD batch file. May be passed multiple times.",
            )
            subparser.add_argument(
                "--config",
                type=Path,
                required=False,
                help="Optional run config JSON to snapshot into the run workspace.",
            )

    return parser


def run(argv: list[str] | None = None) -> tuple[int, str]:
    parser = build_parser()
    buffer = io.StringIO()

    with redirect_stdout(buffer):
        try:
            args = parser.parse_args(argv)
        except SystemExit as exc:
            return int(exc.code), buffer.getvalue()

        command_name = getattr(args, "command_name", None)
        if command_name is None:
            parser.print_help()
        else:
            try:
                _execute_command(command_name, args)
            except Exception as exc:  # noqa: BLE001
                print(str(exc))
                return 1, buffer.getvalue()

    return 0, buffer.getvalue()


def main() -> int:
    exit_code, output = run()
    print(output, end="")
    return exit_code


def _execute_command(command_name: str, args: argparse.Namespace) -> None:
    handlers: dict[str, Callable[[argparse.Namespace], str]] = {
        "ingest": _run_ingest,
        "analyze": _run_analyze,
        "generate": _run_generate,
        "evaluate": _run_evaluate,
        "plan": _run_plan,
        "report": _run_report,
    }
    print(handlers[command_name](args))


def _run_ingest(args: argparse.Namespace) -> str:
    if not args.jd_files:
        raise ValueError("At least one --jd-file input is required for ingest.")
    manifest_path = ingest_run(
        run_dir=args.run_dir,
        candidate_id=args.candidate_id,
        candidate_resume_path=args.candidate_resume,
        jd_sources=args.jd_files,
        config_path=args.config,
    )
    return f"Ingest completed: `{manifest_path}`"


def _run_analyze(args: argparse.Namespace) -> str:
    analysis = analyze_run(args.run_dir)
    return f"Analyze completed: candidate=`{analysis.candidate.candidate_id}`, jd_profiles={len(analysis.jd_profiles)}"


def _run_generate(args: argparse.Namespace) -> str:
    generation = generate_run(args.run_dir)
    return f"Generate completed: resume_variants={len(generation.variants)}"


def _run_evaluate(args: argparse.Namespace) -> str:
    evaluation = evaluate_run(args.run_dir)
    return f"Evaluate completed: scorecards={len(evaluation.scorecards)}, gap_maps={len(evaluation.gap_maps)}"


def _run_plan(args: argparse.Namespace) -> str:
    plan_result = plan_run(args.run_dir)
    return f"Plan completed: strategies={len(plan_result.strategies)}"


def _run_report(args: argparse.Namespace) -> str:
    report_path = report_run(args.run_dir)
    return f"Report completed: `{report_path}`"


if __name__ == "__main__":
    raise SystemExit(main())
