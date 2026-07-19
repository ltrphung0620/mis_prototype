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
    render(<ArtifactAssessmentView artifact={{ artifact_id: "ART-R", artifact_type: "FINAL_RISK_ASSESSMENT", version: 1, validation_status: "VALID", payload: { residual_risk_level: "MEDIUM", residual_findings: [], evidence_ids: ["EVD-HIDDEN"] } }} />);
    expect(screen.getByRole("heading", { name: "Kiểm tra rủi ro cuối" })).toBeInTheDocument();
    expect(screen.queryByText(/EVD-HIDDEN/)).not.toBeInTheDocument();
  });

  it("summarizes an Internal Decision Package without implying a decision", () => {
    render(<ArtifactAssessmentView artifact={{ artifact_id: "ART-IDP", artifact_type: "INTERNAL_DECISION_PACKAGE", version: 1, validation_status: "VALID", payload: { readiness: "READY", assembly_path: "CONDITIONAL_DOCUMENT_READY", finance_assessment: { assessment_status: "COMPLETE" }, operations_assessment: { assessment_status: "COMPLETE" }, risk_assessment: { assessment_status: "LIMITED_BY_EVIDENCE", risk_level: "MEDIUM" }, banking_precheck_result_set: { authority: "SIMULATED_NON_BINDING", results: [{}], bank_approval_obtained: false }, source_artifact_ids: ["SECRET-SOURCE"] } }} />);
    expect(screen.getByText(/chỉ tổng hợp dữ liệu/i)).toBeInTheDocument();
    expect(screen.getByText(/mô phỏng, không ràng buộc/i)).toBeInTheDocument();
    expect(screen.queryByText(/SECRET-SOURCE/)).not.toBeInTheDocument();
  });
});

