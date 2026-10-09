import { useId, useState, type FormEvent, type ReactElement } from "react";

import type { BankingPrecheckEvidenceSubmission } from "./types";

export interface PrecheckEvidenceFormProps {
  workflow_run_id: string;
  missing_request_id: string;
  submitting?: boolean;
  onSubmit: (payload: BankingPrecheckEvidenceSubmission) => void | Promise<void>;
}

export function PrecheckEvidenceForm({ workflow_run_id, missing_request_id, submitting = false, onSubmit }: PrecheckEvidenceFormProps): ReactElement {
  const [reference, setReference] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<{ reference: boolean; note: boolean } | null>(null);
  const errorId = useId();

  function submit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const normalizedReference = reference.trim();
    const normalizedNote = note.trim();
    if (!normalizedReference || !normalizedNote) {
      setError({ reference: !normalizedReference, note: !normalizedNote });
      return;
    }
    setError(null);
    void onSubmit({ workflow_run_id, missing_request_id, evidence_reference_id: normalizedReference, evidence_note: normalizedNote });
  }

  return (
    <form onSubmit={submit} aria-label="Bổ sung căn cứ cho kiểm tra sơ bộ với ngân hàng">
      <p>Thông tin này chỉ giải quyết khoảng trống dữ liệu. Hệ thống phải thực hiện lại bước kiểm tra sơ bộ qua cơ chế kiểm soát; kết quả cũ không bị sửa và ngân hàng chưa phê duyệt.</p>
      <label>Mã tham chiếu tài liệu bổ sung<input required value={reference} aria-invalid={error?.reference || undefined} aria-describedby={error?.reference ? errorId : undefined} onChange={(event) => setReference(event.target.value)} /></label>
      <label>Nội dung bổ sung<textarea required value={note} aria-invalid={error?.note || undefined} aria-describedby={error?.note ? errorId : undefined} onChange={(event) => setNote(event.target.value)} /></label>
      {error && <p id={errorId} role="alert" className="form-error">Cần nhập đủ mã tham chiếu và ghi chú mô tả tài liệu bổ sung.</p>}
      <button type="submit" disabled={submitting}>Gửi thông tin bổ sung</button>
    </form>
  );
}
