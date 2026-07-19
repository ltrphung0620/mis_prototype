import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ArtifactAssessmentView } from "./AssessmentViews";

function artifact(artifact_type: string, payload: Record<string, unknown>) {
  return { artifact_id: `ART-${artifact_type}`, artifact_type, version: 1, validation_status: "VALID", payload };
}

describe("artifact payload compatibility", () => {
  it("renders Finance facts separately from Finance assessment narrative", () => {
    const { rerender } = render(<ArtifactAssessmentView artifact={artifact("FINANCE_FACTS", { facts: [{ fact_id: "F-CASE", metric: "ORDER_REVENUE_TOTAL", value: 3_100_000_000, unit: "VND", scope: "CASE_SPECIFIC", quality: "EXACT" }, { fact_id: "F-GLOBAL", metric: "WORST_RESERVE_GAP", value: 710_000_000, unit: "VND", scope: "OPC_GLOBAL", quality: "DERIVED" }], observations: [{ code: "CASH_RESERVE_SHORTFALL_OBSERVED", title: "Thanh khoản OPC", detail: "Không quy cho hợp đồng", fact_ids: ["F-GLOBAL"] }], limitations: [] })} />);
    expect(screen.getByRole("heading", { name: "Số liệu tài chính của hợp đồng" })).toBeInTheDocument();
    expect(screen.getByText("Tổng doanh thu của đơn hàng liên kết")).toBeInTheDocument();
    expect(screen.queryByText("Chưa xác định")).not.toBeInTheDocument();
    expect(screen.queryByText(/710\.000\.000|Không quy cho hợp đồng/)).not.toBeInTheDocument();

    rerender(<ArtifactAssessmentView artifact={artifact("FINANCE_ASSESSMENT", { assessment_status: "COMPLETE", narrative: { headline: "Kết luận", statements: [{ text: "Doanh thu chỉ tính từ đơn hàng có liên kết rõ ràng." }] }, observations: [], limitations: [], narrative_source: "OPENAI", composer_model: "hidden-model" })} />);
    expect(screen.getByText("Doanh thu chỉ tính từ đơn hàng có liên kết rõ ràng.")).toBeInTheDocument();
    expect(screen.queryByText(/hidden-model|OPENAI/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Chưa có số liệu phù hợp/)).not.toBeInTheDocument();
  });

  it("renders Operations summary from the assessment artifact", () => {
    render(<ArtifactAssessmentView artifact={artifact("OPERATIONS_ASSESSMENT", { assessment_status: "COMPLETE", summary: [{ statement_id: "S-1", text: "Hai đơn hàng nằm trong thời hạn hợp đồng.", fact_ids: ["F-1"] }], observations: [], limitations: [] })} />);
    expect(screen.getByText("Hai đơn hàng nằm trong thời hạn hợp đồng.")).toBeInTheDocument();
    expect(screen.queryByText(/Chưa có số liệu phù hợp/)).not.toBeInTheDocument();
  });

  it("uses overall_risk_level and shows only case confirmation points", () => {
    render(<ArtifactAssessmentView artifact={artifact("INITIAL_RISK_ASSESSMENT", { assessment_status: "COMPLETE", overall_risk_level: "HIGH", findings: [], limitations: [], human_confirmation_points: [{ reason_code: "ALERT_REVIEW", question: "Founder cần xác nhận bối cảnh cảnh báo.", severity: "HIGH", evidence_ids: ["EVD-HIDDEN"] }] })} />);
    expect(screen.getByText("Mức tổng thể: Cao")).toBeInTheDocument();
    expect(screen.getByText("Founder cần xác nhận bối cảnh cảnh báo.")).toBeInTheDocument();
    expect(screen.queryByText(/EVD-HIDDEN/)).not.toBeInTheDocument();
  });

  it("sanitizes Risk pre-scan to contract-linked alerts", () => {
    render(<ArtifactAssessmentView artifact={artifact("RISK_PRE_SCAN", { source_rule_ids: ["RULE-SECRET"], source_record_counts: { alerts: 2 }, case_alerts: [{ alert_type: "CONTRACT_EXECUTION_RISK", severity: "HIGH", description: "Cảnh báo liên kết trực tiếp với hợp đồng.", recommended_action: "Founder kiểm tra bối cảnh.", evidence_ids: ["EVD-SECRET"] }], global_alerts: [{ description: "GLOBAL-HIDDEN" }], global_signals: [{ detail: "GLOBAL-SIGNAL-HIDDEN" }] })} />);
    expect(screen.getByText("Cảnh báo liên kết trực tiếp với hợp đồng.")).toBeInTheDocument();
    expect(screen.queryByText(/RULE-SECRET|EVD-SECRET|GLOBAL-HIDDEN|GLOBAL-SIGNAL-HIDDEN/)).not.toBeInTheDocument();
  });

  it("shows only Banking advice overview and rationales", () => {
    render(<ArtifactAssessmentView artifact={artifact("BANKING_OPTION_ADVICE", { status: "COMPLETED", source: "OPENAI", model: "hidden-model", overview: "Có một phương án bảo lãnh cần xem xét.", suggestions: [{ suggestion_id: "SUG-SECRET", option_ids: ["OPT-SECRET"], rationale: "Ưu tiên phương án đáp ứng đúng nhu cầu bảo lãnh." }] })} />);
    expect(screen.getByText("Có một phương án bảo lãnh cần xem xét.")).toBeInTheDocument();
    expect(screen.getByText("Ưu tiên phương án đáp ứng đúng nhu cầu bảo lãnh.")).toBeInTheDocument();
    expect(screen.queryByText(/OPENAI|hidden-model|SUG-SECRET|OPT-SECRET/)).not.toBeInTheDocument();
  });

  it("renders the actual CON-004 Banking discovery status in Vietnamese", () => {
    render(
      <ArtifactAssessmentView
        artifact={artifact("BANKING_DISCOVERY_RESULT", {
          discovery_status: "OPTIONS_READY",
          candidates: [],
        })}
      />,
    );

    expect(screen.getByText("Đã có phương án phù hợp để xem xét")).toBeInTheDocument();
    expect(screen.queryByText(/OPTIONS_READY|options ready/i)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/Khảo sát này chưa gọi tiền kiểm/i),
    ).not.toBeInTheDocument();
  });

  it("shows Banking readiness without implementation disclaimers", () => {
    render(
      <ArtifactAssessmentView
        artifact={artifact("BANKING_PRECHECK_READINESS", {
          status: "READY",
          option_readiness: [{ status: "READY" }],
        })}
      />,
    );

    expect(
      screen.getByRole("heading", {
        name: "Mức sẵn sàng kiểm tra sơ bộ với ngân hàng",
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/Đây là kiểm tra mức sẵn sàng dữ liệu/i),
    ).not.toBeInTheDocument();
  });

  it("renders package path and major-exception statuses in Vietnamese", () => {
    const { rerender } = render(
      <ArtifactAssessmentView
        artifact={artifact("INTERNAL_DECISION_PACKAGE", {
          readiness: "READY",
          assembly_path: "CONDITIONAL_DOCUMENT_READY",
          finance_assessment: { assessment_status: "COMPLETE" },
          operations_assessment: { assessment_status: "COMPLETE" },
          risk_assessment: {
            assessment_status: "COMPLETE",
            overall_risk_level: "HIGH",
          },
        })}
      />,
    );

    expect(screen.getByText(/Hồ sơ có điều kiện đã được chuẩn bị/)).toBeInTheDocument();
    expect(screen.queryByText(/CONDITIONAL_DOCUMENT_READY/)).not.toBeInTheDocument();

    rerender(
      <ArtifactAssessmentView
        artifact={artifact("FINAL_RISK_ASSESSMENT", {
          residual_risk_level: "MEDIUM",
          major_exception_status: "NOT_DETECTED",
          residual_findings: [],
          required_controls: [],
          limitations: [],
        })}
      />,
    );

    expect(screen.getByText("Ngoại lệ nghiêm trọng: Không phát hiện")).toBeInTheDocument();
    expect(screen.queryByText(/NOT_DETECTED|not detected/i)).not.toBeInTheDocument();
  });

  it("renders a Document Release Package without inventing readiness or sending", () => {
    render(<ArtifactAssessmentView artifact={artifact("DOCUMENT_RELEASE_PACKAGE", { recipient: "VietinBank", purpose: "BANKING_PRECHECK", document_codes: ["SIGNED_CONTRACT"], release_authorized: false, external_release_performed: false })} />);
    expect(screen.getByRole("heading", { name: "Gói hồ sơ đã chuẩn bị nội bộ" })).toBeInTheDocument();
    expect(screen.getByText("Hợp đồng đã ký")).toBeInTheDocument();
    expect(screen.queryByText("Chưa xác định")).not.toBeInTheDocument();
    expect(screen.getByText(/chưa được phép gửi ra ngoài/i)).toBeInTheDocument();
  });
});
