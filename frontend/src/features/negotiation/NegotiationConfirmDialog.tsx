import type { ReactElement } from "react";

import type { ApiApprovalRequest, ApiArtifactEnvelope, JsonRecord } from "../../api/types";

interface Props {
  open: boolean;
  request: ApiApprovalRequest | null;
  artifact: ApiArtifactEnvelope | null;
  submitting?: boolean;
  onClose: () => void;
  onDecision: (requestId: string, decision: "APPROVE" | "REJECT") => void | Promise<void>;
}

function record(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonRecord)
    : {};
}

export function NegotiationConfirmDialog({ open, request, artifact, submitting = false, onClose, onDecision }: Props): ReactElement | null {
  if (!open) return null;
  const payload = record(artifact?.payload);
  const outcomes = Array.isArray(payload.condition_outcomes)
    ? payload.condition_outcomes.map(record)
    : [];
  const rejected = outcomes.filter((item) => item.customer_accepted === false);
  const current = Boolean(
    request &&
      artifact &&
      request.subject_artifact_id === artifact.artifact_id &&
      request.subject_artifact_version === artifact.version &&
      request.subject_input_hash === artifact.input_hash,
  );
  return (
    <div className="approval-dialog" role="dialog" aria-modal="true" aria-labelledby="negotiation-confirm-title">
      <article>
        <header>
          <p>Cổng phê duyệt của Founder</p>
          <h2 id="negotiation-confirm-title">Xác nhận kết quả đàm phán cuối</h2>
        </header>
        {outcomes.length ? (
          <ul>
            {outcomes.map((item) => (
              <li key={String(item.condition_id)}>
                <strong>{String(item.condition_title)}</strong>: {item.customer_accepted ? "Khách hàng đồng ý" : "Khách hàng từ chối"}
                {item.founder_note ? ` — ${String(item.founder_note)}` : ""}
              </li>
            ))}
          </ul>
        ) : <p role="alert">Không tìm thấy bản tổng hợp kết quả đàm phán hiện hành.</p>}
        {rejected.length ? (
          <p role="alert">Có {rejected.length} điều kiện bị từ chối. Nếu Founder xác nhận kết quả này, case sẽ được đóng.</p>
        ) : (
          <p>Tất cả điều kiện đã được chấp thuận. Xác nhận để ghi nhận hợp đồng đáp ứng điều kiện.</p>
        )}
        <footer>
          <button type="button" onClick={onClose} disabled={submitting}>Đóng</button>
          <button type="button" disabled={submitting || !request || !current} onClick={() => request && void onDecision(request.request_id, "REJECT")}>Từ chối phê duyệt</button>
          <button type="button" disabled={submitting || !request || !current || !outcomes.length} onClick={() => request && void onDecision(request.request_id, "APPROVE")}>Xác nhận kết quả</button>
        </footer>
      </article>
    </div>
  );
}
