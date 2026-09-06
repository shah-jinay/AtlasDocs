import type { DocumentStatus } from "../types";

const IN_PROGRESS = new Set<DocumentStatus>(["UPLOADING", "QUEUED", "PROCESSING"]);

export default function StatusPill({ status }: { status: DocumentStatus }) {
  const pulsing = IN_PROGRESS.has(status) ? " pulsing" : "";
  return <span className={`status-pill status-${status}${pulsing}`}>{status}</span>;
}
