"""Switch retrieval embeddings to BAAI/bge-m3 dimensions."""

from __future__ import annotations

from alembic import op


revision = "20260526_0002_bge_m3_embeddings"
down_revision = "20260519_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS retrieval_chunks_embedding_idx")
    op.execute("ALTER TABLE retrieval_chunks ALTER COLUMN embedding TYPE vector(1024) USING NULL::vector(1024)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS retrieval_chunks_embedding_idx "
        "ON retrieval_chunks USING ivfflat (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS retrieval_chunks_embedding_idx")
    op.execute("ALTER TABLE retrieval_chunks ALTER COLUMN embedding TYPE vector(64) USING NULL::vector(64)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS retrieval_chunks_embedding_idx "
        "ON retrieval_chunks USING ivfflat (embedding vector_cosine_ops)"
    )
