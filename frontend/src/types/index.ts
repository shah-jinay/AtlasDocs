export type DocumentStatus = "UPLOADING" | "QUEUED" | "PROCESSING" | "READY" | "FAILED" | "DELETED";

export interface DocumentRecord {
  document_id: string;
  filename: string;
  mime_type: string;
  status: DocumentStatus;
  size_bytes: number;
  page_count: number | null;
  chunk_count: number | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  processed_at: string | null;
}

export interface UploadInitResponse {
  document_id: string;
  upload_url: string;
  expires_in_seconds: number;
  status: DocumentStatus;
}

export interface Citation {
  source_id: string;
  document_id: string;
  filename: string;
  page_start: number | null;
  page_end: number | null;
  excerpt: string;
}

export interface QueryResponse {
  answer: string;
  citations: Citation[];
  request_id: string;
  insufficient_evidence: boolean;
}
