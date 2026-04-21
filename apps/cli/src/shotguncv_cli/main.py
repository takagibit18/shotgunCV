from __future__ import annotations

import argparse
import io
from contextlib import redirect_stdout


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
            print(f"{command_name}: scaffold placeholder")

    return 0, buffer.getvalue()


def main() -> int:
    exit_code, output = run()
    print(output, end="")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
