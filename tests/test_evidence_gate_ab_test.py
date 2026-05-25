from __future__ import annotations

import json
from pathlib import Path

from scripts.run_evidence_gate_ab_test import _aggregate_by_threshold, _collect_ab_run_metrics, _prepare_ab_run


def test_collect_ab_run_metrics_summarizes_threshold_decisions_and_observability(tmp_path: Path) -> None:
    run_dir = tmp_path / "threshold-4" / "source-run"
    (run_dir / "logs").mkdir(parents=True)
    _write_json(
        run_dir / "review" / "post_run_review.json",
        {
            "jd_ids": ["jd-a", "jd-b", "jd-c"],
            "parallel_topology": {"evidence_threshold": 4},
            "decision_review": [
                {"jd_id": "jd-a", "evidence_status": "sufficient", "apply_decision": "apply", "gate_status": "pass"},
                {"jd_id": "jd-b", "evidence_status": "insufficient", "apply_decision": "needs_review", "gate_status": "needs_review"},
                {"jd_id": "jd-c", "evidence_status": "sufficient", "apply_decision": "hold", "gate_status": "pass"},
            ],
            "retrieval": {
                "low_evidence_jd_count": 1,
                "evidence_by_jd": [
                    {"jd_id": "jd-a", "evidence_count": 5, "minimum_required": 4, "result_count": 6},
                    {"jd_id": "jd-b", "evidence_count": 2, "minimum_required": 4, "result_count": 4},
                    {"jd_id": "jd-c", "evidence_count": 4, "minimum_required": 4, "result_count": 5},
                ],
            },
            "evidence_gap_reports": [{"jd_id": "jd-b"}],
        },
    )
    _write_events(
        run_dir / "logs" / "run_events.jsonl",
        [
            {
                "event": "retrieval_query",
                "stage": "review",
                "retrieval_scope": "combined_deduped",
                "supporting_hit_count": 5,
                "source_type_hit_counts": {"candidate_evidence": 2, "requirement_evidence": 3},
                "source_type_available_counts": {"candidate_evidence": 4, "requirement_evidence": 5},
                "duration_ms": 3,
            },
            {
                "event": "retrieval_query",
                "stage": "review",
                "retrieval_scope": "combined_deduped",
                "supporting_hit_count": 2,
                "source_type_hit_counts": {"candidate_evidence": 1},
                "source_type_available_counts": {"candidate_evidence": 4},
                "duration_ms": 2,
            },
            {
                "event": "graph_node_finished",
                "stage": "review",
                "node": "retrieve_relevant_evidence",
                "duration_ms": 8,
                "timing_ms": {"business": 6, "log_write": 1},
            },
        ],
    )

    metrics = _collect_ab_run_metrics(run_dir, source_run_id="source-run", threshold=4)

    assert metrics["threshold"] == 4
    assert metrics["review_decision_count"] == 3
    assert metrics["review_low_evidence_jd_count"] == 1
    assert metrics["evidence_gap_report_count"] == 1
    assert metrics["review_apply_decision_distribution"] == {"apply": 1, "needs_review": 1, "hold": 1}
    assert metrics["retrieval_combined_query_count"] == 2
    assert metrics["retrieval_supporting_hit_count"]["avg"] == 3.5
    assert metrics["retrieval_source_type_hit_counts"] == {"candidate_evidence": 3, "requirement_evidence": 3}
    assert metrics["graph_node_business_duration_ms"]["avg"] == 6


def test_aggregate_by_threshold_keeps_ab_comparison_shape() -> None:
    runs = [
        {
            "threshold": 2,
            "review_decision_count": 3,
            "review_low_evidence_jd_count": 0,
            "evidence_gap_report_count": 0,
            "retrieval_combined_query_count": 3,
            "retrieval_supporting_hit_count": {"avg": 3.0},
            "graph_node_duration_ms": {"avg": 4.0},
            "graph_node_business_duration_ms": {"avg": 3.0},
            "review_apply_decision_distribution": {"apply": 2, "hold": 1},
            "review_gate_status_distribution": {"pass": 3},
            "retrieval_source_type_hit_counts": {"candidate_evidence": 4},
            "retrieval_source_type_available_counts": {"candidate_evidence": 6},
        },
        {
            "threshold": 4,
            "review_decision_count": 3,
            "review_low_evidence_jd_count": 1,
            "evidence_gap_report_count": 1,
            "retrieval_combined_query_count": 3,
            "retrieval_supporting_hit_count": {"avg": 3.0},
            "graph_node_duration_ms": {"avg": 5.0},
            "graph_node_business_duration_ms": {"avg": 4.0},
            "review_apply_decision_distribution": {"apply": 1, "needs_review": 2},
            "review_gate_status_distribution": {"pass": 1, "needs_review": 2},
            "retrieval_source_type_hit_counts": {"candidate_evidence": 4},
            "retrieval_source_type_available_counts": {"candidate_evidence": 6},
        },
    ]

    aggregate = _aggregate_by_threshold(runs)

    assert aggregate["2"]["run_count"] == 1
    assert aggregate["2"]["review_low_evidence_jd_count"] == 0
    assert aggregate["4"]["evidence_gap_report_count"] == 1
    assert aggregate["4"]["review_apply_decision_distribution"] == {"apply": 1, "needs_review": 2}


def test_prepare_ab_run_excludes_existing_logs_and_review_outputs(tmp_path: Path) -> None:
    source = tmp_path / "source-run"
    target = tmp_path / "target-run"
    _write_json(source / "analyze" / "candidate_profile.json", {"candidate_id": "cand-001"})
    _write_events(source / "logs" / "run_events.jsonl", [{"event": "old"}])
    _write_json(source / "review" / "post_run_review.json", {"old": True})

    _prepare_ab_run(source, target)

    assert (target / "analyze" / "candidate_profile.json").exists()
    assert not (target / "logs" / "run_events.jsonl").exists()
    assert not (target / "review" / "post_run_review.json").exists()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_events(path: Path, events: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n", encoding="utf-8")
