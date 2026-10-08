import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  ArtifactAssessmentView,
  BankingAssessmentView,
  DecisionPostPrecheckReviewView,
  FinanceAssessmentView,
  RiskAssessmentView,
} from "./AssessmentViews";

describe("artifact assessment views", () => {
  it("shows contract-scoped facts without exposing evidence lineage", () => {
    const payload = {
      assessment_status: "COMPLETE",
      facts: [
        { metric: "CONTRACT_VALUE", value: 4_200_000_000, unit: "VND", scope: "CASE_SPECIFIC", quality: "VERIFIED" },
        { metric: "RELATED_ORDER_COUNT", value: 2, scope: "CASE_SPECIFIC", quality: "VERIFIED" },
        { metric: "PROJECTED_CLOSING_CASH", value: -710_000_000, unit: "VND", scope: "OPC_GLOBAL" },
      ],
      observations: [{ title: "Thanh khoản OPC", detail: "Không quy cho hợp đồng", scope: "OPC_GLOBAL" }],
      narrative: { headline: "Tóm tắt", statements: [{ text: "Biên lợi nhuận cần được xem xét." }] },
      narrative_source: "OPENAI",
      evidence_ids: ["SECRET-EVIDENCE-ID"],
      source_sheet: "08_FINANCE",
      row_number: 9,
      composer_model: "gpt-private-model-name",
    };

    render(<FinanceAssessmentView payload={payload} />);

    expect(screen.getByText(/4\.200\.000\.000\s*₫/)).toBeInTheDocument();
    expect(screen.queryByText("-710.000.000 ₫")).not.toBeInTheDocument();
    expect(screen.queryByText("Không quy cho hợp đồng")).not.toBeInTheDocument();
    expect(screen.getByText("Số đơn hàng liên kết")).toBeInTheDocument();
    expect(screen.queryByText(/Chất lượng:/i)).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Tóm tắt (Nội dung do OpenAI tạo)" })).toBeInTheDocument();
    expect(screen.queryByText(/gpt-private-model-name|SECRET-EVIDENCE-ID|08_FINANCE|row_number/)).not.toBeInTheDocument();
  });

  it("labels simulated Banking results as non-binding", () => {
    render(
      <BankingAssessmentView
        payload={{
          authority: "SIMULATED_NON_BINDING",
          bank_approval_obtained: false,
          results: [{ product_name: "Performance bond", non_binding: true, supported_amount: 420_000_000, currency: "VND" }],
        }}
      />,
    );

    expect(screen.getAllByText(/mô phỏng|không ràng buộc/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/chưa có xác nhận hay phê duyệt từ ngân hàng/i)).toBeInTheDocument();
  });

  it("never renders a risk level as success", () => {
    const { container, rerender } = render(<RiskAssessmentView payload={{ overall_risk_level: "HIGH" }} />);
    expect(screen.getByText(/Mức tổng thể: Cao/)).toHaveClass("status-badge--danger");

    rerender(<RiskAssessmentView payload={{ overall_risk_level: "LOW" }} />);
    expect(screen.getByText(/Mức tổng thể: Thấp/)).not.toHaveClass("status-badge--success");
    expect(container.querySelector(".status-badge--success")).not.toBeInTheDocument();
  });

  it("states an unresolved Final Risk conclusion as a warning", () => {
    render(<RiskAssessmentView phase="FINAL" payload={{ residual_risk_level: "MEDIUM", conclusion: "ATTENTION_REQUIRED" }} />);
    expect(screen.getByRole("status")).toHaveTextContent(/Cần tiếp tục xử lý/);
    expect(screen.getByText(/Mức còn lại: Trung bình/)).toHaveClass("status-badge--warning");
  });

  it("labels post-precheck outcomes as simulated and never as success", () => {
    const { container } = render(
      <DecisionPostPrecheckReviewView
        payload={{
          outcome: "ALL_OPTIONS_NOT_ELIGIBLE",
          option_reviews: [{ option_id: "OPT-1", api_provider: "Bank A", source_outcome: "NOT_ELIGIBLE", disposition: "NOT_ELIGIBLE", reason_codes: ["NOT_ELIGIBLE"] }],
        }}
      />,
    );
    expect(screen.getByText(/Kết luận: Không có phương án nào đủ điều kiện/)).toHaveClass("status-badge--danger");
    expect(screen.getByRole("note")).toHaveTextContent(/mô phỏng, không ràng buộc/);
    expect(screen.getByText(/Kết quả precheck mô phỏng:/)).toBeInTheDocument();
    expect(screen.queryByText(/Phản hồi từ ngân hàng/)).not.toBeInTheDocument();
    expect(container.querySelector(".status-badge--success")).not.toBeInTheDocument();
  });

  it("does not add thresholds that are absent from approval checkpoints", () => {
    render(
      <ArtifactAssessmentView
        artifact={{ artifact_id: "ART-SCAN", artifact_type: "RISK_PRE_SCAN", version: 1, validation_status: "VALID", payload: {} }}
        runArtifacts={[
          {
            artifact_id: "ART-CHK",
            artifact_type: "APPROVAL_CHECKPOINTS",
            version: 1,
            validation_status: "VALID",
            payload: { checkpoints: [{ source_rule_id: "RR-005", protected_action: "COMMIT_LARGE_FINANCIAL_DECISION" }] },
          },
        ]}
      />,
    );
    expect(screen.getByText(/Founder cần phê duyệt trước khi cam kết quyết định tài chính lớn\./)).toBeInTheDocument();
    expect(screen.queryByText(/300 triệu/)).not.toBeInTheDocument();
  });
});
