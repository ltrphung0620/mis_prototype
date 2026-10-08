import type { ReactElement } from "react";

import { businessValueLabel } from "../../shared/businessLabels";
import { translateText } from "../../shared/translate";

import type {
  ExactArtifactRefPayload,
  ExternalDocumentSubmissionProposalPayload,
  NegotiationOutcomePayload,
  PostDecisionUpdatePayload,
} from "./types";

const LABELS: Record<string, string> = {
  APPROVE: "Phê duyệt",
  REJECT: "Từ chối",
  APPROVED: "Đã phê duyệt",
  REJECTED: "Đã từ chối",
  PENDING: "Đang chờ",
  EXPIRED: "Đã hết hiệu lực",
  SIGNED: "Đã ký",
  PENDING_NEGOTIATION: "Chờ kết quả đàm phán",
  NOT_SIGNED: "Không ký",
  ALL_CONDITIONS_ACCEPTED: "Khách hàng chấp nhận tất cả điều kiện",
  ONE_OR_MORE_CONDITIONS_REJECTED: "Có điều kiện khách hàng không chấp nhận",
  FOUNDER: "Founder",
  CONFIRM_FINAL_CONTRACT_DECISION: "Xác nhận quyết định hợp đồng cuối cùng",
  CONFIRM_NEGOTIATION_OUTCOME: "Xác nhận kết quả đàm phán",
  SEND_DOCUMENT_TO_EXTERNAL_PARTNER: "Gửi tài liệu ra đối tác bên ngoài",
  PERFORMANCE_BOND_DOCUMENT_RELEASE: "Hồ sơ đề nghị bảo lãnh thực hiện",
  SIGNED_CONTRACT: "Hợp đồng đã ký",
  COMPANY_PROFILE: "Hồ sơ doanh nghiệp",
  PERFORMANCE_BOND_REQUEST_FORM: "Đơn đề nghị bảo lãnh thực hiện",
  CASHFLOW_BUFFER_EVIDENCE: "Tài liệu chứng minh nguồn bù dòng tiền",
};

// Unknown codes are shown as-is rather than replaced by a generic phrase.
function label(value?: string | null): string {
  if (!value) return "Chưa xác định";
  return LABELS[value] ?? businessValueLabel(value, value);
}

function formatDateTime(value?: string): string {
  if (!value) return "Chưa xác định";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("vi-VN", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function CardReference({ reference }: { reference?: ExactArtifactRefPayload | null }): ReactElement | null {
  if (!reference?.artifact_id) return null;
  return (
    <p className="assessment-item__meta">
      Căn cứ: Decision Card {reference.version != null ? `v${reference.version}` : ""} ·{" "}
      <span className="artifact-id">{reference.artifact_id}</span>
    </p>
  );
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

export function PostDecisionUpdateView({ payload }: { payload: PostDecisionUpdatePayload }): ReactElement {
  const approval = payload.founder_approval;
  return (
    <article className="assessment-view" aria-label="Cập nhật sau quyết định">
      <header>
        <h3>Cập nhật sau quyết định của Founder</h3>
        <CardReference reference={payload.decision_card_artifact} />
      </header>
      <dl>
        <div>
          <dt>Đề xuất trên Decision Card</dt>
          <dd>{label(payload.recommendation)}</dd>
        </div>
        <div>
          <dt>Kết quả sau quyết định</dt>
          <dd>{label(payload.outcome)}</dd>
        </div>
        <div>
          <dt>Trạng thái hợp đồng</dt>
          <dd>{label(payload.contract_execution_status)}</dd>
        </div>
        {approval && (
          <div>
            <dt>Quyết định của {label(approval.approver_role)}</dt>
            <dd>
              {label(approval.decision)} · {formatDateTime(approval.decided_at)}
            </dd>
          </div>
        )}
      </dl>
      {approval?.decision_reason && (
        <section>
          <h4>Lý do Founder ghi nhận</h4>
          <p>{approval.decision_reason}</p>
        </section>
      )}
      {!!payload.approved_condition_ids?.length && (
        <p>Số điều kiện được phê duyệt: {payload.approved_condition_ids.length}</p>
      )}
      <p role="note" className="assessment-view__footnote">
        {payload.external_action_performed
          ? "Hệ thống ghi nhận đã có hành động bên ngoài."
          : "Đây là bản ghi quyết định nội bộ; hệ thống chưa thực hiện hành động nào ra bên ngoài."}
        {payload.external_document_release_required &&
          " Việc gửi hồ sơ ra ngoài cần đề xuất và phê duyệt riêng."}
      </p>
    </article>
  );
}

export function NegotiationOutcomeView({ payload }: { payload: NegotiationOutcomePayload }): ReactElement {
  const outcomes = payload.condition_outcomes ?? [];
  const tone = payload.outcome_status === "ONE_OR_MORE_CONDITIONS_REJECTED" ? "warning" : "neutral";
  return (
    <article className="assessment-view" aria-label="Kết quả đàm phán">
      <header>
        <div className="assessment-view__title">
          <h3>Kết quả đàm phán</h3>
          {payload.outcome_status && (
            <span className={`status-badge status-badge--${tone}`}>{label(payload.outcome_status)}</span>
          )}
        </div>
        <CardReference reference={payload.decision_card_artifact} />
      </header>
      {outcomes.length ? (
        <section>
          <h4>Phản hồi theo từng điều kiện</h4>
          <ul className="assessment-list">
            {outcomes.map((item, index) => (
              <li key={item.condition_id ?? index}>
                <strong>{item.condition_title ?? item.condition_code ?? `Điều kiện ${index + 1}`}</strong>
                <p>
                  {item.customer_accepted == null
                    ? "Chưa ghi nhận phản hồi"
                    : item.customer_accepted
                      ? "Khách hàng chấp nhận"
                      : "Khách hàng không chấp nhận"}
                </p>
                {item.founder_note && <p className="assessment-item__secondary">Ghi chú: {item.founder_note}</p>}
              </li>
            ))}
          </ul>
        </section>
      ) : (
        <p>Chưa có phản hồi theo điều kiện nào được ghi nhận.</p>
      )}
      {payload.founder_summary && (
        <section>
          <h4>Tóm tắt của Founder</h4>
          <p>{payload.founder_summary}</p>
        </section>
      )}
      <p role="note" className="assessment-view__footnote">
        Kết quả do Founder nhập lại từ trao đổi với khách hàng; hệ thống không tự liên hệ khách hàng.
        {payload.confirmation_requested && " Kết quả này cần Founder xác nhận lần cuối."}
      </p>
    </article>
  );
}

export function ExternalDocumentSubmissionProposalView({
  payload,
}: {
  payload: ExternalDocumentSubmissionProposalPayload;
}): ReactElement {
  return (
    <article className="assessment-view" aria-label="Đề xuất gửi hồ sơ ra ngoài">
      <header>
        <h3>Đề xuất gửi hồ sơ ra ngoài</h3>
        <CardReference reference={payload.decision_card_artifact} />
      </header>
      <dl>
        <div>
          <dt>Người nhận dự kiến</dt>
          <dd>{payload.recipient ?? "Chưa xác định"}</dd>
        </div>
        <div>
          <dt>Mục đích</dt>
          <dd>{label(payload.purpose)}</dd>
        </div>
        <div>
          <dt>Trạng thái hợp đồng</dt>
          <dd>{label(payload.contract_execution_status)}</dd>
        </div>
        <div>
          <dt>Hành động cần phê duyệt</dt>
          <dd>{label(payload.proposed_action)}</dd>
        </div>
      </dl>
      <CodeList title="Tài liệu trong đề xuất" codes={payload.document_codes} />
      <CodeList title="Điều kiện phê duyệt" codes={payload.approval_condition_codes} />
      <CodeList title="Giới hạn còn lại" codes={payload.limitation_codes} />
      <p role="note" className="assessment-view__footnote">
        {payload.external_submission_performed
          ? "Hệ thống ghi nhận hồ sơ đã được gửi ra ngoài."
          : payload.release_authorized
            ? "Đã được phép gửi; prototype không gửi hồ sơ và không tạo biên nhận."
            : "Đây chỉ là đề xuất: chưa được phép gửi. Prototype không gửi hồ sơ và không tạo biên nhận."}
      </p>
    </article>
  );
}
