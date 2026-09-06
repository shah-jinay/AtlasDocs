import type { DocumentStatus } from "../types";

export default function StatusPill({ status }: { status: DocumentStatus }) {
  return <span className={`status-pill status-${status}`}>{status}</span>;
}
