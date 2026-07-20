const WORKFLOW_LABELS: Readonly<Record<string, string>> = {
  PLANNER_INTAKE: "Tiếp nhận và lập hồ sơ đánh giá",
  INITIAL_RISK_PRE_SCAN: "Quét rủi ro sơ bộ",
  INITIAL_ASSESSMENT: "Đánh giá ban đầu",
  INITIAL_ASSESSMENT_PARALLEL: "Đánh giá ban đầu chạy song song",
  FINANCE_ASSESSMENT: "Đánh giá tài chính",
  OPERATIONS_ASSESSMENT: "Đánh giá vận hành",
  INITIAL_RISK_FINALIZATION: "Hoàn tất đánh giá rủi ro ban đầu",
  DECISION_ROUTE_PLANNING: "Xác định nhu cầu vốn từ ngân hàng nếu cần",
  BANKING_DISCOVERY_HANDOFF: "Bàn giao khảo sát ngân hàng cho Banking Integration Skill",
  BANKING_INTERNAL_DISCOVERY: "Khảo sát phương án ngân hàng",
  BANKING_PRECHECK_READINESS: "Kiểm tra dữ liệu đầu vào cho precheck",
  DECISION_POST_BANKING_REVIEW: "Dữ liệu đầu vào có đủ để chạy precheck?",
  BANKING_INPUT_SUPPLEMENT: "Bổ sung dữ liệu ngân hàng",
  BANKING_PRECHECK_SUBMISSION_PROPOSAL: "Chuẩn bị yêu cầu precheck — chưa gửi",
  BANKING_PRECHECK_APPROVAL: "Founder duyệt precheck",
  BANKING_PRECHECK_EXECUTION: "Chạy precheck và nhận phản hồi từ ngân hàng",
  DECISION_POST_PRECHECK_REVIEW: "Đọc kết quả precheck và xác định bước tiếp theo",
  BANKING_PRECHECK_EVIDENCE_INTAKE: "Tiếp nhận kết quả kiểm tra sơ bộ bổ sung",
  DECISION_DOCUMENT_HANDOFF: "Bàn giao yêu cầu chuẩn bị hồ sơ cho Document Skill",
  DOCUMENT_PREPARATION: "Chuẩn bị hồ sơ",
  DOCUMENT_INPUT_INTAKE: "Tiếp nhận tài liệu bổ sung",
  INTERNAL_DECISION_PACKAGE_ASSEMBLY: "Tổng hợp hồ sơ quyết định nội bộ",
  FINAL_RISK_CHECK: "Kiểm tra rủi ro cuối",
  DECISION_CARD_COMPOSITION: "Lập Decision Card",
  DECISION_CARD_READY: "Decision Card đã sẵn sàng",
  FINAL_DECISION_APPROVAL: "Founder xem xét quyết định cuối",
  POST_DECISION_UPDATE: "Cập nhật sau quyết định",
  NEGOTIATION_IN_PROGRESS: "Đang chờ kết quả đàm phán",
  NEGOTIATION_TERMS_SENT: "Gửi điều kiện đàm phán",
  NEGOTIATION_OUTCOME_RECEIVED: "Ghi nhận phản hồi khách hàng",
  NEGOTIATION_FINAL_CONFIRMATION: "Xác nhận kết quả đàm phán cuối",
  FINAL_DECISION_ACCEPTED: "Hợp đồng đã được chấp nhận",
  FINAL_DECISION_NOT_ACCEPTED: "Hợp đồng không được chấp nhận",
  EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL: "Lập đề xuất gửi hồ sơ bên ngoài",
  READY_FOR_EXTERNAL_SUBMISSION: "Hồ sơ sẵn sàng để gửi",
  APPROVAL_GATE: "Cổng phê duyệt của Founder",
  WAITING_FOR_APPROVAL: "Đang chờ Founder phê duyệt",
};

export function stageLabel(code: string): string {
  return WORKFLOW_LABELS[code.toUpperCase()] ?? "Giai đoạn xử lý";
}

export function milestoneLabel(code: string): string {
  return WORKFLOW_LABELS[code.toUpperCase()] ?? "Công việc xử lý";
}

export function statusLabel(status: string): string {
  const labels: Readonly<Record<string, string>> = {
    PENDING: "Chưa bắt đầu",
    RUNNING: "Đang xử lý",
    COMPLETED: "Đã hoàn tất",
    COMPLETED_WITH_WARNINGS: "Hoàn tất, có lưu ý",
    REJECTED: "Đã bị từ chối",
    EXPIRED: "Yêu cầu đã hết hiệu lực",
    WAITING_FOR_DEPENDENCIES: "Đang chờ tác vụ liên quan",
    WAITING_FOR_INPUT: "Chờ bổ sung dữ liệu",
    WAITING_FOR_APPROVAL: "Chờ Founder phê duyệt",
    BLOCKED: "Đã tạm dừng",
    FAILED_SAFE: "Dừng an toàn",
    SKIPPED: "Không áp dụng",
    NOT_APPLICABLE: "Không áp dụng",
    APPLICABLE: "Có áp dụng",
    RESOLVED: "Đã giải quyết",
    UNRESOLVED: "Chưa giải quyết",
    REQUIRED: "Bắt buộc",
    POSSIBLE: "Có thể phát sinh",
  };
  return labels[status.toUpperCase()] ?? statusLabelFallback(status);
}

function statusLabelFallback(status: string): string {
  if (!status) return "Chưa xác định";
  return "Trạng thái chưa được diễn giải";
}

export type StatusTone = "neutral" | "active" | "success" | "warning" | "danger";

export function statusTone(status: string): StatusTone {
  switch (status.toUpperCase()) {
    case "RUNNING":
      return "active";
    case "COMPLETED":
      return "success";
    case "COMPLETED_WITH_WARNINGS":
    case "EXPIRED":
    case "WAITING_FOR_DEPENDENCIES":
    case "WAITING_FOR_INPUT":
    case "WAITING_FOR_APPROVAL":
      return "warning";
    case "BLOCKED":
    case "FAILED_SAFE":
    case "REJECTED":
      return "danger";
    default:
      return "neutral";
  }
}

export function isResolvedStatus(status: string): boolean {
  return [
    "COMPLETED",
    "COMPLETED_WITH_WARNINGS",
    "APPROVED",
    "AUTHORIZED_WITHOUT_HUMAN",
    "REJECTED",
    "EXPIRED",
    "NOT_APPLICABLE",
    "SKIPPED",
    "RESOLVED",
  ].includes(
    status.toUpperCase(),
  );
}

export function isTerminalExecutionStatus(status: string): boolean {
  return ["COMPLETED", "BLOCKED", "FAILED_SAFE"].includes(status.toUpperCase());
}
