import { useRef, useState } from "react";
import { uploadDocument } from "../api/client";

// Upload UX per blueprint section 14.2: validate client-side, request a
// presigned URL, PUT directly to storage with progress, then call complete.
// The API container never sees the file bytes.
export default function DocumentUploader({ onUploaded }: { onUploaded: () => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const ALLOWED = [
    "application/pdf",
    "text/plain",
    "text/markdown",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  ];
  const MAX_BYTES = 25 * 1024 * 1024;

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
      <label htmlFor="file-upload">Upload a document (PDF, DOCX, TXT, MD)</label>
      <div className="mt-16">
        <input
          id="file-upload"
          ref={inputRef}
          type="file"
          accept=".pdf,.docx,.txt,.md"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFile(file);
          }}
        />
      </div>
      {progress !== null && <p className="muted mt-16">Uploading… {progress}%</p>}
      {error && <p className="error-text mt-16">{error}</p>}
    </div>
  );
}
