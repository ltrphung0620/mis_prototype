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
      return <p>Quyết định này sẽ ghi nhận phê duyệt cuối cùng trên Decision Card để hoàn tất quy trình.</p>;
    case "SUBMIT_BANKING_PRECHECK":
      return <p>Lưu ý: Đây chỉ là yêu cầu khảo sát thông tin sơ bộ với ngân hàng, không phải chấp thuận cấp tín dụng hay bảo lãnh chính thức.</p>;
    case "SEND_DOCUMENT_TO_EXTERNAL_PARTNER":
      return <p>Lưu ý: Trước khi phê duyệt, hồ sơ chưa được gửi ra ngoài; hệ thống chỉ gửi đi sau khi được bạn xác nhận.</p>;
    case "COMMIT_LARGE_FINANCIAL_DECISION":
      return <p>Quyết định này ghi nhận cam kết tài chính trong phạm vi được duyệt.</p>;
    default:
      return <p>Vui lòng kiểm tra kỹ nội dung trước khi quyết định. Hệ thống đang chờ sự xác nhận từ bạn.</p>;
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
      <div role="dialog" aria-modal="true" aria-label="Phê duyệt của Founder">
        <p>Không thể hiển thị yêu cầu phê duyệt vì thiếu nội dung cần xem xét.</p>
        <button type="button" onClick={onClose}>Đóng</button>
      </div>
    );
  }

  const action = actionOf(request);
  const pending = request.status === "PENDING";
  const canDecide = pending && is_current_subject;
  const amount = formatMoney(subject.amount, subject.currency);

  const descriptionText = action === "SUBMIT_BANKING_PRECHECK"
    ? `Gửi yêu cầu kiểm tra sơ bộ tới ngân hàng để khảo sát các phương án bảo lãnh thực hiện hợp đồng (Performance Bond) trị giá ${amount ?? "chưa xác định"}.`
    : translateText(subject.description);

  return (
    <div role="dialog" aria-modal="true" aria-labelledby="approval-title" className="approval-dialog">
      <article>
        <header>
          <p>Cổng xác nhận và phê duyệt của Founder</p>
          <h2 id="approval-title">{translateText(subject.title)}</h2>
          <p>Trạng thái: {requestStatus(request.status)}</p>
        </header>
        <p>{descriptionText}</p>
        {subject.recommendation && <p>Đề xuất: <strong>{businessValueLabel(subject.recommendation)}</strong></p>}
        {amount && <p>Giá trị: <strong>{amount}</strong></p>}
        {subject.recipient && <p>Người nhận dự kiến: <strong>{subject.recipient}</strong></p>}
        {!!subject.document_codes?.length && <><h3>Hồ sơ trong phạm vi</h3><ul>{subject.document_codes.map((code) => <li key={code}>{documentLabel(code)}</li>)}</ul></>}
        {actionExplanation(action)}
        {pending && <p role="status">Quy trình đang tạm dừng để chờ bạn xác nhận. Hệ thống sẽ không tự động thực hiện hành động này nếu chưa được bạn phê duyệt.</p>}
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
