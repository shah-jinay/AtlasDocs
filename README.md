# AtlasDocs

A multi-tenant RAG (Retrieval-Augmented Generation) platform for asking
questions over your own private documents, with citations the backend
validates rather than trusts. Built from the engineering blueprint in
`AtlasDocs.pdf`.

This repo implements the **local vertical slice** from that blueprint
(milestones M0–M4, plus the evaluation harness and a load-test script):
upload → parse → chunk → embed → tenant-filtered pgvector retrieval →
citation-constrained generation → backend citation validation — running
entirely on your machine with **zero API keys required**. AWS deployment
(ECS/RDS/real S3+SQS), the HNSW-vs-exact benchmark, and a measured load
test are wired up and ready to run, but deliberately not pre-filled with
invented numbers — see [Honest status](#honest-status).

## Architecture

```
React ──HTTPS──▶ FastAPI ──SQL──▶ RDS PostgreSQL + pgvector
                    │                       ▲
                    │ enqueue               │ write chunks/embeddings
                    ▼                       │
                  SQS/ElasticMQ ──poll──▶ Worker service
                    │                       │
                    ▼                       ▼
                  DLQ                  S3/MinIO (documents)
```

The API and the ingestion worker are **separate processes/containers**
(`app.main` vs `app.workers.main`). That separation is the entire point of
the architecture: bulk uploads run on worker compute, never on the
container answering interactive queries. Locally, MinIO stands in for S3
and ElasticMQ stands in for SQS — both talk the same boto3 S3/SQS API the
code would use against real AWS, so nothing here is a mock of the
*infrastructure*, only of the *cloud provider*.

## Quickstart

```bash
cp .env.example .env
docker compose up -d --build

curl http://localhost:8000/health
open http://localhost:5173                 # or just visit it in a browser

# Load a stable fixture document (needed by evaluation/ and load-tests/)
pip install -r backend/requirements.txt     # once, for the venv running these scripts
python scripts/ingest_fixture.py
```

The frontend's user switcher (top right) picks between two dev accounts
(`alice`, `bob`) that map to `Authorization: Bearer dev-key-alice` /
`dev-key-bob` — see [Auth](#auth-demo-grade). Ask a question on the `/ask`
page once a document shows **READY**.

### Zero-config by design

- **Embeddings**: `EMBEDDING_PROVIDER=mock` (default) is a deterministic
  hashed bag-of-words embedding — a real, testable retrieval baseline with
  no network call. Set `EMBEDDING_PROVIDER=openai` + `OPENAI_API_KEY` for
  real embedding quality (see [Changing the embedding
  model](#changing-the-embedding-model)).
- **Generation**: `GENERATION_PROVIDER=mock` (default) answers extractively
  from the single most relevant retrieved chunk and cites exactly that
  chunk — genuinely grounded, just not a synthesized answer. Set
  `GENERATION_PROVIDER=anthropic` + `ANTHROPIC_API_KEY` for real answers.

Both defaults exist so `docker compose up` is immediately answerable
end-to-end. Flip the two provider flags in `.env` once you want to demo or
evaluate real model quality.

## Repository structure

```
backend/app/
  api/        FastAPI routers (documents, query, health)
  core/       settings, structured logging, auth
  db/         SQLAlchemy models, repositories
  ingestion/  parser, chunker, embedding batching, pipeline orchestration
  rag/        embedding/generation provider interfaces, retrieval SQL,
              prompt/context packing, citation validation
  storage/    S3-compatible adapter (MinIO locally, S3 in AWS)
  queue/      SQS-compatible adapter (ElasticMQ locally, SQS in AWS)
  workers/    the long-polling ingestion worker entrypoint
backend/migrations/   Alembic; 0001 = baseline schema (exact search),
                       0002 = opt-in HNSW index (run after benchmarking)
backend/tests/        unit tests (no infra) + a gated e2e suite (needs the stack up)
frontend/src/         React app: /documents, /documents/:id, /ask
evaluation/           labeled dataset (JSONL), metrics.py, run_eval.py
load-tests/           query_vs_ingestion.py — the section 16 benchmark
scripts/              ingest_fixture.py (bootstraps a stable corpus)
fixtures/             sample.txt used by tests, eval, and the demo
```

## Running tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest                                   # unit tests: chunker, parser,
                                          # citation validation, generation
                                          # parsing, embedding provider —
                                          # none of these need Docker.

# End-to-end acceptance test (blueprint section 22.3) — needs the stack up:
docker compose up -d --build
ATLASDOCS_INTEGRATION=1 pytest tests/test_integration_e2e.py -v
```

```bash
cd evaluation && pytest test_metrics.py    # pure scoring-function tests
```

## Evaluation (blueprint section 15)

```bash
python scripts/ingest_fixture.py            # once, to have a stable corpus
python evaluation/run_eval.py               # scores evaluation/datasets/baseline.jsonl
```

Writes `evaluation/runs/<timestamp>-<git-sha>.json` with Recall@K, MRR,
Precision@K, citation precision/recall, an automated 0/1/2 answer-accuracy
proxy, and abstention accuracy — plus the config and commit hash that
produced it, so results are comparable across runs (section 15.5). The
checked-in dataset (`evaluation/datasets/baseline.jsonl`) is deliberately
small (4 questions against one fixture); treat it as a template to grow,
not a finished benchmark.

## Load test (blueprint section 16)

```bash
python load-tests/query_vs_ingestion.py --duration 120 --qps 2 --bulk-docs 20
```

Measures client-observed query p50/p95/p99 with no concurrent ingestion,
then again while concurrently uploading and ingesting synthetic documents,
and prints/writes the section 16.2 comparison table with a pass/fail
verdict against `--p95-threshold-pct` (default 10%). **Nobody should quote
a "query latency stayed flat" number from this repo until this script has
actually been run** — see [Honest status](#honest-status).

## Changing the embedding model

The embedding dimension is baked into the `document_chunks.embedding`
column at migration time (`backend/migrations/versions/0001_initial_schema.py`,
`EMBEDDING_DIMENSION = 384`, matching the mock provider). Switching to a
model with a different native dimension (e.g. OpenAI's
`text-embedding-3-small` at 1536) requires:

1. Set `EMBEDDING_PROVIDER=openai`, `EMBEDDING_DIMENSION=1536`, `OPENAI_API_KEY` in `.env`.
2. Write a new migration changing the `vector(...)` column size (or drop
   and recreate it in dev).
3. Re-ingest existing documents — a `processing_version` bump, not an
   in-place vector rewrite (blueprint section 11.1).

## Enabling HNSW (blueprint section 4.3, milestone M6)

Migration `0001` intentionally does not create an ANN index — exact
nearest-neighbor search is the evaluation baseline. Once
`evaluation/run_eval.py` has a baseline result on real data:

```bash
cd backend && alembic upgrade 0002    # CONCURRENTLY-created HNSW index
```

No application code changes — pgvector picks the index transparently, and
`app/rag/retrieval.py` doesn't know or care which one served the query. Compare
recall/latency against the exact-search baseline (section 15.2, "Exact-vs-HNSW recall") before treating it as the production configuration.

## Auth (demo-grade)

`backend/app/core/security.py` maps a static bearer token to a user via
`DEV_API_KEYS` in `.env` (`token:email` pairs). This is enough to
demonstrate real tenant isolation (every retrieval SQL query filters on
`owner_id` — see `app/rag/retrieval.py`) without building a login system.
Replace it with real OAuth2/JWT/session auth before this is anything but a
portfolio/demo deployment; nothing downstream assumes a particular auth
mechanism.

## Honest status

Sections 1.2 and 16 of the blueprint are explicit that certain resume
claims must be backed by a real, reproducible measurement — not asserted
from architecture. Where this repo stands today:

| Claim | Status |
|---|---|
| End-to-end RAG pipeline | ✅ Implemented and covered by the e2e acceptance test |
| Citation-grounded responses | ✅ Backend validation implemented and unit-tested (`test_citations.py`) |
| Vector similarity search (exact) | ✅ Implemented; tenant-filtered pgvector query |
| Exact vs. HNSW benchmark | 🔲 Migration ready (`0002`); **not yet run** — no recall/latency numbers exist yet |
| Evaluated answer accuracy | ⚠️ Harness implemented with a 4-question starter dataset; grow the dataset before quoting a score |
| Query latency stayed flat during bulk uploads | 🔲 Load-test script implemented; **has not been run** — no percentile numbers exist yet |
| Deployed on AWS | 🔲 Not implemented in this repo (ECS/RDS/real S3+SQS + Terraform/CFN are milestone M7, still open) |

Do not put percentages, recall numbers, or "stayed flat" language on a
resume from this repo until the corresponding script has actually been run
against a real corpus and the result committed alongside the config that
produced it.

## Environment variables

See `.env.example` for the full list with inline documentation
(`app/core/config.py` is the source of truth).
