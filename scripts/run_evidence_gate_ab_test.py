from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from time import perf_counter
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "cli" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "py-core" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "py-agents" / "src"))

from shotguncv_agents.review_graph import run_post_run_review  # noqa: E402
from shotguncv_core.run_logs import log_stage_failed, log_stage_finished, log_stage_started  # noqa: E402


DEFAULT_THRESHOLDS = [2, 3, 4, 5]


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _events(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / "logs" / "run_events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return round(values[0], 4)
    ordered = sorted(values)
    k = (len(ordered) - 1) * percentile
    lower = int(k)
    upper = min(lower + 1, len(ordered) - 1)
    weight = k - lower
    return round(ordered[lower] * (1 - weight) + ordered[upper] * weight, 4)


def _summary(values: list[float]) -> dict[str, float | int | None]:
    return {
        "count": len(values),
        "avg": round(statistics.fmean(values), 4) if values else None,
        "p50": _percentile(values, 0.50),
        "p95": _percentile(values, 0.95),
        "p99": _percentile(values, 0.99),
        "min": round(min(values), 4) if values else None,
        "max": round(max(values), 4) if values else None,
    }


def _numeric_event_values(events: list[dict[str, Any]], key: str) -> list[float]:
    return [float(event[key]) for event in events if isinstance(event.get(key), int | float)]


def _timing_values(events: list[dict[str, Any]], key: str) -> list[float]:
    values: list[float] = []
    for event in events:
        timing = event.get("timing_ms")
        if isinstance(timing, dict) and isinstance(timing.get(key), int | float):
            values.append(float(timing[key]))
    return values


def _counter_from_event_maps(events: list[dict[str, Any]], key: str) -> Counter[str]:
    counter: Counter[str] = Counter()
    for event in events:
        values = event.get(key)
        if not isinstance(values, dict):
            continue
        for item_key, value in values.items():
            if isinstance(value, int | float):
                counter[str(item_key)] += int(value)
    return counter


def _collect_ab_run_metrics(run_dir: Path, *, source_run_id: str, threshold: int) -> dict[str, Any]:
    events = _events(run_dir)
    graph_finished = [
        event
        for event in events
        if event.get("event") == "graph_node_finished" and event.get("stage") == "review"
    ]
    review = _read_json(run_dir / "review" / "post_run_review.json", {})
    decisions = review.get("decision_review", []) if isinstance(review, dict) else []
    evidence_assessment = (review.get("evidence_assessment", {}) or {}) if isinstance(review, dict) else {}
    evidence_records = evidence_assessment.get("evidence_by_jd", [])

    return {
        "run_id": run_dir.name,
        "source_run_id": source_run_id,
        "threshold": threshold,
        "jd_count": len(review.get("jd_ids", [])) if isinstance(review, dict) else 0,
        "review_decision_count": len(decisions),
        "review_low_evidence_jd_count": sum(1 for item in decisions if item.get("evidence_status") == "insufficient"),
        "review_sufficient_evidence_jd_count": sum(1 for item in decisions if item.get("evidence_status") == "sufficient"),
        "evidence_gap_report_count": len(review.get("evidence_gap_reports", [])) if isinstance(review, dict) else 0,
        "evidence_count_by_jd": [
            {
                "jd_id": item.get("jd_id"),
                "evidence_count": item.get("evidence_count"),
                "verified_count": item.get("verified_count"),
                "inferred_count": item.get("inferred_count"),
                "missing_count": item.get("missing_count"),
                "mismatch_count": item.get("mismatch_count"),
                "gate_status": item.get("gate_status"),
                "evidence_status": item.get("evidence_status"),
                "reason": item.get("reason"),
            }
            for item in evidence_records
        ],
        "review_apply_decision_distribution": dict(Counter(str(item.get("apply_decision", "unknown")) for item in decisions)),
        "review_gate_status_distribution": dict(Counter(str(item.get("gate_status", "unknown")) for item in decisions)),
        "graph_node_finished_count": len(graph_finished),
        "graph_node_duration_ms": _summary(_numeric_event_values(graph_finished, "duration_ms")),
        "graph_node_business_duration_ms": _summary(_timing_values(graph_finished, "business")),
        "graph_node_log_write_duration_ms": _summary(_timing_values(graph_finished, "log_write")),
    }


def _aggregate_by_threshold(runs: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for item in runs:
        grouped[int(item["threshold"])].append(item)

    aggregate: dict[str, Any] = {}
    for threshold, items in sorted(grouped.items()):
        decisions = Counter()
        gates = Counter()
        graph_duration_avgs: list[float] = []
        graph_business_avgs: list[float] = []
        for item in items:
            decisions.update(item.get("review_apply_decision_distribution", {}))
            gates.update(item.get("review_gate_status_distribution", {}))
            if isinstance(item.get("graph_node_duration_ms", {}).get("avg"), int | float):
                graph_duration_avgs.append(float(item["graph_node_duration_ms"]["avg"]))
            if isinstance(item.get("graph_node_business_duration_ms", {}).get("avg"), int | float):
                graph_business_avgs.append(float(item["graph_node_business_duration_ms"]["avg"]))

        aggregate[str(threshold)] = {
            "run_count": len(items),
            "jd_count": sum(int(item.get("jd_count", 0)) for item in items),
            "review_decision_count": sum(int(item.get("review_decision_count", 0)) for item in items),
            "review_low_evidence_jd_count": sum(int(item.get("review_low_evidence_jd_count", 0)) for item in items),
            "review_sufficient_evidence_jd_count": sum(int(item.get("review_sufficient_evidence_jd_count", 0)) for item in items),
            "evidence_gap_report_count": sum(int(item.get("evidence_gap_report_count", 0)) for item in items),
            "graph_node_duration_ms_avg_by_run": _summary(graph_duration_avgs),
            "graph_node_business_duration_ms_avg_by_run": _summary(graph_business_avgs),
            "review_apply_decision_distribution": dict(decisions),
            "review_gate_status_distribution": dict(gates),
        }
    return aggregate


def _prepare_ab_run(source_run_dir: Path, target_run_dir: Path) -> None:
    if target_run_dir.exists():
        shutil.rmtree(target_run_dir)
    shutil.copytree(source_run_dir, target_run_dir, ignore=shutil.ignore_patterns("logs", "review"))
    (target_run_dir / "logs").mkdir(parents=True, exist_ok=True)


def _run_review_for_threshold(
    source_run_dir: Path,
    target_run_dir: Path,
    *,
    threshold: int,
    database_url: str | None,
) -> dict[str, Any]:
    _prepare_ab_run(source_run_dir, target_run_dir)
    stage_started = log_stage_started(target_run_dir, "review")
    try:
        run_post_run_review(target_run_dir, database_url=database_url)
    except Exception as exc:
        log_stage_failed(target_run_dir, "review", stage_started, exc)
        raise
    log_stage_finished(target_run_dir, "review", stage_started)
    return _collect_ab_run_metrics(target_run_dir, source_run_id=source_run_dir.name, threshold=threshold)


def _select_source_runs(source_runs_root: Path, run_ids: list[str]) -> list[Path]:
    if run_ids:
        return [source_runs_root / run_id for run_id in run_ids]
    return sorted(path for path in source_runs_root.iterdir() if path.is_dir())


def run_ab_test(
    *,
    source_runs_root: Path,
    output_root: Path,
    thresholds: list[int],
    run_ids: list[str],
    database_url: str | None = None,
) -> dict[str, Any]:
    source_runs = _select_source_runs(source_runs_root, run_ids)
    output_root.mkdir(parents=True, exist_ok=True)
    run_metrics: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for threshold in thresholds:
        for source_run_dir in source_runs:
            target_run_dir = output_root / f"threshold-{threshold}" / source_run_dir.name
            print(f"[review] threshold={threshold} source={source_run_dir.name}", flush=True)
            started = perf_counter()
            try:
                metric = _run_review_for_threshold(
                    source_run_dir,
                    target_run_dir,
                    threshold=threshold,
                    database_url=database_url,
                )
            except Exception as exc:  # noqa: BLE001
                failure = {
                    "threshold": threshold,
                    "source_run_id": source_run_dir.name,
                    "run_dir": str(target_run_dir),
                    "error_type": exc.__class__.__name__,
                    "error_summary": str(exc)[:500],
                }
                failures.append(failure)
                _write_json(output_root / "failures.json", failures)
                print(f"[fail] {failure}", flush=True)
                continue
            metric["review_wall_duration_ms"] = round((perf_counter() - started) * 1000, 4)
            run_metrics.append(metric)
            _write_json(output_root / "evidence_gate_ab_runs.json", run_metrics)
            _write_json(output_root / "aggregate.json", _result_payload(thresholds, run_metrics, failures))

    result = _result_payload(thresholds, run_metrics, failures)
    _write_json(output_root / "aggregate.json", result)
    return result


def _result_payload(thresholds: list[int], runs: list[dict[str, Any]], failures: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "evidence-gate-ab-v1",
        "thresholds": thresholds,
        "aggregate_by_threshold": _aggregate_by_threshold(runs),
        "runs": runs,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run evidence-gate threshold A/B checks against existing run artifacts.")
    parser.add_argument("--source-runs-root", type=Path, default=ROOT / "baseline" / "runs-formal-20260520")
    parser.add_argument("--output-root", type=Path, default=ROOT / "baseline" / f"evidence-gate-ab-{time.strftime('%Y%m%d-%H%M%S')}")
    parser.add_argument("--thresholds", type=int, nargs="+", default=DEFAULT_THRESHOLDS)
    parser.add_argument("--run-id", dest="run_ids", action="append", default=[])
    parser.add_argument("--database-url-env", default="SHOTGUNCV_DATABASE_URL")
    args = parser.parse_args()

    database_url = os.environ.get(args.database_url_env, "").strip() or None
    result = run_ab_test(
        source_runs_root=args.source_runs_root,
        output_root=args.output_root,
        thresholds=args.thresholds,
        run_ids=args.run_ids,
        database_url=database_url,
    )
    print(json.dumps({"output_root": str(args.output_root), "aggregate_by_threshold": result["aggregate_by_threshold"], "failure_count": len(result["failures"])}, ensure_ascii=False, indent=2))
    return 0 if not result["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
