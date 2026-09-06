import { useState } from "react";
import type { Citation } from "../types";

// Citation UX per blueprint section 14.3: numbered chips next to the
// answer, each opening a panel with filename/page/excerpt. Only citations
// the backend already validated (app.rag.citations) ever reach this
// component -- there is nothing here for the frontend to double-check.
export default function CitationAnswer({
  answer,
  citations,
  insufficientEvidence,
}: {
  answer: string;
  citations: Citation[];
  insufficientEvidence: boolean;
}) {
  const [openIndex, setOpenIndex] = useState<number | null>(null);

  return (
    <div>
      <p style={{ whiteSpace: "pre-wrap" }}>
        {answer}
        {citations.map((_, i) => (
          <span key={i} className="citation-chip" onClick={() => setOpenIndex(openIndex === i ? null : i)}>
            {i + 1}
          </span>
        ))}
      </p>

      {insufficientEvidence && (
        <p className="muted">AtlasDocs abstained rather than answer without sufficient grounded evidence.</p>
      )}

      {openIndex !== null && citations[openIndex] && (
        <div className="citation-panel">
          <div className="doc-meta">
            <strong>{citations[openIndex].filename}</strong>
            {citations[openIndex].page_start != null && ` · page ${citations[openIndex].page_start}`}
          </div>
          <p style={{ marginBottom: 0 }}>{citations[openIndex].excerpt}</p>
        </div>
      )}

      {citations.length > 0 && (
        <div className="mt-16">
          <span className="muted" style={{ fontSize: 12 }}>
            Sources: {citations.map((c, i) => `[${i + 1}] ${c.filename}`).join("  ")}
          </span>
        </div>
      )}
    </div>
  );
}
