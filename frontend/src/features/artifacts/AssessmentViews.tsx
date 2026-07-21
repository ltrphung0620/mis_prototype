import type { ReactElement } from "react";

import { businessValueLabel } from "../../shared/businessLabels";
import { translateText } from "../../shared/translate";

import type {
  ArtifactEnvelope,
  AssessmentFact,
  AssessmentNote,
  BankingArtifactPayload,
  BankingOption,
  DocumentArtifactPayload,
  FinanceArtifactPayload,
  OperationsArtifactPayload,
  RiskArtifactPayload,
  DecisionPostPrecheckReviewPayload,
} from "./types";
import {
  BankingAdviceView,
  BankingDiscoveryView,
  BankingReadinessView,
  DocumentChecklistView,
  EvaluationCaseView,
  InternalDecisionPackageView,
  PlannerAssessmentView,
  RiskPreScanView,
} from "./WorkflowArtifactViews";
import type {
  BankingAdvicePayload,
  BankingDiscoveryPayload,
  BankingReadinessPayload,
  DocumentChecklistPayload,
  EvaluationCasePayload,
  InternalDecisionPackagePayload,
  PlannerResultPayload,
  RiskPreScanPayload,
} from "./types";

const LABELS: Record<string, string> = {
  CONTRACT_VALUE: "Giá trị hợp đồng",
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
  EARLIEST_ORDER_DATE: "Ngày bắt đầu đơn hàng sớm nhất",
  LATEST_ORDER_DUE_DATE: "Hạn đơn hàng muộn nhất",
  ORDER_SCHEDULE_SPAN_DAYS: "Khoảng thời gian triển khai đơn hàng",
  ORDER_OUTSIDE_CONTRACT_WINDOW_COUNT: "Số đơn hàng ngoài thời hạn hợp đồng",
  ORDER_INTERVAL_GAP_COUNT: "Số khoảng trống giữa các đơn hàng",
  MAX_ORDER_INTERVAL_GAP_DAYS: "Khoảng trống giữa đơn hàng dài nhất",
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
  SIGNED_CONTRACT: "Hợp đồng đã ký",
  COMPANY_PROFILE: "Hồ sơ doanh nghiệp",
  PERFORMANCE_BOND_REQUEST_FORM: "Đơn đề nghị bảo lãnh thực hiện",
  CASHFLOW_BUFFER_EVIDENCE: "Tài liệu chứng minh nguồn bù dòng tiền",
  BANKING_PRECHECK: "Khảo sát điều kiện ngân hàng",
  RELATED_ORDER_REVENUE: "Doanh thu từ đơn hàng đã liên kết",
  RELATED_ORDER_ESTIMATED_COST: "Chi phí ước tính từ đơn hàng đã liên kết",
  RELATED_ORDER_GROSS_PROFIT: "Lợi nhuận gộp từ đơn hàng đã liên kết",
  ORDER_GROSS_MARGIN: "Biên lợi nhuận gộp từ đơn hàng đã liên kết",
  CONTRACT_VALUE_NOT_COVERED_BY_ORDERS: "Giá trị hợp đồng chưa được đơn hàng giải thích",
  CONTRACT_ORDER_COUNT: "Số đơn hàng liên quan",
  CONTRACT_PHASE_COUNT: "Số giai đoạn triển khai",
  CONTRACT_PROVINCE_COUNT: "Số tỉnh triển khai",
  HIGH: "Cao",
  MEDIUM: "Trung bình",
  LOW: "Thấp",
  LIMITED_BY_EVIDENCE: "Giới hạn bởi dữ liệu hiện có",
  COMPLETE: "Đầy đủ",
  OPEN_UNCHANGED: "Đang mở",
  VERIFIED: "Đã kiểm tra",
  LIMITED_BY_COVERAGE: "Giới hạn do phạm vi dữ liệu",
  NOT_AVAILABLE: "Chưa có dữ liệu",
  NOT_EVALUABLE: "Chưa đủ cơ sở đánh giá",
  CRITICAL: "Nghiêm trọng",
  NO_CASE_SIGNAL: "Chưa ghi nhận tín hiệu riêng của hợp đồng",
  COMPLETED_SOURCE_STATUS: "Đã hoàn thành",
  ACTIVE_SOURCE_STATUS: "Đang triển khai",
  PLANNED_SOURCE_STATUS: "Đã lên kế hoạch",
  SOURCE_PENDING_STATUS: "Đang chờ",
  SOURCE_FLAGGED_STATUS: "Cần lưu ý",
  UNCLASSIFIED_SOURCE_STATUS: "Chưa phân loại",
  CONDITIONAL_PRECHECK: "Kiểm tra sơ bộ có điều kiện",
  ELIGIBLE: "Đủ điều kiện sơ bộ",
  CONDITIONAL: "Có điều kiện",
  NO_DECISION: "Chưa có quyết định",
};

function humanize(value?: string | null): string {
  if (!value) return "Chưa xác định";
  return LABELS[value] ?? businessValueLabel(value);
}

function formatValue(value: AssessmentFact["value"], unit?: string): string {
  if (value === null || value === undefined || value === "") return "Chưa xác định";
  if (typeof value === "boolean") return value ? "Có" : "Không";
  if (typeof value !== "number") return String(value);
  const normalizedUnit = (unit ?? "").trim().toUpperCase();
  if (normalizedUnit === "COUNT") {
    return new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 }).format(value);
  }
  if (normalizedUnit === "DAYS") {
    return `${new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 }).format(value)} ngày`;
  }
  if (normalizedUnit === "VND") {
    return new Intl.NumberFormat("vi-VN", {
      style: "currency",
      currency: "VND",
      maximumFractionDigits: 0,
    }).format(value);
  }
  if (normalizedUnit.includes("RATIO") || normalizedUnit.includes("PERCENT")) {
    return `${new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 }).format(
      Math.abs(value) <= 1 ? value * 100 : value,
    )}%`;
  }
  return `${new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 }).format(value)}${
    unit ? ` ${unit}` : ""
  }`;
}

function contractFacts(facts: AssessmentFact[] = []): AssessmentFact[] {
  return facts.filter((fact) => (fact.scope ?? "CASE_SPECIFIC") !== "OPC_GLOBAL");
}

function globalFactIds(facts: AssessmentFact[] = []): Set<string> {
  return new Set(
    facts
      .filter((fact) => fact.scope === "OPC_GLOBAL" && fact.fact_id)
      .map((fact) => fact.fact_id as string),
  );
}

function isGlobalOnlyReference(factIds: string[] | undefined, globalIds: Set<string>): boolean {
  return Boolean(factIds?.length && factIds.every((factId) => globalIds.has(factId)));
}

function FactGrid({ facts }: { facts: AssessmentFact[] }): ReactElement {
  if (!facts.length) return <p>Chưa có số liệu phù hợp để hiển thị.</p>;
  return (
    <dl className="assessment-fact-grid">
      {facts.map((fact, index) => (
        <div key={`${fact.metric ?? fact.code ?? "metric"}-${index}`}>
          <dt>{humanize(fact.metric ?? fact.code ?? fact.title)}</dt>
          <dd>{formatValue(fact.value, fact.unit)}</dd>
          {fact.note && fact.note !== "Source contract field; not recalculated from orders." && (
            <small>{translateText(fact.note)}</small>
          )}
        </div>
      ))}
    </dl>
  );
}

function Notes({ title, items = [] }: { title: string; items?: AssessmentNote[] }): ReactElement | null {
  const visibleItems = items.filter((item) => item.scope !== "OPC_GLOBAL");
  if (!visibleItems.length) return null;
  return (
    <section>
      <h4>{title}</h4>
      <ul>
        {visibleItems.map((item, index) => {
          const rawTitle = item.title ?? humanize(item.code);
          const hasTitle = rawTitle && rawTitle !== "Trạng thái đã được hệ thống ghi nhận";
          const rawDetail = item.detail ?? item.text ?? item.description;
          return (
            <li key={`${item.code ?? item.title ?? title}-${index}`}>
              {hasTitle && <strong>{translateText(rawTitle)}</strong>}
              {rawDetail && (
                <p style={hasTitle ? {} : { margin: 0 }}>{translateText(rawDetail)}</p>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export function FinanceAssessmentView({ payload, variant = "ASSESSMENT" }: { payload: FinanceArtifactPayload; variant?: "FACTS" | "ASSESSMENT" }): ReactElement {
  const facts = contractFacts(payload.facts);
  const globalIds = globalFactIds(payload.facts);
  const caseObservations = (payload.observations ?? []).filter(
    (item) => item.scope !== "OPC_GLOBAL" && !isGlobalOnlyReference(item.fact_ids, globalIds),
  );
  const caseLimitations = (payload.limitations ?? []).filter((item) => item.scope !== "OPC_GLOBAL");
  return (
    <article aria-label="Đánh giá tài chính" className="assessment-view">
      <header>
        <h3>{variant === "FACTS" ? "Số liệu tài chính của hợp đồng" : "Đánh giá tài chính"}</h3>
        {payload.assessment_status && payload.assessment_status !== "LIMITED_BY_EVIDENCE" && (
          <span>{humanize(payload.assessment_status)}</span>
        )}
      </header>
      {facts.length ? <FactGrid facts={facts} /> : variant === "FACTS" ? <p>Chưa có số liệu tài chính phù hợp để hiển thị.</p> : null}
      {payload.narrative && (
        <section aria-label="Diễn giải tài chính">
          <h4>
            {payload.narrative.headline ?? "Diễn giải"}
            {payload.narrative_source === "OPENAI" ? " (Nội dung do OpenAI tạo)" : ""}
          </h4>
          <ul>
            {(payload.narrative.statements ?? []).filter(
              (statement) => !isGlobalOnlyReference(statement.fact_ids, globalIds),
            ).map((statement, index) => (
              <li key={index}>{statement.text}</li>
            ))}
          </ul>
        </section>
      )}
      <Notes title="Điểm cần lưu ý" items={caseObservations} />
      <Notes title="Giới hạn dữ liệu" items={caseLimitations} />
    </article>
  );
}

export function OperationsAssessmentView({ payload, variant = "ASSESSMENT" }: { payload: OperationsArtifactPayload; variant?: "FACTS" | "ASSESSMENT" }): ReactElement {
  const globalIds = globalFactIds(payload.facts);
  return (
    <article aria-label="Đánh giá vận hành" className="assessment-view">
      <header>
        <h3>{variant === "FACTS" ? "Số liệu vận hành của hợp đồng" : "Đánh giá vận hành"}</h3>
        {payload.assessment_status && payload.assessment_status !== "LIMITED_BY_EVIDENCE" && (
          <span>{humanize(payload.assessment_status)}</span>
        )}
      </header>
      {contractFacts(payload.facts).length ? <FactGrid facts={contractFacts(payload.facts)} /> : variant === "FACTS" ? <p>Chưa có số liệu vận hành phù hợp để hiển thị.</p> : null}
      {!!payload.summary?.length && (
        <section><h4>Tóm tắt vận hành</h4><ul>{payload.summary.filter((statement) => !isGlobalOnlyReference(statement.fact_ids, globalIds)).map((statement, index) => <li key={index}>{translateText(statement.text)}</li>)}</ul></section>
      )}
      {!!payload.order_schedules?.length && (
        <section>
          <h4>Tiến độ đơn hàng</h4>
          <ul>
            {payload.order_schedules.map((order) => (
              <li key={order.order_id}>
                <strong>{order.order_id}</strong>: hạn {order.due_date ?? "chưa xác định"} · {humanize(order.status_category)}
                {typeof order.past_due_days === "number" && ` · trễ ${order.past_due_days} ngày`}
              </li>
            ))}
          </ul>
        </section>
      )}
      <Notes title="Quan sát vận hành" items={payload.observations?.filter((item) => !isGlobalOnlyReference(item.fact_ids, globalIds))} />
      <Notes title="Giới hạn dữ liệu" items={payload.limitations} />
    </article>
  );
}

export function RiskAssessmentView({ payload, phase = "INITIAL" }: { payload: RiskArtifactPayload; phase?: "INITIAL" | "FINAL" }): ReactElement {
  const riskLevel = payload.residual_risk_level ?? payload.overall_risk_level ?? payload.risk_level ?? payload.initial_risk_level;
  const confirmations = payload.human_confirmation_points ?? [];
  const gates = payload.unresolved_approval_gates ?? [];
  const hasActions = !!confirmations.length || !!gates.length;
  const finalConclusion = payload.conclusion === "SAFE"
    ? "An toàn: không còn rủi ro chưa được kiểm soát và không còn điểm nào chờ Founder xác nhận/phê duyệt."
    : "Cần tiếp tục xử lý: vẫn còn rủi ro, giới hạn bằng chứng hoặc điểm xác nhận/phê duyệt chưa hoàn tất.";

  return (
    <article aria-label="Đánh giá rủi ro" className="assessment-view">
      <header style={{ borderBottom: "1px solid var(--color-line)", paddingBottom: "12px", marginBottom: "4px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
          <h3 style={{ margin: 0, fontSize: "18px", fontWeight: 700 }}>
            {phase === "FINAL" ? "Kiểm tra rủi ro cuối" : "Đánh giá rủi ro ban đầu"}
          </h3>
          <span className="status-badge status-badge--success" style={{ fontWeight: 700, fontSize: "12px" }}>
            {phase === "FINAL" ? "Mức còn lại" : "Mức tổng thể"}: {translateText(humanize(riskLevel))}
          </span>
        </div>
        {(payload.major_exception_status || payload.major_exception_signal) && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", marginTop: "8px", fontSize: "11px", color: "var(--color-ink-450)" }}>
            {payload.major_exception_status && (
              <span>Ngoại lệ nghiêm trọng: {translateText(humanize(payload.major_exception_status))}</span>
            )}
            {payload.major_exception_signal && (
              <span>· {translateText(payload.major_exception_signal.detail)}</span>
            )}
          </div>
        )}
      </header>

      {phase === "FINAL" && (
        <p role="status" className={payload.conclusion === "SAFE" ? "status-badge status-badge--success" : undefined}>
          {finalConclusion}
        </p>
      )}

      {/* Rủi ro và kiểm soát */}
      <Notes title="Rủi ro đang mở" items={payload.residual_findings ?? payload.findings} />
      <Notes title="Biện pháp kiểm soát bắt buộc" items={payload.required_controls} />
      {phase === "FINAL" && <Notes title="Giới hạn đánh giá" items={payload.limitations} />}

      {/* Cổng kiểm soát & hành động cần xử lý */}
      {hasActions && (
        <section style={{ borderTop: "1px solid var(--color-line)", paddingTop: "12px", marginTop: "8px" }}>
          <h4 style={{ color: "var(--color-red-700)", marginBottom: "8px" }}>Cần xử lý phê duyệt</h4>
          <ul style={{ paddingLeft: "1.2rem", margin: 0 }}>
            {confirmations.map((point, index) => (
              <li key={`${point.reason_code ?? "confirmation"}-${index}`} style={{ marginBottom: "6px" }}>
                <strong>Xác nhận bối cảnh rủi ro:</strong> {translateText(point.question)}
              </li>
            ))}
            {gates.map((gate, index) => (
              <li key={`gate-${index}`} style={{ marginBottom: "6px" }}>
                <strong>Yêu cầu phê duyệt:</strong> {translateText(humanize(gate.protected_action))} ({translateText(humanize(gate.request_status))})
                {gate.reason && <p style={{ margin: "2px 0 0 0", fontSize: "11px", color: "var(--color-ink-600)" }}>Lý do: {translateText(gate.reason)}</p>}
              </li>
            ))}
          </ul>
        </section>
      )}
    </article>
  );
}

function BankingOptionCard({ option }: { option: BankingOption }): ReactElement {
  const simulated = option.non_binding || (option.authority ?? "").includes("SIMULATED");
  return (
    <li>
      <strong>{option.product_name ?? option.bank_product_id ?? option.option_id ?? "Phương án ngân hàng"}</strong>
      <p>
        {option.provider ?? option.api_provider ?? "Nhà cung cấp chưa xác định"} · yêu cầu {formatValue(option.requested_amount, option.currency)} · hỗ trợ {formatValue(option.supported_amount, option.currency)}
      </p>
      {option.collateral_ratio != null && <p>Tỷ lệ tài sản bảo đảm tham khảo: {formatValue(option.collateral_ratio, "RATIO")}</p>}
      {option.annual_rate_or_fee != null && <p>Phí/lãi suất tham khảo: {formatValue(option.annual_rate_or_fee, "RATIO")}</p>}
      {option.outcome && <p>Kết quả: {humanize(option.outcome)}</p>}
      {simulated && <p role="note">Kết quả mô phỏng, không ràng buộc và không phải phê duyệt của ngân hàng.</p>}
    </li>
  );
}

export function BankingAssessmentView({ payload }: { payload: BankingArtifactPayload }): ReactElement {
  const options = payload.results ?? payload.options ?? payload.candidates ?? [];
  const globallySimulated = (payload.authority ?? "").includes("SIMULATED");
  return (
    <article aria-label="Khảo sát phương án ngân hàng" className="assessment-view">
      <header><h3>Phương án ngân hàng</h3><span>{humanize(payload.status)}</span></header>
      {(globallySimulated || payload.bank_approval_obtained === false) && (
        <p role="note">Kết quả kiểm tra sơ bộ hiện tại là mô phỏng không ràng buộc; chưa có xác nhận hay phê duyệt từ ngân hàng.</p>
      )}
      {options.length ? <ul>{options.map((option, index) => <BankingOptionCard key={option.option_id ?? index} option={option} />)}</ul> : <p>Chưa có phương án ngân hàng phù hợp.</p>}
    </article>
  );
}

const SANITIZED_FIELD_LABELS: Record<string, string> = {
  company_name: "Tên doanh nghiệp",
  company_id: "Mã số thuế",
  customer_id: "Mã khách hàng",
  contract_value: "Giá trị hợp đồng",
  payment_terms: "Điều khoản thanh toán",
  contract_id: "Mã hợp đồng",
  requested_amount: "Số tiền bảo lãnh yêu cầu",
  currency: "Loại tiền tệ",
  bank_product_id: "Sản phẩm bảo lãnh",
  request_type: "Loại bảo lãnh",
};

export function DocumentPackageView({ payload, variant = "DRAFT" }: { payload: DocumentArtifactPayload; variant?: "DRAFT" | "RELEASE" }): ReactElement {
  const manifest: Array<{ document_code?: string; status?: string }> =
    payload.document_manifest ??
    payload.document_codes?.map((document_code) => ({ document_code })) ??
    [];
  const sanitized = payload.sanitized_payload ?? {};
  const sanitizedEntries = Object.entries(sanitized);

  return (
    <article aria-label="Hồ sơ tài liệu" className="assessment-view">
      <header>
        <h3>{variant === "RELEASE" ? "Gói hồ sơ đã chuẩn bị nội bộ" : "Bản nháp hồ sơ nội bộ"}</h3>
        {payload.readiness && <span>{humanize(payload.readiness)}</span>}
      </header>
      <p>Người nhận dự kiến: {payload.recipient ?? "Chưa xác định"}</p>
      <p>Mục đích: {humanize(payload.purpose)}</p>
      {!!manifest.length && (
        <section>
          <h4 style={{ marginBottom: "8px" }}>Danh mục tài liệu đính kèm</h4>
          <ul>
            {manifest.map((item, index) => (
              <li key={`${item.document_code ?? "document"}-${index}`}>
                {item.document_code === "SIGNED_CONTRACT" && item.status === "DRAFTED"
                  ? "Tạo bản nháp hợp đồng"
                  : `${humanize(item.document_code)}${item.status ? ` — ${humanize(item.status)}` : ""}`}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Dữ liệu đã tối giản & masking */}
      {!!sanitizedEntries.length && (
        <section style={{ marginTop: "12px", borderTop: "1px solid var(--color-line)", paddingTop: "12px" }}>
          <h4 style={{ marginBottom: "8px" }}>Dữ liệu hồ sơ sau khi lọc & mã hóa (Masked/Minimized Data)</h4>
          <dl className="decision-metrics" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: "10px" }}>
            {sanitizedEntries.map(([key, val]) => {
              const labelText = SANITIZED_FIELD_LABELS[key] ?? key;
              let displayVal = String(val);
              if (typeof val === "number") {
                if (key.includes("value") || key.includes("amount")) {
                  displayVal = formatValue(val, "VND");
                } else {
                  displayVal = formatValue(val);
                }
              }
              return (
                <div key={key} style={{ background: "rgba(0,0,0,0.02)", padding: "8px 12px", borderRadius: "8px" }}>
                  <dt style={{ fontSize: "10px", color: "var(--color-ink-450)" }}>{labelText}</dt>
                  <dd style={{ margin: "2px 0 0 0", fontWeight: 650, fontSize: "13px" }}>{displayVal}</dd>
                </div>
              );
            })}
          </dl>
        </section>
      )}

      <p style={{ marginTop: "12px" }}>
        {payload.external_release_performed
          ? "Hệ thống ghi nhận hồ sơ đã được gửi ra ngoài."
          : payload.release_authorized
            ? "Đã được phép chuẩn bị gửi; chưa có xác nhận đã gửi."
            : "Hồ sơ đang ở nội bộ và chưa được phép gửi ra ngoài."}
      </p>
    </article>
  );
}

const POST_PRECHECK_LABELS: Record<string, string> = {
  FOLLOW_UP_EVIDENCE_REQUIRED: "Cần bổ sung hồ sơ/bằng chứng",
  CONDITIONAL_OPTIONS_AVAILABLE: "Có phương án khả thi kèm điều kiện",
  ALL_OPTIONS_NOT_ELIGIBLE: "Không có phương án nào đủ điều kiện",
  NO_PROVIDER_RECOMMENDATION: "Không nhận được đề xuất từ ngân hàng",
  PRECHECK_SERVICE_UNAVAILABLE: "Dịch vụ precheck không khả dụng",
  MIXED_NON_ACTIONABLE_RESULTS: "Kết quả hỗn hợp không thể xử lý tiếp",
  PRECHECK_UNAVAILABLE: "Không có dữ liệu precheck",
  ELIGIBLE: "Đủ điều kiện",
  CONDITIONAL: "Có điều kiện",
  NOT_ELIGIBLE: "Không đủ điều kiện",
};

export function DecisionPostPrecheckReviewView({ payload }: { payload: DecisionPostPrecheckReviewPayload }): ReactElement {
  const reviews = payload.option_reviews ?? [];
  const outcomeText = payload.outcome ? (POST_PRECHECK_LABELS[payload.outcome] ?? humanize(payload.outcome)) : "Chưa xác định";

  return (
    <article aria-label="Kết quả precheck" className="assessment-view">
      <header style={{ borderBottom: "1px solid var(--color-line)", paddingBottom: "12px", marginBottom: "4px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
          <h3 style={{ margin: 0, fontSize: "18px", fontWeight: 700 }}>Kết quả đánh giá Precheck</h3>
          <span className="status-badge status-badge--success" style={{ fontWeight: 700, fontSize: "12px" }}>
            Kết luận: {translateText(outcomeText)}
          </span>
        </div>
      </header>

      {reviews.length ? (
        <section>
          <h4 style={{ marginBottom: "8px" }}>Chi tiết kết quả phản hồi từ Ngân hàng</h4>
          <ul style={{ paddingLeft: "1.2rem", margin: 0 }}>
            {reviews.map((item, index: number) => {
              const disp = item.disposition ? (POST_PRECHECK_LABELS[item.disposition] ?? humanize(item.disposition)) : "Chưa rõ";
              const srcOutcome = item.source_outcome ? (POST_PRECHECK_LABELS[item.source_outcome] ?? humanize(item.source_outcome)) : "Chưa rõ";
              return (
                <li key={`${item.option_id ?? "option"}-${index}`} style={{ marginBottom: "12px" }}>
                  <strong>{item.api_provider ?? "Ngân hàng"} — {humanize(item.bank_product_id)}</strong>
                  <div style={{ fontSize: "12px", color: "var(--color-ink-600)", marginTop: "4px" }}>
                    <p style={{ margin: "2px 0" }}>Phản hồi từ ngân hàng: <strong>{translateText(srcOutcome)}</strong></p>
                    <p style={{ margin: "2px 0" }}>Trạng thái xử lý nội bộ: <strong>{translateText(disp)}</strong></p>
                    {!!item.reason_codes?.length && (
                      <p style={{ margin: "2px 0", color: "var(--color-red-650)" }}>
                        Mã lý do: {item.reason_codes.map((code: string) => translateText(humanize(code))).join(", ")}
                      </p>
                    )}
                    {!!item.required_follow_up_fields?.length && (
                      <p style={{ margin: "2px 0", color: "var(--color-amber-700)" }}>
                        Trường thông tin cần bổ sung: {item.required_follow_up_fields.map((f: string) => translateText(humanize(f))).join(", ")}
                      </p>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      ) : (
        <p>Không có kết quả precheck nào được ghi nhận.</p>
      )}
    </article>
  );
}

export function ArtifactAssessmentView({
  artifact,
  runArtifacts = [],
}: {
  artifact: ArtifactEnvelope;
  runArtifacts?: readonly ArtifactEnvelope[];
}): ReactElement {
  switch (artifact.artifact_type) {
    case "PLANNER_RESULT":
      return <PlannerAssessmentView payload={artifact.payload as PlannerResultPayload} />;
    case "EVALUATION_CASE":
      return <EvaluationCaseView payload={artifact.payload as unknown as EvaluationCasePayload} />;
    case "FINANCE_FACTS":
      return <FinanceAssessmentView payload={artifact.payload as FinanceArtifactPayload} variant="FACTS" />;
    case "FINANCE_ASSESSMENT":
      return <FinanceAssessmentView payload={artifact.payload as FinanceArtifactPayload} variant="ASSESSMENT" />;
    case "OPERATIONS_FACTS":
      return <OperationsAssessmentView payload={artifact.payload as OperationsArtifactPayload} variant="FACTS" />;
    case "OPERATIONS_ASSESSMENT":
      return <OperationsAssessmentView payload={artifact.payload as OperationsArtifactPayload} variant="ASSESSMENT" />;
    case "INITIAL_RISK_ASSESSMENT":
      return <RiskAssessmentView payload={artifact.payload as RiskArtifactPayload} phase="INITIAL" />;
    case "RISK_PRE_SCAN":
      return <RiskPreScanView payload={artifact.payload as RiskPreScanPayload} runArtifacts={runArtifacts} />;
    case "FINAL_RISK_ASSESSMENT":
      return <RiskAssessmentView payload={artifact.payload as RiskArtifactPayload} phase="FINAL" />;
    case "BANKING_DISCOVERY_REQUEST":
    case "BANKING_OPTION_MATRIX":
    case "BANKING_DISCOVERY_RESULT":
      return (
        <BankingDiscoveryView
          payload={artifact.payload as BankingDiscoveryPayload}
          runArtifacts={runArtifacts}
        />
      );
    case "BANKING_PRECHECK_READINESS":
      return (
        <BankingReadinessView
          payload={artifact.payload as BankingReadinessPayload}
          runArtifacts={runArtifacts}
        />
      );
    case "BANKING_OPTION_ADVICE":
      return <BankingAdviceView payload={artifact.payload as BankingAdvicePayload} />;
    case "BANKING_PRECHECK_RESULT_SET":
      return <BankingAssessmentView payload={artifact.payload as BankingArtifactPayload} />;
    case "DECISION_POST_PRECHECK_REVIEW":
      return <DecisionPostPrecheckReviewView payload={artifact.payload as DecisionPostPrecheckReviewPayload} />;
    case "DOCUMENT_CHECKLIST":
      return <DocumentChecklistView payload={artifact.payload as DocumentChecklistPayload} />;
    case "DOCUMENT_PACKAGE_DRAFT":
      return <DocumentPackageView payload={artifact.payload as DocumentArtifactPayload} variant="DRAFT" />;
    case "DOCUMENT_RELEASE_PACKAGE":
      return <DocumentPackageView payload={artifact.payload as DocumentArtifactPayload} variant="RELEASE" />;
    case "INTERNAL_DECISION_PACKAGE":
      return <InternalDecisionPackageView payload={artifact.payload as InternalDecisionPackagePayload} />;
    default:
      return <p>Chưa có màn hình đánh giá dành cho loại kết quả này.</p>;
  }
}
