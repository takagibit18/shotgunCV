from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from shotguncv_core.db.schema import all_schema_sql
from shotguncv_core.rag.embeddings import embed_text
from shotguncv_core.rag.documents import build_retrieval_chunks
from shotguncv_core.run_logs import log_index_batch, log_stage_failed, log_stage_finished, log_stage_started
from shotguncv_core.storage import load_json


ARTIFACT_PATHS = [
    "config/run_config.json",
    "ingest/manifest.json",
    "analyze/candidate_profile.json",
    "analyze/jd_profiles.json",
    "analyze/requirement_matrix.json",
    "analyze/preflight_gates.json",
    "generate/resume_variants.json",
    "evaluate/scorecards.json",
    "evaluate/gap_maps.json",
    "evaluate/ranking_explanations.json",
    "evaluate/eval_summary.json",
    "plan/application_strategies.json",
    "report/summary.md",
    "logs/run_events.jsonl",
]

TABLE_COLUMNS = {
    "candidate_sources": ["source_id", "candidate_id", "source_type", "artifact_path", "payload"],
    "jd_inputs": ["jd_id", "company_id", "candidate_id", "source_type", "source_value", "payload"],
    "run_artifacts": ["run_id", "artifact_path", "payload"],
    "resume_variants": ["run_id", "variant_id", "candidate_id", "payload"],
    "requirement_evidence": ["run_id", "jd_id", "requirement_id", "candidate_id", "payload"],
    "preflight_gates": ["run_id", "jd_id", "payload"],
    "scorecards": ["run_id", "jd_id", "variant_id", "candidate_id", "payload"],
    "gap_maps": ["run_id", "jd_id", "candidate_id", "payload"],
    "ranking_explanations": ["run_id", "jd_id", "variant_id", "payload"],
    "application_strategies": ["run_id", "jd_id", "candidate_id", "payload"],
}


@dataclass(frozen=True)
class ProjectionRun:
    run_id: str
    candidate_id: str
    run_dir: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class ProjectionBatch:
    run: ProjectionRun
    candidates: list[dict[str, Any]] = field(default_factory=list)
    candidate_sources: list[dict[str, Any]] = field(default_factory=list)
    companies: list[dict[str, Any]] = field(default_factory=list)
    jd_inputs: list[dict[str, Any]] = field(default_factory=list)
    run_artifacts: list[dict[str, Any]] = field(default_factory=list)
    resume_variants: list[dict[str, Any]] = field(default_factory=list)
    requirement_evidence: list[dict[str, Any]] = field(default_factory=list)
    preflight_gates: list[dict[str, Any]] = field(default_factory=list)
    scorecards: list[dict[str, Any]] = field(default_factory=list)
    gap_maps: list[dict[str, Any]] = field(default_factory=list)
    ranking_explanations: list[dict[str, Any]] = field(default_factory=list)
    application_strategies: list[dict[str, Any]] = field(default_factory=list)
    retrieval_chunks: list[dict[str, Any]] = field(default_factory=list)


def build_projection_batch(run_dir: Path, *, include_chunks: bool = True) -> ProjectionBatch:
    run_dir = run_dir.resolve()
    run_id = run_dir.name
    manifest = _read_json_if_exists(run_dir / "ingest" / "manifest.json") or {}
    candidate_profile = _read_json_if_exists(run_dir / "analyze" / "candidate_profile.json") or {}
    jd_profiles = _read_json_if_exists(run_dir / "analyze" / "jd_profiles.json") or []
    candidate_id = str(candidate_profile.get("candidate_id") or manifest.get("candidate_id") or "unknown-candidate")
    run_payload = {
        "run_id": run_id,
        "artifact_contract": "run_dir-projection-v1",
        "completed_artifacts": [path for path in ARTIFACT_PATHS if (run_dir / path).exists()],
    }
    candidate = {"candidate_id": candidate_id, "payload": candidate_profile or {"candidate_id": candidate_id}}
    companies = _build_companies(jd_profiles)
    batch = ProjectionBatch(
        run=ProjectionRun(run_id=run_id, candidate_id=candidate_id, run_dir=str(run_dir), payload=run_payload),
        candidates=[candidate],
        candidate_sources=_build_candidate_sources(candidate_id, manifest),
        companies=companies,
        jd_inputs=_build_jd_inputs(candidate_id, jd_profiles),
        run_artifacts=_build_run_artifacts(run_id, run_dir),
        resume_variants=_attach_run_candidate(
            _read_json_if_exists(run_dir / "generate" / "resume_variants.json") or [],
            run_id=run_id,
            candidate_id=candidate_id,
            id_key="variant_id",
        ),
        requirement_evidence=_attach_run_candidate(
            _read_json_if_exists(run_dir / "analyze" / "requirement_matrix.json") or [],
            run_id=run_id,
            candidate_id=candidate_id,
            id_key="requirement_id",
        ),
        preflight_gates=_attach_run(_read_json_if_exists(run_dir / "analyze" / "preflight_gates.json") or [], run_id=run_id),
        scorecards=_attach_run_candidate(
            _read_json_if_exists(run_dir / "evaluate" / "scorecards.json") or [],
            run_id=run_id,
            candidate_id=candidate_id,
            id_key="variant_id",
        ),
        gap_maps=_attach_run_candidate(
            _read_json_if_exists(run_dir / "evaluate" / "gap_maps.json") or [],
            run_id=run_id,
            candidate_id=candidate_id,
            id_key="jd_id",
        ),
        ranking_explanations=_attach_run(
            _read_json_if_exists(run_dir / "evaluate" / "ranking_explanations.json") or [], run_id=run_id
        ),
        application_strategies=_attach_run_candidate(
            _read_json_if_exists(run_dir / "plan" / "application_strategies.json") or [],
            run_id=run_id,
            candidate_id=candidate_id,
            id_key="jd_id",
        ),
    )
    if include_chunks:
        return ProjectionBatch(**{**batch.__dict__, "retrieval_chunks": build_retrieval_chunks(run_dir, run_id, candidate_id)})
    return batch


def index_runs(runs_dir: Path, database_url: str, *, skip_chunks: bool = False) -> dict[str, int]:
    from shotguncv_core.db.session import connect

    run_dirs = [path for path in sorted(runs_dir.iterdir()) if path.is_dir()]
    with connect(database_url) as conn:
        _ensure_schema(conn)
        counts = {"runs": 0, "chunks": 0}
        for run_dir in run_dirs:
            stage_started = log_stage_started(run_dir, "index")
            try:
                batch = build_projection_batch(run_dir, include_chunks=not skip_chunks)
                _upsert_batch(conn, batch, skip_chunks=skip_chunks)
                chunk_count = len(batch.retrieval_chunks)
                counts["runs"] += 1
                counts["chunks"] += chunk_count
                log_index_batch(
                    run_dir,
                    run_id=batch.run.run_id,
                    artifact_count=len(batch.run_artifacts),
                    chunk_count=chunk_count,
                    started=stage_started,
                    skip_chunks=skip_chunks,
                )
                log_stage_finished(run_dir, "index", stage_started)
            except Exception as exc:
                log_stage_failed(run_dir, "index", stage_started, exc)
                raise
        conn.commit()
        return counts


def _ensure_schema(conn: object) -> None:
    with conn.cursor() as cur:
        for statement in all_schema_sql():
            cur.execute(statement)


def _upsert_batch(conn: object, batch: ProjectionBatch, *, skip_chunks: bool) -> None:
    from psycopg.types.json import Json

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO candidates(candidate_id, payload) VALUES (%s, %s)
            ON CONFLICT(candidate_id) DO UPDATE SET payload=EXCLUDED.payload, updated_at=now()
            """,
            (batch.run.candidate_id, Json(batch.candidates[0]["payload"])),
        )
        for company in batch.companies:
            cur.execute(
                """
                INSERT INTO companies(company_id, name, payload) VALUES (%s, %s, %s)
                ON CONFLICT(company_id) DO UPDATE SET name=EXCLUDED.name, payload=EXCLUDED.payload, updated_at=now()
                """,
                (company["company_id"], company["name"], Json(company["payload"])),
            )
        cur.execute(
            """
            INSERT INTO runs(run_id, candidate_id, run_dir, payload) VALUES (%s, %s, %s, %s)
            ON CONFLICT(run_id) DO UPDATE
            SET candidate_id=EXCLUDED.candidate_id, run_dir=EXCLUDED.run_dir, payload=EXCLUDED.payload, updated_at=now()
            """,
            (batch.run.run_id, batch.run.candidate_id, batch.run.run_dir, Json(batch.run.payload)),
        )
        _upsert_simple_rows(cur, "candidate_sources", ["source_id"], batch.candidate_sources)
        _upsert_simple_rows(cur, "jd_inputs", ["jd_id"], batch.jd_inputs)
        _upsert_simple_rows(cur, "run_artifacts", ["run_id", "artifact_path"], batch.run_artifacts)
        _upsert_simple_rows(cur, "resume_variants", ["run_id", "variant_id"], batch.resume_variants)
        _upsert_simple_rows(cur, "requirement_evidence", ["run_id", "jd_id", "requirement_id"], batch.requirement_evidence)
        _upsert_simple_rows(cur, "preflight_gates", ["run_id", "jd_id"], batch.preflight_gates)
        _upsert_simple_rows(cur, "scorecards", ["run_id", "jd_id", "variant_id"], batch.scorecards)
        _upsert_simple_rows(cur, "gap_maps", ["run_id", "jd_id"], batch.gap_maps)
        _upsert_simple_rows(cur, "ranking_explanations", ["run_id", "jd_id", "variant_id"], batch.ranking_explanations)
        _upsert_simple_rows(cur, "application_strategies", ["run_id", "jd_id"], batch.application_strategies)
        if not skip_chunks:
            for chunk in batch.retrieval_chunks:
                metadata = chunk["metadata"]
                cur.execute(
                    """
                    INSERT INTO retrieval_chunks(
                        chunk_id, source_type, source_id, candidate_id, jd_id, run_id, artifact_path,
                        provenance_summary, text, metadata, embedding
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT(chunk_id) DO UPDATE SET
                        source_type=EXCLUDED.source_type,
                        source_id=EXCLUDED.source_id,
                        candidate_id=EXCLUDED.candidate_id,
                        jd_id=EXCLUDED.jd_id,
                        run_id=EXCLUDED.run_id,
                        artifact_path=EXCLUDED.artifact_path,
                        provenance_summary=EXCLUDED.provenance_summary,
                        text=EXCLUDED.text,
                        metadata=EXCLUDED.metadata,
                        embedding=EXCLUDED.embedding,
                        updated_at=now()
                    """,
                    (
                        chunk["chunk_id"],
                        metadata["source_type"],
                        metadata["source_id"],
                        metadata["candidate_id"],
                        metadata.get("jd_id"),
                        metadata.get("run_id"),
                        metadata.get("artifact_path"),
                        metadata["provenance_summary"],
                        chunk["text"],
                        Json(metadata),
                        embed_text(chunk["text"]),
                    ),
                )


def _upsert_simple_rows(cur: object, table: str, conflict_keys: list[str], rows: list[dict[str, Any]]) -> None:
    from psycopg.types.json import Json

    table_columns = TABLE_COLUMNS[table]
    for row in rows:
        payload = row.get("payload", row)
        columns = table_columns
        placeholders = ", ".join(["%s"] * len(columns))
        updates = ", ".join(f"{column}=EXCLUDED.{column}" for column in columns if column not in conflict_keys)
        conflict = ", ".join(conflict_keys)
        sql = (
            f"INSERT INTO {table}({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT({conflict}) DO UPDATE SET {updates}, updated_at=now()"
        )
        values = [row.get(column) for column in columns if column != "payload"] + [Json(payload)]
        cur.execute(sql, values)


def _read_json_if_exists(path: Path) -> Any:
    if not path.exists():
        return None
    return load_json(path)


def _build_candidate_sources(candidate_id: str, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(manifest.get("candidate_inputs", []) or []):
        source_id = f"{candidate_id}:candidate-source:{index}:{item.get('relative_path') or item.get('source_value') or index}"
        rows.append(
            {
                "source_id": _stable_id(source_id),
                "candidate_id": candidate_id,
                "source_type": str(item.get("source_type") or "unknown"),
                "artifact_path": item.get("relative_path") or item.get("source_value"),
                "payload": item,
            }
        )
    return rows


def _build_companies(jd_profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    companies: dict[str, dict[str, Any]] = {}
    for jd in jd_profiles:
        name = str(jd.get("company") or "Unknown").strip() or "Unknown"
        company_id = _slug(name)
        companies[company_id] = {"company_id": company_id, "name": name, "payload": {"name": name, "source": "jd_profile"}}
    return list(companies.values())


def _build_jd_inputs(candidate_id: str, jd_profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for jd in jd_profiles:
        company = str(jd.get("company") or "Unknown").strip() or "Unknown"
        rows.append(
            {
                "jd_id": jd["jd_id"],
                "company_id": _slug(company),
                "candidate_id": candidate_id,
                "source_type": str(jd.get("source_type") or "unknown"),
                "source_value": str(jd.get("source_value") or ""),
                "payload": jd,
            }
        )
    return rows


def _build_run_artifacts(run_id: str, run_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for artifact_path in ARTIFACT_PATHS:
        path = run_dir / artifact_path
        if not path.exists():
            continue
        payload: Any
        if path.suffix == ".json":
            payload = load_json(path)
        else:
            payload = {"text_preview": path.read_text(encoding="utf-8", errors="replace")[:2000]}
        rows.append({"run_id": run_id, "artifact_path": artifact_path, "payload": payload})
    return rows


def _attach_run(items: list[dict[str, Any]], *, run_id: str) -> list[dict[str, Any]]:
    return [{"run_id": run_id, **item, "payload": item} for item in items]


def _attach_run_candidate(
    items: list[dict[str, Any]], *, run_id: str, candidate_id: str, id_key: str
) -> list[dict[str, Any]]:
    rows = []
    for item in items:
        row = {"run_id": run_id, "candidate_id": candidate_id, **item, "payload": item}
        if id_key not in row:
            row[id_key] = _stable_id(json.dumps(item, ensure_ascii=False, sort_keys=True))
        rows.append(row)
    return rows


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or _stable_id(value)[:12]


def _stable_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
