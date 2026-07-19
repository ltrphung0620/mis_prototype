import { useState, type FormEvent, type ReactElement } from "react";

import type { DocumentEvidenceSubmission, DocumentRequirementCode } from "./types";

export interface DocumentSupplementFormProps {
  workflow_run_id: string;
  missing_request_id: string;
  allowed_document_types?: DocumentRequirementCode[];
  submitting?: boolean;
  onSubmit: (payload: DocumentEvidenceSubmission) => void | Promise<void>;
}

const DOCREF_PATTERN = /^DOCREF-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const SHA256_PATTERN = /^[0-9a-f]{64}$/i;
const DEFAULT_TYPES: DocumentRequirementCode[] = ["SIGNED_CONTRACT", "COMPANY_PROFILE", "PERFORMANCE_BOND_REQUEST_FORM", "CASHFLOW_BUFFER_EVIDENCE"];

const TYPE_LABELS: Record<DocumentRequirementCode, string> = {
  SIGNED_CONTRACT: "Hợp đồng đã ký",
  COMPANY_PROFILE: "Hồ sơ doanh nghiệp",
  PERFORMANCE_BOND_REQUEST_FORM: "Đơn đề nghị bảo lãnh thực hiện",
  CASHFLOW_BUFFER_EVIDENCE: "Tài liệu chứng minh nguồn bù dòng tiền",
};

export function DocumentSupplementForm({ workflow_run_id, missing_request_id, allowed_document_types = DEFAULT_TYPES, submitting = false, onSubmit }: DocumentSupplementFormProps): ReactElement {
  const [documentReference, setDocumentReference] = useState("");
  const [contentHash, setContentHash] = useState("");
  const [documentType, setDocumentType] = useState<DocumentRequirementCode>(allowed_document_types[0] ?? "SIGNED_CONTRACT");
  const [error, setError] = useState<string | null>(null);

  function submit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const reference = documentReference.trim();
    const hash = contentHash.trim().toLowerCase();
    if (!DOCREF_PATTERN.test(reference)) {
      setError("Mã tài liệu phải có dạng DOCREF-UUIDv4; không nhập đường dẫn hoặc URL.");
      return;
    }
    if (!SHA256_PATTERN.test(hash)) {
      setError("SHA-256 phải gồm đúng 64 ký tự hexadecimal.");
      return;
    }
    setError(null);
    void onSubmit({ workflow_run_id, missing_request_id, document_reference_id: reference, content_sha256: hash, document_type: documentType, evidence_note: "REQUESTED_DOCUMENT_REFERENCE_SUPPLIED" });
  }

  return (
    <form onSubmit={submit} aria-label="Bổ sung tham chiếu tài liệu">
      <p>Chỉ nhập mã tham chiếu và mã băm của tài liệu đã lưu trong kho được quản lý. Form không nhận file, nội dung file, đường dẫn hay URL.</p>
      <label>Loại tài liệu<select value={documentType} onChange={(event) => setDocumentType(event.target.value as DocumentRequirementCode)}>{allowed_document_types.map((type) => <option key={type} value={type}>{TYPE_LABELS[type]}</option>)}</select></label>
      <label>Mã tham chiếu tài liệu<input required value={documentReference} placeholder="DOCREF-00000000-0000-4000-8000-000000000000" pattern="DOCREF-[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-4[0-9A-Fa-f]{3}-[89ABab][0-9A-Fa-f]{3}-[0-9A-Fa-f]{12}" onChange={(event) => setDocumentReference(event.target.value)} /></label>
      <label>SHA-256 của nội dung<input required value={contentHash} minLength={64} maxLength={64} pattern="[0-9A-Fa-f]{64}" onChange={(event) => setContentHash(event.target.value)} /></label>
      {error && <p role="alert">{error}</p>}
      <button type="submit" disabled={submitting}>Gửi tham chiếu bổ sung</button>
    </form>
  );
}

