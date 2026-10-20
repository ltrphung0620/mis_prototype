/** Labels for the viewer. These never replace stored actions or conditions. */
const LABELS: Readonly<Record<string, string>> = {
  SUBMIT_BANKING_PRECHECK: "Duyệt kiểm tra sơ bộ với ngân hàng",
  CONFIRM_FINAL_CONTRACT_DECISION: "Xác nhận quyết định hợp đồng",
  SEND_DOCUMENT_TO_EXTERNAL_PARTNER: "Cho phép gửi hồ sơ ra ngoài",
  BANKING_DISCOVERY_REQUIRED: "Cần khảo sát ngân hàng",
  DIRECT_ROUTE: "Xử lý nội bộ",
  BANKING_PRECHECK_READY: "Đủ dữ liệu kiểm tra sơ bộ",
  "NO_VIABLE_OPTION / NO_PRECHECK_PATH":
    "Không có phương án hoặc cách kiểm tra phù hợp",
  AUTHORIZED: "Đã được cho phép",
  DECLINED: "Không được chấp thuận",
  CONDITIONAL_OPTIONS_AVAILABLE: "Có phương án kèm điều kiện",
  NON_ACTIONABLE: "Chưa thể xử lý tiếp",
  CONDITIONAL_DOCUMENT_READY: "Hồ sơ có điều kiện đã sẵn sàng",
  APPROVABLE_CARD: "Đề xuất đủ cơ sở để xem xét",
  EXACT_APPROVAL: "Đã duyệt đúng kết quả và phiên bản",
  NEGOTIATION_AUTHORIZED: "Đã cho phép đàm phán",
  "ACCEPTED + RELEASE_REQUIRED": "Đã chấp nhận và cần gửi hồ sơ",
  RELEASE_REQUIRED: "Cần gửi hồ sơ",
  EXACT_AUTHORIZATION: "Đã cho phép đúng đề xuất và phiên bản",
};

export function workflowDetailLabel(value: string): string {
  return LABELS[value] ?? value;
}
