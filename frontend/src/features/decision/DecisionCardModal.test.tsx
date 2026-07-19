import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DecisionCardModal } from "./DecisionCardModal";
import type { DecisionCardArtifact } from "./types";

const card: DecisionCardArtifact = {
  artifact_id: "ART-CURRENT",
  version: 1,
  payload: {
    decision_card_id: "CARD-1",
    contract_id: "CON-004",
    recommendation: "NEGOTIATE_CONDITIONS_TO_ACCEPT",
    executive_summary: "Chỉ chấp nhận sau khi hoàn tất điều kiện thương mại.",
    confidence: "HIGH",
    reasons: [{ title: "Biên lợi nhuận", detail: "Biên hiện tại chưa đạt mục tiêu." }],
    finance_metrics: [
      { metric: "ORDER_GROSS_MARGIN", value: 0.12, unit: "RATIO", role: "CASE_FACT", contract_attributable: true },
      { metric: "PROJECTED_CLOSING_CASH", value: -500_000_000, unit: "VND", scope: "OPC_GLOBAL", contract_attributable: false },
    ],
    conditions: [{ title: "Đạt biên mục tiêu", description: "Đàm phán lại giá.", status: "OPEN", enforcement_point: "BEFORE_ACCEPTANCE", target: { metric: "ORDER_GROSS_MARGIN", operator: "GTE", current_value: 0.12, target_value: 0.2, unit: "RATIO" } }],
    selected_options: [{ product_name: "Performance bond", provider: "VietinBank", requested_amount: 420_000_000, supported_amount: 420_000_000, currency: "VND", non_binding: true }],
    residual_risk_level: "MEDIUM",
    residual_findings: [],
  },
};

describe("DecisionCardModal", () => {
  it("shows only contract-attributable metrics and allows only exact current approval", () => {
    const approve = vi.fn();
    render(<DecisionCardModal open card={card} current_decision_card_artifact_id="ART-CURRENT" pending_approval={{ request_id: "APR-1", status: "PENDING", subject_artifact_id: "ART-CURRENT", subject_artifact_version: 1, protected_action: "CONFIRM_FINAL_CONTRACT_DECISION" }} onClose={vi.fn()} onApprove={approve} onReject={vi.fn()} />);

    expect(screen.getAllByText("12%").length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: /Decision Card/ })).toBeInTheDocument();
    expect(screen.queryByText(/500\.000\.000/)).not.toBeInTheDocument();
    expect(screen.getByText(/mô phỏng, không ràng buộc/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Phê duyệt" }));
    expect(approve).toHaveBeenCalledWith("APR-1");
  });

  it("does not expose approval actions for a stale or non-evaluable card", () => {
    render(<DecisionCardModal open card={{ ...card, payload: { ...card.payload, recommendation: "NOT_EVALUABLE" } }} current_decision_card_artifact_id="ART-NEW" pending_approval={{ request_id: "APR-1", status: "PENDING", subject_artifact_id: "ART-CURRENT", subject_artifact_version: 1, protected_action: "CONFIRM_FINAL_CONTRACT_DECISION" }} onClose={vi.fn()} onApprove={vi.fn()} onReject={vi.fn()} />);

    expect(screen.queryByRole("button", { name: "Phê duyệt" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Từ chối" })).not.toBeInTheDocument();
    expect(screen.getByText(/không phải Decision Card hiện hành/i)).toBeInTheDocument();
  });

  it("does not expose approval actions for a stale Decision Card version", () => {
    render(
      <DecisionCardModal
        open
        card={card}
        current_decision_card_artifact_id="ART-CURRENT"
        pending_approval={{
          request_id: "APR-STALE-VERSION",
          status: "PENDING",
          subject_artifact_id: "ART-CURRENT",
          subject_artifact_version: 2,
          protected_action: "CONFIRM_FINAL_CONTRACT_DECISION",
        }}
        onClose={vi.fn()}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />,
    );

    expect(screen.queryByRole("button", { name: "Phê duyệt" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Từ chối" })).not.toBeInTheDocument();
  });

  it("does not render evidence or model provenance carried by an oversized API object", () => {
    const oversized = { ...card, payload: { ...card.payload, evidence_ids: ["EVD-SECRET"], source: "OPENAI", model: "private-model" } } as DecisionCardArtifact;
    render(<DecisionCardModal open card={oversized} current_decision_card_artifact_id="ART-CURRENT" onClose={vi.fn()} onApprove={vi.fn()} onReject={vi.fn()} />);
    expect(screen.queryByText(/EVD-SECRET|OPENAI|private-model/)).not.toBeInTheDocument();
  });
});
