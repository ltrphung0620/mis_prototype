import type { ReactElement } from "react";

import { businessValueLabel } from "../../shared/businessLabels";

import type {
  BankingInputSupplementPayload,
  BankingPrecheckEvidenceSupplementPayload,
  BankingPrecheckSubmissionProposalPayload,
  DocumentEvidenceSupplementPayload,
} from "./types";

const LABELS: Record<string, string> = {
  PERFORMANCE_BOND: "Bảo lãnh thực hiện hợp đồng",
  SUBMIT_BANKING_PRECHECK: "Chạy precheck với ngân hàng",
  AUTHORIZED_STAFF: "Người dùng được ủy quyền",
  FOUNDER: "Founder",
  REQUESTED_DOCUMENT_REFERENCE_SUPPLIED: "Đã cung cấp mã tham chiếu tài liệu được yêu cầu",
  SIGNED_CONTRACT: "Hợp đồng đã ký",
  COMPANY_PROFILE: "Hồ sơ doanh nghiệp",
  PERFORMANCE_BOND_REQUEST_FORM: "Đơn đề nghị bảo lãnh thực hiện",
  CASHFLOW_BUFFER_EVIDENCE: "Tài liệu chứng minh nguồn bù dòng tiền",
  CONDITIONAL_PRECHECK: "Kiểm tra sơ bộ có điều kiện",
  MISSING_EVIDENCE: "Còn thiếu tài liệu xác nhận",
  NOT_ELIGIBLE: "Không đủ điều kiện",
  NO_RECOMMENDATION: "Không có đề xuất",
  SERVICE_UNAVAILABLE: "Dịch vụ không khả dụng",
};

// Unknown codes are shown as-is rather than replaced by a generic phrase.
function label(value?: string | null): string {
  if (!value) return "Chưa xác định";
  return LABELS[value] ?? businessValueLabel(value, value);
}

function money(amount?: number | null, currency = "VND"): string {
  if (amount == null) return "Chưa xác định";
  return new Intl.NumberFormat("vi-VN", { style: "currency", currency, maximumFractionDigits: 0 }).format(amount);
}

function ratio(value?: number | null): string | null {
  if (value == null) return null;
  return `${new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 }).format(Math.abs(value) <= 1 ? value * 100 : value)}%`;
}

export function BankingPrecheckSubmissionProposalView({
  payload,
}: {
  payload: BankingPrecheckSubmissionProposalPayload;
}): ReactElement {
  const candidates = payload.candidates ?? [];
  const executed = payload.precheck_executed || payload.submission_executed;
  return (
    <article className="assessment-view" aria-label="Đề xuất chạy precheck với ngân hàng">
      <header>
        <div className="assessment-view__title">
          <h3>Đề xuất chạy precheck với ngân hàng</h3>
          <span className="status-badge status-badge--neutral">
            {executed ? "Đã ghi nhận lượt chạy" : "Chưa chạy precheck"}
          </span>
        </div>
      </header>
      <dl>
        <div>
          <dt>Số tiền cần hỗ trợ</dt>
          <dd>{money(payload.requested_amount, payload.requested_amount_currency)}</dd>
        </div>
        <div>
          <dt>Hành động cần phê duyệt</dt>
          <dd>{label(payload.proposed_action)}</dd>
        </div>
        <div>
          <dt>Phương án đủ dữ liệu để gửi</dt>
          <dd>{payload.candidate_option_ids?.length ?? candidates.length}</dd>
        </div>
        <div>
          <dt>Phương án chưa sẵn sàng</dt>
          <dd>{payload.non_ready_option_ids?.length ?? 0}</dd>
        </div>
      </dl>
      {candidates.length ? (
        <section>
          <h4>Phương án trong đề xuất</h4>
          <ul className="assessment-list">
            {candidates.map((candidate, index) => {
              const terms = candidate.catalog_terms;
              const termParts = [
                ratio(terms?.annual_rate_or_fee) && `phí/lãi suất ${ratio(terms?.annual_rate_or_fee)}`,
                ratio(terms?.processing_fee_rate) && `phí xử lý ${ratio(terms?.processing_fee_rate)}`,
                ratio(terms?.collateral_ratio) && `tài sản bảo đảm ${ratio(terms?.collateral_ratio)}`,
                terms?.minimum_amount != null && `tối thiểu ${money(terms.minimum_amount, terms.minimum_amount_currency)}`,
              ].filter(Boolean);
              return (
                <li key={candidate.option_id ?? index}>
                  <strong>
                    {candidate.product_name ?? candidate.bank_product_id ?? "Sản phẩm ngân hàng"} —{" "}
                    {candidate.provider ?? "Chưa xác định ngân hàng"}
                  </strong>
                  <p>{label(candidate.need_type)}</p>
                  {!!termParts.length && (
                    <p className="assessment-item__secondary">Điều khoản tham khảo theo danh mục: {termParts.join(" · ")}</p>
                  )}
                  {!!candidate.field_bindings?.length && (
                    <p className="assessment-item__meta">
                      Trường dữ liệu sẽ gửi: {candidate.field_bindings.map((binding) => binding.required_field).filter(Boolean).join(", ")}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      ) : (
        <p>Đề xuất không có phương án nào đủ dữ liệu để gửi.</p>
      )}
      <p role="note" className="assessment-view__footnote">
        Đề xuất cần Founder phê duyệt trước khi chạy. Precheck trong prototype là mô phỏng, không ràng buộc và
        không phải phê duyệt của ngân hàng.
      </p>
    </article>
  );
}

export function BankingInputSupplementView({ payload }: { payload: BankingInputSupplementPayload }): ReactElement {
  return (
    <article className="assessment-view" aria-label="Số tiền ngân hàng được bổ sung">
      <header>
        <h3>Số tiền ngân hàng được bổ sung</h3>
      </header>
      <dl>
        <div>
          <dt>Số tiền cần hỗ trợ</dt>
          <dd>{money(payload.requested_amount, payload.requested_amount_currency)}</dd>
        </div>
        <div>
          <dt>Ngân hàng / nhà cung cấp</dt>
          <dd>{payload.provider ?? "Chưa xác định"}</dd>
        </div>
      </dl>
      {payload.note && (
        <section>
          <h4>Căn cứ nhập liệu</h4>
          <p>{payload.note}</p>
        </section>
      )}
      <p role="note" className="assessment-view__footnote">
        Dữ liệu do người dùng nhập để tiếp tục quy trình; chưa được ngân hàng xác nhận.
      </p>
    </article>
  );
}

export function BankingPrecheckEvidenceSupplementView({
  payload,
}: {
  payload: BankingPrecheckEvidenceSupplementPayload;
}): ReactElement {
  return (
    <article className="assessment-view" aria-label="Bằng chứng bổ sung cho precheck">
      <header>
        <h3>Bằng chứng bổ sung cho precheck</h3>
      </header>
      <dl>
        <div>
          <dt>Sản phẩm ngân hàng</dt>
          <dd>{payload.bank_product_id ?? "Chưa xác định"}</dd>
        </div>
        <div>
          <dt>Trường thông tin được bổ sung</dt>
          <dd>{label(payload.required_field)}</dd>
        </div>
        <div>
          <dt>Kết quả precheck mô phỏng trước đó</dt>
          <dd>{label(payload.source_outcome)}</dd>
        </div>
        <div>
          <dt>Mã tham chiếu tài liệu</dt>
          <dd className="artifact-id">{payload.evidence_reference_id ?? "Chưa có"}</dd>
        </div>
        <div>
          <dt>Người cung cấp</dt>
          <dd>{label(payload.provided_by)}</dd>
        </div>
      </dl>
      {payload.evidence_note && (
        <section>
          <h4>Nội dung bổ sung</h4>
          <p>{payload.evidence_note}</p>
        </section>
      )}
      <p role="note" className="assessment-view__footnote">
        Chỉ ghi nhận mã tham chiếu; kết quả precheck trước đó giữ nguyên.
        {payload.fresh_governed_precheck_required !== false && " Cần chạy lại precheck mô phỏng và được phê duyệt."}
        {payload.bank_approval_obtained ? "" : " Chưa có phê duyệt từ ngân hàng."}
      </p>
    </article>
  );
}

export function DocumentEvidenceSupplementView({
  payload,
}: {
  payload: DocumentEvidenceSupplementPayload;
}): ReactElement {
  return (
    <article className="assessment-view" aria-label="Tài liệu được bổ sung">
      <header>
        <h3>Tài liệu được bổ sung</h3>
      </header>
      <dl>
        <div>
          <dt>Loại tài liệu</dt>
          <dd>{label(payload.document_type)}</dd>
        </div>
        <div>
          <dt>Người cung cấp</dt>
          <dd>{label(payload.provided_by)}</dd>
        </div>
        <div>
          <dt>Mã tham chiếu tài liệu</dt>
          <dd className="artifact-id">{payload.document_reference_id ?? "Chưa có"}</dd>
        </div>
        <div>
          <dt>Mã băm SHA-256</dt>
          <dd className="artifact-id">{payload.content_sha256 ?? "Chưa có"}</dd>
        </div>
      </dl>
      <p role="note" className="assessment-view__footnote">
        Hệ thống chỉ lưu mã tham chiếu và mã băm, không lưu nội dung tệp và không xác minh chữ ký hay giá trị pháp lý.
      </p>
    </article>
  );
}
