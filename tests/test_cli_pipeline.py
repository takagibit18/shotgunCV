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
        if argv[0] == "evaluate":
            assert "Evaluate started:" in output
            assert "Evaluate finished:" in output
            assert "[1/" in output

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


def test_cli_ingest_accepts_cv_and_jd_directories_from_web_draft(tmp_path: Path) -> None:
    run_dir = tmp_path / "draft-run"
    cv_dir = tmp_path / "input_files" / "cv"
    jd_dir = tmp_path / "input_files" / "jd"
    cv_dir.mkdir(parents=True)
    jd_dir.mkdir(parents=True)
    (cv_dir / "resume.md").write_text("Built AI workflow tools.", encoding="utf-8")
    (cv_dir / "notes.txt").write_text("Prefers product AI roles.", encoding="utf-8")
    (jd_dir / "jd-a.txt").write_text("AI Product Engineer\nRequires Python.", encoding="utf-8")
    (jd_dir / "jd-b.md").write_text("Evaluation Engineer\nRequires eval design.", encoding="utf-8")

    exit_code, output = run(
        [
            "ingest",
            "--run-dir",
            str(run_dir),
            "--candidate-id",
            "cand-001",
            "--cv",
            str(cv_dir),
            "--jd",
            str(jd_dir),
        ]
    )

    assert exit_code == 0, output
    manifest = json.loads((run_dir / "ingest" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["candidate_resume_text"] == "Built AI workflow tools.\n\nPrefers product AI roles."
    assert [item["source_value"] for item in manifest["candidate_inputs"]] == [
        str(cv_dir / "resume.md"),
        str(cv_dir / "notes.txt"),
    ]
    assert [item["source_value"] for item in manifest["jd_inputs"]] == [
        str(jd_dir / "jd-a.txt"),
        str(jd_dir / "jd-b.md"),
    ]


def test_cli_run_executes_from_cv_and_jd_directories(tmp_path: Path) -> None:
    run_dir = tmp_path / "one-command-run"
    cv_dir = tmp_path / "input_files" / "cv"
    jd_dir = tmp_path / "input_files" / "jd"
    cv_dir.mkdir(parents=True)
    jd_dir.mkdir(parents=True)
    (cv_dir / "resume.md").write_text((ROOT / "fixtures" / "candidates" / "base_resume.md").read_text(encoding="utf-8"), encoding="utf-8")
    (jd_dir / "sample_batch.txt").write_text((ROOT / "fixtures" / "jds" / "sample_batch.txt").read_text(encoding="utf-8"), encoding="utf-8")

    exit_code, output = run(
        [
            "run",
            "--run-dir",
            str(run_dir),
            "--candidate-id",
            "cand-001",
            "--cv",
            str(cv_dir),
            "--jd",
            str(jd_dir),
        ]
    )

    assert exit_code == 0, output
    assert "Run completed" in output
    assert (run_dir / "report" / "summary.md").exists()
