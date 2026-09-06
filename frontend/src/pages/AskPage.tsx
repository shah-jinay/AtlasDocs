import { useEffect, useState } from "react";
import { askQuestion, listDocuments } from "../api/client";
import CitationAnswer from "../components/CitationAnswer";
import Mascot from "../components/Mascot";
import type { DocumentRecord, QueryResponse } from "../types";

export default function AskPage() {
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [question, setQuestion] = useState("");
  const [response, setResponse] = useState<QueryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listDocuments().then((docs) => setDocuments(docs.filter((d) => d.status === "READY")));
  }, []);

  function toggleDoc(id: string) {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  async function submit() {
    if (!question.trim()) return;
    setLoading(true);
    setError(null);
    setResponse(null);
    try {
      const result = await askQuestion(question, selectedIds);
      setResponse(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Query failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page-enter">
      <div className="eyebrow">Retrieval-augmented Q&A</div>
      <h1 className="page-title">Ask</h1>
      <div className="card">
        <label>Documents to search</label>
        <div className="mt-16" style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {documents.length === 0 && (
            <span className="muted" style={{ fontSize: 13.5 }}>
              No READY documents yet — searches all if none selected.
            </span>
          )}
          {documents.map((doc) => (
            <label key={doc.document_id} className="doc-toggle">
              <input
                type="checkbox"
                checked={selectedIds.includes(doc.document_id)}
                onChange={() => toggleDoc(doc.document_id)}
              />
              {doc.filename}
            </label>
          ))}
        </div>

        <div className="mt-16" style={{ display: "flex", gap: 10 }}>
          <input
            type="text"
            placeholder="Ask a question about your documents…"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
            style={{ flex: 1 }}
          />
          <button onClick={submit} disabled={loading || !question.trim()}>
            {loading ? (
              <>
                <span className="spinner spinner-on-accent" style={{ marginRight: 7 }} />
                Asking…
              </>
            ) : (
              "Ask"
            )}
          </button>
        </div>
        {error && <p className="error-text mt-16">{error}</p>}
      </div>

      {response && (
        <div className="card animate-in">
          <CitationAnswer
            answer={response.answer}
            citations={response.citations}
            insufficientEvidence={response.insufficient_evidence}
          />
        </div>
      )}

      {!response && !loading && !error && (
        <div
          className="animate-in"
          style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 14, padding: "40px 0" }}
        >
          <Mascot tip="Pick a document above, then type your question" />
          <p className="muted" style={{ margin: 0 }}>
            Ask a question to get started
          </p>
        </div>
      )}
    </div>
  );
}
