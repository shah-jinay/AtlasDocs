#!/usr/bin/env python3
"""Query-vs-bulk-ingestion load test (blueprint section 16).

This is the actual evidence behind "query latency stayed flat during bulk
uploads" -- that claim must never be asserted from architecture alone
(section 16.1). Run it against a running local stack (or a real AWS
deployment, pointed at with --api-base) with a stable corpus already
ingested:

    docker compose up -d --build
    python scripts/ingest_fixture.py             # loads fixtures/sample.txt
    python load-tests/query_vs_ingestion.py --duration 120 --qps 3

It measures a fixed query workload's client-observed latency twice: once
with no concurrent ingestion (baseline), once while concurrently uploading
and ingesting a batch of synthetic documents (treatment) -- with the API
task count held fixed across both phases (section 16.1 step 5), since the
result is meant to demonstrate workload isolation, not just more capacity.
Results, including the pass/fail verdict against the threshold you set,
are written to load-tests/results/<timestamp>.json (section 16.2).
"""
import argparse
import asyncio
import json
import statistics
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.queue import sqs as sqs_adapter  # noqa: E402

QUESTIONS = [
    "What is the data retention period for uploaded documents?",
    "Why is document ingestion handled by a separate worker service?",
    "Does AtlasDocs support OCR for scanned PDFs in this version?",
]


@dataclass
class RequestResult:
    latency_ms: float
    success: bool


@dataclass
class PhaseResult:
    name: str
    n_requests: int
    error_rate: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    queue_depth_samples: list[int]


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    return statistics.quantiles(values, n=100, method="inclusive")[int(pct) - 1] if len(values) > 1 else values[0]


async def _ask_once(client: httpx.AsyncClient, headers: dict, question: str) -> RequestResult:
    start = time.perf_counter()
    try:
        resp = await client.post("/v1/query", headers=headers, json={"question": question})
        resp.raise_for_status()
        return RequestResult(latency_ms=(time.perf_counter() - start) * 1000, success=True)
    except Exception:
        return RequestResult(latency_ms=(time.perf_counter() - start) * 1000, success=False)


async def _query_workload(
    client: httpx.AsyncClient, headers: dict, *, duration_s: float, qps: float
) -> list[RequestResult]:
    results: list[RequestResult] = []
    interval = 1.0 / qps
    deadline = time.perf_counter() + duration_s
    tasks = []
    while time.perf_counter() < deadline:
        question = QUESTIONS[len(tasks) % len(QUESTIONS)]
        tasks.append(asyncio.create_task(_ask_once(client, headers, question)))
        await asyncio.sleep(interval)
    results = await asyncio.gather(*tasks)
    return list(results)


def _synthetic_document_bytes(index: int) -> bytes:
    filler = (
        f"Synthetic load-test document {index}.\n\n"
        "This paragraph exists only to give the parser and chunker real "
        "text to process during the bulk-ingestion phase of the load "
        "test, so worker CPU and embedding calls reflect realistic work. "
    ) * 20
    return filler.encode("utf-8")


async def _upload_one(client: httpx.AsyncClient, headers: dict, index: int) -> None:
    data = _synthetic_document_bytes(index)
    init = await client.post(
        "/v1/documents/uploads",
        headers=headers,
        json={"filename": f"loadtest-{uuid.uuid4().hex[:8]}.txt", "mime_type": "text/plain", "size_bytes": len(data)},
    )
    init.raise_for_status()
    payload = init.json()
    put_resp = await client.put(payload["upload_url"], content=data, headers={"Content-Type": "text/plain"})
    put_resp.raise_for_status()
    complete = await client.post(f"/v1/documents/{payload['document_id']}/complete", headers=headers)
    complete.raise_for_status()


async def _bulk_ingest(client: httpx.AsyncClient, headers: dict, *, count: int) -> None:
    await asyncio.gather(*[_upload_one(client, headers, i) for i in range(count)])


def _sample_queue_depth() -> int:
    try:
        return sqs_adapter.queue_depth()
    except Exception:
        return -1


def _summarize(name: str, results: list[RequestResult], queue_depths: list[int]) -> PhaseResult:
    latencies = [r.latency_ms for r in results]
    errors = sum(1 for r in results if not r.success)
    return PhaseResult(
        name=name,
        n_requests=len(results),
        error_rate=round(errors / len(results), 4) if results else 0.0,
        p50_ms=round(_percentile(latencies, 50), 1),
        p95_ms=round(_percentile(latencies, 95), 1),
        p99_ms=round(_percentile(latencies, 99), 1),
        queue_depth_samples=queue_depths,
    )


async def run(args: argparse.Namespace) -> None:
    headers = {"Authorization": f"Bearer {args.api_key}"}
    # 60s: a real generation provider can take 15-25s+ per call; the mock
    # provider is instant, but this has to tolerate whichever is configured.
    async with httpx.AsyncClient(base_url=args.api_base, timeout=60.0) as client:
        print(f"Warming up for {args.warmup}s...")
        await _query_workload(client, headers, duration_s=args.warmup, qps=args.qps)

        print(f"Baseline: {args.duration}s at {args.qps} qps, no concurrent ingestion...")
        baseline_results = await _query_workload(client, headers, duration_s=args.duration, qps=args.qps)
        baseline = _summarize("baseline", baseline_results, queue_depths=[_sample_queue_depth()])

        print(f"Treatment: {args.duration}s at {args.qps} qps, concurrently ingesting {args.bulk_docs} documents...")
        queue_depths: list[int] = []

        async def _monitor_queue() -> None:
            for _ in range(int(args.duration)):
                queue_depths.append(_sample_queue_depth())
                await asyncio.sleep(1)

        _, treatment_results, _ = await asyncio.gather(
            _bulk_ingest(client, headers, count=args.bulk_docs),
            _query_workload(client, headers, duration_s=args.duration, qps=args.qps),
            _monitor_queue(),
        )
        treatment = _summarize("during_bulk_ingestion", treatment_results, queue_depths=queue_depths)

    delta_pct = (
        round(((treatment.p95_ms - baseline.p95_ms) / baseline.p95_ms) * 100, 1) if baseline.p95_ms else None
    )
    passed = delta_pct is not None and delta_pct <= args.p95_threshold_pct

    print("\n=== Result (blueprint section 16.2) ===")
    print(f"{'Metric':<12} {'Baseline':>12} {'During bulk ingestion':>22} {'Delta':>10}")
    print(f"{'p50 (ms)':<12} {baseline.p50_ms:>12} {treatment.p50_ms:>22} {'':>10}")
    print(f"{'p95 (ms)':<12} {baseline.p95_ms:>12} {treatment.p95_ms:>22} {f'{delta_pct}%':>10}")
    print(f"{'p99 (ms)':<12} {baseline.p99_ms:>12} {treatment.p99_ms:>22} {'':>10}")
    print(f"{'error rate':<12} {baseline.error_rate:>12} {treatment.error_rate:>22} {'':>10}")
    print(
        f"\nThreshold: during-ingestion p95 <= baseline p95 * (1 + {args.p95_threshold_pct}%) "
        f"-> {'PASS' if passed else 'FAIL'}"
    )

    output = {
        "baseline": asdict(baseline),
        "treatment": asdict(treatment),
        "p95_delta_pct": delta_pct,
        "p95_threshold_pct": args.p95_threshold_pct,
        "passed": passed,
        "config": {"duration_s": args.duration, "qps": args.qps, "bulk_docs": args.bulk_docs},
    }
    output_dir = Path(__file__).parent / "results"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"{time.strftime('%Y-%m-%dT%H-%M-%S')}.json"
    output_path.write_text(json.dumps(output, indent=2))
    print(f"\nWrote {output_path}")

    if not passed:
        # Non-zero exit so this is CI-friendly as a regression gate once you
        # have a real baseline to compare against.
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default="http://localhost:8000")
    parser.add_argument("--api-key", default="dev-key-alice")
    parser.add_argument("--duration", type=float, default=120.0, help="seconds per phase")
    parser.add_argument("--warmup", type=float, default=10.0)
    parser.add_argument("--qps", type=float, default=2.0)
    parser.add_argument("--bulk-docs", type=int, default=20)
    parser.add_argument(
        "--p95-threshold-pct",
        type=float,
        default=10.0,
        help='pass threshold, e.g. 10 means "during-ingestion p95 must be within 10%% of baseline p95" (section 16.1 step 7)',
    )
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
