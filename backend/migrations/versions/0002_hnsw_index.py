"""hnsw index for approximate nearest-neighbor retrieval

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-05

Do not run this until you have benchmarked exact-vs-HNSW recall on real
data (blueprint sections 4.3, 12.2, milestone M6). It is a separate,
opt-in migration -- not applied by the default `alembic upgrade head` in
docker-compose -- specifically so the vertical slice starts on the exact
baseline it needs for evaluation ground truth. Run `alembic upgrade 0002`
once evaluation/run_eval.py has a baseline result to compare against.

CONCURRENTLY cannot run inside Alembic's transactional DDL, so this
migration runs outside a transaction.
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_chunks_embedding_hnsw "
            "ON document_chunks USING hnsw (embedding vector_cosine_ops)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_chunks_embedding_hnsw")
