from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "cli" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "py-core" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "py-agents" / "src"))

from shotguncv_cli.main import run as cli_run  # noqa: E402


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
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


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


def _duration_ms(event: dict[str, Any]) -> float | None:
    value = event.get("duration_ms")
    if isinstance(value, int | float):
        return float(value)
    return None


def _numeric_event_values(events: list[dict[str, Any]], key: str) -> list[float]:
    return [float(event[key]) for event in events if isinstance(event.get(key), int | float)]


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


def _event_duration_by_stage(events: list[dict[str, Any]], stage: str) -> float | None:
    durations = [
        float(event["duration_ms"])
        for event in events
        if event.get("event") == "stage_finished"
        and event.get("stage") == stage
        and isinstance(event.get("duration_ms"), int | float)
    ]
    return durations[-1] if durations else None


def _collect_run_metrics(run_dir: Path, spec: dict[str, Any], repeat_round: int) -> dict[str, Any]:
    events = _events(run_dir)
    input_events = [event for event in events if event.get("event") == "input_extracted"]
    jd_input_events = [event for event in input_events if event.get("role") == "jd"]
    graph_finished = [event for event in events if event.get("event") == "graph_node_finished"]
    retrieval_events = [event for event in events if event.get("event") == "retrieval_query"]

    scorecards = _read_json(run_dir / "evaluate" / "scorecards.json", [])
    strategies = _read_json(run_dir / "strategy" / "application_strategy.json", [])
    preflight = _read_json(run_dir / "preflight" / "preflight_gates.json", [])
    review = _read_json(run_dir / "review" / "post_run_review.json", {})
    review_decisions = review.get("decision_review", []) if isinstance(review, dict) else []

    extraction_statuses = Counter(str(event.get("status") or event.get("extraction_status") or "unknown") for event in jd_input_events)
    extraction_providers = Counter(str(event.get("provider") or "unknown") for event in jd_input_events)
    fallback_from = Counter(str(event.get("fallback_from") or "none") for event in jd_input_events)
    media_types = Counter(str(event.get("media_type") or "unknown") for event in jd_input_events)
    text_lengths = [
        float(event["text_chars"])
        for event in jd_input_events
        if isinstance(event.get("text_chars"), int | float)
    ]
    retrieval_durations = [value for event in retrieval_events if (value := _duration_ms(event)) is not None]
    graph_durations = [value for event in graph_finished if (value := _duration_ms(event)) is not None]
    retrieval_scopes = Counter(str(event.get("retrieval_scope") or "unknown") for event in retrieval_events)
    retrieval_misses_by_scope = Counter(
        str(event.get("retrieval_scope") or "unknown")
        for event in retrieval_events
        if int(event.get("hit_count") or 0) == 0
    )
    retrieval_supporting_zero_by_scope = Counter(
        str(event.get("retrieval_scope") or "unknown")
        for event in retrieval_events
        if isinstance(event.get("supporting_hit_count"), int | float) and event.get("supporting_hit_count") == 0
    )
    for scope in retrieval_scopes:
        retrieval_misses_by_scope.setdefault(scope, 0)
        retrieval_supporting_zero_by_scope.setdefault(scope, 0)
    retrieval_raw_hits = _numeric_event_values(retrieval_events, "raw_hit_count")
    retrieval_unique_hits = _numeric_event_values(retrieval_events, "unique_hit_count")
    retrieval_supporting_hits = _numeric_event_values(retrieval_events, "supporting_hit_count")
    retrieval_source_type_hits = _counter_from_event_maps(retrieval_events, "source_type_hit_counts")
    retrieval_source_type_available = _counter_from_event_maps(retrieval_events, "source_type_available_counts")

    return {
        "run_id": run_dir.name,
        "baseline_run_id": spec["run_id"],
        "bucket": spec["bucket"],
        "repeat": spec["repeat"],
        "benchmark_round": repeat_round,
        "expected_jd_count": spec["jd_count"],
        "media_counts": spec.get("media_counts", {}),
        "pipeline_run_duration_ms": _event_duration_by_stage(events, "pipeline"),
        "cli_run_wall_duration_ms": spec.get("_cli_run_wall_duration_ms"),
        "cli_review_wall_duration_ms": spec.get("_cli_review_wall_duration_ms"),
        "review_stage_duration_ms": _event_duration_by_stage(events, "review"),
        "actual_jd_input_count": len(jd_input_events),
        "scorecard_count": len(scorecards),
        "strategy_count": len(strategies),
        "preflight_count": len(preflight),
        "review_decision_count": len(review_decisions),
        "review_low_evidence_jd_count": sum(1 for item in review_decisions if item.get("evidence_status") == "insufficient"),
        "extraction_status_distribution": dict(extraction_statuses),
        "extraction_provider_distribution": dict(extraction_providers),
        "extraction_fallback_from_distribution": dict(fallback_from),
        "extraction_media_type_distribution": dict(media_types),
        "extracted_text_length": _summary(text_lengths),
        "retrieval_query_count": len(retrieval_events),
        "retrieval_miss_count": sum(1 for event in retrieval_events if int(event.get("hit_count") or 0) == 0),
        "retrieval_duration_ms": _summary(retrieval_durations),
        "retrieval_scope_distribution": dict(retrieval_scopes),
        "retrieval_miss_count_by_scope": dict(retrieval_misses_by_scope),
        "retrieval_combined_query_count": retrieval_scopes.get("combined_deduped", 0),
        "retrieval_raw_hit_count": _summary(retrieval_raw_hits),
        "retrieval_unique_hit_count": _summary(retrieval_unique_hits),
        "retrieval_supporting_hit_count": _summary(retrieval_supporting_hits),
        "retrieval_supporting_zero_count": sum(
            1 for event in retrieval_events if isinstance(event.get("supporting_hit_count"), int | float) and event.get("supporting_hit_count") == 0
        ),
        "retrieval_supporting_zero_count_by_scope": dict(retrieval_supporting_zero_by_scope),
        "retrieval_source_type_hit_counts": dict(retrieval_source_type_hits),
        "retrieval_source_type_available_counts": dict(retrieval_source_type_available),
        "graph_node_finished_count": len(graph_finished),
        "graph_node_duration_ms": _summary(graph_durations),
        "review_apply_decision_distribution": dict(Counter(str(item.get("apply_decision", "unknown")) for item in review_decisions)),
        "review_gate_status_distribution": dict(Counter(str(item.get("gate_status", "unknown")) for item in review_decisions)),
    }


def _aggregate(runs: list[dict[str, Any]]) -> dict[str, Any]:
    pipeline = [item["pipeline_run_duration_ms"] for item in runs if isinstance(item.get("pipeline_run_duration_ms"), int | float)]
    cli_run_wall = [item["cli_run_wall_duration_ms"] for item in runs if isinstance(item.get("cli_run_wall_duration_ms"), int | float)]
    cli_review_wall = [item["cli_review_wall_duration_ms"] for item in runs if isinstance(item.get("cli_review_wall_duration_ms"), int | float)]
    review = [item["review_stage_duration_ms"] for item in runs if isinstance(item.get("review_stage_duration_ms"), int | float)]
    text_length_counts: list[float] = []
    retrieval_durations: list[float] = []
    graph_durations: list[float] = []
    by_bucket: dict[str, list[dict[str, Any]]] = defaultdict(list)
    status = Counter()
    provider = Counter()
    fallback = Counter()
    media = Counter()
    decisions = Counter()
    gates = Counter()
    retrieval_scopes = Counter()
    retrieval_misses_by_scope = Counter()
    retrieval_supporting_zero_by_scope = Counter()
    retrieval_source_type_hits = Counter()
    retrieval_source_type_available = Counter()
    retrieval_raw_hit_avgs: list[float] = []
    retrieval_unique_hit_avgs: list[float] = []
    retrieval_supporting_hit_avgs: list[float] = []

    for item in runs:
        by_bucket[item["bucket"]].append(item)
        status.update(item.get("extraction_status_distribution", {}))
        provider.update(item.get("extraction_provider_distribution", {}))
        fallback.update(item.get("extraction_fallback_from_distribution", {}))
        media.update(item.get("extraction_media_type_distribution", {}))
        decisions.update(item.get("review_apply_decision_distribution", {}))
        gates.update(item.get("review_gate_status_distribution", {}))
        retrieval_scopes.update(item.get("retrieval_scope_distribution", {}))
        retrieval_misses_by_scope.update(item.get("retrieval_miss_count_by_scope", {}))
        retrieval_supporting_zero_by_scope.update(item.get("retrieval_supporting_zero_count_by_scope", {}))
        retrieval_source_type_hits.update(item.get("retrieval_source_type_hit_counts", {}))
        retrieval_source_type_available.update(item.get("retrieval_source_type_available_counts", {}))
        if isinstance(item.get("extracted_text_length", {}).get("avg"), int | float):
            text_length_counts.append(float(item["extracted_text_length"]["avg"]))
        if isinstance(item.get("retrieval_duration_ms", {}).get("avg"), int | float):
            retrieval_durations.append(float(item["retrieval_duration_ms"]["avg"]))
        if isinstance(item.get("retrieval_raw_hit_count", {}).get("avg"), int | float):
            retrieval_raw_hit_avgs.append(float(item["retrieval_raw_hit_count"]["avg"]))
        if isinstance(item.get("retrieval_unique_hit_count", {}).get("avg"), int | float):
            retrieval_unique_hit_avgs.append(float(item["retrieval_unique_hit_count"]["avg"]))
        if isinstance(item.get("retrieval_supporting_hit_count", {}).get("avg"), int | float):
            retrieval_supporting_hit_avgs.append(float(item["retrieval_supporting_hit_count"]["avg"]))
        if isinstance(item.get("graph_node_duration_ms", {}).get("avg"), int | float):
            graph_durations.append(float(item["graph_node_duration_ms"]["avg"]))

    return {
        "run_count": len(runs),
        "expected_jd_count": sum(int(item["expected_jd_count"]) for item in runs),
        "actual_jd_input_count": sum(int(item["actual_jd_input_count"]) for item in runs),
        "scorecard_count": sum(int(item["scorecard_count"]) for item in runs),
        "review_decision_count": sum(int(item["review_decision_count"]) for item in runs),
        "review_low_evidence_jd_count": sum(int(item["review_low_evidence_jd_count"]) for item in runs),
        "pipeline_run_duration_ms": _summary(pipeline),
        "cli_run_wall_duration_ms": _summary(cli_run_wall),
        "cli_review_wall_duration_ms": _summary(cli_review_wall),
        "review_stage_duration_ms": _summary(review),
        "extraction_status_distribution": dict(status),
        "extraction_provider_distribution": dict(provider),
        "extraction_fallback_from_distribution": dict(fallback),
        "extraction_media_type_distribution": dict(media),
        "extracted_text_length_avg_by_run": _summary(text_length_counts),
        "retrieval_query_count": sum(int(item["retrieval_query_count"]) for item in runs),
        "retrieval_miss_count": sum(int(item["retrieval_miss_count"]) for item in runs),
        "retrieval_duration_ms_avg_by_run": _summary(retrieval_durations),
        "retrieval_scope_distribution": dict(retrieval_scopes),
        "retrieval_miss_count_by_scope": dict(retrieval_misses_by_scope),
        "retrieval_combined_query_count": sum(int(item.get("retrieval_combined_query_count", 0)) for item in runs),
        "retrieval_supporting_zero_count": sum(int(item.get("retrieval_supporting_zero_count", 0)) for item in runs),
        "retrieval_supporting_zero_count_by_scope": dict(retrieval_supporting_zero_by_scope),
        "retrieval_raw_hit_count_avg_by_run": _summary(retrieval_raw_hit_avgs),
        "retrieval_unique_hit_count_avg_by_run": _summary(retrieval_unique_hit_avgs),
        "retrieval_supporting_hit_count_avg_by_run": _summary(retrieval_supporting_hit_avgs),
        "retrieval_source_type_hit_counts": dict(retrieval_source_type_hits),
        "retrieval_source_type_available_counts": dict(retrieval_source_type_available),
        "graph_node_finished_count": sum(int(item["graph_node_finished_count"]) for item in runs),
        "graph_node_duration_ms_avg_by_run": _summary(graph_durations),
        "review_apply_decision_distribution": dict(decisions),
        "review_gate_status_distribution": dict(gates),
        "by_bucket": {
            bucket: {
                "run_count": len(items),
                "expected_jd_count": sum(int(item["expected_jd_count"]) for item in items),
                "scorecard_count": sum(int(item["scorecard_count"]) for item in items),
                "review_decision_count": sum(int(item["review_decision_count"]) for item in items),
                "pipeline_run_duration_ms": _summary(
                    [item["pipeline_run_duration_ms"] for item in items if isinstance(item.get("pipeline_run_duration_ms"), int | float)]
                ),
                "cli_run_wall_duration_ms": _summary(
                    [item["cli_run_wall_duration_ms"] for item in items if isinstance(item.get("cli_run_wall_duration_ms"), int | float)]
                ),
                "cli_review_wall_duration_ms": _summary(
                    [item["cli_review_wall_duration_ms"] for item in items if isinstance(item.get("cli_review_wall_duration_ms"), int | float)]
                ),
                "review_stage_duration_ms": _summary(
                    [item["review_stage_duration_ms"] for item in items if isinstance(item.get("review_stage_duration_ms"), int | float)]
                ),
            }
            for bucket, items in sorted(by_bucket.items())
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--output-root", type=Path, default=ROOT / "runs" / f"current-media-benchmark-{time.strftime('%Y%m%d-%H%M%S')}")
    parser.add_argument("--tesseract-dir", type=Path, default=Path(r"C:\Program Files\Tesseract-OCR"))
    args = parser.parse_args()

    if args.tesseract_dir.exists():
        os.environ["PATH"] = str(args.tesseract_dir) + os.pathsep + os.environ.get("PATH", "")

    specs = _read_json(ROOT / "baseline" / "baseline_runs_formal_20260520.json", [])
    if not specs:
        raise RuntimeError("No baseline specs found.")

    args.output_root.mkdir(parents=True, exist_ok=True)
    run_metrics: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for round_index in range(1, args.rounds + 1):
        for spec in specs:
            run_dir = args.output_root / f"r{round_index}-{spec['run_id'].replace('baseline-formal-', 'current-media-')}"
            argv = [
                "run",
                "--run-dir",
                str(run_dir),
                "--candidate-id",
                f"media-benchmark-r{round_index}",
                "--cv",
                str(ROOT / "fixtures" / "candidates" / "base_resume.md"),
                "--config",
                str(ROOT / "baseline" / "deterministic-run-config.json"),
                "--no-vision-fallback",
                "--ocr-languages",
                "eng+chi_sim",
            ]
            for jd_path in spec["jd_source_files"]:
                argv.extend(["--jd", jd_path])

            print(f"[run] round={round_index} baseline={spec['run_id']} jd={spec['jd_count']}", flush=True)
            started = time.perf_counter()
            code, output = cli_run(argv)
            cli_run_wall_duration_ms = round((time.perf_counter() - started) * 1000, 4)
            if code != 0:
                failure = {
                    "round": round_index,
                    "baseline_run_id": spec["run_id"],
                    "run_dir": str(run_dir),
                    "phase": "run",
                    "output": output,
                }
                failures.append(failure)
                _write_json(args.output_root / "failures.json", failures)
                print(f"[fail] {failure}", flush=True)
                continue

            started = time.perf_counter()
            code, output = cli_run(["review", "--run-dir", str(run_dir)])
            cli_review_wall_duration_ms = round((time.perf_counter() - started) * 1000, 4)
            if code != 0:
                failure = {
                    "round": round_index,
                    "baseline_run_id": spec["run_id"],
                    "run_dir": str(run_dir),
                    "phase": "review",
                    "output": output,
                }
                failures.append(failure)
                _write_json(args.output_root / "failures.json", failures)
                print(f"[fail] {failure}", flush=True)
                continue

            metric_spec = dict(spec)
            metric_spec["_cli_run_wall_duration_ms"] = cli_run_wall_duration_ms
            metric_spec["_cli_review_wall_duration_ms"] = cli_review_wall_duration_ms
            metric = _collect_run_metrics(run_dir, metric_spec, round_index)
            run_metrics.append(metric)
            _write_json(args.output_root / "current_media_run_metrics.json", run_metrics)
            _write_json(args.output_root / "current_media_metrics.json", {"aggregate": _aggregate(run_metrics), "runs": run_metrics, "failures": failures})

    result = {"aggregate": _aggregate(run_metrics), "runs": run_metrics, "failures": failures}
    _write_json(args.output_root / "current_media_metrics.json", result)
    print(json.dumps({"output_root": str(args.output_root), "aggregate": result["aggregate"], "failure_count": len(failures)}, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
