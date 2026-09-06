import { useRef, useState } from "react";
import { uploadDocument } from "../api/client";

const ALLOWED = [
  "application/pdf",
  "text/plain",
  "text/markdown",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
];
const MAX_BYTES = 25 * 1024 * 1024;

// Upload UX per blueprint section 14.2: validate client-side, request a
// presigned URL, PUT directly to storage with progress, then call complete.
// The API container never sees the file bytes.
export default function DocumentUploader({ onUploaded }: { onUploaded: () => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  async function handleFile(file: File) {
    setError(null);
    const mime = file.type || (file.name.endsWith(".md") ? "text/markdown" : "");
    if (!ALLOWED.includes(mime)) {
      setError(`Unsupported file type: ${mime || "unknown"}. Allowed: PDF, DOCX, TXT, MD.`);
      return;
    }
    if (file.size > MAX_BYTES) {
      setError(`File exceeds the ${MAX_BYTES / (1024 * 1024)}MB limit.`);
      return;
    }
    setProgress(0);
    try {
      await uploadDocument(file, setProgress);
      onUploaded();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setProgress(null);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <div className="card">
      <div
        className={`dropzone${dragOver ? " dragover" : ""}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          const file = e.dataTransfer.files?.[0];
          if (file) handleFile(file);
        }}
        role="button"
        tabIndex={0}
      >
        <svg className="dz-icon" width="28" height="28" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="M12 15V4m0 0L7.5 8.5M12 4l4.5 4.5M4 16v2.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V16"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <div className="dz-title">Drop a document here, or click to browse</div>
        <div className="dz-hint">PDF, DOCX, TXT, or MD — up to 25MB</div>
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.docx,.txt,.md"
          hidden
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFile(file);
          }}
        />
      </div>

      {progress !== null && (
        <>
          <div className="progress-track">
            <div className="progress-fill" style={{ width: `${progress}%` }} />
          </div>
          <p className="muted mt-16" style={{ fontSize: 13 }}>
            <span className="spinner" style={{ marginRight: 6 }} />
            Uploading… {progress}%
          </p>
        </>
      )}
      {error && <p className="error-text mt-16">{error}</p>}
    </div>
  );
}
