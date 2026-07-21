import type { ReactElement } from "react";

import { businessValueLabel } from "../../shared/businessLabels";
import { translateText } from "../../shared/translate";

import type {
  ApprovalCheckpointPayload,
  ArtifactEnvelope,
  BankingOption,
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
  FINANCE: "Đánh giá tài chính",
  OPERATIONS: "Đánh giá vận hành",
  RISK: "Quét rủi ro ban đầu",
  SEND_DOCUMENT_TO_EXTERNAL_PARTNER: "Gửi tài liệu ra đối tác bên ngoài",
  COMMIT_LARGE_FINANCIAL_DECISION: "Cam kết quyết định tài chính lớn",
  SUBMIT_BANKING_PRECHECK: "Chạy precheck với ngân hàng",
  // TeamPack sheet names (source_record_counts)
  "06_Risk_Rules": "Quy tắc rủi ro (Sheet 06)",
  "07_Alerts": "Cảnh báo rủi ro (Sheet 07)",
  "08_Bank_Transactions": "Giao dịch ngân hàng (Sheet 08)",
  "09_Data_Classification": "Phân loại dữ liệu (Sheet 09)",
  // Risk types
  MARGIN_RISK: "Rủi ro biên lợi nhuận",
  EXECUTION_RISK: "Rủi ro triển khai",
  CASHFLOW_RISK: "Rủi ro dòng tiền",
  CREDIT_RISK: "Rủi ro tín dụng",
  DELIVERY_RISK: "Rủi ro giao hàng",
  COMPLIANCE_RISK: "Rủi ro tuân thủ",
  // Alert types
  CONTRACT_ALERT: "Cảnh báo hợp đồng",
  CUSTOMER_ALERT: "Cảnh báo khách hàng",
  FINANCIAL_ALERT: "Cảnh báo tài chính",
  OPERATIONAL_ALERT: "Cảnh báo vận hành",
  // Trigger events
  DOCUMENT_EXTERNAL_RELEASE_REQUESTED: "Yêu cầu phát hành tài liệu ra ngoài",
  LARGE_FINANCIAL_DECISION_REQUESTED: "Yêu cầu cam kết tài chính lớn",
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
  return (
    <section>
      <h4>Cảnh báo</h4>
      <ul>
        {warnings.map((warning, index) => (
          <li key={`${warning.warning_code ?? "warning"}-${index}`}>{translateText(warning.reason)}</li>
        ))}
      </ul>
    </section>
  );
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
    </section>
  );
}

export function EvaluationCaseView({ payload }: { payload: EvaluationCasePayload }): ReactElement {
  return (
    <article className="assessment-view">
      <header><h3>Hồ sơ đánh giá do bộ phận Lập kế hoạch chuẩn hóa</h3></header>
      <EvaluationCaseSummary payload={payload} />
      <Warnings warnings={payload.warnings} />
    </article>
  );
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

export function RiskPreScanView({
  payload,
  runArtifacts = [],
}: {
  payload: RiskPreScanPayload;
  runArtifacts?: readonly ArtifactEnvelope[];
}): ReactElement {
  const caseAlerts = payload.case_alerts ?? [];
  const globalAlerts = payload.global_alerts ?? [];
  const rules = payload.source_rules ?? [];
  const recordCounts = payload.source_record_counts ?? {};
  const recordCountEntries = Object.entries(recordCounts);

  const checkpointArtifact = runArtifacts.find(
    (item) => item.artifact_type === "APPROVAL_CHECKPOINTS" && item.version === 1,
  ) ?? runArtifacts.find((item) => item.artifact_type === "APPROVAL_CHECKPOINTS");
  const checkpoints = (
    checkpointArtifact?.payload as ApprovalCheckpointPayload | undefined
  )?.checkpoints ?? [];

  return (
    <article className="assessment-view" aria-label="Quét rủi ro ban đầu">
      <header><h3>Quét tín hiệu rủi ro sơ bộ</h3></header>

      {/* Mục 1: Dữ liệu nguồn & Quy tắc rủi ro đã quét */}
      <section>
        <h4>1. Dữ liệu nguồn & Quy tắc rủi ro đã quét (Sheet 06)</h4>
        {!!recordCountEntries.length && (
          <p style={{ margin: "0 0 10px 0" }}>
            <strong>Dữ liệu nguồn đã quét:</strong>{" "}
            {recordCountEntries
              .map(([sheet, count]) => `${translateText(label(sheet))}: ${count} dòng`)
              .join(" · ")}
          </p>
        )}
        {rules.length ? (
          <ul>
            {rules.map((rule) => (
              <li key={rule.rule_id} style={{ marginBottom: "8px" }}>
                <strong>{rule.rule_id} · {translateText(label(rule.risk_type))} · {translateText(label(rule.severity))}</strong>
                <p style={{ margin: "2px 0" }}>{translateText(rule.declared_condition)}</p>
                <p style={{ margin: "0", fontSize: "12px", color: "var(--color-ink-600)" }}>
                  Hành động yêu cầu: {translateText(rule.required_action)}
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <p>Không tìm thấy quy tắc rủi ro nào được nạp từ nguồn.</p>
        )}
      </section>

      {/* Mục 2: Cảnh báo rủi ro được phát hiện */}
      <section>
        <h4>2. Cảnh báo rủi ro phát hiện (Sheet 07)</h4>
        {caseAlerts.length ? (
          <div>
            <h5 style={{ margin: "5px 0" }}>Cảnh báo riêng của Hợp đồng:</h5>
            <ul>
              {caseAlerts.map((alert, index) => (
                <li key={`case-alert-${index}`} style={{ marginBottom: "6px" }}>
                  <strong>{translateText(label(alert.alert_type))} · {translateText(label(alert.severity))}</strong>
                  <p style={{ margin: "2px 0" }}>{translateText(alert.description)}</p>
                  {alert.recommended_action && (
                    <p style={{ margin: "0", fontSize: "12px", color: "var(--color-ink-600)" }}>
                      Hướng xử lý: {translateText(alert.recommended_action)}
                    </p>
                  )}
                  {!!alert.related_entity_ids?.length && (
                    <p style={{ margin: "0", fontSize: "11px", color: "var(--color-ink-450)" }}>
                      Thực thể liên quan: {alert.related_entity_ids.join(", ")}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {globalAlerts.length ? (
          <div style={{ marginTop: "10px" }}>
            <h5 style={{ margin: "5px 0" }}>Cảnh báo rủi ro toàn OPC:</h5>
            <ul>
              {globalAlerts.map((alert, index) => (
                <li key={`global-alert-${index}`} style={{ marginBottom: "6px" }}>
                  <strong>{translateText(label(alert.alert_type))} · {translateText(label(alert.severity))}</strong>
                  <p style={{ margin: "2px 0" }}>{translateText(alert.description)}</p>
                  {alert.recommended_action && (
                    <p style={{ margin: "0", fontSize: "12px", color: "var(--color-ink-600)" }}>
                      Hướng xử lý: {translateText(alert.recommended_action)}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {!caseAlerts.length && !globalAlerts.length && (
          <p>Không ghi nhận cảnh báo rủi ro nào trực tiếp hoặc gián tiếp ở bước này.</p>
        )}
      </section>

      {/* Mục 3: Cổng kiểm soát phê duyệt cần thiết */}
      <section>
        <h4>3. Các điểm phê duyệt được đăng ký (Approval signals)</h4>
        {checkpoints.length ? (
          <ul>
            {checkpoints.map((checkpoint, index) => (
              <li key={`${checkpoint.source_rule_id ?? "approval"}-${index}`}>
                <strong>{checkpoint.source_rule_id ?? "Quy tắc kiểm soát"}</strong>: Founder cần phê duyệt trước khi{" "}
                {translateText(label(checkpoint.protected_action)).toLowerCase()}
                {checkpoint.source_rule_id === "RR-005" ? " (lớn hơn 300 triệu)" : ""}.
              </li>
            ))}
          </ul>
        ) : (
          <p>Không có điểm phê duyệt nào được kích hoạt ở bước quét sơ bộ này.</p>
        )}
      </section>

      <p style={{ marginTop: "15px", fontStyle: "italic", fontSize: "12px", color: "var(--color-ink-600)" }}>
        Kết quả này mới là tín hiệu đầu vào; mức rủi ro được kết luận sau khi có kết quả Tài chính và Vận hành.
      </p>
    </article>
  );
}

export function BankingDiscoveryView({
  payload,
  runArtifacts = [],
}: {
  payload: BankingDiscoveryPayload;
  runArtifacts?: readonly ArtifactEnvelope[];
}): ReactElement {
  const needs = payload.need_types ?? payload.requested_need_types ?? [];
  let displayCandidates = payload.candidates ?? [];
  if (!displayCandidates.length && payload.candidate_option_ids?.length && runArtifacts.length) {
    const matrixArtifact = runArtifacts.find(
      (art) => art.artifact_type === "BANKING_OPTION_MATRIX"
    );
    if (matrixArtifact?.payload) {
      const matrixPayload = matrixArtifact.payload as { candidates?: BankingOption[] };
      if (matrixPayload.candidates) {
        displayCandidates = matrixPayload.candidates.filter(
          (cand) => cand.option_id && payload.candidate_option_ids?.includes(cand.option_id)
        );
      }
    }
  }

  return (
    <article className="assessment-view" aria-label="Khảo sát phương án ngân hàng">
      <header><h3>Khảo sát phương án ngân hàng</h3><strong>{label(payload.discovery_status ?? payload.status)}</strong></header>
      {!!needs.length && <p><strong>Nhu cầu:</strong> {needs.map(label).join(", ")}</p>}
      {payload.requested_amount != null && <p><strong>Giá trị yêu cầu:</strong> {money(payload.requested_amount, payload.requested_amount_currency)}</p>}
      {!!displayCandidates.length && <section><h4>Phương án tìm thấy</h4><ul>{displayCandidates.map((candidate, index) => <li key={`${candidate.product_name ?? "candidate"}-${index}`}>
        <strong>{candidate.product_name ?? "Sản phẩm ngân hàng"}</strong> — {candidate.provider ?? "Chưa xác định ngân hàng"}
        {candidate.description && <p>{candidate.description}</p>}
        {candidate.annual_rate_or_fee != null && <p>Phí/lãi suất tham khảo: {ratio(candidate.annual_rate_or_fee)}.</p>}
        {candidate.processing_fee_rate != null && <p>Phí xử lý tham khảo: {ratio(candidate.processing_fee_rate)}.</p>}
        {candidate.collateral_ratio != null && <p>Tỷ lệ tài sản bảo đảm tham khảo: {ratio(candidate.collateral_ratio)}.</p>}
        {candidate.minimum_amount != null && <p>Giá trị tối thiểu: {money(candidate.minimum_amount, candidate.minimum_amount_currency)}.</p>}
      </li>)}</ul></section>}
      {!displayCandidates.length && (payload.candidate_option_ids?.length ?? 0) > 0 && <p>Đã tìm thấy {payload.candidate_option_ids?.length} phương án; chi tiết nằm trong ma trận phương án ngân hàng.</p>}
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

export function BankingReadinessView({
  payload,
  runArtifacts = [],
}: {
  payload: BankingReadinessPayload;
  runArtifacts?: readonly ArtifactEnvelope[];
}): ReactElement {
  const matrixArtifact = runArtifacts.find(
    (art) => art.artifact_type === "BANKING_OPTION_MATRIX"
  );
  const matrixCandidates = (matrixArtifact?.payload as { candidates?: BankingOption[] } | undefined)?.candidates ?? [];

  return (
    <article className="assessment-view" aria-label="Mức sẵn sàng kiểm tra sơ bộ với ngân hàng">
      <header><h3>Mức sẵn sàng kiểm tra sơ bộ với ngân hàng</h3><strong>{label(payload.status)}</strong></header>
      <ul>{(payload.option_readiness ?? []).map((option, index) => {
        const candidate = matrixCandidates.find((cand) => cand.option_id === option.option_id);
        const name = candidate
          ? `Phương án: ${candidate.product_name ?? "Sản phẩm"} — ${candidate.provider ?? "Ngân hàng"}`
          : `Phương án ${index + 1}`;

        return (
          <li key={index}>
            <strong>{name}: {label(option.status)}</strong>
            {!!option.missing_fields?.length && <p>Còn thiếu: {option.missing_fields.map(label).join(", ")}.</p>}
            {!!option.unmapped_fields?.length && <p>Chưa có ánh xạ dữ liệu: {option.unmapped_fields.map(label).join(", ")}.</p>}
          </li>
        );
      })}</ul>
    </article>
  );
}

export function DocumentChecklistView({ payload }: { payload: DocumentChecklistPayload }): ReactElement {
  const guidance: Record<string, string> = {
    SIGNED_CONTRACT: "Hệ thống tạo bản nháp từ dữ liệu TeamPack và chỉ hoàn tất sau khi Founder chấp nhận hợp đồng.",
    COMPANY_PROFILE: "Hệ thống lấy từ hồ sơ OPC trong TeamPack và áp dụng masking trước khi phát hành.",
    PERFORMANCE_BOND_REQUEST_FORM: "Founder cần tải lên tệp PDF hoặc DOCX của đơn đề nghị bảo lãnh thực hiện.",
    CASHFLOW_BUFFER_EVIDENCE: "Founder cần tải lên tệp PDF hoặc DOCX chứng minh nguồn bù dòng tiền.",
  };
  return (
    <article className="assessment-view" aria-label="Danh mục hồ sơ">
      <header><h3>Danh mục hồ sơ cần chuẩn bị</h3></header>
      <ul>{(payload.items ?? []).map((item) => {
        return (
          <li key={item.document_code}>
            <strong>
              {item.document_code === "SIGNED_CONTRACT" && item.status === "DRAFTED"
                ? "Tạo bản nháp hợp đồng"
                : `${label(item.document_code)}: ${label(item.status)}`}
            </strong>
            <p>{guidance[item.document_code] ?? "Hồ sơ được xử lý theo yêu cầu đã kiểm định."}</p>
          </li>
        );
      })}</ul>
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
