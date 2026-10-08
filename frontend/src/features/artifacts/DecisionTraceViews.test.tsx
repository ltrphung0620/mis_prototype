import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ArtifactDetailDialog } from "./ArtifactDetailDialog";
import { ArtifactAssessmentView } from "./AssessmentViews";
import type { ArtifactEnvelope } from "./types";

function envelope(artifact_type: string, payload: Record<string, unknown>, extra: Partial<ArtifactEnvelope> = {}): ArtifactEnvelope {
  return { artifact_id: `ART-${artifact_type}`, artifact_type, version: 1, validation_status: "VALID", payload, ...extra };
}

describe("audit and handoff renderers", () => {
  it("shows registered checkpoints as future gates, not as approval requests", () => {
    render(
      <ArtifactAssessmentView
        artifact={envelope("APPROVAL_CHECKPOINTS", {
          checkpoints: [
            {
              checkpoint_id: "CP-1",
              source_rule_id: "R-7",
              trigger_event: "DOCUMENT_EXTERNAL_RELEASE_REQUESTED",
              protected_action: "SEND_DOCUMENT_TO_EXTERNAL_PARTNER",
              condition: { source_field: "contract_value", operator: "GTE", threshold: 5_000_000_000 },
              status: "REGISTERED",
              approver_role: "FOUNDER",
              evidence_ids: ["EVD-HIDDEN"],
            },
          ],
          policy_coverages: [
            { coverage_id: "COV-1", protected_action: "SUBMIT_BANKING_PRECHECK", source_policy_ids: ["POL-2"], requires_human_approval: true, approver_role: "FOUNDER" },
          ],
        })}
      />,
    );
    expect(screen.getByText("Gửi tài liệu ra đối tác bên ngoài")).toBeInTheDocument();
    expect(screen.getByText(/contract_value ≥ 5\.000\.000\.000/)).toBeInTheDocument();
    expect(screen.getByText("Cần Founder phê duyệt")).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("không tự dừng quy trình");
    expect(screen.queryByText(/EVD-HIDDEN/)).not.toBeInTheDocument();
  });

  it("separates triggered, not-triggered and not-evaluable rules without success styling", () => {
    const { container } = render(
      <ArtifactAssessmentView
        artifact={envelope("RISK_RULE_EVALUATION", {
          evaluations: [
            { evaluation_id: "E1", rule_id: "R-1", risk_type: "CASHFLOW", applicability_scope: "CASE_SPECIFIC", status: "TRIGGERED", severity: "HIGH", source_field: "gap_days", operator: "GT", threshold: 30, actual_value: 45, declared_condition: "Gap > 30", explanation: "45 > 30" },
            { evaluation_id: "E2", rule_id: "R-2", risk_type: "DELIVERY", applicability_scope: "CASE_SPECIFIC", status: "NOT_TRIGGERED", severity: null, source_field: "late_orders", operator: "GTE", threshold: 1, actual_value: 0, declared_condition: "Late ≥ 1", explanation: "0 < 1" },
            { evaluation_id: "E3", rule_id: "R-3", risk_type: "DELIVERY", applicability_scope: "CASE_SPECIFIC", status: "NOT_EVALUABLE", severity: null, source_field: null, operator: null, threshold: null, actual_value: null, declared_condition: "Capacity", explanation: "No capacity data" },
          ],
        })}
      />,
    );
    const rows = screen.getAllByRole("row").slice(1);
    expect(within(rows[0]).getByText("Kích hoạt · Cao")).toHaveClass("status-badge--danger");
    expect(within(rows[1]).getByText("Không kích hoạt")).toHaveClass("status-badge--neutral");
    expect(within(rows[2]).getByText("Chưa đủ cơ sở đánh giá")).toHaveClass("status-badge--warning");
    expect(container.querySelector(".status-badge--success")).toBeNull();
    expect(screen.getByRole("note")).toHaveTextContent("không có nghĩa quy tắc không bị vi phạm");
  });

  it("describes the route plan as classification with the evidenced amount", () => {
    render(
      <ArtifactAssessmentView
        artifact={envelope("DECISION_ROUTE_PLAN", {
          route_outcome: "BANKING_DISCOVERY_REQUIRED",
          required_capabilities: ["BANKING_INTERNAL_DISCOVERY"],
          banking_need_types: ["PERFORMANCE_BOND"],
          routing_reasons: [{ reason_id: "RR-1", code: "PERFORMANCE_BOND_REQUIREMENT", requirement_id: "REQ-1", requirement_certainty: "REQUIRED", requested_amount: 350_000_000, requested_amount_currency: "VND" }],
        })}
      />,
    );
    expect(screen.getByText("Cần khảo sát phương án ngân hàng")).toBeInTheDocument();
    expect(screen.getByText("Hợp đồng yêu cầu bảo lãnh thực hiện")).toBeInTheDocument();
    expect(screen.getByText(/350\.000\.000/)).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("Chưa có yêu cầu nào gửi tới ngân hàng");
  });

  it("states that the post-banking review neither runs precheck nor selects an option", () => {
    render(
      <ArtifactAssessmentView
        artifact={envelope("DECISION_POST_BANKING_REVIEW", {
          outcome: "BANKING_INPUT_REQUIRED",
          candidate_option_ids: ["O1", "O2"],
          precheck_ready_option_ids: [],
          pending_option_ids: ["O1", "O2"],
          required_input_fields: ["requested_amount"],
          missing_data_requests: [{ request_id: "MDR-1", field: "requested_amount", reason: "Founder must supply the amount." }],
          precheck_executed: false,
        })}
      />,
    );
    expect(screen.getByText("Cần bổ sung dữ liệu trước khi chạy precheck")).toHaveClass("status-badge--warning");
    expect(screen.getAllByText("Số tiền yêu cầu")).toHaveLength(2);
    expect(screen.getByRole("note")).toHaveTextContent("Chưa chạy precheck");
  });

  it("keeps the document preparation request non-binding and unsent", () => {
    render(
      <ArtifactAssessmentView
        artifact={envelope("DOCUMENT_PREPARATION_REQUEST", {
          provider: "Bank A",
          bank_product_id: "PERFORMANCE_BOND",
          requested_amount: 350_000_000,
          supported_amount: 350_000_000,
          currency: "VND",
          required_document_codes: ["SIGNED_CONTRACT", "NEW_DOC_CODE"],
          approval_condition_codes: ["MISSING_EVIDENCE"],
          provider_result_authority: "SIMULATED_NON_BINDING",
          documents_prepared: false,
          external_release_performed: false,
        })}
      />,
    );
    expect(screen.getByText("Chưa chuẩn bị hồ sơ")).toBeInTheDocument();
    expect(screen.getByText("Mô phỏng, không ràng buộc")).toBeInTheDocument();
    expect(screen.getByText("Hợp đồng đã ký")).toBeInTheDocument();
    expect(screen.getByText("NEW_DOC_CODE")).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("không gửi hồ sơ ra ngoài");
  });

  it("labels a fallback analysis and keeps it separate from the Founder decision", () => {
    render(
      <ArtifactDetailDialog
        artifact={envelope(
          "AI_DECISION_ANALYSIS",
          {
            source: "DETERMINISTIC_FALLBACK",
            model: "configured-model",
            prompt_version: "v3",
            fallback_reason: "OpenAI disabled",
            recommendation: "NOT_EVALUABLE",
            confidence: "NOT_EVALUABLE",
            executive_summary: "Chưa đủ cơ sở.",
            reasons: [{ reason_id: "R1", code: "INSUFFICIENT", title: "Thiếu dữ liệu", detail: "Không có phản hồi AI." }],
            internal_decision_package_artifact: { artifact_id: "ART-PKG", version: 2 },
            final_risk_artifact: { artifact_id: "ART-FR", version: 1 },
          },
          { version: 4, input_artifact_ids: ["ART-PKG"] },
        )}
        onClose={() => {}}
      />,
    );
    expect(screen.getByText("Nguồn: Dự phòng xác định (không gọi được AI)")).toHaveClass("status-badge--warning");
    expect(screen.getByText(/Lý do dùng dự phòng/)).toBeInTheDocument();
    expect(screen.getAllByText("Chưa đủ cơ sở đánh giá")).toHaveLength(2);
    expect(screen.getByText("ART-PKG", { selector: ".assessment-item__meta .artifact-id" })).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("chưa phải quyết định của Founder");
    expect(screen.getByText(/ART-AI_DECISION_ANALYSIS · v4/)).toBeInTheDocument();
  });
});
