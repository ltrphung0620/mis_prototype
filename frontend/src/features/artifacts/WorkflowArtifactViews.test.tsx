import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ArtifactAssessmentView } from "./AssessmentViews";

describe("workflow artifact presenters", () => {
  it("presents Planner links and readiness without lineage fields", () => {
    render(<ArtifactAssessmentView artifact={{ artifact_id: "ART-1", artifact_type: "PLANNER_RESULT", version: 1, validation_status: "VALID", payload: { evaluation_case: { contract_id: "CON-004", customer_id: "CUS-004", related_order_ids: ["ORD-004"], related_invoice_ids: ["INV-004"], related_service_ids: [], related_credit_case_ids: ["CRD-004"], contract_requirements: [{ requirement_type: "PERFORMANCE_BOND", certainty: "EXPLICIT", requested_amount: 420_000_000, requested_amount_currency: "VND", evidence_ids: ["EVD-NESTED"] }], evidence_refs: [{ evidence_id: "EVD-HIDDEN" }] }, data_readiness: { status: "READY", blocking_missing_fields: [], non_blocking_warnings: [] }, run_plan: { parallel_initial_tasks: ["FINANCE_ASSESSMENT", "OPERATIONS_ASSESSMENT", "INITIAL_RISK_SCAN"] }, evidence_refs: [{ evidence_id: "EVD-ROOT" }] } }} />);
    expect(screen.getByText(/CUS-004/)).toBeInTheDocument();
    expect(screen.getByText(/420\.000\.000/)).toBeInTheDocument();
    expect(screen.queryByText(/EVD-HIDDEN|EVD-NESTED|EVD-ROOT|evidence_refs/i)).not.toBeInTheDocument();
  });

  it("labels Final Risk separately from Initial Risk", () => {
    render(<ArtifactAssessmentView artifact={{ artifact_id: "ART-R", artifact_type: "FINAL_RISK_ASSESSMENT", version: 1, validation_status: "VALID", payload: { residual_risk_level: "NO_CASE_SIGNAL", conclusion: "SAFE", residual_findings: [], evidence_ids: ["EVD-HIDDEN"] } }} />);
    expect(screen.getByRole("heading", { name: "Kiểm tra rủi ro cuối" })).toBeInTheDocument();
    expect(screen.getByText(/An toàn: không còn rủi ro/)).toBeInTheDocument();
    expect(screen.queryByText(/EVD-HIDDEN/)).not.toBeInTheDocument();
  });

  it("summarizes an Internal Decision Package without implying a decision", () => {
    render(<ArtifactAssessmentView artifact={{ artifact_id: "ART-IDP", artifact_type: "INTERNAL_DECISION_PACKAGE", version: 1, validation_status: "VALID", payload: { readiness: "READY", assembly_path: "CONDITIONAL_DOCUMENT_READY", finance_assessment: { assessment_status: "COMPLETE" }, operations_assessment: { assessment_status: "COMPLETE" }, risk_assessment: { assessment_status: "LIMITED_BY_EVIDENCE", risk_level: "MEDIUM" }, banking_precheck_result_set: { authority: "SIMULATED_NON_BINDING", results: [{}], bank_approval_obtained: false }, source_artifact_ids: ["SECRET-SOURCE"] } }} />);
    expect(screen.getByText(/chỉ tổng hợp dữ liệu/i)).toBeInTheDocument();
    expect(screen.getByText(/mô phỏng, không ràng buộc/i)).toBeInTheDocument();
    expect(screen.queryByText(/SECRET-SOURCE/)).not.toBeInTheDocument();
  });

  it("resolves and renders candidate details from the BANKING_OPTION_MATRIX when candidates is empty", () => {
    const runArtifacts = [
      {
        artifact_id: "ART-MATRIX",
        artifact_type: "BANKING_OPTION_MATRIX",
        version: 1,
        validation_status: "VALID",
        payload: {
          candidates: [
            {
              option_id: "OPT-001",
              product_name: "Gói hỗ trợ trọn gói",
              provider: "VietinBank",
              description: "Mô tả chi tiết gói thứ nhất",
              annual_rate_or_fee: 0.08,
            },
            {
              option_id: "OPT-002",
              product_name: "Gói hỗ trợ nhanh",
              provider: "Techcombank",
              description: "Mô tả chi tiết gói thứ hai",
              annual_rate_or_fee: 0.1,
            }
          ]
        }
      }
    ];

    render(
      <ArtifactAssessmentView
        artifact={{
          artifact_id: "ART-DISCOVERY",
          artifact_type: "BANKING_DISCOVERY_RESULT",
          version: 1,
          validation_status: "VALID",
          payload: {
            discovery_status: "READY",
            candidate_option_ids: ["OPT-001"],
          },
        }}
        runArtifacts={runArtifacts}
      />
    );

    expect(screen.getByText("Gói hỗ trợ trọn gói")).toBeInTheDocument();
    expect(screen.getByText(/VietinBank/)).toBeInTheDocument();
    expect(screen.getByText("Mô tả chi tiết gói thứ nhất")).toBeInTheDocument();
    expect(screen.queryByText("Gói hỗ trợ nhanh")).not.toBeInTheDocument();
  });

  it("resolves and renders candidate details from the BANKING_OPTION_MATRIX for option readiness list", () => {
    const runArtifacts = [
      {
        artifact_id: "ART-MATRIX",
        artifact_type: "BANKING_OPTION_MATRIX",
        version: 1,
        validation_status: "VALID",
        payload: {
          candidates: [
            {
              option_id: "OPT-001",
              product_name: "Performance bond",
              provider: "VietinBank",
            }
          ]
        }
      }
    ];

    render(
      <ArtifactAssessmentView
        artifact={{
          artifact_id: "ART-READINESS",
          artifact_type: "BANKING_PRECHECK_READINESS",
          version: 1,
          validation_status: "VALID",
          payload: {
            status: "READY",
            option_readiness: [
              {
                option_id: "OPT-001",
                status: "READY",
              }
            ]
          },
        }}
        runArtifacts={runArtifacts}
      />
    );

    expect(screen.getByText("Phương án: Performance bond — VietinBank: Sẵn sàng")).toBeInTheDocument();
  });
});
