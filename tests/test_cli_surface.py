from __future__ import annotations

from shotguncv_cli.main import build_parser, run


def test_cli_exposes_v1_command_family() -> None:
    parser = build_parser()

    subcommands = parser._subparsers._group_actions[0].choices.keys()

    assert set(subcommands) == {
        "ingest",
        "analyze",
        "generate",
        "evaluate",
        "plan",
        "report",
        "run",
    }


def test_cli_run_lists_commands() -> None:
    exit_code, output = run(["--help"])

    assert exit_code == 0
    assert "shotguncv" in output
    assert "ingest" in output
    assert "report" in output
    assert "run" in output


def test_cli_command_descriptions_use_neutral_jd_specific_language() -> None:
    parser = build_parser()
    subcommands = parser._subparsers._group_actions[0].choices

    analyze_help = subcommands["analyze"].description
    generate_help = subcommands["generate"].description

    assert "cluster" not in analyze_help.lower()
    assert "cluster" not in generate_help.lower()
    assert "JD" in analyze_help
    assert "JD-specific" in generate_help
