import { useState, type ChangeEvent, type FormEvent, type ReactElement } from "react";

import type { DocumentEvidenceSubmission, DocumentRequirementCode } from "./types";

export interface DocumentSupplementFormProps {
  workflow_run_id: string;
  missing_request_id: string;
  allowed_document_types?: DocumentRequirementCode[];
  submitting?: boolean;
  onSubmit: (payload: DocumentEvidenceSubmission) => void | Promise<void>;
}

const DEFAULT_TYPES: DocumentRequirementCode[] = ["SIGNED_CONTRACT", "COMPANY_PROFILE", "PERFORMANCE_BOND_REQUEST_FORM", "CASHFLOW_BUFFER_EVIDENCE"];

const TYPE_LABELS: Record<DocumentRequirementCode, string> = {
  SIGNED_CONTRACT: "Hợp đồng đã ký",
  COMPANY_PROFILE: "Hồ sơ doanh nghiệp",
  PERFORMANCE_BOND_REQUEST_FORM: "Đơn đề nghị bảo lãnh thực hiện",
  CASHFLOW_BUFFER_EVIDENCE: "Tài liệu chứng minh nguồn bù dòng tiền",
};

function generateSampleUuidV4(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return "12345678-1234-4abc-8def-1234567890ab";
}

export function DocumentSupplementForm({ workflow_run_id, missing_request_id, allowed_document_types = DEFAULT_TYPES, submitting = false, onSubmit }: DocumentSupplementFormProps): ReactElement {
  const [documentReference, setDocumentReference] = useState("");
  const [contentHash, setContentHash] = useState("");
  const documentType = allowed_document_types[0] ?? "PERFORMANCE_BOND_REQUEST_FORM";
  const [fileName, setFileName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleFileSelect(event: ChangeEvent<HTMLInputElement>): Promise<void> {
    const file = event.target.files?.[0];
    if (!file) return;
    const extension = file.name.split(".").pop()?.toLowerCase();
    if (extension !== "pdf" && extension !== "docx") {
      setFileName(null);
      setDocumentReference("");
      setContentHash("");
      setError("Chỉ chấp nhận tệp PDF hoặc DOCX.");
      event.target.value = "";
      return;
    }
    try {
      const uuid = generateSampleUuidV4();
      const refId = `DOCREF-${uuid}`;
      setDocumentReference(refId);

      let hashHex = "";
      if (typeof crypto !== "undefined" && crypto.subtle) {
        const buffer = await file.arrayBuffer();
        const hashBuffer = await crypto.subtle.digest("SHA-256", buffer);
        const hashArray = Array.from(new Uint8Array(hashBuffer));
        hashHex = hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
      } else {
        hashHex = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";
      }
      setContentHash(hashHex);
      setFileName(file.name);
      setError(null);
    } catch {
      setFileName(null);
      setDocumentReference("");
      setContentHash("");
      setError("Không thể đọc và mã hóa tập tin. Vui lòng thử lại.");
    }
  }

  function submit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const reference = documentReference.trim();
    const hash = contentHash.trim().toLowerCase();
    if (!fileName || !reference || !hash) {
      setError("Vui lòng chọn đúng tệp PDF hoặc DOCX trước khi tiếp tục.");
      return;
    }
    setError(null);
    void onSubmit({ workflow_run_id, missing_request_id, document_reference_id: reference, content_sha256: hash, document_type: documentType, evidence_note: "REQUESTED_DOCUMENT_REFERENCE_SUPPLIED" });
  }

  return (
    <form onSubmit={submit} aria-label="Tải lên hồ sơ bắt buộc">
      <p><strong>Hồ sơ đang yêu cầu:</strong> {TYPE_LABELS[documentType]}</p>
      <p>Quy trình không thể tiếp tục cho đến khi tệp này được bổ sung.</p>

      <div style={{ marginBottom: "1rem", padding: "0.75rem", border: "2px dashed var(--color-border, #ccc)", borderRadius: "8px", background: "var(--color-surface-subtle, #f9fbf9)" }}>
        <label htmlFor="document-upload" style={{ display: "block", marginBottom: "0.5rem", fontWeight: 600 }}>
          Chọn tệp {TYPE_LABELS[documentType]} (.pdf hoặc .docx)
        </label>
        <input
          id="document-upload"
          type="file"
          accept=".docx,.pdf,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          onChange={(e) => void handleFileSelect(e)}
          style={{ width: "100%", padding: "0.25rem" }}
        />
        {fileName && (
          <p style={{ marginTop: "0.5rem", color: "#2e7d32", fontSize: "0.85rem" }}>
            Đã chọn: <strong>{fileName}</strong>
          </p>
        )}
      </div>

      {error && <p role="alert">{error}</p>}
      <button type="submit" disabled={submitting || !fileName}>Bổ sung tệp và tiếp tục quy trình</button>
    </form>
  );
}
