import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { listDocuments } from "../api/client";
import DocumentUploader from "../components/DocumentUploader";
import StatusPill from "../components/StatusPill";
import type { DocumentRecord } from "../types";

const POLLING_STATUSES = new Set(["UPLOADING", "QUEUED", "PROCESSING"]);
const POLL_INTERVAL_MS = 3000;

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  async function refresh() {
    try {
      const docs = await listDocuments();
      setDocuments(docs);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  // Poll only while at least one document is in a non-terminal state
  // (section 14.2 step 5-6: "stop polling at terminal state").
  useEffect(() => {
    const anyInFlight = documents.some((d) => POLLING_STATUSES.has(d.status));
    if (anyInFlight && !timerRef.current) {
      timerRef.current = setInterval(refresh, POLL_INTERVAL_MS);
    } else if (!anyInFlight && timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, [documents]);

  return (
    <div>
      <DocumentUploader onUploaded={refresh} />

      {loading && <p className="muted">Loading documents…</p>}
      {!loading && documents.length === 0 && <p className="muted">No documents yet. Upload one above.</p>}

      {documents.map((doc) => (
        <Link key={doc.document_id} to={`/documents/${doc.document_id}`} style={{ textDecoration: "none", color: "inherit" }}>
          <div className="card doc-row">
            <div>
              <div>{doc.filename}</div>
              <div className="doc-meta">
                {doc.chunk_count != null
                  ? `${doc.chunk_count} chunk${doc.chunk_count === 1 ? "" : "s"}`
                  : doc.mime_type}
                {doc.error_code && <span className="error-text"> · {doc.error_code}</span>}
              </div>
            </div>
            <StatusPill status={doc.status} />
          </div>
        </Link>
      ))}
    </div>
  );
}
