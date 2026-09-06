import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getDocument } from "../api/client";
import StatusPill from "../components/StatusPill";
import type { DocumentRecord } from "../types";

export default function DocumentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [doc, setDoc] = useState<DocumentRecord | null>(null);

  useEffect(() => {
    if (id) getDocument(id).then(setDoc);
  }, [id]);

  if (!doc) return <p className="muted">Loading…</p>;

  return (
    <div>
      <Link to="/documents" className="muted">
        ← Back to documents
      </Link>
      <div className="card mt-16">
        <h2 style={{ marginTop: 0 }}>{doc.filename}</h2>
        <StatusPill status={doc.status} />
        <table style={{ width: "100%", marginTop: 16, borderCollapse: "collapse" }}>
          <tbody>
            <Row label="MIME type" value={doc.mime_type} />
            <Row label="Size" value={`${(doc.size_bytes / 1024).toFixed(1)} KB`} />
            <Row label="Pages" value={doc.page_count ?? "—"} />
            <Row label="Chunks" value={doc.chunk_count ?? "—"} />
            <Row label="Uploaded" value={new Date(doc.created_at).toLocaleString()} />
            <Row label="Processed" value={doc.processed_at ? new Date(doc.processed_at).toLocaleString() : "—"} />
          </tbody>
        </table>
        {doc.status === "FAILED" && (
          <div className="citation-panel mt-16" style={{ borderLeftColor: "var(--danger)" }}>
            <strong className="error-text">{doc.error_code}</strong>
            <p style={{ marginBottom: 0 }}>{doc.error_message}</p>
          </div>
        )}
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string | number }) {
  return (
    <tr>
      <td className="muted" style={{ padding: "4px 0", width: 140 }}>
        {label}
      </td>
      <td>{value}</td>
    </tr>
  );
}
