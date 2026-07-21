import { describe, expect, it } from "vitest";
import { normalizeWorkflowDashboard } from "../../api/normalize";
import type { NormalizedWorkflowDashboard, WorkflowStage } from "../../api/types";
import {
  parallelAssessmentLanes,
  stageMilestoneProgress,
  workflowMilestoneProgress,
} from "./workflowModel";

function dashboard(stages: readonly WorkflowStage[]): NormalizedWorkflowDashboard {
  return {
    datasetId: "DATASET",
    snapshotHash: "HASH",
    workflowRunId: "RUN-001",
    contractId: "CON-004",
    status: "RUNNING",
    statusLabel: "Đang xử lý",
    currentStage: stages[0]?.code ?? "",
    currentStageLabel: stages[0]?.label ?? "",
    pendingApprovalCount: 0,
    pendingMissingDataCount: 0,
    businessStatus: "ASSESSING",
    businessStatusLabel: "Đang đánh giá",
    input: {
      contractId: "CON-004",
      contractLabel: "CON-004",
      readinessStatus: "RUNNING",
      blockingCount: 0,
      warningCount: 0,
      linkedRecords: [],
      blockingItems: [],
      warnings: [],
      contractRequirements: [],
    },
    stages,
    runArtifacts: [],
    approvalRequestIds: [],
    pendingInteractions: [],
    metrics: [],
    decisionCard: {
      available: false,
      recommendation_label_vi: "Chưa có Phiếu quyết định",
    },
  };
}

describe("workflow timeline model", () => {
  it("giữ đúng thứ tự sequence do backend cung cấp", () => {
    const normalized = normalizeWorkflowDashboard({
      workflow_run_id: "RUN-001",
      contract_id: "CON-004",
      execution_status: "RUNNING",
      progress: {
        resolved_task_count: 1,
        total_task_count: 2,
        percent: 50,
        basis: "RESOLVED_APPLICABLE_TASKS",
      },
      input: {
        available: true,
        readiness_status: "READY",
        readiness_label_vi: "Đủ dữ liệu đánh giá ban đầu",
        linked_customer_count: 1,
        linked_order_count: 2,
        linked_invoice_count: 1,
        contract_requirements: [
          {
            requirement_type: "PERFORMANCE_BOND",
            certainty: "REQUIRED",
            requested_amount: 420_000_000,
            requested_amount_currency: "VND",
            credit_case_id: "CR-002",
          },
        ],
      },
      pending_interactions: [
        {
          interaction_type: "DOCUMENT_EVIDENCE",
          title_vi: "Bổ sung hồ sơ",
          instruction_vi: "Cung cấp tài liệu còn thiếu.",
          request_ids: ["MDR-1"],
          approval_request_ids: [],
          required_fields: ["document_reference_id"],
        },
        {
          interaction_type: "APPROVAL",
          title_vi: "Phê duyệt",
          instruction_vi: "Founder xem xét.",
          request_ids: [],
          approval_request_ids: ["APR-1"],
          required_fields: [],
        },
      ],
      stages: [
        {
          stage_id: "RISK",
          sequence: 20,
          title_vi: "Đánh giá rủi ro",
          status: "PENDING",
          tasks: [],
        },
        {
          stage_id: "PLANNER",
          sequence: 10,
          title_vi: "Tiếp nhận hợp đồng",
          status: "COMPLETED",
          tasks: [],
        },
      ],
    });

    expect(normalized.stages.map((stage) => stage.id)).toEqual(["PLANNER", "RISK"]);
    expect(normalized.stages.map((stage) => stage.label)).toEqual([
      "Tiếp nhận hợp đồng",
      "Đánh giá rủi ro",
    ]);
    expect(normalized.progressPercent).toBe(50);
    expect(
      normalized.input.linkedRecords.find(
        (item) => item.key === "linked_order_count",
      )?.count,
    ).toBe(2);
    expect(normalized.input.contractRequirements[0]).toMatchObject({
      requirementType: "PERFORMANCE_BOND",
      amount: 420_000_000,
      currency: "VND",
      creditCaseId: "CR-002",
    });
    expect(normalized.pendingMissingDataCount).toBe(1);
    expect(normalized.pendingApprovalCount).toBe(1);
  });

  it("biểu diễn Finance và Operations thành hai nhánh song song", () => {
    const normalized = normalizeWorkflowDashboard({
      workflow_run_id: "RUN-001",
      contract_id: "CON-004",
      execution_status: "RUNNING",
      stages: [
        {
          stage_id: "INITIAL_ASSESSMENT",
          sequence: 2,
          title_vi: "Đánh giá ban đầu",
          parallel: true,
          status: "RUNNING",
          tasks: [
            {
              task_id: "FINANCE_ASSESSMENT",
              owner_id: "FINANCE",
              title_vi: "Đánh giá tài chính",
              applicability: "APPLICABLE",
              status: "COMPLETED",
              artifact_ids: ["ART-FINANCE"],
            },
            {
              task_id: "OPERATIONS_ASSESSMENT",
              owner_id: "OPERATIONS",
              title_vi: "Đánh giá vận hành",
              applicability: "APPLICABLE",
              status: "RUNNING",
            },
          ],
        },
      ],
    });

    const lanes = parallelAssessmentLanes(normalized.stages[0]);
    expect(lanes.map((lane) => lane.id)).toEqual(["finance", "operations"]);
    expect(lanes[0].milestones[0].label).toBe("Đánh giá tài chính");
    expect(lanes[0].milestones[0].artifactIds).toEqual(["ART-FINANCE"]);
  });

  it("giữ nguyên nhãn trạng thái và lý do áp dụng do backend cung cấp", () => {
    const normalized = normalizeWorkflowDashboard({
      workflow_run_id: "RUN-LABELS",
      contract_id: "CON-004",
      execution_status: "COMPLETED",
      stages: [
        {
          stage_id: "FINAL_DECISION",
          sequence: 11,
          title_vi: "Quyết định cuối",
          status: "REJECTED",
          status_label_vi: "Founder đã từ chối quyết định",
          tasks: [
            {
              task_id: "FINAL_DECISION_APPROVAL",
              owner_id: "GOVERNANCE",
              title_vi: "Founder xem xét",
              applicability: "NOT_APPLICABLE",
              applicability_reason_vi:
                "Phiếu quyết định chưa đủ cơ sở để mở quyết định cuối.",
              status: "EXPIRED",
              status_label_vi: "Yêu cầu phê duyệt đã hết hiệu lực",
              resolution_status: "EXPIRED",
            },
          ],
        },
      ],
    });

    expect(normalized.stages[0].statusLabel).toBe("Founder đã từ chối quyết định");
    expect(normalized.stages[0].milestones[0]).toMatchObject({
      statusLabel: "Yêu cầu phê duyệt đã hết hiệu lực",
      applicabilityReason: "Phiếu quyết định chưa đủ cơ sở để mở quyết định cuối.",
      resolutionStatus: "EXPIRED",
    });
  });

  it("tính tiến độ từ mốc thực, loại trừ nhánh không áp dụng", () => {
    const stage: WorkflowStage = {
      id: "S1",
      code: "S1",
      label: "Giai đoạn một",
      status: "RUNNING",
      order: 1,
      parallel: false,
      applicability: "APPLICABLE",
      milestones: [
        {
          id: "M1",
          code: "M1",
          label: "Mốc một",
          status: "COMPLETED",
          waitingFor: [],
          applicability: "APPLICABLE",
          artifactIds: [],
        },
        {
          id: "M2",
          code: "M2",
          label: "Mốc hai",
          status: "PENDING",
          waitingFor: [],
          applicability: "APPLICABLE",
          artifactIds: [],
        },
        {
          id: "M3",
          code: "M3",
          label: "Mốc ba",
          status: "SKIPPED",
          waitingFor: [],
          applicability: "NOT_APPLICABLE",
          artifactIds: [],
        },
      ],
    };

    expect(stageMilestoneProgress(stage)).toEqual({ resolved: 1, total: 2, pending: 1 });
    expect(workflowMilestoneProgress(dashboard([stage]))).toEqual({
      resolved: 1,
      total: 2,
      pending: 1,
    });
  });

  it("ưu tiên số mốc resolved/total chính thức từ projection", () => {
    const value = {
      ...dashboard([]),
      resolvedMilestoneCount: 7,
      totalMilestoneCount: 19,
    };
    expect(workflowMilestoneProgress(value)).toEqual({
      resolved: 0,
      total: 0,
      pending: 0,
    });
  });

  it("tính REJECTED và EXPIRED là trạng thái đã giải quyết", () => {
    const stage: WorkflowStage = {
      id: "GOVERNANCE",
      code: "GOVERNANCE",
      label: "Kiểm soát",
      status: "REJECTED",
      order: 1,
      parallel: false,
      applicability: "APPLICABLE",
      milestones: [
        {
          id: "REJECTED",
          code: "REJECTED",
          label: "Yêu cầu bị từ chối",
          status: "REJECTED",
          waitingFor: [],
          applicability: "APPLICABLE",
          artifactIds: [],
        },
        {
          id: "EXPIRED",
          code: "EXPIRED",
          label: "Yêu cầu hết hiệu lực",
          status: "EXPIRED",
          waitingFor: [],
          applicability: "APPLICABLE",
          artifactIds: [],
        },
        {
          id: "PENDING",
          code: "PENDING",
          label: "Yêu cầu đang chờ",
          status: "PENDING",
          waitingFor: [],
          applicability: "APPLICABLE",
          artifactIds: [],
        },
      ],
    };

    expect(stageMilestoneProgress(stage)).toEqual({ resolved: 2, total: 3, pending: 1 });
    expect(workflowMilestoneProgress(dashboard([stage]))).toEqual({
      resolved: 2,
      total: 3,
      pending: 1,
    });
  });
});
