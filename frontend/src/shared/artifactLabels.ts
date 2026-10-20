import { businessValueLabel } from "./businessLabels";

const ARTIFACT_TYPE_LABELS: Readonly<Record<string, string>> = {
  PLANNER_RESULT: "Kết quả tiếp nhận",
  EVALUATION_CASE: "Hồ sơ đánh giá",
  FINANCE_FACTS: "Tài chính · Số liệu tài chính",
  FINANCE_ASSESSMENT: "Tài chính · Đánh giá tài chính",
  OPERATIONS_FACTS: "Vận hành · Số liệu vận hành",
  OPERATIONS_ASSESSMENT: "Vận hành · Đánh giá vận hành",
  RISK_PRE_SCAN: "Rủi ro · Quét sơ bộ",
  APPROVAL_CHECKPOINTS: "Điểm phê duyệt đã đăng ký",
  RISK_RULE_EVALUATION: "Rủi ro · Đối chiếu quy tắc",
  INITIAL_RISK_ASSESSMENT: "Rủi ro · Đánh giá ban đầu",
  DECISION_ROUTE_PLAN: "Tuyến xử lý quyết định",
  BANKING_DISCOVERY_REQUEST: "Ngân hàng · Yêu cầu khảo sát",
  BANKING_OPTION_MATRIX: "Ngân hàng · Ma trận phương án",
  BANKING_DISCOVERY_RESULT: "Ngân hàng · Kết quả khảo sát",
  BANKING_OPTION_ADVICE: "Ngân hàng · Diễn giải phương án",
  BANKING_INPUT_SUPPLEMENT: "Ngân hàng · Số tiền người phê duyệt bổ sung",
  BANKING_PRECHECK_READINESS: "Ngân hàng · Mức sẵn sàng kiểm tra sơ bộ",
  DECISION_POST_BANKING_REVIEW: "Rà soát sau khảo sát ngân hàng",
  BANKING_PRECHECK_SUBMISSION_PROPOSAL: "Ngân hàng · Đề xuất chạy kiểm tra sơ bộ",
  BANKING_PRECHECK_RESULT_SET: "Kết quả kiểm tra sơ bộ mô phỏng",
  DECISION_POST_PRECHECK_REVIEW: "Rà soát sau kiểm tra sơ bộ",
  BANKING_PRECHECK_EVIDENCE_SUPPLEMENT: "Ngân hàng · Bằng chứng kiểm tra sơ bộ bổ sung",
  DOCUMENT_PREPARATION_REQUEST: "Hồ sơ · Yêu cầu chuẩn bị hồ sơ",
  DOCUMENT_CHECKLIST: "Hồ sơ · Danh mục hồ sơ",
  DOCUMENT_PACKAGE_DRAFT: "Hồ sơ · Bản nháp hồ sơ",
  DOCUMENT_RELEASE_PACKAGE: "Gói hồ sơ nội bộ",
  DOCUMENT_EVIDENCE_SUPPLEMENT: "Hồ sơ · Tài liệu người phê duyệt bổ sung",
  INTERNAL_DECISION_PACKAGE: "Hồ sơ quyết định nội bộ",
  FINAL_RISK_ASSESSMENT: "Rủi ro · Kiểm tra cuối",
  AI_DECISION_ANALYSIS: "Phân tích quyết định",
  DECISION_CARD: "Phiếu đề xuất quyết định",
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
