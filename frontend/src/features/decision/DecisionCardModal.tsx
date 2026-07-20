import type { ReactElement } from "react";

import { businessValueLabel } from "../../shared/businessLabels";
import { translateText } from "../../shared/translate";

import type {
  DecisionCalculation,
  DecisionCardArtifact,
  DecisionCondition,
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
  ACCEPT: "Chấp nhận hợp đồng",
  NEGOTIATE_CONDITIONS_TO_ACCEPT: "Đàm phán điều kiện để chấp nhận",
  DO_NOT_ACCEPT: "Không chấp nhận hợp đồng",
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
};

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

function Target({ condition }: { condition: DecisionCondition }): ReactElement | null {
  if (!condition.target) return null;
  const target = condition.target;
  const unit = target.currency ?? target.unit;
  return (
    <p>
      Hiện tại: <strong>{formatNumber(target.current_value, unit)}</strong>. Mục tiêu:{" "}
      <strong>{label(target.operator)} {formatNumber(target.target_value, unit)}</strong>.
    </p>
  );
}

function Conditions({ conditions = [] }: { conditions?: DecisionCondition[] }): ReactElement | null {
  if (!conditions.length) return null;
  return (
    <section>
      <h3>Điều kiện cần đáp ứng</h3>
      <ol>
        {conditions.map((condition, index) => (
          <li key={condition.condition_id ?? condition.code ?? index}>
            <strong>{translateText(condition.title)}</strong>
            <p>{translateText(condition.description)}</p>
            <p>Trạng thái: {label(condition.status)} · Điểm kiểm tra: {label(condition.enforcement_point)}</p>
            <Target condition={condition} />
            {condition.expected_risk_effect && <p>Tác dụng dự kiến: {translateText(condition.expected_risk_effect)}</p>}
          </li>
        ))}
      </ol>
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
  if (!calculations.length) return null;
  return (
    <section>
      <h3>Số liệu tính toán</h3>
      <ul>
        {calculations.map((calculation, index) => (
          <li key={calculation.calculation_id ?? `${calculation.code}-${index}`}>
            {label(calculation.code)}: <strong>{formatNumber(calculation.result_value, calculation.result_unit)}</strong>
          </li>
        ))}
      </ul>
    </section>
  );
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
  const isEvaluable = payload.recommendation !== "NOT_EVALUABLE";
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
        <section>
          <h3>Tóm tắt cho Nhà sáng lập</h3>
          <p>{translateText(payload.executive_summary)}</p>
          <ul>{payload.reasons.map((reason, index) => <li key={reason.code ?? index}><strong>{translateText(reason.title)}</strong>: {translateText(reason.detail)}</li>)}</ul>
        </section>

        <Metrics title="Tài chính của hợp đồng" metrics={payload.finance_metrics} />
        <Metrics title="Vận hành của hợp đồng" metrics={payload.operations_metrics} />
        <Calculations calculations={payload.calculations} />
        <Options options={payload.selected_options} />
        <Conditions conditions={payload.conditions} />

        {!!payload.selected_negotiation_strategies?.length && (
          <section>
            <h3>Phương án đàm phán</h3>
            <ul>{payload.selected_negotiation_strategies.map((strategy, index) => (
              <li key={strategy.strategy_id ?? index}>
                <strong>{translateText(strategy.title)}</strong>
                <p>{translateText(strategy.founder_instruction)}</p>
                {strategy.required_adjustment_value != null && <p>Mức điều chỉnh tối thiểu: {formatNumber(strategy.required_adjustment_value, strategy.currency ?? "VND")}.</p>}
              </li>
            ))}</ul>
          </section>
        )}

        <section>
          <h3>Rủi ro còn lại</h3>
          <p>Mức rủi ro: <strong>{label(payload.residual_risk_level)}</strong>.</p>
          {payload.major_exception_status && <p>Ngoại lệ nghiêm trọng: {label(payload.major_exception_status)}.</p>}
          <ul>{(payload.residual_findings ?? []).map((finding, index) => <li key={finding.code ?? index}><strong>{translateText(finding.title)}</strong>: {translateText(finding.detail)}</li>)}</ul>
        </section>

        {!!payload.required_controls?.length && <section><h3>Kiểm soát bắt buộc</h3><ul>{payload.required_controls.map((control, index) => <li key={control.code ?? index}>{translateText(control.description)}</li>)}</ul></section>}
        {!!payload.limitations?.length && <section><h3>Giới hạn cần biết</h3><ul>{payload.limitations.map((item, index) => <li key={item.code ?? index}>{translateText(item.detail)}</li>)}</ul></section>}
        {!!payload.human_attention_points?.length && <section><h3>Điểm Nhà sáng lập cần xem</h3><ul>{payload.human_attention_points.map((item, index) => <li key={item.code ?? index}>{translateText(item.text)}</li>)}</ul></section>}

        {payload.document_release_package && (
          <section>
            <h3>Hồ sơ dự kiến gửi bên ngoài</h3>
            <p>{payload.document_release_package.recipient} · {label(payload.document_release_package.purpose)}</p>
            <p>Hồ sơ này đang ở gói quyết định nội bộ; chưa được phép và chưa được gửi ra ngoài.</p>
          </section>
        )}

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
        {!isEvaluable && <p role="status">Decision Card này vẫn được hiển thị để Nhà sáng lập xem giới hạn, nhưng không thể phê duyệt một đề xuất chưa đủ cơ sở.</p>}
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
