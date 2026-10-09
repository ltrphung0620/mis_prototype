import { describe, expect, it } from "vitest";

import type {
  ApiApprovalRequest,
  ApiArtifactEnvelope,
  NormalizedWorkflowDashboard,
} from "../api/types";
import {
  allowedDocumentTypes,
  decisionDashboardData,
  hasAssessmentArtifact,
  pendingApproval,
  pendingMissingInteraction,
  pendingNotEvaluableReview,
  selectAssessmentArtifact,
} from "./dashboardIntegration";

function artifact(
  artifact_id: string,
  artifact_type: string,
  payload: Record<string, unknown>,
): ApiArtifactEnvelope {
  return {
    artifact_id,
    artifact_type,
    evaluation_case_id: "CASE-1",
    producer: "TEST",
    version: 1,
    status: "CREATED",
    validation_status: "VALID",
    payload,
  };
}

describe("dashboard integration", () => {
  it("never selects evidence bundles and merges Finance facts with its narrative", () => {
    const artifacts = [
      artifact("ART-E", "EVIDENCE_BUNDLE", { source: "must stay hidden" }),
      artifact("ART-F", "FINANCE_FACTS", {
        facts: [{ metric: "ORDER_GROSS_MARGIN", value: 0.24, unit: "RATIO" }],
      }),
      artifact("ART-A", "FINANCE_ASSESSMENT", {
        narrative: { statements: [{ text: "Biên lợi nhuận cần được cải thiện." }] },
      }),
    ];

    const selected = selectAssessmentArtifact(
      ["ART-E", "ART-F", "ART-A"],
      artifacts,
    );

    expect(selected?.artifact_type).toBe("FINANCE_ASSESSMENT");
    expect(selected?.payload.facts).toEqual([
      { metric: "ORDER_GROSS_MARGIN", value: 0.24, unit: "RATIO" },
    ]);
    expect(selected?.payload.narrative).toEqual({
      statements: [{ text: "Biên lợi nhuận cần được cải thiện." }],
    });
    expect(selected?.payload).not.toHaveProperty("source");
  });

  it("opens post-decision artifacts and keeps their recorded upstream IDs", () => {
    const outcome = {
      ...artifact("ART-NEG", "NEGOTIATION_OUTCOME", { outcome_status: "ALL_CONDITIONS_ACCEPTED" }),
      version: 2,
      input_artifact_ids: ["ART-CARD"],
    };

    expect(hasAssessmentArtifact(["ART-NEG"], [outcome])).toBe(true);
    const selected = selectAssessmentArtifact(["ART-NEG"], [outcome]);
    expect(selected).toMatchObject({
      artifact_id: "ART-NEG",
      artifact_type: "NEGOTIATION_OUTCOME",
      version: 2,
      input_artifact_ids: ["ART-CARD"],
    });
  });

  it("keeps the existing assessment preference when supplements share a row", () => {
    const artifacts = [
      artifact("ART-SUP", "BANKING_INPUT_SUPPLEMENT", { requested_amount: 1 }),
      artifact("ART-RES", "BANKING_PRECHECK_RESULT_SET", { results: [] }),
    ];
    expect(selectAssessmentArtifact(["ART-SUP", "ART-RES"], artifacts)?.artifact_id).toBe("ART-RES");
  });

  it("still refuses artifact types without a typed renderer", () => {
    // Decision Card keeps its own guarded review; evidence bundles and unknown codes have no view.
    for (const type of ["DECISION_CARD", "EVIDENCE_BUNDLE", "SOMETHING_NEW"]) {
      expect(hasAssessmentArtifact(["ART-X"], [artifact("ART-X", type, {})])).toBe(false);
    }
  });

  it("opens audit and handoff records without displacing existing milestone choices", () => {
    const artifacts = [
      artifact("ART-RULES", "RISK_RULE_EVALUATION", { evaluations: [] }),
      artifact("ART-CHECKPOINTS", "APPROVAL_CHECKPOINTS", { checkpoints: [] }),
      artifact("ART-INITIAL", "INITIAL_RISK_ASSESSMENT", { findings: [] }),
      artifact("ART-AI", "AI_DECISION_ANALYSIS", { source: "OPENAI" }),
      artifact("ART-ROUTE", "DECISION_ROUTE_PLAN", { route_outcome: "DIRECT_INTERNAL_DECISION" }),
    ];

    expect(
      selectAssessmentArtifact(["ART-RULES", "ART-CHECKPOINTS", "ART-INITIAL"], artifacts)?.artifact_id,
    ).toBe("ART-INITIAL");
    expect(selectAssessmentArtifact(["ART-AI"], artifacts)?.artifact_type).toBe("AI_DECISION_ANALYSIS");
    expect(selectAssessmentArtifact(["ART-ROUTE"], artifacts)?.artifact_type).toBe("DECISION_ROUTE_PLAN");
    expect(
      [
        "APPROVAL_CHECKPOINTS",
        "RISK_RULE_EVALUATION",
        "DECISION_ROUTE_PLAN",
        "DECISION_POST_BANKING_REVIEW",
        "DOCUMENT_PREPARATION_REQUEST",
        "AI_DECISION_ANALYSIS",
      ].every((type) => hasAssessmentArtifact(["ART-X"], [artifact("ART-X", type, {})])),
    ).toBe(true);
  });

  it("selects only the pending approval named by the current projection", () => {
    const dashboard = {
      pendingInteractions: [
        {
          interaction_type: "APPROVAL",
          title_vi: "Founder xác nhận",
          instruction_vi: "Xem nội dung",
          request_ids: [],
          approval_request_ids: ["APR-CURRENT"],
          required_fields: [],
        },
      ],
    } as unknown as NormalizedWorkflowDashboard;
    const approvals = [
      {
        request_id: "APR-OLD",
        workflow_run_id: "RUN-1",
        evaluation_case_id: "CASE-1",
        subject_artifact_id: "ART-OLD",
        subject_artifact_version: 1,
        command: { action_type: "CONFIRM_FINAL_CONTRACT_DECISION" },
        status: "PENDING",
      },
      {
        request_id: "APR-CURRENT",
        workflow_run_id: "RUN-1",
        evaluation_case_id: "CASE-1",
        subject_artifact_id: "ART-CURRENT",
        subject_artifact_version: 1,
        command: { action_type: "SUBMIT_BANKING_PRECHECK" },
        status: "PENDING",
      },
    ] as ApiApprovalRequest[];

    expect(pendingApproval(dashboard, approvals)?.request_id).toBe("APR-CURRENT");
  });

  it("limits the document form to document types currently missing", () => {
    const artifacts = [
      artifact("ART-DOC", "DOCUMENT_CHECKLIST", {
        missing_document_codes: ["SIGNED_CONTRACT", "UNSUPPORTED_DOCUMENT"],
      }),
    ];

    expect(allowedDocumentTypes(artifacts)).toEqual(["SIGNED_CONTRACT"]);
  });

  it("selects NOT_EVALUABLE review separately from missing-data interactions", () => {
    const dashboard = {
      pendingInteractions: [
        {
          interaction_type: "NOT_EVALUABLE_REVIEW",
          title_vi: "Founder xem giới hạn đánh giá",
          instruction_vi:
            "Quyết định cuối và hậu quyết định chưa được mở.",
          request_ids: [],
          approval_request_ids: [],
          required_fields: [],
          subject_artifact_id: "ART-CARD",
          subject_artifact_version: 2,
        },
      ],
    } as unknown as NormalizedWorkflowDashboard;

    expect(pendingMissingInteraction(dashboard)).toBeNull();
    expect(pendingNotEvaluableReview(dashboard)).toMatchObject({
      interaction_type: "NOT_EVALUABLE_REVIEW",
      subject_artifact_id: "ART-CARD",
      subject_artifact_version: 2,
    });
  });

  it("reports a projected card as pending reveal during playback, not as missing", () => {
    const projected = {
      contractId: "CON-1",
      statusLabel: "Chờ Founder",
      businessStatus: "WAITING_FOR_FINAL_DECISION",
      businessStatusLabel: "Chờ duyệt quyết định cuối",
      currentStageLabel: "Founder xem xét",
      progressPercent: 40,
      metrics: [],
      decisionCard: {
        available: true,
        artifact_id: "ART-CARD",
        decision_card_id: "DC-1",
        recommendation: "ACCEPT",
        recommendation_label_vi: "Chấp nhận hợp đồng",
        confidence: "MEDIUM",
        executive_summary: "Tóm tắt.",
      },
    } as unknown as NormalizedWorkflowDashboard;

    const pending = decisionDashboardData(projected, null, { revealPending: true });
    expect(pending.decision_card).toMatchObject({
      available: false,
      reveal_pending: true,
      artifact_id: "ART-CARD",
    });
    expect(pending.decision_card.recommendation).toBeUndefined();
    expect(pending.decision_card.executive_summary).toBeUndefined();

    expect(decisionDashboardData(projected, null).decision_card).toMatchObject({
      available: true,
      recommendation_label_vi: "Chấp nhận hợp đồng",
    });

    const missing = decisionDashboardData(
      { ...projected, decisionCard: { available: false, recommendation_label_vi: "Chưa có" } },
      null,
      { revealPending: true },
    );
    expect(missing.decision_card.available).toBe(false);
    expect(missing.decision_card.reveal_pending).toBeUndefined();
  });
});
