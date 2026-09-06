#!/usr/bin/env python3
"""Evaluation runner (blueprint section 15.4).

Usage (after `docker compose up -d --build` and ingesting fixtures/sample.txt
as the `alice` dev user -- see scripts/ingest_fixture.py):

    python evaluation/run_eval.py --dataset evaluation/datasets/baseline.jsonl

For each labeled question this calls the live API (exactly what a client
would call) with eval_mode=true to get back the ranked retrieved chunk ids
alongside the answer and validated citations, resolves each case's labeled
"relevant" chunks by looking up the current chunk table directly (chunk ids
are regenerated every time a fixture is re-ingested, so they can't be
hardcoded into the checked-in dataset), and scores Recall@K/MRR/Precision@K/
citation precision & recall/answer score/abstention accuracy.

Every run is written to evaluation/runs/<timestamp>-<git-sha>.json with the
config and commit hash attached, per section 15.5 ("persist config + git
commit hash with every evaluation result").
"""
import argparse
import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import NamedTuple

import httpx
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.security import email_to_user_id  # noqa: E402
from app.db.models import Document, DocumentChunk  # noqa: E402
from app.db.session import get_sessionmaker  # noqa: E402

from metrics import MetricsAccumulator  # noqa: E402

DEFAULT_DATASET = Path(__file__).parent / "datasets" / "baseline.jsonl"
DEFAULT_OUTPUT_DIR = Path(__file__).parent / "runs"


def load_dataset(path: Path) -> list[dict]:
    cases = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


class ResolvedCase(NamedTuple):
    relevant_chunk_ids: set[str]
    relevant_document_ids: set[str]


async def resolve_relevant(owner_email: str, relevant: list[dict]) -> ResolvedCase:
    """Look up which real chunk_ids and document_ids currently satisfy each
    labeled (document_filename, content_contains) pair for this owner.
    Chunk ids can't be hardcoded into the checked-in dataset because they
    are regenerated every time a fixture is re-ingested (see module
    docstring), so this resolves them against the live database instead.
    """
    if not relevant:
        return ResolvedCase(set(), set())
    owner_id = email_to_user_id(owner_email)
    chunk_ids: set[str] = set()
    document_ids: set[str] = set()
    async with get_sessionmaker()() as db:
        for entry in relevant:
            stmt = (
                select(DocumentChunk.id, DocumentChunk.document_id)
                .join(Document, Document.id == DocumentChunk.document_id)
                .where(
                    Document.owner_id == owner_id,
                    Document.filename == entry["document_filename"],
                    Document.status == "READY",
                    DocumentChunk.processing_version == Document.processing_version,
                    DocumentChunk.content.ilike(f"%{entry['content_contains']}%"),
                )
            )
            rows = (await db.execute(stmt)).all()
            chunk_ids.update(str(r.id) for r in rows)
            document_ids.update(str(r.document_id) for r in rows)
    return ResolvedCase(chunk_ids, document_ids)


def git_commit_hash() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()
    except Exception:
        return "unknown"


async def run(args: argparse.Namespace) -> None:
    cases = load_dataset(Path(args.dataset))
    accumulator = MetricsAccumulator()

    # 60s: a real generation provider can take 15-25s+ per call; the mock
    # provider is instant, but this has to tolerate whichever is configured.
    with httpx.Client(base_url=args.api_base, timeout=60.0) as client:
        headers = {"Authorization": f"Bearer {args.api_key}"}
        for case in cases:
            resolved = await resolve_relevant(args.owner_email, case.get("relevant", []))

            resp = client.post(
                "/v1/query",
                headers=headers,
                json={"question": case["question"], "top_k": args.top_k, "eval_mode": True},
            )
            resp.raise_for_status()
            body = resp.json()

            retrieved_ids = [str(c["chunk_id"]) for c in (body.get("debug_retrieved_chunks") or [])]
            # Citations round-trip filename/page/excerpt but not chunk_id to
            # the client by design (section 13.3) -- citation precision/
            # recall are therefore scored at document granularity instead
            # of chunk granularity.
            cited_document_ids = {c["document_id"] for c in body["citations"]}

            accumulator.add_case(
                case_id=case["id"],
                relevant_ids=resolved.relevant_chunk_ids,
                retrieved_ids=retrieved_ids,
                cited_ids=cited_document_ids,
                relevant_cited_ids=resolved.relevant_document_ids,
                answer=body["answer"],
                must_include=case.get("must_include", []),
                must_not_claim=case.get("must_not_claim", []),
                k=args.top_k,
                expect_abstention=case.get("expect_abstention"),
                actual_abstained=body.get("insufficient_evidence", False),
            )

    summary = accumulator.summary()
    print(json.dumps(summary, indent=2))

    timestamp = time.strftime("%Y-%m-%dT%H-%M-%S")
    output_path = DEFAULT_OUTPUT_DIR / f"{timestamp}-{git_commit_hash()}.json"
    accumulator.write_json(
        str(output_path),
        extra_meta={
            "git_commit": git_commit_hash(),
            "dataset": str(args.dataset),
            "top_k": args.top_k,
            "api_base": args.api_base,
        },
    )
    print(f"\nWrote {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--api-base", default="http://localhost:8000")
    parser.add_argument("--api-key", default="dev-key-alice")
    parser.add_argument("--owner-email", default="alice@example.com")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
