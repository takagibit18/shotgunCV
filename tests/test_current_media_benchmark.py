from __future__ import annotations

import json
from pathlib import Path

from scripts.run_current_media_benchmark import _collect_run_metrics


def test_collect_run_metrics_summarizes_retrieval_observability(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    (run_dir / "logs").mkdir(parents=True)
    _write_events(
        run_dir / "logs" / "run_events.jsonl",
        [
            {
                "event": "retrieval_query",
                "stage": "review",
                "retrieval_scope": "jd_filtered",
                "hit_count": 2,
                "raw_hit_count": 2,
                "unique_hit_count": 2,
                "supporting_hit_count": 0,
                "source_type_hit_counts": {"jd_profile": 1, "requirement_evidence": 1},
                "source_type_available_counts": {"jd_profile": 1, "requirement_evidence": 2},
                "duration_ms": 3,
            },
            {
                "event": "retrieval_query",
                "stage": "review",
                "retrieval_scope": "combined_deduped",
                "hit_count": 3,
                "raw_hit_count": 4,
                "unique_hit_count": 3,
                "supporting_hit_count": 1,
                "source_type_hit_counts": {"candidate_evidence": 1, "jd_profile": 1, "requirement_evidence": 1},
                "source_type_available_counts": {"candidate_evidence": 3, "jd_profile": 1, "requirement_evidence": 2},
                "duration_ms": 1,
            },
        ],
    )
    _write_json(run_dir / "review" / "post_run_review.json", {"decision_review": []})

    metrics = _collect_run_metrics(
        run_dir,
        {
            "run_id": "baseline-formal-example",
            "bucket": "small",
            "repeat": 1,
            "jd_count": 1,
        },
        repeat_round=1,
    )

    assert metrics["retrieval_scope_distribution"] == {"jd_filtered": 1, "combined_deduped": 1}
    assert metrics["retrieval_miss_count_by_scope"] == {"jd_filtered": 0, "combined_deduped": 0}
    assert metrics["retrieval_combined_query_count"] == 1
    assert metrics["retrieval_supporting_zero_count"] == 1
    assert metrics["retrieval_supporting_zero_count_by_scope"] == {"jd_filtered": 1, "combined_deduped": 0}
    assert metrics["retrieval_raw_hit_count"]["avg"] == 3
    assert metrics["retrieval_unique_hit_count"]["avg"] == 2.5
    assert metrics["retrieval_supporting_hit_count"]["avg"] == 0.5
    assert metrics["retrieval_source_type_hit_counts"] == {
        "candidate_evidence": 1,
        "jd_profile": 2,
        "requirement_evidence": 2,
    }
    assert metrics["retrieval_source_type_available_counts"] == {
        "candidate_evidence": 3,
        "jd_profile": 2,
        "requirement_evidence": 4,
    }


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_events(path: Path, events: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n", encoding="utf-8")
