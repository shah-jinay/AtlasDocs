"""widen embedding column to 1536 dims (openai text-embedding-3-small)

Revision ID: 0003
Revises: 0001
Create Date: 2026-09-06

This is a sibling branch of 0002 (hnsw_index), not a continuation of it --
both apply on top of 0001, and they're independent, composable changes
(HNSW works at any vector width). If you want both HNSW *and* 1536-dim
embeddings, run `alembic upgrade 0003` then `alembic merge heads` to
create a merge revision, then `alembic upgrade head`.

pgvector cannot cast an existing vector(384) value to vector(1536) --
the dimensions are simply different data. There is no in-place migration
path for real production data hitting this; it means a full re-embed.
For this project's fixture/demo data, that's exactly what happens here:
existing chunks (and the query telemetry that references them) are
wiped, and every document must be re-ingested against the new provider
-- see scripts/ingest_fixture.py.
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "0003"
down_revision = "0001"
branch_labels = None
depends_on = None

NEW_DIMENSION = 1536


def upgrade() -> None:
    # Existing embeddings are incompatible with the new width -- there is
    # nothing to migrate them to, so clear everything downstream of a
    # document's chunks and force a clean re-ingest.
    op.execute("TRUNCATE TABLE query_citations, query_runs, document_chunks, ingestion_jobs, documents CASCADE")
    op.alter_column(
        "document_chunks",
        "embedding",
        type_=Vector(NEW_DIMENSION),
        existing_type=Vector(384),
        postgresql_using="NULL",  # table is empty post-truncate; nothing to cast
    )


def downgrade() -> None:
    op.execute("TRUNCATE TABLE query_citations, query_runs, document_chunks, ingestion_jobs, documents CASCADE")
    op.alter_column(
        "document_chunks",
        "embedding",
        type_=Vector(384),
        existing_type=Vector(NEW_DIMENSION),
        postgresql_using="NULL",
    )
