from __future__ import annotations

import json
from pathlib import Path

from shotguncv_cli.main import run


ROOT = Path(__file__).resolve().parents[1]


def test_cli_commands_execute_end_to_end_pipeline(tmp_path: Path) -> None:
    run_dir = tmp_path / "cli-run"
    resume_path = ROOT / "fixtures" / "candidates" / "base_resume.md"
    jd_path = ROOT / "fixtures" / "jds" / "sample_batch.txt"

    commands = [
        [
            "ingest",
            "--run-dir",
            str(run_dir),
            "--candidate-id",
            "cand-001",
            "--candidate-resume",
            str(resume_path),
            "--jd-file",
            str(jd_path),
        ],
        ["analyze", "--run-dir", str(run_dir)],
        ["generate", "--run-dir", str(run_dir)],
        ["evaluate", "--run-dir", str(run_dir)],
        ["plan", "--run-dir", str(run_dir)],
        ["report", "--run-dir", str(run_dir)],
    ]

    for argv in commands:
        exit_code, output = run(argv)
        assert exit_code == 0, output
        assert "placeholder" not in output.lower()

    report_text = (run_dir / "report" / "summary.md").read_text(encoding="utf-8")
    assert "ShotgunCV" in report_text
    assert "Applied AI Engineer" in report_text


def test_cli_ingest_command_writes_manifest_for_file_inputs(tmp_path: Path) -> None:
    run_dir = tmp_path / "cli-run"
    resume_path = ROOT / "fixtures" / "candidates" / "base_resume.md"
    jd_path = ROOT / "fixtures" / "jds" / "sample_batch.txt"

    exit_code, output = run(
        [
            "ingest",
            "--run-dir",
            str(run_dir),
            "--candidate-id",
            "cand-001",
            "--candidate-resume",
            str(resume_path),
            "--jd-file",
            str(jd_path),
        ]
    )

    assert exit_code == 0
    assert "ingest completed" in output.lower()

    manifest = json.loads((run_dir / "ingest" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["candidate_id"] == "cand-001"
    assert manifest["jd_inputs"][0]["source_type"] == "file"
