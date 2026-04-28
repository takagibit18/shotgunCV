from __future__ import annotations

from shotguncv_cli.main import build_parser, run


def test_cli_exposes_v1_command_family() -> None:
    parser = build_parser()

    subcommands = parser._subparsers._group_actions[0].choices.keys()

    assert set(subcommands) == {
        "run",
        "ingest",
        "analyze",
        "generate",
        "evaluate",
        "plan",
        "report",
    }


def test_cli_run_lists_commands() -> None:
    exit_code, output = run(["--help"])

    assert exit_code == 0
    assert "shotguncv" in output
    assert "ingest" in output
    assert "run" in output
    assert "report" in output


def test_cli_run_help_lists_image_extraction_options() -> None:
    exit_code, output = run(["run", "--help"])

    assert exit_code == 0
    assert "--no-vision-fallback" in output
    assert "--ocr-languages" in output


def test_cli_command_descriptions_use_neutral_jd_specific_language() -> None:
    parser = build_parser()
    subcommands = parser._subparsers._group_actions[0].choices

    analyze_help = subcommands["analyze"].description
    generate_help = subcommands["generate"].description

    assert "cluster" not in analyze_help.lower()
    assert "cluster" not in generate_help.lower()
    assert "JD" in analyze_help
    assert "JD-specific" in generate_help


def test_cli_ingest_accepts_multiform_input_flags() -> None:
    parser = build_parser()
    ingest = parser._subparsers._group_actions[0].choices["ingest"]
    option_dests = {action.dest for action in ingest._actions}

    assert {"cv_sources", "jd_input_sources", "candidate_resume", "jd_files"} <= option_dests


def test_cli_run_accepts_multiform_input_flags() -> None:
    parser = build_parser()
    run_command = parser._subparsers._group_actions[0].choices["run"]
    option_dests = {action.dest for action in run_command._actions}

    assert {"cv_sources", "jd_input_sources", "candidate_id", "run_dir"} <= option_dests
