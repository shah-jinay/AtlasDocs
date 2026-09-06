import type { MouseEvent } from "react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { deleteDocument, listDocuments } from "../api/client";
import DocumentUploader from "../components/DocumentUploader";
import Mascot from "../components/Mascot";
import StatusPill from "../components/StatusPill";
import type { DocumentRecord } from "../types";

const POLLING_STATUSES = new Set(["UPLOADING", "QUEUED", "PROCESSING"]);
const POLL_INTERVAL_MS = 3000;

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  async function refresh() {
    try {
      const docs = await listDocuments();
      setDocuments(docs);
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(e: MouseEvent, doc: DocumentRecord) {
    e.preventDefault(); // this row is a <Link> -- don't navigate on delete
    e.stopPropagation();
    if (!window.confirm(`Remove "${doc.filename}"? This can't be undone.`)) return;
    setDeletingId(doc.document_id);
    try {
      await deleteDocument(doc.document_id);
      await refresh();
    } finally {
      setDeletingId(null);
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
    <div className="page-enter">
      <div className="eyebrow">Document library</div>
      <h1 className="page-title">Documents</h1>
      <DocumentUploader onUploaded={refresh} />

      {loading && (
        <p className="muted">
          <span className="spinner" style={{ marginRight: 8 }} />
          Loading documents…
        </p>
      )}
      {!loading && documents.length === 0 && (
        <div
          className="animate-in"
          style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 14, padding: "32px 0" }}
        >
          <Mascot tip="Drop a file here to get started" />
          <p className="muted" style={{ margin: 0 }}>
            No documents yet
          </p>
        </div>
      )}

      {documents.map((doc, i) => (
        <Link
          key={doc.document_id}
          to={`/documents/${doc.document_id}`}
          style={{ textDecoration: "none", color: "inherit" }}
        >
          <div className="doc-row animate-in" style={{ animationDelay: `${Math.min(i * 40, 400)}ms` }}>
            <div>
              <div className="doc-name">{doc.filename}</div>
              <div className="doc-meta">
                {doc.chunk_count != null
                  ? `${doc.chunk_count} chunk${doc.chunk_count === 1 ? "" : "s"}`
                  : doc.mime_type}
                {doc.error_code && <span className="error-text"> · {doc.error_code}</span>}
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <StatusPill status={doc.status} />
              <button
                className="icon-button"
                aria-label={`Remove ${doc.filename}`}
                title="Remove"
                disabled={deletingId === doc.document_id}
                onClick={(e) => handleDelete(e, doc)}
              >
                {deletingId === doc.document_id ? (
                  <span className="spinner" />
                ) : (
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path
                      d="M4 7h16M9 7V4.5A1.5 1.5 0 0 1 10.5 3h3A1.5 1.5 0 0 1 15 4.5V7m2 0v12.5A1.5 1.5 0 0 1 15.5 21h-7A1.5 1.5 0 0 1 7 19.5V7h10Z"
                      stroke="currentColor"
                      strokeWidth="1.6"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                )}
              </button>
            </div>
          </div>
        </Link>
      ))}
    </div>
  );
}
