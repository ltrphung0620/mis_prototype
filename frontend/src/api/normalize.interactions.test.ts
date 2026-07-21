import { describe, expect, it } from "vitest";

import { normalizeWorkflowDashboard } from "./normalize";

describe("workflow interaction normalization", () => {
  it("preserves a typed NOT_EVALUABLE review without counting it as missing data or approval", () => {
    const normalized = normalizeWorkflowDashboard({
      workflow_run_id: "RUN-NOT-EVALUABLE",
      contract_id: "CON-004",
      execution_status: "WAITING_FOR_REVIEW",
      pending_interactions: [
        {
          interaction_type: "NOT_EVALUABLE_REVIEW",
          title_vi: "Founder xem giới hạn đánh giá",
          instruction_vi:
            "Decision Card chỉ để xem; quyết định cuối và hậu quyết định chưa được mở.",
          request_ids: [],
          approval_request_ids: [],
          required_fields: [],
          endpoint: null,
          protected_action: null,
          subject_artifact_id: "ART-DECISION-CARD",
          subject_artifact_version: 4,
        },
      ],
    });

    expect(normalized.pendingApprovalCount).toBe(0);
    expect(normalized.pendingMissingDataCount).toBe(0);
    expect(normalized.pendingInteractions).toEqual([
      expect.objectContaining({
        interaction_type: "NOT_EVALUABLE_REVIEW",
        subject_artifact_id: "ART-DECISION-CARD",
        subject_artifact_version: 4,
        protected_action: null,
        endpoint: null,
      }),
    ]);
  });
});
