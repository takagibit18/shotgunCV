from __future__ import annotations


SCHEMA_VERSION = "20260519_0001_projection_rag"
EMBEDDING_DIMENSIONS = 64


CREATE_EXTENSION_SQL = "CREATE EXTENSION IF NOT EXISTS vector"


CREATE_TABLE_SQL: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS candidates (
        candidate_id text PRIMARY KEY,
        payload jsonb NOT NULL,
        updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS candidate_sources (
        source_id text PRIMARY KEY,
        candidate_id text NOT NULL REFERENCES candidates(candidate_id) ON DELETE CASCADE,
        source_type text NOT NULL,
        artifact_path text,
        payload jsonb NOT NULL,
        updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS companies (
        company_id text PRIMARY KEY,
        name text NOT NULL,
        payload jsonb NOT NULL,
        updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS jd_inputs (
        jd_id text PRIMARY KEY,
        company_id text REFERENCES companies(company_id) ON DELETE SET NULL,
        candidate_id text REFERENCES candidates(candidate_id) ON DELETE CASCADE,
        source_type text NOT NULL,
        source_value text NOT NULL,
        payload jsonb NOT NULL,
        updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runs (
        run_id text PRIMARY KEY,
        candidate_id text NOT NULL REFERENCES candidates(candidate_id) ON DELETE CASCADE,
        run_dir text NOT NULL,
        payload jsonb NOT NULL,
        updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS run_artifacts (
        run_id text NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
        artifact_path text NOT NULL,
        payload jsonb NOT NULL,
        updated_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (run_id, artifact_path)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS resume_variants (
        run_id text NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
        variant_id text NOT NULL,
        candidate_id text NOT NULL REFERENCES candidates(candidate_id) ON DELETE CASCADE,
        payload jsonb NOT NULL,
        updated_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (run_id, variant_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS requirement_evidence (
        run_id text NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
        jd_id text NOT NULL,
        requirement_id text NOT NULL,
        candidate_id text NOT NULL REFERENCES candidates(candidate_id) ON DELETE CASCADE,
        payload jsonb NOT NULL,
        updated_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (run_id, jd_id, requirement_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS preflight_gates (
        run_id text NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
        jd_id text NOT NULL,
        payload jsonb NOT NULL,
        updated_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (run_id, jd_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS scorecards (
        run_id text NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
        jd_id text NOT NULL,
        variant_id text NOT NULL,
        candidate_id text NOT NULL REFERENCES candidates(candidate_id) ON DELETE CASCADE,
        payload jsonb NOT NULL,
        updated_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (run_id, jd_id, variant_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gap_maps (
        run_id text NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
        jd_id text NOT NULL,
        candidate_id text NOT NULL REFERENCES candidates(candidate_id) ON DELETE CASCADE,
        payload jsonb NOT NULL,
        updated_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (run_id, jd_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ranking_explanations (
        run_id text NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
        jd_id text NOT NULL,
        variant_id text NOT NULL,
        payload jsonb NOT NULL,
        updated_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (run_id, jd_id, variant_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS application_strategies (
        run_id text NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
        jd_id text NOT NULL,
        candidate_id text NOT NULL REFERENCES candidates(candidate_id) ON DELETE CASCADE,
        payload jsonb NOT NULL,
        updated_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (run_id, jd_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS application_feedback (
        feedback_id text PRIMARY KEY,
        run_id text REFERENCES runs(run_id) ON DELETE SET NULL,
        candidate_id text NOT NULL REFERENCES candidates(candidate_id) ON DELETE CASCADE,
        jd_id text,
        payload jsonb NOT NULL,
        updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS retrieval_chunks (
        chunk_id text PRIMARY KEY,
        source_type text NOT NULL,
        source_id text NOT NULL,
        candidate_id text NOT NULL REFERENCES candidates(candidate_id) ON DELETE CASCADE,
        jd_id text,
        run_id text REFERENCES runs(run_id) ON DELETE CASCADE,
        artifact_path text,
        provenance_summary text NOT NULL,
        text text NOT NULL,
        metadata jsonb NOT NULL,
        embedding vector({EMBEDDING_DIMENSIONS}),
        updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS retrieval_chunks_source_idx ON retrieval_chunks(source_type, candidate_id, jd_id, run_id)",
    "CREATE INDEX IF NOT EXISTS retrieval_chunks_embedding_idx ON retrieval_chunks USING ivfflat (embedding vector_cosine_ops)",
]


def all_schema_sql() -> list[str]:
    return [CREATE_EXTENSION_SQL, *CREATE_TABLE_SQL]
