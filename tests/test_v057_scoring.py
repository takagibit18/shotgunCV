from __future__ import annotations

import json
from pathlib import Path

from shotguncv_cli.main import run


def test_requirement_matrix_blocks_missing_hard_gate_and_skips_costly_stages(tmp_path: Path) -> None:
    run_dir = tmp_path / "hard-gate-run"
    cv_path = tmp_path / "resume.md"
    jd_path = tmp_path / "jd.txt"
    config_path = _write_deterministic_config(tmp_path)
    cv_path.write_text(
        "- Built Python automation tools\n"
        "- Delivered product-facing LLM workflow prototypes\n",
        encoding="utf-8",
    )
    jd_path.write_text(
        "Title: Regulated AI Engineer\n"
        "Company: Example\n"
        "Body:\n"
        "- 本科及以上学历，计算机相关专业\n"
        "- 负责风控项目落地\n",
        encoding="utf-8",
    )

    exit_code, output = run(
        [
            "run",
            "--run-dir",
            str(run_dir),
            "--candidate-id",
            "cand-001",
            "--cv",
            str(cv_path),
            "--jd",
            str(jd_path),
            "--config",
            str(config_path),
        ]
    )

    assert exit_code == 0, output
    matrix = json.loads((run_dir / "analyze" / "requirement_matrix.json").read_text(encoding="utf-8"))
    gates = json.loads((run_dir / "analyze" / "preflight_gates.json").read_text(encoding="utf-8"))
    variants = json.loads((run_dir / "generate" / "resume_variants.json").read_text(encoding="utf-8"))
    scorecards = json.loads((run_dir / "evaluate" / "scorecards.json").read_text(encoding="utf-8"))

    hard_gate = next(item for item in matrix if "学历" in item["requirement_text"])
    assert hard_gate["tier"] == "hard_gate"
    assert hard_gate["evidence_status"] == "missing"
    assert hard_gate["fabrication_policy"] == "never_fabricate"
    assert all("项目" not in item["requirement_text"] for item in matrix)

    assert gates == [
        {
            "jd_id": "jd-001",
            "status": "pass",
            "reasons": ["hard_gate_unverified: 本科及以上学历，计算机相关专业"],
            "skipped_stages": [],
            "user_action": "",
        }
    ]
    assert variants
    assert scorecards[0]["final_decision_source"] == "v0.5.7-conservative-fusion+guardrail"
    assert scorecards[0]["gate_status"] == "pass"
    assert "score_conflict" in scorecards[0]["guardrail_flags"]
    assert "needs_review" in scorecards[0]["guardrail_flags"]
    assert round(scorecards[0]["llm_overall_score"] - scorecards[0]["final_overall_score"], 2) <= 0.30


def test_preflight_gate_skips_only_review_jd_and_uses_three_scores_for_passed_jd(tmp_path: Path) -> None:
    run_dir = tmp_path / "mixed-run"
    cv_path = tmp_path / "resume.md"
    jd_path = tmp_path / "jds.txt"
    config_path = _write_deterministic_config(tmp_path)
    cv_path.write_text(
        "- Bachelor degree in Computer Science\n"
        "- Built Python automation tools\n"
        "- Delivered product-facing LLM workflow prototypes\n",
        encoding="utf-8",
    )
    jd_path.write_text(
        "Title: Credentialed AI Engineer\n"
        "Company: Example\n"
        "Body:\n"
        "- 持有 PMP 证书\n"
        "- 负责风控项目落地\n"
        "\n=== JD ===\n"
        "Title: Applied AI Engineer\n"
        "Company: Example\n"
        "Body:\n"
        "- Build Python automation\n"
        "- Own LLM workflow prototypes\n",
        encoding="utf-8",
    )

    exit_code, output = run(
        [
            "run",
            "--run-dir",
            str(run_dir),
            "--candidate-id",
            "cand-001",
            "--cv",
            str(cv_path),
            "--jd",
            str(jd_path),
            "--config",
            str(config_path),
        ]
    )

    assert exit_code == 0, output
    gates = json.loads((run_dir / "analyze" / "preflight_gates.json").read_text(encoding="utf-8"))
    variants = json.loads((run_dir / "generate" / "resume_variants.json").read_text(encoding="utf-8"))
    scorecards = json.loads((run_dir / "evaluate" / "scorecards.json").read_text(encoding="utf-8"))

    assert [gate["status"] for gate in gates] == ["pass", "pass"]
    assert [variant["target_jd_ids"] for variant in variants] == [["jd-001"], ["jd-002"]]
    assert variants[1]["safe_rewrites"]
    assert "jd-001" in {scorecard["jd_id"] for scorecard in scorecards}
    passed_scorecard = next(scorecard for scorecard in scorecards if scorecard["jd_id"] == "jd-002")
    assert passed_scorecard["gate_status"] == "pass"
    assert passed_scorecard["verified_fit_score"] > 0
    assert passed_scorecard["rewrite_potential_score"] >= passed_scorecard["verified_fit_score"]
    assert passed_scorecard["risk_score"] < 0.7
    expected_final = round(
        passed_scorecard["verified_fit_score"] * 0.65
        + passed_scorecard["rewrite_potential_score"] * 0.20
        + (1 - passed_scorecard["risk_score"]) * 0.15,
        2,
    )
    assert passed_scorecard["final_overall_score"] == expected_final
    assert passed_scorecard["final_decision_source"].startswith("v0.5.7")


def test_pdf_cv_paragraphs_feed_hard_gate_evidence(tmp_path: Path) -> None:
    run_dir = tmp_path / "pdf-cv-run"
    cv_path = tmp_path / "resume.pdf"
    jd_path = tmp_path / "jd.txt"
    config_path = _write_deterministic_config(tmp_path)
    cv_path.write_bytes(
        b"%PDF-1.4\n"
        b"1 0 obj <<>> endobj\n"
        b"2 0 obj << /Length 220 >> stream\n"
        b"BT /F1 12 Tf 72 720 Td (Education: Bachelor degree in Computer Science. "
        b"Certificate: PMP. Experience: Built Python automation platform and LLM workflow prototypes.) Tj ET\n"
        b"endstream endobj\n"
        b"trailer <<>>\n%%EOF\n"
    )
    jd_path.write_text(
        "Title: Applied AI Engineer\n"
        "Company: Example\n"
        "Body:\n"
        "- Bachelor degree in Computer Science\n"
        "- PMP certificate\n"
        "- Build Python automation\n",
        encoding="utf-8",
    )

    exit_code, output = run(
        [
            "run",
            "--run-dir",
            str(run_dir),
            "--candidate-id",
            "cand-001",
            "--cv",
            str(cv_path),
            "--jd",
            str(jd_path),
            "--config",
            str(config_path),
        ]
    )

    assert exit_code == 0, output
    candidate = json.loads((run_dir / "analyze" / "candidate_profile.json").read_text(encoding="utf-8"))
    matrix = json.loads((run_dir / "analyze" / "requirement_matrix.json").read_text(encoding="utf-8"))
    gates = json.loads((run_dir / "analyze" / "preflight_gates.json").read_text(encoding="utf-8"))

    assert candidate["experiences"]
    assert any("Bachelor" in item or "Computer Science" in item for item in candidate["verified_evidence"])
    assert any("PMP" in item for item in candidate["verified_evidence"])
    assert all(item["evidence_status"] == "verified" for item in matrix if item["tier"] == "hard_gate")
    assert gates[0]["status"] == "pass"


def _write_deterministic_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "deterministic.json"
    config_path.write_text(
        json.dumps(
            {
                "analyzer": {"provider": "deterministic", "model": ""},
                "generator": {"provider": "deterministic", "model": ""},
                "judge": {"provider": "deterministic", "model": ""},
                "planner": {"provider": "deterministic", "model": ""},
                "openai": {"base_url": None, "api_key_env": "OPENAI_API_KEY", "env_file": ".env"},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return config_path
