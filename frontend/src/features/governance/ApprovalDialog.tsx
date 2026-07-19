import type { ReactElement } from "react";

import { businessValueLabel } from "../../shared/businessLabels";
import { translateText } from "../../shared/translate";
import type { ApprovalDecision, ApprovalRequestView, ApprovalSubjectSummary, ProtectedAction } from "./types";

export interface ApprovalDialogProps {
  open: boolean;
  request: ApprovalRequestView | null;
  subject: ApprovalSubjectSummary | null;
  is_current_subject?: boolean;
  submitting?: boolean;
  onClose: () => void;
  onDecision: (requestId: string, decision: ApprovalDecision) => void | Promise<void>;
}

function actionOf(request: ApprovalRequestView): ProtectedAction {
  return request.protected_action ?? request.command?.action_type ?? "UNKNOWN";
}

function formatMoney(amount?: number | null, currency = "VND"): string | null {
  if (amount == null) return null;
  return new Intl.NumberFormat("vi-VN", { style: "currency", currency, maximumFractionDigits: 0 }).format(amount);
}

function requestStatus(status: string): string {
  const labels: Record<string, string> = {
    PENDING: "Đang chờ quyết định",
    APPROVED: "Đã phê duyệt",
    REJECTED: "Đã từ chối",
    EXPIRED: "Đã hết hiệu lực",
    AUTHORIZED_WITHOUT_HUMAN: "Được chính sách cho phép",
  };
  return labels[status] ?? "Chưa xác định";
}

function documentLabel(code: string): string {
  const labels: Record<string, string> = {
    SIGNED_CONTRACT: "Hợp đồng đã ký",
    COMPANY_PROFILE: "Hồ sơ doanh nghiệp",
    PERFORMANCE_BOND_REQUEST_FORM: "Đơn đề nghị bảo lãnh thực hiện",
    CASHFLOW_BUFFER_EVIDENCE: "Tài liệu chứng minh nguồn bù dòng tiền",
  };
  return labels[code] ?? "Tài liệu theo yêu cầu";
}

function actionExplanation(action: ProtectedAction): ReactElement {
  switch (action) {
    case "CONFIRM_FINAL_CONTRACT_DECISION":
      return <p>Phê duyệt sẽ ghi nhận quyết định cuối cùng cho đúng Decision Card hiện hành và cho phép quy trình đi tiếp. Đây không phải thao tác gửi hồ sơ ra ngoài.</p>;
    case "SUBMIT_BANKING_PRECHECK":
      return <p>Phê duyệt chỉ cho phép gửi yêu cầu kiểm tra sơ bộ đã xác định tới ngân hàng. Đây không phải chấp thuận cấp tín dụng hay bảo lãnh.</p>;
    case "SEND_DOCUMENT_TO_EXTERNAL_PARTNER":
      return <p>Phê duyệt chỉ cho phép gửi đúng gói hồ sơ đã nêu tới đúng người nhận. Trước khi phê duyệt, hồ sơ chưa được gửi ra ngoài.</p>;
    case "COMMIT_LARGE_FINANCIAL_DECISION":
      return <p>Phê duyệt cho phép quy trình ghi nhận cam kết tài chính đúng phạm vi đang trình; không mở rộng sang hành động khác.</p>;
    default:
      return <p>Hãy kiểm tra kỹ nội dung và phạm vi trước khi quyết định. Quy trình đang tạm dừng và chưa thực hiện hành động được bảo vệ.</p>;
  }
}

export function ApprovalDialog({
  open,
  request,
  subject,
  is_current_subject = true,
  submitting = false,
  onClose,
  onDecision,
}: ApprovalDialogProps): ReactElement | null {
  if (!open) return null;
  if (!request || !subject) {
    return (
      <div role="dialog" aria-modal="true" aria-label="Phê duyệt của Nhà sáng lập">
        <p>Không thể hiển thị yêu cầu phê duyệt vì thiếu nội dung cần xem xét.</p>
        <button type="button" onClick={onClose}>Đóng</button>
      </div>
    );
  }

  const action = actionOf(request);
  const pending = request.status === "PENDING";
  const canDecide = pending && is_current_subject;
  const amount = formatMoney(subject.amount, subject.currency);

  return (
    <div role="dialog" aria-modal="true" aria-labelledby="approval-title" className="approval-dialog">
      <article>
        <header>
          <p>Cổng xác nhận và phê duyệt của Nhà sáng lập</p>
          <h2 id="approval-title">{translateText(subject.title)}</h2>
          <p>Trạng thái: {requestStatus(request.status)}</p>
        </header>
        <p>{translateText(subject.description)}</p>
        {subject.recommendation && <p>Đề xuất: <strong>{businessValueLabel(subject.recommendation)}</strong></p>}
        {amount && <p>Giá trị: <strong>{amount}</strong></p>}
        {subject.recipient && <p>Người nhận dự kiến: <strong>{subject.recipient}</strong></p>}
        {!!subject.document_codes?.length && <><h3>Hồ sơ trong phạm vi</h3><ul>{subject.document_codes.map((code) => <li key={code}>{documentLabel(code)}</li>)}</ul></>}
        {actionExplanation(action)}
        {pending && <p role="status">Quy trình đang tạm dừng. Không có hành động được bảo vệ nào được thực hiện trước quyết định này.</p>}
        {!is_current_subject && <p role="alert">Yêu cầu này không còn khớp nội dung hiện hành nên không thể quyết định.</p>}
        {!pending && <p>Yêu cầu đã được xử lý; không thể quyết định lại.</p>}
        <footer>
          {canDecide && (
            <>
              <button type="button" disabled={submitting} onClick={() => void onDecision(request.request_id, "REJECT")}>Từ chối</button>
              <button type="button" disabled={submitting} onClick={() => void onDecision(request.request_id, "APPROVE")}>Phê duyệt</button>
            </>
          )}
          <button type="button" onClick={onClose}>Đóng</button>
        </footer>
      </article>
    </div>
  );
}
