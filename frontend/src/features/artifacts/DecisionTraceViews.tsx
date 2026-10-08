import type { ReactElement } from "react";

import { businessValueLabel } from "../../shared/businessLabels";
import { translateText } from "../../shared/translate";
import type { StatusTone } from "../../shared/workflowLabels";

import type {
  AIDecisionAnalysisPayload,
  ApprovalCheckpointSetPayload,
  ApprovalConditionPayload,
  DecisionPostBankingReviewPayload,
  DecisionRoutePlanPayload,
  DocumentPreparationRequestPayload,
  ExactArtifactRefPayload,
  RiskRuleEvaluationSetPayload,
} from "./types";

const LABELS: Record<string, string> = {
  // Governance
  REGISTERED: "Đã đăng ký",
  FOUNDER: "Founder",
  SEND_DOCUMENT_TO_EXTERNAL_PARTNER: "Gửi tài liệu ra đối tác bên ngoài",
  COMMIT_LARGE_FINANCIAL_DECISION: "Cam kết quyết định tài chính lớn",
  SUBMIT_BANKING_PRECHECK: "Chạy precheck với ngân hàng",
  CONFIRM_FINAL_CONTRACT_DECISION: "Xác nhận quyết định hợp đồng cuối cùng",
  CONFIRM_NEGOTIATION_OUTCOME: "Xác nhận kết quả đàm phán",
  DOCUMENT_EXTERNAL_RELEASE_REQUESTED: "Khi có đề xuất gửi tài liệu ra ngoài",
  LARGE_FINANCIAL_DECISION_REQUESTED: "Khi có đề xuất quyết định tài chính lớn",
  // Risk rules
  TRIGGERED: "Kích hoạt",
  NOT_TRIGGERED: "Không kích hoạt",
  NOT_APPLICABLE: "Không áp dụng",
  CASE_SPECIFIC: "Riêng hợp đồng",
  OPC_GLOBAL: "Toàn OPC",
  EVENT_SPECIFIC: "Theo sự kiện",
  CRITICAL: "Nghiêm trọng",
  // Route plan
  DIRECT_INTERNAL_DECISION: "Quyết định nội bộ trực tiếp",
  BANKING_DISCOVERY_REQUIRED: "Cần khảo sát phương án ngân hàng",
  INTERNAL_DECISION_PACKAGE: "Tổng hợp hồ sơ quyết định nội bộ",
  BANKING_INTERNAL_DISCOVERY: "Khảo sát phương án ngân hàng",
  PERFORMANCE_BOND: "Bảo lãnh thực hiện hợp đồng",
  PERFORMANCE_BOND_REQUIREMENT: "Hợp đồng yêu cầu bảo lãnh thực hiện",
  REQUIRED: "Bắt buộc",
  POSSIBLE: "Có thể phát sinh",
  // Post-banking review
  BANKING_PRECHECK_READY: "Có phương án đủ dữ liệu để chạy precheck",
  BANKING_INPUT_REQUIRED: "Cần bổ sung dữ liệu trước khi chạy precheck",
  NO_PRECHECK_PATH: "Không có tuyến precheck phù hợp",
  UNSUPPORTED_PRECHECK_MAPPING: "Chưa hỗ trợ ánh xạ dữ liệu precheck",
  NO_VIABLE_OPTION: "Không có phương án khả thi",
  requested_amount: "Số tiền yêu cầu",
  // Document preparation
  SIMULATED_NON_BINDING: "Mô phỏng, không ràng buộc",
  SIGNED_CONTRACT: "Hợp đồng đã ký",
  COMPANY_PROFILE: "Hồ sơ doanh nghiệp",
  PERFORMANCE_BOND_REQUEST_FORM: "Đơn đề nghị bảo lãnh thực hiện",
  CASHFLOW_BUFFER_EVIDENCE: "Tài liệu chứng minh nguồn bù dòng tiền",
  // AI analysis
  OPENAI: "OpenAI",
  DETERMINISTIC_FALLBACK: "Dự phòng xác định (không gọi được AI)",
};

const OPERATORS: Record<string, string> = { GTE: "≥", LTE: "≤", GT: ">", LT: "<", EQ: "=" };

// Unknown codes are shown as-is rather than replaced by a generic phrase.
function label(value?: string | null): string {
  if (!value) return "Chưa xác định";
  return LABELS[value] ?? businessValueLabel(value, value);
}

function money(amount?: number | null, currency = "VND"): string {
  if (amount == null) return "Chưa xác định";
  return new Intl.NumberFormat("vi-VN", { style: "currency", currency, maximumFractionDigits: 0 }).format(amount);
}

function value(raw?: string | number | boolean | null): string {
  if (raw === null || raw === undefined || raw === "") return "Không có dữ liệu";
  if (typeof raw === "boolean") return raw ? "Có" : "Không";
  if (typeof raw === "number") return new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 4 }).format(raw);
  return raw;
}

function condition(item?: ApprovalConditionPayload | null): string | null {
  if (!item?.source_field) return null;
  const operator = item.operator ? (OPERATORS[item.operator] ?? item.operator) : "?";
  return `${item.source_field} ${operator} ${value(item.threshold)}`;
}

function CodeList({ title, codes }: { title: string; codes?: string[] }): ReactElement | null {
  if (!codes?.length) return null;
  return (
    <section>
      <h4>{title}</h4>
      <ul className="assessment-list">
        {codes.map((code) => (
          <li key={code}>{translateText(label(code))}</li>
        ))}
      </ul>
    </section>
  );
}

function ArtifactRef({ title, reference }: { title: string; reference?: ExactArtifactRefPayload | null }): ReactElement | null {
  if (!reference?.artifact_id) return null;
  return (
    <p className="assessment-item__meta">
      {title}: {reference.version != null ? `v${reference.version} · ` : ""}
      <span className="artifact-id">{reference.artifact_id}</span>
    </p>
  );
}

export function ApprovalCheckpointsView({ payload }: { payload: ApprovalCheckpointSetPayload }): ReactElement {
  const checkpoints = payload.checkpoints ?? [];
  const coverages = payload.policy_coverages ?? [];
  return (
    <article className="assessment-view" aria-label="Điểm phê duyệt đã đăng ký">
      <header>
        <h3>Điểm phê duyệt đã đăng ký</h3>
      </header>
      {checkpoints.length ? (
        <section>
          <h4>Các điểm phê duyệt trong tương lai</h4>
          <ul className="assessment-list">
            {checkpoints.map((item, index) => (
              <li key={item.checkpoint_id ?? index}>
                <strong>{translateText(label(item.protected_action))}</strong>
                <p>
                  {translateText(label(item.trigger_event))} · người duyệt: {label(item.approver_role)} ·{" "}
                  {label(item.status)}
                </p>
                {condition(item.condition) && (
                  <p className="assessment-item__secondary">Điều kiện kích hoạt: {condition(item.condition)}</p>
                )}
                {item.source_rule_id && (
                  <p className="assessment-item__meta">Quy tắc nguồn: {item.source_rule_id}</p>
                )}
              </li>
            ))}
          </ul>
        </section>
      ) : (
        <p>Chưa có điểm phê duyệt nào được đăng ký từ quy tắc rủi ro.</p>
      )}
      {!!coverages.length && (
        <section className="assessment-view__divided">
          <h4>Phạm vi chính sách đã đối chiếu</h4>
          <ul className="assessment-list">
            {coverages.map((item, index) => (
              <li key={item.coverage_id ?? index}>
                <strong>{translateText(label(item.protected_action))}</strong>
                <p>
                  {item.requires_human_approval
                    ? `Cần ${label(item.approver_role)} phê duyệt`
                    : "Chính sách không yêu cầu phê duyệt thủ công"}
                </p>
                {!!item.source_policy_ids?.length && (
                  <p className="assessment-item__meta">Chính sách nguồn: {item.source_policy_ids.join(", ")}</p>
                )}
                {item.subject_artifact_id && (
                  <p className="assessment-item__meta">
                    Đối tượng: <span className="artifact-id">{item.subject_artifact_id}</span>
                  </p>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
      <p role="note" className="assessment-view__footnote">
        Đăng ký điểm phê duyệt không tự dừng quy trình và không phải yêu cầu phê duyệt. Yêu cầu chỉ được tạo khi
        hành động được bảo vệ thực sự được đề xuất.
      </p>
    </article>
  );
}

function ruleTone(status?: string, severity?: string | null): StatusTone {
  if (status === "NOT_EVALUABLE") return "warning";
  if (status !== "TRIGGERED") return "neutral";
  return severity === "HIGH" || severity === "CRITICAL" ? "danger" : "warning";
}

export function RiskRuleEvaluationView({ payload }: { payload: RiskRuleEvaluationSetPayload }): ReactElement {
  const evaluations = payload.evaluations ?? [];
  const counts = evaluations.reduce<Record<string, number>>((result, item) => {
    const key = item.status ?? "UNKNOWN";
    result[key] = (result[key] ?? 0) + 1;
    return result;
  }, {});
  return (
    <article className="assessment-view" aria-label="Đối chiếu quy tắc rủi ro">
      <header>
        <h3>Đối chiếu từng quy tắc rủi ro</h3>
        {!!evaluations.length && (
          <div className="assessment-view__meta">
            {Object.entries(counts).map(([status, count]) => (
              <span key={status}>
                {label(status)}: {count}
              </span>
            ))}
          </div>
        )}
      </header>
      {evaluations.length ? (
        <div className="table-scroll">
          <table className="evidence-table evidence-table--detail">
            <thead>
              <tr>
                <th>Quy tắc</th>
                <th>Kết quả</th>
                <th>Giá trị thực tế / ngưỡng</th>
                <th>Giải thích</th>
              </tr>
            </thead>
            <tbody>
              {evaluations.map((item, index) => (
                <tr key={item.evaluation_id ?? index}>
                  <td>
                    <strong>{item.rule_id ?? "Chưa xác định"}</strong>
                    <small>
                      {translateText(label(item.risk_type))} · {label(item.applicability_scope)}
                    </small>
                  </td>
                  <td>
                    <span className={`status-badge status-badge--${ruleTone(item.status, item.severity)}`}>
                      {label(item.status)}
                      {item.status === "TRIGGERED" && item.severity ? ` · ${label(item.severity)}` : ""}
                    </span>
                  </td>
                  <td>
                    {item.source_field ? (
                      <>
                        {value(item.actual_value)}{" "}
                        <small>
                          {item.source_field} {item.operator ? (OPERATORS[item.operator] ?? item.operator) : ""}{" "}
                          {value(item.threshold)}
                        </small>
                      </>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>
                    {item.declared_condition && <strong>{translateText(item.declared_condition)}</strong>}
                    {item.explanation && <small>{translateText(item.explanation)}</small>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p>Chưa có quy tắc rủi ro nào được đối chiếu.</p>
      )}
      <p role="note" className="assessment-view__footnote">
        &quot;Chưa đủ cơ sở đánh giá&quot; nghĩa là thiếu dữ liệu để đối chiếu, không có nghĩa quy tắc không bị vi phạm.
      </p>
    </article>
  );
}

export function DecisionRoutePlanView({ payload }: { payload: DecisionRoutePlanPayload }): ReactElement {
  const reasons = payload.routing_reasons ?? [];
  return (
    <article className="assessment-view" aria-label="Tuyến xử lý quyết định">
      <header>
        <div className="assessment-view__title">
          <h3>Tuyến xử lý quyết định</h3>
          <span className="status-badge status-badge--neutral">{translateText(label(payload.route_outcome))}</span>
        </div>
      </header>
      <CodeList title="Năng lực cần dùng tiếp theo" codes={payload.required_capabilities} />
      <CodeList title="Nhu cầu ngân hàng" codes={payload.banking_need_types} />
      {!!reasons.length && (
        <section>
          <h4>Căn cứ chọn tuyến</h4>
          <ul className="assessment-list">
            {reasons.map((item, index) => (
              <li key={item.reason_id ?? index}>
                <strong>{translateText(label(item.code))}</strong>
                <p>
                  {label(item.requirement_certainty)} · số tiền yêu cầu{" "}
                  {money(item.requested_amount, item.requested_amount_currency ?? "VND")}
                </p>
                {item.requirement_id && (
                  <p className="assessment-item__meta">Yêu cầu hợp đồng: {item.requirement_id}</p>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
      {!!payload.conditional_approval_checkpoint_ids?.length && (
        <p className="assessment-item__meta">
          Điểm phê duyệt có điều kiện liên quan: {payload.conditional_approval_checkpoint_ids.length}
        </p>
      )}
      <p role="note" className="assessment-view__footnote">
        Đây là phân loại nghiệp vụ; bước tiếp theo do quy trình quyết định. Chưa có yêu cầu nào gửi tới ngân hàng.
      </p>
    </article>
  );
}

function postBankingTone(outcome?: string): StatusTone {
  return !outcome || outcome === "BANKING_PRECHECK_READY" ? "neutral" : "warning";
}

export function DecisionPostBankingReviewView({ payload }: { payload: DecisionPostBankingReviewPayload }): ReactElement {
  const requests = payload.missing_data_requests ?? [];
  return (
    <article className="assessment-view" aria-label="Rà soát sau khảo sát ngân hàng">
      <header>
        <div className="assessment-view__title">
          <h3>Rà soát sau khảo sát ngân hàng</h3>
          <span className={`status-badge status-badge--${postBankingTone(payload.outcome)}`}>
            {translateText(label(payload.outcome))}
          </span>
        </div>
      </header>
      <dl>
        <div>
          <dt>Phương án ứng viên</dt>
          <dd>{payload.candidate_option_ids?.length ?? 0}</dd>
        </div>
        <div>
          <dt>Đủ dữ liệu để chạy precheck</dt>
          <dd>{payload.precheck_ready_option_ids?.length ?? 0}</dd>
        </div>
        <div>
          <dt>Còn chờ dữ liệu</dt>
          <dd>{payload.pending_option_ids?.length ?? 0}</dd>
        </div>
      </dl>
      <CodeList title="Trường dữ liệu cần bổ sung" codes={payload.required_input_fields} />
      {!!requests.length && (
        <section>
          <h4>Yêu cầu bổ sung dữ liệu</h4>
          <ul className="assessment-list">
            {requests.map((item, index) => (
              <li key={item.request_id ?? index}>
                <strong>{translateText(label(item.field))}</strong>
                {item.reason && <p>{translateText(item.reason)}</p>}
              </li>
            ))}
          </ul>
        </section>
      )}
      <p role="note" className="assessment-view__footnote">
        {payload.precheck_executed
          ? "Hệ thống ghi nhận precheck đã chạy."
          : "Chưa chạy precheck. Rà soát này không chọn phương án ngân hàng nào."}
      </p>
    </article>
  );
}

export function DocumentPreparationRequestView({ payload }: { payload: DocumentPreparationRequestPayload }): ReactElement {
  const currency = payload.currency ?? "VND";
  return (
    <article className="assessment-view" aria-label="Yêu cầu chuẩn bị hồ sơ">
      <header>
        <div className="assessment-view__title">
          <h3>Yêu cầu chuẩn bị hồ sơ</h3>
          <span className="status-badge status-badge--neutral">
            {payload.documents_prepared ? "Đã chuẩn bị hồ sơ" : "Chưa chuẩn bị hồ sơ"}
          </span>
        </div>
      </header>
      <dl>
        <div>
          <dt>Ngân hàng / sản phẩm</dt>
          <dd>
            {payload.provider ?? "Chưa xác định"} · {translateText(label(payload.bank_product_id))}
          </dd>
        </div>
        <div>
          <dt>Số tiền yêu cầu</dt>
          <dd>{money(payload.requested_amount, currency)}</dd>
        </div>
        <div>
          <dt>Số tiền được hỗ trợ (kết quả precheck)</dt>
          <dd>{money(payload.supported_amount, currency)}</dd>
        </div>
        <div>
          <dt>Tính chất kết quả</dt>
          <dd>{translateText(label(payload.provider_result_authority))}</dd>
        </div>
      </dl>
      <CodeList title="Tài liệu cần chuẩn bị" codes={payload.required_document_codes} />
      <CodeList title="Điều kiện từ kết quả precheck" codes={payload.approval_condition_codes} />
      <p role="note" className="assessment-view__footnote">
        Kết quả precheck là mô phỏng, không ràng buộc và chưa phải phê duyệt của ngân hàng. Yêu cầu này không chọn
        phương án và không gửi hồ sơ ra ngoài.
        {payload.external_release_performed && " Hệ thống ghi nhận đã có hành động gửi ra ngoài."}
      </p>
    </article>
  );
}

export function AIDecisionAnalysisView({ payload }: { payload: AIDecisionAnalysisPayload }): ReactElement {
  const fromOpenAI = payload.source === "OPENAI";
  const reasons = payload.reasons ?? [];
  const conditions = payload.conditions ?? [];
  const attention = payload.human_attention_points ?? [];
  return (
    <article className="assessment-view" aria-label="Phân tích quyết định">
      <header>
        <div className="assessment-view__title">
          <h3>Phân tích quyết định</h3>
          <span className={`status-badge status-badge--${fromOpenAI ? "neutral" : "warning"}`}>
            Nguồn: {label(payload.source)}
          </span>
        </div>
        <div className="assessment-view__meta">
          {payload.model && <span>Model: {payload.model}</span>}
          {payload.prompt_version && <span>· Prompt: {payload.prompt_version}</span>}
        </div>
      </header>
      {payload.fallback_reason && (
        <p className="assessment-item__meta assessment-item__meta--warning">
          Lý do dùng dự phòng: {translateText(payload.fallback_reason)}
        </p>
      )}
      <dl>
        <div>
          <dt>Đề xuất của bước phân tích</dt>
          <dd>{label(payload.recommendation)}</dd>
        </div>
        <div>
          <dt>Độ tin cậy</dt>
          <dd>{label(payload.confidence)}</dd>
        </div>
      </dl>
      {payload.executive_summary && <p>{translateText(payload.executive_summary)}</p>}
      {!!reasons.length && (
        <section>
          <h4>Lý do</h4>
          <ul className="assessment-list">
            {reasons.map((item, index) => (
              <li key={item.reason_id ?? index}>
                <strong>{translateText(item.title ?? label(item.code))}</strong>
                {item.detail && <p>{translateText(item.detail)}</p>}
              </li>
            ))}
          </ul>
        </section>
      )}
      {!!conditions.length && (
        <section>
          <h4>Điều kiện đề xuất</h4>
          <ul className="assessment-list">
            {conditions.map((item, index) => (
              <li key={item.condition_id ?? index}>{translateText(item.title ?? label(item.code))}</li>
            ))}
          </ul>
        </section>
      )}
      {!!attention.length && (
        <section>
          <h4>Điểm Founder cần lưu ý</h4>
          <ul className="assessment-list">
            {attention.map((item, index) => (
              <li key={item.attention_point_id ?? index}>{translateText(item.text ?? label(item.code))}</li>
            ))}
          </ul>
        </section>
      )}
      <section className="assessment-view__divided">
        <h4>Đầu vào được phân tích</h4>
        <ArtifactRef title="Hồ sơ quyết định nội bộ" reference={payload.internal_decision_package_artifact} />
        <ArtifactRef title="Kiểm tra rủi ro cuối" reference={payload.final_risk_artifact} />
      </section>
      <p role="note" className="assessment-view__footnote">
        Đây là đề xuất đã qua kiểm tra xác định, chưa phải quyết định của Founder; Decision Card hiện hành nằm ở view
        Quyết định. Model không tự tính số liệu, không tạo yêu cầu phê duyệt và không thực hiện hành động bên ngoài.
        {payload.external_action_performed && " Hệ thống ghi nhận đã có hành động bên ngoài."}
      </p>
    </article>
  );
}
