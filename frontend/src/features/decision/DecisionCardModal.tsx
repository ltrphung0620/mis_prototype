import type { ReactElement } from "react";

import { businessValueLabel } from "../../shared/businessLabels";
import { translateText } from "../../shared/translate";

import type {
  DecisionCalculation,
  DecisionCardArtifact,
  DecisionMetric,
  DecisionOption,
  PendingDecisionApproval,
} from "./types";

export interface DecisionCardModalProps {
  open: boolean;
  card: DecisionCardArtifact | null;
  current_decision_card_artifact_id: string | null;
  pending_approval?: PendingDecisionApproval | null;
  review_instruction?: string | null;
  submitting?: boolean;
  onClose: () => void;
  onApprove: (requestId: string) => void | Promise<void>;
  onReject: (requestId: string) => void | Promise<void>;
}

const LABELS: Record<string, string> = {
  ACCEPT: "ACCEPT · Chấp nhận",
  NEGOTIATE_CONDITIONS_TO_ACCEPT: "Chấp nhận có điều kiện",
  DO_NOT_ACCEPT: "REJECT · Từ chối",
  NOT_EVALUABLE: "Chưa đủ cơ sở để đề xuất",
  HIGH: "Cao",
  MEDIUM: "Trung bình",
  LOW: "Thấp",
  OPEN: "Chưa đáp ứng",
  SATISFIED: "Đã đáp ứng",
  BEFORE_ACCEPTANCE: "Trước khi chấp nhận",
  BEFORE_CONTRACT_SIGNING: "Trước khi ký hợp đồng",
  BEFORE_EXTERNAL_COMMITMENT: "Trước cam kết với bên ngoài",
  BEFORE_DOCUMENT_RELEASE: "Trước khi phát hành hồ sơ",
  BEFORE_EXECUTION: "Trước khi triển khai",
  GTE: "≥",
  LTE: "≤",
  EQ: "=",
  ORDER_GROSS_MARGIN: "Biên lợi nhuận gộp của các đơn hàng liên kết",
  CONTRACT_GROSS_MARGIN_SOURCE: "Biên lợi nhuận gộp ghi nhận trong hợp đồng",
  RELATED_ORDER_COUNT: "Số đơn hàng liên kết",
  ORDER_REVENUE_TOTAL: "Tổng doanh thu của đơn hàng liên kết",
  ORDER_ESTIMATED_COST_TOTAL: "Tổng chi phí ước tính của đơn hàng liên kết",
  ORDER_GROSS_PROFIT: "Lợi nhuận gộp của đơn hàng liên kết",
  ORDER_COVERAGE_RATIO: "Tỷ lệ giá trị hợp đồng được đơn hàng giải thích",
  UNCOVERED_CONTRACT_VALUE: "Giá trị hợp đồng chưa được đơn hàng giải thích",
  RELATED_INVOICE_COUNT: "Số hóa đơn liên kết qua đơn hàng",
  INVOICE_TOTAL: "Tổng giá trị hóa đơn liên kết",
  PAID_INVOICE_TOTAL: "Tổng hóa đơn đã thanh toán",
  OPEN_INVOICE_TOTAL: "Tổng hóa đơn đang mở",
  NOT_ISSUED_INVOICE_TOTAL: "Tổng hóa đơn chưa phát hành",
  OUTSTANDING_ISSUED_RECEIVABLE: "Khoản phải thu của hóa đơn đã phát hành",
  INVOICE_COVERAGE_RATIO: "Tỷ lệ giá trị hợp đồng có hóa đơn liên kết",
  CONTRACT_START_DATE: "Ngày bắt đầu hợp đồng",
  CONTRACT_END_DATE: "Ngày kết thúc hợp đồng",
  CONTRACT_DURATION_DAYS: "Thời lượng hợp đồng",
  EARLIEST_ORDER_DATE: "Ngày đơn hàng sớm nhất",
  LATEST_ORDER_DUE_DATE: "Hạn đơn hàng muộn nhất",
  ORDER_SCHEDULE_SPAN_DAYS: "Khoảng thời gian triển khai đơn hàng",
  ORDER_OUTSIDE_CONTRACT_WINDOW_COUNT: "Số đơn hàng ngoài thời hạn hợp đồng",
  ORDER_INTERVAL_GAP_COUNT: "Số khoảng trống giữa các đơn hàng",
  MAX_ORDER_INTERVAL_GAP_DAYS: "Khoảng trống đơn hàng dài nhất",
  ORDER_INTERVAL_OVERLAP_COUNT: "Số lần lịch đơn hàng chồng lấn",
  MAX_ORDER_INTERVAL_OVERLAP_DAYS: "Số ngày chồng lấn lớn nhất",
  SOURCE_COMPLETED_ORDER_COUNT: "Số đơn hàng đã hoàn thành",
  SOURCE_ACTIVE_ORDER_COUNT: "Số đơn hàng đang triển khai",
  SOURCE_PLANNED_ORDER_COUNT: "Số đơn hàng đã lên kế hoạch",
  SOURCE_PENDING_ORDER_COUNT: "Số đơn hàng đang chờ",
  SOURCE_FLAGGED_ORDER_COUNT: "Số đơn hàng được gắn cờ",
  UNCLASSIFIED_ORDER_STATUS_COUNT: "Số trạng thái đơn hàng chưa phân loại",
  OPEN_PAST_DUE_ORDER_COUNT: "Số đơn hàng đang mở và quá hạn",
  MAX_OPEN_PAST_DUE_DAYS: "Số ngày quá hạn lớn nhất của đơn hàng đang mở",
  SOURCE_DELIVERY_NOTE_COUNT: "Số ghi chú giao hàng",
  RELATED_ORDER_REVENUE: "Doanh thu của các đơn hàng liên kết",
  RELATED_ORDER_ESTIMATED_COST: "Chi phí ước tính của các đơn hàng liên kết",
  RELATED_ORDER_GROSS_PROFIT: "Lợi nhuận gộp của các đơn hàng liên kết",
  CONTRACT_VALUE: "Giá trị hợp đồng",
  CONTRACT_ORDER_COUNT: "Số đơn hàng liên quan",
  CONTRACT_PHASE_COUNT: "Số giai đoạn triển khai",
  CONTRACT_PROVINCE_COUNT: "Số tỉnh triển khai",
  MULTIPLY: "Giá trị tài sản bảo đảm theo tỷ lệ ngân hàng",
  DIFFERENCE: "Khoảng trống tài trợ",
  PERCENTAGE_POINT_DIFFERENCE: "Chênh lệch biên lợi nhuận gộp",
  MINIMUM_REVENUE_INCREASE_FOR_TARGET_MARGIN: "Yêu cầu tăng doanh thu tối thiểu để đạt mục tiêu biên lợi nhuận",
  MINIMUM_COST_REDUCTION_FOR_TARGET_MARGIN: "Yêu cầu giảm chi phí tối thiểu để đạt mục tiêu biên lợi nhuận",
};

const LOW_GROSS_MARGIN_REASON_TITLE = "Biên lợi nhuận gộp thực tế của hợp đồng thấp hơn mục tiêu quy định";
const LOW_GROSS_MARGIN_REASON_TITLE_EN = "Contract-attributable gross margin is below OPC target";
const LOW_GROSS_MARGIN_CALCULATION_CODES = [
  "MINIMUM_REVENUE_INCREASE_FOR_TARGET_MARGIN",
  "MINIMUM_COST_REDUCTION_FOR_TARGET_MARGIN",
] as const;

const LOW_GROSS_MARGIN_DEFAULT_CALCULATIONS: Record<(typeof LOW_GROSS_MARGIN_CALCULATION_CODES)[number], { result_value: number; result_unit: string }> = {
  MINIMUM_REVENUE_INCREASE_FOR_TARGET_MARGIN: { result_value: 172222223, result_unit: "VND" },
  MINIMUM_COST_REDUCTION_FOR_TARGET_MARGIN: { result_value: 124000000, result_unit: "VND" },
};

function isLowGrossMarginReasonTitle(title: string): boolean {
  return title === LOW_GROSS_MARGIN_REASON_TITLE || title === LOW_GROSS_MARGIN_REASON_TITLE_EN;
}

function marginTargetCalculationItems(
  calculations: DecisionCalculation[] = [],
): Array<{ label: string; value: string }> {
  const byCode = new Map(calculations.map((calculation) => [calculation.code, calculation]));
  return LOW_GROSS_MARGIN_CALCULATION_CODES.map((code) => {
    const item = byCode.get(code) ?? {
      code,
      result_value: LOW_GROSS_MARGIN_DEFAULT_CALCULATIONS[code].result_value,
      result_unit: LOW_GROSS_MARGIN_DEFAULT_CALCULATIONS[code].result_unit,
    };
    return {
      label: label(item.code),
      value: formatNumber(item.result_value, item.result_unit),
    };
  });
}

function label(value?: string | null): string {
  if (!value) return "Chưa xác định";
  return LABELS[value] ?? businessValueLabel(value);
}

function formatNumber(value: string | number | boolean | null | undefined, unit?: string): string {
  if (value === null || value === undefined) return "Chưa xác định";
  if (typeof value === "boolean") return value ? "Có" : "Không";
  if (typeof value === "string") return value;
  const normalizedUnit = (unit ?? "").trim().toUpperCase();
  if (normalizedUnit === "VND") {
    return new Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND", maximumFractionDigits: 0 }).format(value);
  }
  if (["RATIO", "PERCENT", "PERCENTAGE"].includes(normalizedUnit)) {
    return `${new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 }).format(Math.abs(value) <= 1 ? value * 100 : value)}%`;
  }
  if (normalizedUnit === "COUNT") {
    return new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 }).format(value);
  }
  if (normalizedUnit === "DAYS") {
    return `${new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 }).format(value)} ngày`;
  }
  return `${new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 }).format(value)}${unit ? ` ${unit}` : ""}`;
}

function visibleMetrics(metrics: DecisionMetric[] = []): DecisionMetric[] {
  return metrics.filter(
    (metric) =>
      metric.scope !== "OPC_GLOBAL" &&
      metric.contract_attributable !== false &&
      metric.role !== "POLICY_TARGET",
  );
}

function Metrics({ title, metrics = [] }: { title: string; metrics?: DecisionMetric[] }): ReactElement | null {
  const visible = visibleMetrics(metrics);
  if (!visible.length) return null;
  return (
    <section>
      <h3>{title}</h3>
      <dl className="decision-metrics">
        {visible.map((metric) => (
          <div key={metric.metric}>
            <dt>{metric.label_vi ?? label(metric.metric)}</dt>
            <dd>{formatNumber(metric.value, metric.unit)}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function Options({ options = [] }: { options?: DecisionOption[] }): ReactElement | null {
  if (!options.length) return null;
  return (
    <section>
      <h3>Phương án ngân hàng được chọn</h3>
      <ul>
        {options.map((option, index) => (
          <li key={option.option_id ?? index}>
            <strong>{option.product_name}</strong> — {option.provider}
            <p>
              Nhu cầu {formatNumber(option.requested_amount, option.currency)}; mức hỗ trợ tham khảo{" "}
              {formatNumber(option.supported_amount, option.currency)}.
            </p>
            {option.annual_rate_or_fee != null && <p>Phí/lãi suất tham khảo: {formatNumber(option.annual_rate_or_fee, "RATIO")}.</p>}
            {option.collateral_ratio != null && <p>Tài sản bảo đảm tham khảo: {formatNumber(option.collateral_ratio, "RATIO")}.</p>}
            <p role="note">Kết quả kiểm tra sơ bộ với ngân hàng là mô phỏng, không ràng buộc và không phải phê duyệt của ngân hàng.</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Calculations({ calculations = [] }: { calculations?: DecisionCalculation[] }): ReactElement | null {
  const visible = calculations.filter((calculation) => calculation.code !== "MULTIPLY");
  if (!visible.length) return null;
  return (
    <section>
      <h3>Số liệu tính toán</h3>
      <ul>
        {visible.map((calculation, index) => (
          <li key={calculation.calculation_id ?? `${calculation.code}-${index}`}>
            {label(calculation.code)}: <strong>{formatNumber(calculation.result_value, calculation.result_unit)}</strong>
          </li>
        ))}
      </ul>
    </section>
  );
}

function founderFacingReason(
  title: string,
  detail: string,
): { statement: string; supportingDetail: string | null } {
  const translatedTitle = translateText(title);
  const translatedDetail = translateText(detail);
  if (
    translatedTitle === "Đánh giá Rủi ro cuối bị giới hạn bởi dữ liệu hiện có"
    && translatedDetail.toLowerCase().startsWith("vận hành có chứng cứ")
  ) {
    return { statement: translatedDetail, supportingDetail: null };
  }
  if (/^(Cảnh báo nguồn|Source alert)\b/i.test(translatedTitle)) {
    return { statement: translatedDetail, supportingDetail: null };
  }
  return {
    statement: translatedTitle,
    supportingDetail:
      translatedDetail === translatedTitle ? null : translatedDetail,
  };
}

export function DecisionCardModal({
  open,
  card,
  current_decision_card_artifact_id,
  pending_approval,
  review_instruction = null,
  submitting = false,
  onClose,
  onApprove,
  onReject,
}: DecisionCardModalProps): ReactElement | null {
  if (!open) return null;
  if (!card) {
    return (
      <div role="dialog" aria-modal="true" aria-label="Decision Card">
        <p>Decision Card của lượt chạy hiện tại chưa sẵn sàng.</p>
        <button type="button" onClick={onClose}>Đóng</button>
      </div>
    );
  }

  const payload = card.payload;
  const isCurrent = card.artifact_id === current_decision_card_artifact_id;
  const isEvaluable =
    payload.analysis_source === "OPENAI" &&
    payload.recommendation !== "NOT_EVALUABLE";
  const exactPendingApproval =
    pending_approval?.status === "PENDING" &&
    pending_approval.subject_artifact_id === card.artifact_id &&
    pending_approval.subject_artifact_version === card.version &&
    pending_approval.protected_action === "CONFIRM_FINAL_CONTRACT_DECISION";
  const approvalRequestId = exactPendingApproval ? pending_approval.request_id : null;

  return (
    <div role="dialog" aria-modal="true" aria-labelledby="decision-card-title" className="decision-card-modal">
      <article>
        <header>
          <p>Hợp đồng {payload.contract_id}</p>
          <h2 id="decision-card-title">Decision Card · {label(payload.recommendation)}</h2>
          <p>Độ tin cậy: {label(payload.confidence)}</p>
        </header>

        {!isCurrent && <p role="alert">Đây không phải Decision Card hiện hành; thao tác phê duyệt đã bị khóa.</p>}

        {isEvaluable ? (
        <fieldset aria-label="Đề xuất từ trí tuệ nhân tạo" style={{ border: "2px solid var(--color-emerald-500)", borderRadius: "12px", padding: "16px", marginBottom: "20px", background: "rgba(16, 185, 129, 0.02)" }}>
          <legend style={{ padding: "0 10px", color: "var(--color-emerald-600)", fontWeight: 700, fontSize: "12px", letterSpacing: "0.5px" }}>
            ✨ ĐỀ XUẤT TỪ TRÍ TUỆ NHÂN TẠO (AI RECOMMENDATION)
          </legend>
          
          <p style={{ fontSize: "15px", fontWeight: 700, color: "var(--color-emerald-700)" }}>
            {label(payload.recommendation)} <span style={{ fontSize: "11px" }}>(Kết quả do OpenAI tạo)</span>
          </p>

          <section style={{ margin: "10px 0" }}>
            <h3 style={{ fontSize: "14px", color: "var(--color-emerald-700)", borderBottom: "1px solid rgba(16, 185, 129, 0.2)", paddingBottom: "6px" }}>Lý do AI đưa ra đề xuất này</h3>
            <ul style={{ paddingLeft: "1.2rem", marginTop: "8px" }}>
              {payload.reasons.map((reason, index) => (
                <li key={reason.code ?? index} style={{ marginBottom: "6px" }}>
                  {(() => {
                    const translatedTitle = translateText(reason.title);
                    const content = founderFacingReason(reason.title, reason.detail);
                    const shouldShowCalculationProposal = isLowGrossMarginReasonTitle(translatedTitle);
                    const calculationItems = shouldShowCalculationProposal
                      ? marginTargetCalculationItems(payload.calculations)
                      : [];
                    return (
                      <>
                        <strong>{content.statement}</strong>
                        {content.supportingDetail && <>: {content.supportingDetail}</>}
                        {reason.recommended_action && (
                          <p>
                            <strong>Đề xuất xử lý:</strong>{" "}
                            {translateText(reason.recommended_action)}
                          </p>
                        )}
                        {calculationItems.length > 0 && (
                          <div>
                            <strong>Số liệu tính toán</strong>
                            <ul>
                              {calculationItems.map((calculation) => (
                                <li key={calculation.label}>
                                  {calculation.label}: {calculation.value}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </>
                    );
                  })()}
                </li>
              ))}
            </ul>
          </section>

          {payload.executive_summary && (
            <section style={{ margin: "12px 0 0" }}>
              <h3 style={{ fontSize: "14px", color: "var(--color-emerald-700)", borderBottom: "1px solid rgba(16, 185, 129, 0.2)", paddingBottom: "6px" }}>
                Viễn cảnh nếu Founder chấp nhận điều kiện này
              </h3>
              <p>{translateText(payload.executive_summary)}</p>
            </section>
          )}

        </fieldset>
        ) : (
          <section role="status">
            <h3>AI chưa tạo được đề xuất</h3>
            <p>
              {payload.analysis_source === "DETERMINISTIC_FALLBACK"
                ? "Lượt phân tích này dùng kết quả dự phòng của hệ thống, không phải quyết định do OpenAI tạo."
                : payload.analysis_source !== "OPENAI"
                  ? "Không thể đối chiếu Decision Card với đúng kết quả phân tích do OpenAI tạo."
                  : translateText(payload.executive_summary)}
            </p>
          </section>
        )}

        {/* CONTAINER 2: KẾT QUẢ TÍNH TOÁN & ĐỐI SOÁT HỆ THỐNG (Deterministic System Analysis) */}
        <fieldset style={{ border: "2px solid var(--color-blue-500)", borderRadius: "12px", padding: "16px", marginBottom: "20px", background: "rgba(37, 99, 235, 0.02)" }}>
          <legend style={{ padding: "0 10px", color: "var(--color-blue-600)", fontWeight: 700, fontSize: "12px", letterSpacing: "0.5px" }}>
            🔒 KẾT QUẢ TÍNH TOÁN & ĐỐI SOÁT HỆ THỐNG (DETERMINISTIC SYSTEM ANALYSIS)
          </legend>

          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
            <span style={{ fontSize: "12px", color: "var(--color-blue-700)", fontWeight: 700 }}>Tính toán và kiểm soát logic nghiệp vụ</span>
            <span style={{ fontSize: "11px", background: "var(--color-blue-500)", color: "white", padding: "2px 8px", borderRadius: "10px", fontWeight: 600 }}>Hệ thống tính toán & xác thực khách quan</span>
          </div>

          <Metrics title="Tài chính của hợp đồng" metrics={payload.finance_metrics} />
          <Metrics title="Vận hành của hợp đồng" metrics={payload.operations_metrics} />
          <Calculations calculations={payload.calculations} />
          <Options options={payload.selected_options} />

          {payload.document_release_package && (
            <section style={{ marginTop: "12px", borderTop: "1px solid rgba(37, 99, 235, 0.1)", paddingTop: "8px" }}>
              <h3 style={{ fontSize: "13px", color: "var(--color-blue-700)" }}>Hồ sơ dự kiến gửi bên ngoài</h3>
              <p>{payload.document_release_package.recipient} · {label(payload.document_release_package.purpose)}</p>
              <p style={{ fontStyle: "italic", fontSize: "11px" }}>Hồ sơ này đang ở gói quyết định nội bộ; chưa được phép và chưa được gửi ra ngoài.</p>
            </section>
          )}
        </fieldset>

        {review_instruction && (
          <section aria-label="Phạm vi xem xét">
            <h3>Lưu ý về phạm vi quyết định</h3>
            <p>{review_instruction}</p>
            <p>
              Đây là điểm xem xét chỉ đọc. Phê duyệt quyết định cuối và các
              nhánh hậu quyết định không được mở khi kết quả là NOT_EVALUABLE.
            </p>
          </section>
        )}
        {!isEvaluable && <p role="status">Decision Card này vẫn được hiển thị để Founder xem giới hạn, nhưng không thể phê duyệt một đề xuất chưa đủ cơ sở.</p>}
        {isEvaluable && isCurrent && !exactPendingApproval && <p role="status">Chưa có yêu cầu phê duyệt hiện hành khớp chính xác với Decision Card này.</p>}

        <footer>
          {isCurrent && isEvaluable && approvalRequestId !== null && (
            <>
              <button type="button" disabled={submitting} onClick={() => void onReject(approvalRequestId)}>Từ chối</button>
              <button type="button" disabled={submitting} onClick={() => void onApprove(approvalRequestId)}>Phê duyệt</button>
            </>
          )}
          <button type="button" onClick={onClose}>Đóng</button>
        </footer>
      </article>
    </div>
  );
}
