import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ArtifactDetailDialog } from "./ArtifactDetailDialog";
import { ArtifactAssessmentView } from "./AssessmentViews";
import type { ArtifactEnvelope } from "./types";

function envelope(artifact_type: string, payload: Record<string, unknown>, extra: Partial<ArtifactEnvelope> = {}): ArtifactEnvelope {
  return { artifact_id: `ART-${artifact_type}`, artifact_type, version: 1, validation_status: "VALID", payload, ...extra };
}

describe("post-decision, proposal and supplement renderers", () => {
  it("states that a banking precheck proposal has not been run or approved by a bank", () => {
    render(
      <ArtifactAssessmentView
        artifact={envelope("BANKING_PRECHECK_SUBMISSION_PROPOSAL", {
          requested_amount: 420_000_000,
          requested_amount_currency: "VND",
          proposed_action: "SUBMIT_BANKING_PRECHECK",
          candidate_option_ids: ["OPT-1"],
          non_ready_option_ids: ["OPT-2"],
          candidates: [{ option_id: "OPT-1", product_name: "Bảo lãnh A", provider: "Bank A", need_type: "PERFORMANCE_BOND", api_endpoint: "https://internal.example/precheck", field_bindings: [{ required_field: "requested_amount" }] }],
          evidence_ids: ["EVD-HIDDEN"],
          precheck_executed: false,
          submission_executed: false,
        })}
      />,
    );
    expect(screen.getByText("Chưa chạy precheck")).toBeInTheDocument();
    expect(screen.getByText(/420\.000\.000/)).toBeInTheDocument();
    expect(screen.getByText(/Bảo lãnh A — Bank A/)).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent(/mô phỏng, không ràng buộc/);
    expect(screen.queryByText(/EVD-HIDDEN|internal\.example/)).not.toBeInTheDocument();
  });

  it("separates the recorded Founder decision from any external action", () => {
    render(
      <ArtifactAssessmentView
        artifact={envelope("POST_DECISION_UPDATE", {
          decision_card_artifact: { artifact_id: "ART-CARD", version: 3 },
          founder_approval: { decision: "APPROVE", decided_at: "2026-10-08T03:00:00Z", decision_reason: "Đủ điều kiện", approver_role: "FOUNDER" },
          recommendation: "NEGOTIATE_CONDITIONS_TO_ACCEPT",
          outcome: "NEGOTIATION_AUTHORIZED",
          contract_execution_status: "PENDING_NEGOTIATION",
          external_document_release_required: true,
          external_action_performed: false,
        })}
      />,
    );
    expect(screen.getByText("Đã cho phép tiến hành đàm phán")).toBeInTheDocument();
    expect(screen.getByText(/Decision Card v3/)).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent(/chưa thực hiện hành động nào ra bên ngoài/);
    expect(screen.getByRole("note")).toHaveTextContent(/cần đề xuất và phê duyệt riêng/);
  });

  it("shows each negotiation condition without rendering rejection as success", () => {
    const { container } = render(
      <ArtifactAssessmentView
        artifact={envelope("NEGOTIATION_OUTCOME", {
          outcome_status: "ONE_OR_MORE_CONDITIONS_REJECTED",
          condition_outcomes: [
            { condition_id: "C1", condition_title: "Tạm ứng 30%", customer_accepted: true },
            { condition_id: "C2", condition_title: "Rút ngắn hạn thanh toán", customer_accepted: false, founder_note: "Khách đề nghị 45 ngày" },
          ],
          confirmation_requested: true,
        })}
      />,
    );
    expect(screen.getByText("Có điều kiện khách hàng không chấp nhận")).toHaveClass("status-badge--warning");
    expect(screen.getByText("Khách hàng không chấp nhận")).toBeInTheDocument();
    expect(screen.getByText(/Khách đề nghị 45 ngày/)).toBeInTheDocument();
    expect(container.querySelector(".status-badge--success")).not.toBeInTheDocument();
  });

  it("keeps an external release proposal unauthorized and unsent", () => {
    render(
      <ArtifactAssessmentView
        artifact={envelope("EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL", {
          recipient: "Bank A",
          purpose: "PERFORMANCE_BOND_DOCUMENT_RELEASE",
          document_codes: ["SIGNED_CONTRACT", "UNMAPPED_DOCUMENT"],
          proposed_action: "SEND_DOCUMENT_TO_EXTERNAL_PARTNER",
          release_authorized: false,
          external_submission_performed: false,
        })}
      />,
    );
    expect(screen.getByText("Hồ sơ đề nghị bảo lãnh thực hiện")).toBeInTheDocument();
    expect(screen.getByText("Hợp đồng đã ký")).toBeInTheDocument();
    expect(screen.getByText("UNMAPPED_DOCUMENT")).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent(/chưa được phép gửi/);
  });

  it("presents supplements as user-provided references, not verified documents", () => {
    const { rerender } = render(
      <ArtifactAssessmentView
        artifact={envelope("DOCUMENT_EVIDENCE_SUPPLEMENT", {
          document_type: "PERFORMANCE_BOND_REQUEST_FORM",
          document_reference_id: "DOCREF-1",
          content_sha256: "a".repeat(64),
          provided_by: "AUTHORIZED_STAFF",
        })}
      />,
    );
    expect(screen.getByText("Đơn đề nghị bảo lãnh thực hiện")).toBeInTheDocument();
    expect(screen.getByText("a".repeat(64))).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent(/không xác minh chữ ký hay giá trị pháp lý/);

    rerender(
      <ArtifactAssessmentView
        artifact={envelope("BANKING_PRECHECK_EVIDENCE_SUPPLEMENT", {
          bank_product_id: "BP-1",
          required_field: "collateral_document",
          evidence_reference_id: "DOC-REF-22",
          source_outcome: "MISSING_EVIDENCE",
          fresh_governed_precheck_required: true,
          bank_approval_obtained: false,
        })}
      />,
    );
    expect(screen.getByText("Còn thiếu tài liệu xác nhận")).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent(/Chưa có phê duyệt từ ngân hàng/);

    rerender(
      <ArtifactAssessmentView
        artifact={envelope("BANKING_INPUT_SUPPLEMENT", { requested_amount: 420_000_000, requested_amount_currency: "VND", provider: "Bank A", note: "Theo hợp đồng" })}
      />,
    );
    expect(screen.getByText(/420\.000\.000/)).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent(/chưa được ngân hàng xác nhận/);
  });
});

describe("artifact detail dialog", () => {
  it("shows exact identity and resolves upstream artifacts from the current run", () => {
    const card = envelope("DECISION_CARD", {}, { artifact_id: "ART-CARD", version: 3 });
    const outcome = envelope("NEGOTIATION_OUTCOME", { outcome_status: "ALL_CONDITIONS_ACCEPTED" }, {
      artifact_id: "ART-NEG",
      version: 2,
      input_artifact_ids: ["ART-CARD", "ART-OTHER-RUN"],
    });
    render(<ArtifactDetailDialog artifact={outcome} runArtifacts={[card, outcome]} onClose={() => undefined} />);

    expect(screen.getByText(/ART-NEG · v2 · Đã kiểm tra bằng chứng/)).toBeInTheDocument();
    const lineage = screen.getByRole("region", { name: "Nguồn đầu vào" });
    expect(lineage).toHaveTextContent(/Decision Card · v3/);
    expect(lineage).toHaveTextContent("ART-CARD");
    expect(lineage).toHaveTextContent(/Không thuộc danh sách của lượt xử lý này/);
    expect(lineage).toHaveTextContent("ART-OTHER-RUN");
  });

  it("labels a merged Finance view by the stored artifact type", () => {
    const facts = envelope("FINANCE_FACTS", { facts: [] }, { artifact_id: "ART-F" });
    render(
      <ArtifactDetailDialog
        artifact={{ ...facts, artifact_type: "FINANCE_ASSESSMENT" }}
        runArtifacts={[facts]}
        onClose={() => undefined}
      />,
    );
    expect(screen.getByText("Finance · Số liệu tài chính")).toBeInTheDocument();
  });
});
