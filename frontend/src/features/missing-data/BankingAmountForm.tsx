import { useState, type FormEvent, type ReactElement } from "react";

import type { BankingAmountSubmission } from "./types";

export interface BankingAmountFormProps {
  workflow_run_id: string;
  missing_request_id: string;
  submitting?: boolean;
  onSubmit: (payload: BankingAmountSubmission) => void | Promise<void>;
}

export function BankingAmountForm({ workflow_run_id, missing_request_id, submitting = false, onSubmit }: BankingAmountFormProps): ReactElement {
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  function submit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const normalizedAmount = amount.trim();
    const requestedAmount = Number(normalizedAmount);
    if (!/^\d+$/.test(normalizedAmount) || !Number.isSafeInteger(requestedAmount) || requestedAmount <= 0) {
      setError("Số tiền phải là số nguyên VND dương và nằm trong giới hạn an toàn.");
      return;
    }
    const normalizedNote = note.trim();
    if (!normalizedNote) {
      setError("Cần ghi rõ căn cứ cho số tiền được bổ sung.");
      return;
    }
    setError(null);
    void onSubmit({ workflow_run_id, missing_request_id, requested_amount: requestedAmount, requested_amount_currency: "VND", evidence_note: normalizedNote });
  }

  return (
    <form onSubmit={submit} aria-label="Bổ sung số tiền ngân hàng">
      <p>Chỉ dùng cho yêu cầu số tiền kiểu cũ do quy trình tạo. Không dùng biểu mẫu này để ghi đè nhu cầu đã được bộ phận Lập kế hoạch liên kết từ hợp đồng hoặc hồ sơ tín dụng.</p>
      <label>Số tiền cần hỗ trợ (VND)<input required inputMode="numeric" min="1" step="1" value={amount} onChange={(event) => setAmount(event.target.value)} /></label>
      <label>Căn cứ nhập liệu<textarea required maxLength={500} value={note} onChange={(event) => setNote(event.target.value)} /></label>
      {error && <p role="alert">{error}</p>}
      <button type="submit" disabled={submitting}>Gửi số tiền bổ sung</button>
    </form>
  );
}
