const BUSINESS_VALUE_LABELS: Readonly<Record<string, string>> = {
  ACCEPT: "ACCEPT Â· Cháº¥p nháº­n",
  NEGOTIATE_CONDITIONS_TO_ACCEPT: "Chấp nhận có điều kiện",
  DO_NOT_ACCEPT: "REJECT · Từ chối",
  HIGH: "Cao",
  MEDIUM: "Trung bình",
  LOW: "Thấp",
  NOT_EVALUABLE: "Chưa đủ cơ sở đánh giá",
  DETECTED: "Đã phát hiện",
  NOT_DETECTED: "Không phát hiện",
  OPTIONS_READY: "Đã có phương án phù hợp để xem xét",
  OPTIONS_READY_WITH_GAPS: "Đã có phương án nhưng còn thiếu dữ liệu",
  NO_CONFIGURED_OPTIONS: "Không có phương án được cấu hình phù hợp",
  WAITING_FOR_REQUEST: "Đang chờ yêu cầu khảo sát",
  REQUEST_CREATED: "Đã tạo yêu cầu",
  WAITING_FOR_ROUTE: "Đang chờ xác định tuyến xử lý",
  FAILED_SAFE: "Đã dừng an toàn",
  DIRECT_ROUTE: "Tuyến quyết định nội bộ trực tiếp",
  BANKING_NO_VIABLE_OPTION: "Không có phương án ngân hàng khả thi",
  BANKING_NO_PRECHECK_PATH: "Không có tuyến kiểm tra sơ bộ với ngân hàng phù hợp",
  BANKING_PRECHECK_DECLINED: "Yêu cầu kiểm tra sơ bộ với ngân hàng không được phê duyệt",
  BANKING_NON_ACTIONABLE: "Kết quả ngân hàng chưa đủ điều kiện xử lý tiếp",
  CONDITIONAL_DOCUMENT_READY: "Hồ sơ có điều kiện đã được chuẩn bị",
  FINAL_DECISION_ACCEPTED: "Đã chấp nhận hợp đồng",
  NEGOTIATION_AUTHORIZED: "Đã cho phép tiến hành đàm phán",
  CASE_CLOSED_NO_EXTERNAL_ACTION: "Đã đóng hồ sơ, không cần hành động bên ngoài",
  NOT_INVOKED: "Không cần thực hiện",
  PARTIALLY_READY: "Sẵn sàng một phần",
  INPUT_REQUIRED: "Cần bổ sung dữ liệu",
  NOT_CONFIGURED: "Chưa được cấu hình",
  UNSUPPORTED_MAPPING: "Chưa hỗ trợ ánh xạ dữ liệu",
  OPTION_REQUIREMENTS_NOT_MET: "Chưa đáp ứng điều kiện của phương án",
  CONDITIONAL_PRECHECK: "Kiểm tra sơ bộ có điều kiện",
  MISSING_EVIDENCE: "Còn thiếu tài liệu xác nhận",
  RELATED_ORDER_COUNT: "Số đơn hàng liên kết",
  RELATED_INVOICE_COUNT: "Số hóa đơn liên kết qua đơn hàng",
  CONTRACT_ORDER_COUNT: "Số đơn hàng liên quan",
  CONTRACT_PHASE_COUNT: "Số giai đoạn triển khai",
  CONTRACT_PROVINCE_COUNT: "Số tỉnh triển khai",
  ORDER_OUTSIDE_CONTRACT_WINDOW_COUNT: "Số đơn hàng ngoài thời hạn hợp đồng",
  ORDER_INTERVAL_GAP_COUNT: "Số khoảng trống giữa các đơn hàng",
  ORDER_INTERVAL_OVERLAP_COUNT: "Số lần lịch đơn hàng chồng lấn",
  SOURCE_COMPLETED_ORDER_COUNT: "Số đơn hàng đã hoàn thành",
  SOURCE_ACTIVE_ORDER_COUNT: "Số đơn hàng đang triển khai",
  SOURCE_PLANNED_ORDER_COUNT: "Số đơn hàng đã lên kế hoạch",
  SOURCE_PENDING_ORDER_COUNT: "Số đơn hàng đang chờ",
  SOURCE_FLAGGED_ORDER_COUNT: "Số đơn hàng được gắn cờ",
  UNCLASSIFIED_ORDER_STATUS_COUNT: "Số trạng thái đơn hàng chưa phân loại",
  OPEN_PAST_DUE_ORDER_COUNT: "Số đơn hàng đang mở và quá hạn",
  SOURCE_DELIVERY_NOTE_COUNT: "Số ghi chú giao hàng",
};

export function businessValueLabel(
  value?: string | null,
  fallback = "Trạng thái đã được hệ thống ghi nhận",
): string {
  if (!value) return "Chưa xác định";
  const upper = value.toUpperCase();
  if (BUSINESS_VALUE_LABELS[upper]) {
    return BUSINESS_VALUE_LABELS[upper];
  }
  if (upper.includes("COUNT")) {
    const clean = upper
      .replace(/_COUNT$/, "")
      .replace(/^COUNT_/, "")
      .replace(/_COUNT_/g, "_");
    return BUSINESS_VALUE_LABELS[clean] ?? `Số lượng ${clean.toLowerCase().replace(/_/g, " ")}`;
  }
  return fallback;
}

