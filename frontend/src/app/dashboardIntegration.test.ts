import { describe, expect, it } from "vitest";

import type {
  ApiApprovalRequest,
  ApiArtifactEnvelope,
  NormalizedWorkflowDashboard,
} from "../api/types";
import {
  allowedDocumentTypes,
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
});
