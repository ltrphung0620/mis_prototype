import type { ReactElement } from "react";

import { businessValueLabel } from "../../shared/businessLabels";

import type {
  BankingDiscoveryPayload,
  BankingAdvicePayload,
  BankingReadinessPayload,
  DocumentChecklistPayload,
  EvaluationCasePayload,
  InternalDecisionPackagePayload,
  PlannerResultPayload,
  PlannerWarningPayload,
  RiskPreScanPayload,
} from "./types";

const LABELS: Record<string, string> = {
  READY: "Sẵn sàng",
  READY_FOR_INITIAL_ASSESSMENT: "Sẵn sàng đánh giá ban đầu",
  WAITING_FOR_INPUT: "Đang chờ bổ sung dữ liệu",
  COMPLETE: "Đầy đủ",
  LIMITED_BY_EVIDENCE: "Giới hạn bởi dữ liệu hiện có",
  FINANCE_ASSESSMENT: "Đánh giá tài chính",
  OPERATIONS_ASSESSMENT: "Đánh giá vận hành",
  INITIAL_RISK_SCAN: "Quét rủi ro ban đầu",
  PERFORMANCE_BOND: "Bảo lãnh thực hiện hợp đồng",
  WORKING_CAPITAL: "Vốn lưu động",
  SIGNED_CONTRACT: "Hợp đồng đã ký",
  COMPANY_PROFILE: "Hồ sơ doanh nghiệp",
  PERFORMANCE_BOND_REQUEST_FORM: "Đơn đề nghị bảo lãnh thực hiện",
  CASHFLOW_BUFFER_EVIDENCE: "Tài liệu chứng minh nguồn bù dòng tiền",
  AVAILABLE: "Có sẵn",
  DRAFTED: "Đã tạo bản nháp",
  MISSING: "Còn thiếu",
  AVAILABLE_WITH_LIMITATIONS: "Có sẵn nhưng còn giới hạn",
  NOT_APPLICABLE: "Không áp dụng",
  REQUIRED: "Bắt buộc",
  POSSIBLE: "Có thể phát sinh",
  VERIFIED: "Đã kiểm tra",
  NOT_AVAILABLE: "Chưa có dữ liệu",
  NOT_EVALUABLE: "Chưa đủ cơ sở đánh giá",
  ADVISORY_ONLY: "Chỉ mang tính tham khảo",
  COMPLETED: "Đã hoàn tất",
  COMPLETED_WITH_WARNINGS: "Đã hoàn tất, có lưu ý",
  HIGH: "Cao",
  MEDIUM: "Trung bình",
  LOW: "Thấp",
  CRITICAL: "Nghiêm trọng",
  NO_CASE_SIGNAL: "Chưa ghi nhận tín hiệu riêng của hợp đồng",
};

function label(value?: string | null): string {
  if (!value) return "Chưa xác định";
  return LABELS[value] ?? businessValueLabel(value);
}

function money(amount?: number | null, currency = "VND"): string {
  if (amount == null) return "Chưa xác định";
  return new Intl.NumberFormat("vi-VN", { style: "currency", currency, maximumFractionDigits: 0 }).format(amount);
}

function ratio(value?: number | null): string | null {
  if (value == null) return null;
  return `${new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 }).format(Math.abs(value) <= 1 ? value * 100 : value)}%`;
}

function EntityList({ title, values = [] }: { title: string; values?: string[] }): ReactElement {
  return <p><strong>{title}:</strong> {values.length ? values.join(", ") : "Không có liên kết rõ ràng"}</p>;
}

function Warnings({ warnings = [] }: { warnings?: PlannerWarningPayload[] }): ReactElement | null {
  if (!warnings.length) return null;
  return <section><h4>Cảnh báo không chặn</h4><ul>{warnings.map((warning, index) => <li key={`${warning.warning_code ?? "warning"}-${index}`}>{warning.reason}</li>)}</ul></section>;
}

function EvaluationCaseSummary({ payload }: { payload: EvaluationCasePayload }): ReactElement {
  return (
    <section aria-label="Hồ sơ đánh giá">
      <p><strong>Hợp đồng:</strong> {payload.contract_id}</p>
      <p><strong>Khách hàng:</strong> {payload.customer_id}</p>
      <EntityList title="Đơn hàng liên kết" values={payload.related_order_ids} />
      <EntityList title="Hóa đơn qua đơn hàng" values={payload.related_invoice_ids} />
      <EntityList title="Dịch vụ liên kết rõ ràng" values={payload.related_service_ids} />
      <EntityList title="Hồ sơ tín dụng liên kết rõ ràng" values={payload.related_credit_case_ids} />
      {!!payload.evaluation_scope?.length && <p><strong>Phạm vi đánh giá:</strong> {payload.evaluation_scope.map(label).join(", ")}</p>}
      {!!payload.contract_requirements?.length && <section><h4>Yêu cầu của hợp đồng</h4><ul>{payload.contract_requirements.map((requirement, index) => (
        <li key={`${requirement.requirement_type}-${index}`}>
          <strong>{label(requirement.requirement_type)}</strong> · {label(requirement.certainty)}
          {requirement.requested_amount != null && <> · {money(requirement.requested_amount, requirement.requested_amount_currency)}</>}
        </li>
      ))}</ul></section>}
      <Warnings warnings={payload.warnings} />
    </section>
  );
}

export function EvaluationCaseView({ payload }: { payload: EvaluationCasePayload }): ReactElement {
  return <article className="assessment-view"><header><h3>Hồ sơ đánh giá do bộ phận Lập kế hoạch chuẩn hóa</h3></header><EvaluationCaseSummary payload={payload} /></article>;
}

export function PlannerAssessmentView({ payload }: { payload: PlannerResultPayload }): ReactElement {
  return (
    <article className="assessment-view" aria-label="Kết quả lập kế hoạch">
      <header><h3>Kết quả tiếp nhận và kiểm tra dữ liệu</h3><strong>{label(payload.data_readiness?.status)}</strong></header>
      {payload.evaluation_case ? <EvaluationCaseSummary payload={payload.evaluation_case} /> : <p>Chưa thể tạo hồ sơ đánh giá chuẩn hóa.</p>}
      {!!payload.data_readiness?.blocking_missing_fields?.length && <section><h4>Dữ liệu còn thiếu làm quy trình tạm dừng</h4><ul>{payload.data_readiness.blocking_missing_fields.map((field) => <li key={field}>{label(field)}</li>)}</ul></section>}
      <Warnings warnings={payload.data_readiness?.non_blocking_warnings ?? payload.warnings} />
      {!!payload.run_plan?.parallel_initial_tasks?.length && <section><h4>Kế hoạch đánh giá ban đầu chạy song song</h4><ul>{payload.run_plan.parallel_initial_tasks.map((task) => <li key={task}>{label(task)}</li>)}</ul></section>}
    </article>
  );
}

export function RiskPreScanView({ payload }: { payload: RiskPreScanPayload }): ReactElement {
  const alerts = payload.case_alerts ?? [];
  return (
    <article className="assessment-view" aria-label="Quét rủi ro ban đầu">
      <header><h3>Quét tín hiệu rủi ro liên quan trực tiếp đến hợp đồng</h3></header>
      {alerts.length ? <ul>{alerts.map((alert, index) => (
        <li key={`${alert.alert_type ?? "alert"}-${index}`}>
          <strong>{label(alert.alert_type)} · {label(alert.severity)}</strong>
          <p>{alert.description}</p>
          {alert.recommended_action && <p>Hướng xử lý được ghi nhận: {alert.recommended_action}</p>}
        </li>
      ))}</ul> : <p>Không có cảnh báo được liên kết rõ ràng với hợp đồng ở bước quét ban đầu.</p>}
      <p>Kết quả này là tín hiệu đầu vào; mức rủi ro chỉ được xác định sau khi có kết quả Tài chính và Vận hành.</p>
    </article>
  );
}

export function BankingDiscoveryView({ payload }: { payload: BankingDiscoveryPayload }): ReactElement {
  const needs = payload.need_types ?? payload.requested_need_types ?? [];
  return (
    <article className="assessment-view" aria-label="Khảo sát phương án ngân hàng">
      <header><h3>Khảo sát phương án ngân hàng</h3><strong>{label(payload.discovery_status ?? payload.status)}</strong></header>
      {!!needs.length && <p><strong>Nhu cầu:</strong> {needs.map(label).join(", ")}</p>}
      {payload.requested_amount != null && <p><strong>Giá trị yêu cầu:</strong> {money(payload.requested_amount, payload.requested_amount_currency)}</p>}
      {!!payload.candidates?.length && <section><h4>Phương án tìm thấy</h4><ul>{payload.candidates.map((candidate, index) => <li key={`${candidate.product_name ?? "candidate"}-${index}`}>
        <strong>{candidate.product_name ?? "Sản phẩm ngân hàng"}</strong> — {candidate.provider ?? "Chưa xác định ngân hàng"}
        {candidate.description && <p>{candidate.description}</p>}
        {candidate.annual_rate_or_fee != null && <p>Phí/lãi suất tham khảo: {ratio(candidate.annual_rate_or_fee)}.</p>}
        {candidate.processing_fee_rate != null && <p>Phí xử lý tham khảo: {ratio(candidate.processing_fee_rate)}.</p>}
        {candidate.collateral_ratio != null && <p>Tỷ lệ tài sản bảo đảm tham khảo: {ratio(candidate.collateral_ratio)}.</p>}
        {candidate.minimum_amount != null && <p>Giá trị tối thiểu: {money(candidate.minimum_amount, candidate.minimum_amount_currency)}.</p>}
      </li>)}</ul></section>}
      {!payload.candidates?.length && (payload.candidate_option_ids?.length ?? 0) > 0 && <p>Đã tìm thấy {payload.candidate_option_ids?.length} phương án; chi tiết nằm trong ma trận phương án ngân hàng.</p>}
      {!!payload.data_gaps?.length && <section><h4>Dữ liệu cần có trước khi kiểm tra sơ bộ với ngân hàng</h4><ul>{payload.data_gaps.map((gap, index) => <li key={`${gap.code ?? "gap"}-${index}`}>{gap.detail}</li>)}</ul></section>}
    </article>
  );
}

export function BankingAdviceView({ payload }: { payload: BankingAdvicePayload }): ReactElement {
  return (
    <article className="assessment-view" aria-label="Diễn giải phương án ngân hàng">
      <header><h3>Diễn giải phương án ngân hàng</h3>{payload.status && <strong>{label(payload.status)}</strong>}</header>
      {payload.overview ? <p>{payload.overview}</p> : <p>Chưa có diễn giải tổng quan.</p>}
      {!!payload.suggestions?.length && <section><h4>Gợi ý tham khảo</h4><ul>{payload.suggestions.map((suggestion, index) => <li key={index}>{suggestion.rationale}</li>)}</ul></section>}
      <p>Nội dung này chỉ hỗ trợ đọc ma trận; không tự chọn phương án và không phải xác nhận của ngân hàng.</p>
    </article>
  );
}

export function BankingReadinessView({ payload }: { payload: BankingReadinessPayload }): ReactElement {
  return (
    <article className="assessment-view" aria-label="Mức sẵn sàng kiểm tra sơ bộ với ngân hàng">
      <header><h3>Mức sẵn sàng kiểm tra sơ bộ với ngân hàng</h3><strong>{label(payload.status)}</strong></header>
      <ul>{(payload.option_readiness ?? []).map((option, index) => <li key={index}><strong>Phương án {index + 1}: {label(option.status)}</strong>{!!option.missing_fields?.length && <p>Còn thiếu: {option.missing_fields.map(label).join(", ")}.</p>}{!!option.unmapped_fields?.length && <p>Chưa có ánh xạ dữ liệu: {option.unmapped_fields.map(label).join(", ")}.</p>}</li>)}</ul>
    </article>
  );
}

export function DocumentChecklistView({ payload }: { payload: DocumentChecklistPayload }): ReactElement {
  return (
    <article className="assessment-view" aria-label="Danh mục hồ sơ">
      <header><h3>Danh mục hồ sơ cần chuẩn bị</h3></header>
      <ul>{(payload.items ?? []).map((item) => <li key={item.document_code}><strong>{label(item.document_code)}: {label(item.status)}</strong><p>{item.reason}</p></li>)}</ul>
      {!!payload.missing_document_codes?.length && <p role="status">Quy trình đang chờ bổ sung: {payload.missing_document_codes.map(label).join(", ")}.</p>}
    </article>
  );
}

export function InternalDecisionPackageView({ payload }: { payload: InternalDecisionPackagePayload }): ReactElement {
  const bankResults = payload.banking_precheck_result_set?.results?.length ?? 0;
  const bankCandidates = payload.banking_option_matrix?.candidates?.length ?? 0;
  return (
    <article className="assessment-view" aria-label="Hồ sơ quyết định nội bộ">
      <header><h3>Hồ sơ quyết định nội bộ</h3><strong>{label(payload.readiness)}</strong></header>
      <p>Luồng tập hợp: {label(payload.assembly_path)}</p>
      <ul>
        <li>Tài chính: {label(payload.finance_assessment?.assessment_status)}</li>
        <li>Vận hành: {label(payload.operations_assessment?.assessment_status)}</li>
        <li>Rủi ro ban đầu: {label(payload.risk_assessment?.assessment_status)}{(payload.risk_assessment?.overall_risk_level ?? payload.risk_assessment?.risk_level) && ` · ${label(payload.risk_assessment?.overall_risk_level ?? payload.risk_assessment?.risk_level)}`}</li>
        {payload.banking_option_matrix && <li>Ngân hàng: {bankCandidates} phương án · {label(payload.banking_precheck_readiness?.status)}</li>}
        {payload.banking_precheck_result_set && <li>Kiểm tra sơ bộ với ngân hàng: {bankResults} kết quả mô phỏng, không ràng buộc; chưa phải phê duyệt của ngân hàng.</li>}
        {payload.document_release_package && <li>Hồ sơ nội bộ cho {payload.document_release_package.recipient ?? "đối tác dự kiến"}; chưa được phép và chưa gửi ra ngoài.</li>}
      </ul>
      <p>Gói này chỉ tổng hợp dữ liệu đã kiểm định để bước Quyết định sử dụng; bản thân nó không đưa ra đề xuất hay phê duyệt.</p>
    </article>
  );
}
