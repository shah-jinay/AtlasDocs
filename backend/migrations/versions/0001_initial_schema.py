"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-05

Creates the core tables from blueprint section 7. Deliberately does NOT
create an HNSW index yet -- exact nearest-neighbor search is the evaluation
baseline (section 4.3); migration 0002 adds HNSW once there's a benchmark
justifying it (milestone M6).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# Must match Settings.embedding_dimension / the mock embedding provider.
# Changing providers to a different dimension requires a new migration
# (see backend/app/db/models.py and README "Changing the embedding model").
EMBEDDING_DIMENSION = 384


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("s3_key", sa.Text(), nullable=False, unique=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("status", sa.Text(), nullable=False, server_default="UPLOADING"),
        sa.Column("processing_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("page_count", sa.Integer()),
        sa.Column("chunk_count", sa.Integer()),
        sa.Column("error_code", sa.Text()),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('UPLOADING','QUEUED','PROCESSING','READY','FAILED','DELETED')",
            name="ck_documents_status",
        ),
    )
    op.create_index("ix_documents_owner_id", "documents", ["owner_id"])

    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("processing_version", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("page_start", sa.Integer()),
        sa.Column("page_end", sa.Integer()),
        sa.Column("section_path", sa.Text()),
        sa.Column("token_count", sa.Integer()),
        sa.Column("content_sha256", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIMENSION)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("document_id", "processing_version", "chunk_index", name="uq_chunk_position"),
    )
    op.create_index("idx_chunks_document", "document_chunks", ["document_id", "processing_version"])

    op.create_table(
        "ingestion_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.Text(), nullable=False, server_default="QUEUED"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
    )

    op.create_table(
        "query_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("retrieval_k", sa.Integer(), nullable=False),
        sa.Column("answer", sa.Text()),
        sa.Column("total_latency_ms", sa.Integer()),
        sa.Column("retrieval_latency_ms", sa.Integer()),
        sa.Column("generation_latency_ms", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_query_runs_owner_id", "query_runs", ["owner_id"])

    op.create_table(
        "query_citations",
        sa.Column("query_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("query_runs.id"), primary_key=True),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("document_chunks.id"), primary_key=True),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("distance", sa.Double()),
        sa.Column("cited", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_table("query_citations")
    op.drop_table("query_runs")
    op.drop_table("ingestion_jobs")
    op.drop_table("document_chunks")
    op.drop_table("documents")
