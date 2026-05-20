"""create optional projection and retrieval tables

Revision ID: 20260519_0001
Revises:
Create Date: 2026-05-19
"""

from __future__ import annotations

from alembic import op

from shotguncv_core.db.schema import CREATE_EXTENSION_SQL, CREATE_TABLE_SQL


revision = "20260519_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(CREATE_EXTENSION_SQL)
    for statement in CREATE_TABLE_SQL:
        op.execute(statement)


def downgrade() -> None:
    for table in [
        "retrieval_chunks",
        "application_feedback",
        "application_strategies",
        "ranking_explanations",
        "gap_maps",
        "scorecards",
        "preflight_gates",
        "requirement_evidence",
        "resume_variants",
        "run_artifacts",
        "runs",
        "jd_inputs",
        "companies",
        "candidate_sources",
        "candidates",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
