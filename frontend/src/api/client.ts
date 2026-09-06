import type { DocumentRecord, QueryResponse, UploadInitResponse } from "../types";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

// Demo-grade auth token (blueprint section 8, backend/app/core/security.py).
// A real deployment would exchange this for a login flow / session token.
const DEV_TOKEN_KEY = "atlasdocs_dev_token";

export function getDevToken(): string {
  return localStorage.getItem(DEV_TOKEN_KEY) || "dev-key-alice";
}

export function setDevToken(token: string): void {
  localStorage.setItem(DEV_TOKEN_KEY, token);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      Authorization: `Bearer ${getDevToken()}`,
      ...init.headers,
    },
  });
  if (!resp.ok) {
    const detail = await resp.text();
    throw new Error(`${resp.status} ${resp.statusText}: ${detail}`);
  }
  if (resp.status === 204) return undefined as T;
  return resp.json() as Promise<T>;
}

export async function listDocuments(): Promise<DocumentRecord[]> {
  return request<DocumentRecord[]>("/v1/documents");
}

export async function getDocument(id: string): Promise<DocumentRecord> {
  return request<DocumentRecord>(`/v1/documents/${id}`);
}

export async function uploadDocument(file: File, onProgress?: (pct: number) => void): Promise<string> {
  const init = await request<UploadInitResponse>("/v1/documents/uploads", {
    method: "POST",
    body: JSON.stringify({ filename: file.name, mime_type: file.type || "text/plain", size_bytes: file.size }),
  });

  await new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", init.upload_url);
    xhr.setRequestHeader("Content-Type", file.type || "text/plain");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => (xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error(xhr.statusText)));
    xhr.onerror = () => reject(new Error("Upload to storage failed"));
    xhr.send(file);
  });

  await request(`/v1/documents/${init.document_id}/complete`, { method: "POST" });
  return init.document_id;
}

export async function askQuestion(question: string, documentIds?: string[]): Promise<QueryResponse> {
  return request<QueryResponse>("/v1/query", {
    method: "POST",
    body: JSON.stringify({ question, document_ids: documentIds && documentIds.length ? documentIds : null }),
  });
}
