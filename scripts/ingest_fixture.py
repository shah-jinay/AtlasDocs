#!/usr/bin/env python3
"""Upload fixtures/sample.txt through the real API and wait for it to reach
READY. This is the "one tiny document through the whole pipeline" step
from blueprint section 23.1 -- run it once after `docker compose up` to
have a stable corpus for evaluation/run_eval.py and load-tests/.

    python scripts/ingest_fixture.py
"""
import argparse
import sys
import time
from pathlib import Path

import httpx

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "sample.txt"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default="http://localhost:8000")
    parser.add_argument("--api-key", default="dev-key-alice")
    parser.add_argument("--file", default=str(FIXTURE_PATH))
    args = parser.parse_args()

    data = Path(args.file).read_bytes()
    headers = {"Authorization": f"Bearer {args.api_key}"}

    with httpx.Client(base_url=args.api_base, timeout=30.0) as client:
        init = client.post(
            "/v1/documents/uploads",
            headers=headers,
            json={"filename": Path(args.file).name, "mime_type": "text/plain", "size_bytes": len(data)},
        )
        init.raise_for_status()
        payload = init.json()
        print(f"Created document {payload['document_id']}, uploading...")

        httpx.put(payload["upload_url"], content=data, headers={"Content-Type": "text/plain"}).raise_for_status()

        complete = client.post(f"/v1/documents/{payload['document_id']}/complete", headers=headers)
        complete.raise_for_status()
        print("Queued for ingestion, waiting for READY...")

        deadline = time.time() + 60
        while time.time() < deadline:
            resp = client.get(f"/v1/documents/{payload['document_id']}", headers=headers)
            resp.raise_for_status()
            doc = resp.json()
            if doc["status"] in ("READY", "FAILED"):
                print(f"Status: {doc['status']}")
                if doc["status"] == "FAILED":
                    print(f"  {doc['error_code']}: {doc['error_message']}")
                    sys.exit(1)
                print(f"  {doc['chunk_count']} chunks, {doc['page_count']} pages")
                return
            time.sleep(1)
        print("Timed out waiting for document to become READY")
        sys.exit(1)


if __name__ == "__main__":
    main()
