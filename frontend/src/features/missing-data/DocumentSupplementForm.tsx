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

// Reference IDs and hashes must come from the selected file; never fall back to fixed values.
function hasBrowserCrypto(): boolean {
  return typeof crypto !== "undefined" && typeof crypto.randomUUID === "function" && Boolean(crypto.subtle);
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
    if (!hasBrowserCrypto()) {
      setFileName(null);
      setDocumentReference("");
      setContentHash("");
      setError("Trình duyệt không hỗ trợ tính mã băm SHA-256. Hãy mở ứng dụng qua localhost hoặc HTTPS rồi thử lại.");
      event.target.value = "";
      return;
    }
    try {
      const buffer = await file.arrayBuffer();
      const hashBuffer = await crypto.subtle.digest("SHA-256", buffer);
      const hashHex = Array.from(new Uint8Array(hashBuffer))
        .map((b) => b.toString(16).padStart(2, "0"))
        .join("");
      setDocumentReference(`DOCREF-${crypto.randomUUID()}`);
      setContentHash(hashHex);
      setFileName(file.name);
      setError(null);
    } catch {
      setFileName(null);
      setDocumentReference("");
      setContentHash("");
      setError("Không thể đọc tệp để tính mã băm. Vui lòng thử lại.");
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

      <div className="upload-field">
        <label htmlFor="document-upload">
          Chọn tệp {TYPE_LABELS[documentType]} (.pdf hoặc .docx)
        </label>
        <input
          id="document-upload"
          type="file"
          accept=".docx,.pdf,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          aria-describedby={error ? "document-upload-hint document-upload-error" : "document-upload-hint"}
          aria-invalid={error ? true : undefined}
          onChange={(e) => void handleFileSelect(e)}
        />
        <p id="document-upload-hint">
          Tệp chỉ được tính mã băm SHA-256 trên trình duyệt; nội dung tệp không được gửi lên máy chủ và hệ thống không xác minh chữ ký hay giá trị pháp lý.
        </p>
        {fileName && (
          <p>
            Đã chọn: <strong>{fileName}</strong>
          </p>
        )}
      </div>

      {error && <p id="document-upload-error" role="alert" className="form-error">{error}</p>}
      <button type="submit" disabled={submitting || !fileName}>Bổ sung tệp và tiếp tục quy trình</button>
    </form>
  );
}
