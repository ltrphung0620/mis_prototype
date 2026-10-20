import { describe, expect, it } from "vitest";

import { normalizeWorkflowDashboard } from "./normalize";
import type { WorkflowDashboardResponse } from "./types";

describe("workflow interaction normalization", () => {
  it("translates presentation labels while preserving source statuses and exact approval binding", () => {
    const response: WorkflowDashboardResponse = {
      workflow_run_id: "RUN-ORIGINAL",
      contract_id: "CON-004",
      execution_status: "WAITING_FOR_APPROVAL",
      execution_status_label_vi: "Chờ Founder duyệt",
      business_status: "WAITING_FOR_FINAL_DECISION",
      business_status_label_vi: "Chờ Founder duyệt Decision Card",
      pending_interactions: [{
        interaction_type: "APPROVAL",
        title_vi: "Founder duyệt Decision Card",
        instruction_vi: "Xem Decision Card của lượt chạy hiện tại",
        request_ids: ["REQ-EXACT"], approval_request_ids: ["REQ-EXACT"],
        protected_action: "CONFIRM_FINAL_CONTRACT_DECISION",
        subject_artifact_id: "ART-EXACT", subject_artifact_version: 7,
        endpoint: "/api/approvals/REQ-EXACT", required_fields: [],
      }],
    };
    const original = structuredClone(response);
    const normalized = normalizeWorkflowDashboard(response);
    expect(normalized.status).toBe("WAITING_FOR_APPROVAL");
    expect(normalized.statusLabel).toBe("Chờ phê duyệt");
    expect(normalized.businessStatus).toBe("WAITING_FOR_FINAL_DECISION");
    expect(normalized.businessStatusLabel).toBe("Chờ phê duyệt Phiếu đề xuất quyết định");
    expect(normalized.pendingInteractions[0]).toMatchObject({
      title_vi: "Phê duyệt Phiếu đề xuất quyết định",
      protected_action: "CONFIRM_FINAL_CONTRACT_DECISION",
      subject_artifact_id: "ART-EXACT", subject_artifact_version: 7,
      request_ids: ["REQ-EXACT"], approval_request_ids: ["REQ-EXACT"],
      endpoint: "/api/approvals/REQ-EXACT",
    });
    expect(response).toEqual(original);
  });
  it("preserves a typed NOT_EVALUABLE review without counting it as missing data or approval", () => {
    const normalized = normalizeWorkflowDashboard({
      workflow_run_id: "RUN-NOT-EVALUABLE",
      contract_id: "CON-004",
      execution_status: "WAITING_FOR_REVIEW",
      pending_interactions: [
        {
          interaction_type: "NOT_EVALUABLE_REVIEW",
          title_vi: "người phê duyệt xem giới hạn đánh giá",
          instruction_vi:
            "Phiếu đề xuất quyết định chỉ để xem; quyết định cuối và hậu quyết định chưa được mở.",
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
