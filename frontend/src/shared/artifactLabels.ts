import { businessValueLabel } from "./businessLabels";

const ARTIFACT_TYPE_LABELS: Readonly<Record<string, string>> = {
  PLANNER_RESULT: "Kết quả tiếp nhận",
  EVALUATION_CASE: "Hồ sơ đánh giá",
  FINANCE_FACTS: "Finance · Số liệu tài chính",
  FINANCE_ASSESSMENT: "Finance · Đánh giá tài chính",
  OPERATIONS_FACTS: "Operations · Số liệu vận hành",
  OPERATIONS_ASSESSMENT: "Operations · Đánh giá vận hành",
  RISK_PRE_SCAN: "Risk · Quét sơ bộ",
  APPROVAL_CHECKPOINTS: "Điểm phê duyệt đã đăng ký",
  RISK_RULE_EVALUATION: "Risk · Đối chiếu quy tắc",
  INITIAL_RISK_ASSESSMENT: "Risk · Đánh giá ban đầu",
  DECISION_ROUTE_PLAN: "Tuyến xử lý quyết định",
  BANKING_DISCOVERY_REQUEST: "Banking · Yêu cầu khảo sát",
  BANKING_OPTION_MATRIX: "Banking · Ma trận phương án",
  BANKING_DISCOVERY_RESULT: "Banking · Kết quả khảo sát",
  BANKING_OPTION_ADVICE: "Banking · Diễn giải phương án",
  BANKING_INPUT_SUPPLEMENT: "Banking · Số tiền Founder bổ sung",
  BANKING_PRECHECK_READINESS: "Banking · Mức sẵn sàng precheck",
  DECISION_POST_BANKING_REVIEW: "Rà soát sau khảo sát ngân hàng",
  BANKING_PRECHECK_SUBMISSION_PROPOSAL: "Banking · Đề xuất chạy precheck",
  BANKING_PRECHECK_RESULT_SET: "Kết quả precheck mô phỏng",
  DECISION_POST_PRECHECK_REVIEW: "Rà soát sau precheck",
  BANKING_PRECHECK_EVIDENCE_SUPPLEMENT: "Banking · Bằng chứng precheck bổ sung",
  DOCUMENT_PREPARATION_REQUEST: "Document · Yêu cầu chuẩn bị hồ sơ",
  DOCUMENT_CHECKLIST: "Document · Danh mục hồ sơ",
  DOCUMENT_PACKAGE_DRAFT: "Document · Bản nháp hồ sơ",
  DOCUMENT_RELEASE_PACKAGE: "Gói hồ sơ nội bộ",
  DOCUMENT_EVIDENCE_SUPPLEMENT: "Document · Tài liệu Founder bổ sung",
  INTERNAL_DECISION_PACKAGE: "Hồ sơ quyết định nội bộ",
  FINAL_RISK_ASSESSMENT: "Risk · Kiểm tra cuối",
  AI_DECISION_ANALYSIS: "Phân tích quyết định",
  DECISION_CARD: "Decision Card",
  POST_DECISION_UPDATE: "Cập nhật sau quyết định",
  NEGOTIATION_OUTCOME: "Kết quả đàm phán",
  EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL: "Đề xuất gửi hồ sơ ra ngoài",
};

const VALIDATION_LABELS: Readonly<Record<string, string>> = {
  VALID: "Đã kiểm tra bằng chứng",
  VALID_WITH_WARNINGS: "Đã kiểm tra · có cảnh báo",
  INVALID: "Không đạt kiểm tra",
  BLOCKED: "Bị chặn bởi kiểm tra",
  PENDING: "Chưa kiểm tra",
};

/** Business name for an artifact type; unknown codes stay visible instead of being guessed. */
export function artifactTypeLabel(artifactType: string): string {
  return (
    ARTIFACT_TYPE_LABELS[artifactType] ??
    businessValueLabel(artifactType, artifactType)
  );
}

export function artifactValidationLabel(validationStatus: string): string {
  return VALIDATION_LABELS[validationStatus] ?? validationStatus;
}
