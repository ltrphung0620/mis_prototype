import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BankingAssessmentView, FinanceAssessmentView } from "./AssessmentViews";

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
});
