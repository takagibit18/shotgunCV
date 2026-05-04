from __future__ import annotations

import argparse
import io
from contextlib import redirect_stdout
from pathlib import Path
from time import perf_counter
from typing import Callable

from shotguncv_core.pipeline import (
    EVALUATE_MAX_WORKERS,
    analyze_run,
    estimate_evaluate_task_total,
    evaluate_run,
    generate_run,
    ingest_run,
    plan_run,
    report_run,
)
from shotguncv_core.run_logs import (
    log_run_finished,
    log_run_started,
    log_stage_failed,
    log_stage_finished,
    log_stage_started,
)
from shotguncv_core.run_status import (
    STAGES,
    RunAction,
    StageName,
    cleanup_stages_from,
    first_incomplete_stage,
    mark_done,
    mark_failed,
    mark_queued,
    mark_running,
    now_iso,
    stages_from,
)


COMMAND_DESCRIPTIONS = {
    "run": "Run the full pipeline from CV and JD inputs to report output.",
    "ingest": "Load candidate material and job descriptions into a run workspace.",
    "analyze": "Parse JDs and build candidate and JD profiles.",
    "generate": "Create JD-specific resume variants.",
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
        if command == "run":
            subparser.add_argument(
                "--resume",
                action="store_true",
                help="Continue from the first incomplete stage based on artifacts already in the run directory.",
            )
            subparser.add_argument(
                "--retry-full",
                action="store_true",
                help="Clear post-ingest artifacts and rerun the full pipeline from ingest.",
            )
            subparser.add_argument(
                "--from-stage",
                choices=STAGES,
                required=False,
                help="Start execution at a specific stage after clearing that stage and later artifacts.",
            )
        if command in {"run", "ingest"}:
            subparser.add_argument("--candidate-id", required=False, help="Stable candidate identifier for the run.")
            subparser.add_argument(
                "--cv",
                dest="cv_sources",
                action="append",
                type=Path,
                default=[],
                help="CV file or directory. Supports text, markdown, text PDFs, and images with text sidecars.",
            )
            subparser.add_argument(
                "--jd",
                dest="jd_input_sources",
                action="append",
                type=Path,
                default=[],
                help="JD file or directory. Supports text, markdown, text PDFs, and images with text sidecars.",
            )
            subparser.add_argument("--candidate-resume", type=Path, required=False, help="Legacy path to the base resume markdown.")
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
            subparser.add_argument(
                "--no-vision-fallback",
                action="store_true",
                help="Disable OpenAI-compatible vision fallback for image extraction.",
            )
            subparser.add_argument(
                "--ocr-languages",
                required=False,
                help="Override OCR languages, for example `eng` or `eng+chi_sim`.",
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
                _execute_command(command_name, args, argv or [])
            except Exception as exc:  # noqa: BLE001
                print(str(exc))
                return 1, buffer.getvalue()

    return 0, buffer.getvalue()


def main() -> int:
    exit_code, output = run()
    print(output, end="")
    return exit_code


def _execute_command(command_name: str, args: argparse.Namespace, argv: list[str]) -> None:
    handlers: dict[str, Callable[[argparse.Namespace], str]] = {
        "run": _run_full_pipeline,
        "ingest": _run_ingest,
        "analyze": _run_analyze,
        "generate": _run_generate,
        "evaluate": _run_evaluate,
        "plan": _run_plan,
        "report": _run_report,
    }
    print(handlers[command_name](args) if command_name != "run" else _run_full_pipeline(args, argv))


def _run_ingest(args: argparse.Namespace) -> str:
    started_at = now_iso()
    mark_running(args.run_dir, "ingest", started_at=started_at, action="run")
    try:
        if not getattr(args, "candidate_id", None):
            raise ValueError("`--candidate-id` is required for ingest.")
        candidate_resume = getattr(args, "candidate_resume", None)
        cv_sources = getattr(args, "cv_sources", [])
        jd_files = getattr(args, "jd_files", [])
        jd_input_sources = getattr(args, "jd_input_sources", [])
        if candidate_resume is None and not cv_sources:
            raise ValueError("At least one --cv or --candidate-resume input is required for ingest.")
        if not jd_files and not jd_input_sources:
            raise ValueError("At least one --jd or --jd-file input is required for ingest.")
        manifest_path = ingest_run(
            run_dir=args.run_dir,
            candidate_id=args.candidate_id,
            candidate_resume_path=candidate_resume,
            jd_sources=jd_files,
            config_path=args.config,
            candidate_sources=cv_sources,
            jd_input_sources=jd_input_sources,
            vision_fallback_enabled=False if getattr(args, "no_vision_fallback", False) else None,
            ocr_languages=getattr(args, "ocr_languages", None),
        )
    except Exception as exc:
        mark_failed(args.run_dir, "ingest", exc, started_at=started_at, action="run")
        raise
    mark_done(args.run_dir, "ingest", started_at=started_at, action="run")
    return f"Ingest completed: `{manifest_path}`"


def _run_full_pipeline(args: argparse.Namespace, argv: list[str] | None = None) -> str:
    action: RunAction = "run"
    if getattr(args, "retry_full", False):
        action = "retry_full"
    elif getattr(args, "resume", False):
        action = "resume_failed"

    run_started = perf_counter()
    started_at = mark_queued(args.run_dir, action=action)["started_at"]
    log_run_started(
        args.run_dir,
        trigger_entrypoint="cli",
        argv=["shotguncv", *(argv or [])],
        input_scale=_build_input_scale(args),
    )
    stage = _resolve_start_stage(args)
    if getattr(args, "retry_full", False):
        cleanup_stages_from(args.run_dir, "analyze")
    elif getattr(args, "resume", False) or getattr(args, "from_stage", None):
        cleanup_stages_from(args.run_dir, stage)

    report_path: Path | None = None
    for stage_name in stages_from(stage):
        try:
            mark_running(args.run_dir, stage_name, started_at=started_at, action=action)
            stage_started = log_stage_started(args.run_dir, stage_name)
            if stage_name == "ingest":
                _run_ingest(args)
            elif stage_name == "analyze":
                analyze_run(args.run_dir)
            elif stage_name == "generate":
                generate_run(args.run_dir)
            elif stage_name == "evaluate":
                evaluate_run(args.run_dir)
            elif stage_name == "plan":
                plan_run(args.run_dir)
            elif stage_name == "report":
                report_path = report_run(args.run_dir)
            log_stage_finished(args.run_dir, stage_name, stage_started)
        except Exception as exc:
            log_stage_failed(args.run_dir, stage_name, stage_started, exc)
            mark_failed(args.run_dir, stage_name, exc, started_at=started_at, action=action)
            log_run_finished(args.run_dir, status="failed", duration_ms=int((perf_counter() - run_started) * 1000))
            raise

    mark_done(args.run_dir, "report", started_at=started_at, action=action)
    log_run_finished(args.run_dir, status="done", duration_ms=int((perf_counter() - run_started) * 1000))
    if report_path is None:
        report_path = args.run_dir / "report" / "summary.md"
    return f"Run completed: `{report_path}`"


def _run_analyze(args: argparse.Namespace) -> str:
    analysis = _execute_single_stage(args.run_dir, "analyze", lambda: analyze_run(args.run_dir))
    return f"Analyze completed: candidate=`{analysis.candidate.candidate_id}`, jd_profiles={len(analysis.jd_profiles)}"


def _run_generate(args: argparse.Namespace) -> str:
    generation = _execute_single_stage(args.run_dir, "generate", lambda: generate_run(args.run_dir))
    return f"Generate completed: resume_variants={len(generation.variants)}"


def _run_evaluate(args: argparse.Namespace) -> str:
    total_tasks = estimate_evaluate_task_total(args.run_dir)
    print(f"Evaluate started: total_tasks={total_tasks}, max_workers={EVALUATE_MAX_WORKERS}")
    started = perf_counter()
    ok_count = 0
    fallback_count = 0

    def _progress_callback(payload: dict[str, object]) -> None:
        nonlocal ok_count, fallback_count
        status = str(payload.get("status", "fallback"))
        if status == "ok":
            ok_count += 1
        else:
            fallback_count += 1
        print(
            f"[{payload.get('completed', 0)}/{payload.get('total', 0)}] "
            f"jd={payload.get('jd_id', '')} "
            f"variant={payload.get('variant_id', '')} "
            f"status={status} "
            f"duration_ms={payload.get('duration_ms', 0)}"
        )

    evaluation = _execute_single_stage(args.run_dir, "evaluate", lambda: evaluate_run(args.run_dir, progress_cb=_progress_callback))
    duration_ms = int((perf_counter() - started) * 1000)
    print(f"Evaluate finished: ok={ok_count}, fallback={fallback_count}, duration_ms={duration_ms}")
    return f"Evaluate completed: scorecards={len(evaluation.scorecards)}, gap_maps={len(evaluation.gap_maps)}"


def _run_plan(args: argparse.Namespace) -> str:
    plan_result = _execute_single_stage(args.run_dir, "plan", lambda: plan_run(args.run_dir))
    return f"Plan completed: strategies={len(plan_result.strategies)}"


def _run_report(args: argparse.Namespace) -> str:
    report_path = _execute_single_stage(args.run_dir, "report", lambda: report_run(args.run_dir))
    return f"Report completed: `{report_path}`"


def _resolve_start_stage(args: argparse.Namespace) -> StageName:
    from_stage = getattr(args, "from_stage", None)
    if from_stage:
        return from_stage
    if getattr(args, "resume", False):
        return first_incomplete_stage(args.run_dir)
    if getattr(args, "retry_full", False):
        return "ingest"
    return "ingest"


def _execute_single_stage(run_dir: Path, stage: StageName, callback: Callable[[], object]) -> object:
    started_at = now_iso()
    mark_running(run_dir, stage, started_at=started_at, action="run")
    stage_started = log_stage_started(run_dir, stage)
    try:
        result = callback()
    except Exception as exc:
        log_stage_failed(run_dir, stage, stage_started, exc)
        mark_failed(run_dir, stage, exc, started_at=started_at, action="run")
        raise
    log_stage_finished(run_dir, stage, stage_started)
    mark_done(run_dir, stage, started_at=started_at, action="run")
    return result


def _build_input_scale(args: argparse.Namespace) -> dict[str, int]:
    cv_sources = len(getattr(args, "cv_sources", []) or []) + (1 if getattr(args, "candidate_resume", None) else 0)
    jd_sources = len(getattr(args, "jd_input_sources", []) or []) + len(getattr(args, "jd_files", []) or [])
    return {
        "cv_sources": cv_sources,
        "jd_sources": jd_sources,
        "cli_cv_sources": cv_sources,
        "cli_jd_sources": jd_sources,
    }


if __name__ == "__main__":
    raise SystemExit(main())
