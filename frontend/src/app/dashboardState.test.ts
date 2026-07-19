import { describe, expect, it } from "vitest";
import type { ContractCatalog, NormalizedWorkflowDashboard } from "../api/types";
import {
  dashboardReducer,
  initialDashboardState,
  restoreWorkflowRef,
  serializeWorkflowRef,
} from "./dashboardState";

const catalog: ContractCatalog = {
  datasetId: "TEAM-PACK-V3",
  snapshotHash: "snapshot-a",
  contracts: [
    { contractId: "CON-001", label: "CON-001" },
    { contractId: "CON-004", label: "CON-004" },
  ],
};

const dashboard: NormalizedWorkflowDashboard = {
  datasetId: catalog.datasetId,
  snapshotHash: catalog.snapshotHash,
  workflowRunId: "RUN-OLD",
  evaluationCaseId: "CASE-OLD",
  contractId: "CON-001",
  status: "RUNNING",
  statusLabel: "Đang xử lý",
  currentStage: "PLANNER_INTAKE",
  currentStageLabel: "Tiếp nhận hợp đồng",
  pendingApprovalCount: 0,
  pendingMissingDataCount: 0,
  businessStatus: "ASSESSING",
  businessStatusLabel: "Đang đánh giá",
  input: {
    contractId: "CON-001",
    contractLabel: "CON-001",
    readinessStatus: "RUNNING",
    blockingCount: 0,
    warningCount: 0,
    linkedRecords: [],
    blockingItems: [],
    warnings: [],
    contractRequirements: [],
  },
  stages: [],
  runArtifacts: [],
  approvalRequestIds: [],
  pendingInteractions: [],
  metrics: [],
  decisionCard: {
    available: false,
    recommendation_label_vi: "Chưa có Phiếu quyết định",
  },
};

describe("dashboardReducer", () => {
  it("xóa dữ liệu lượt cũ ngay khi chọn hợp đồng khác", () => {
    const state = {
      ...initialDashboardState,
      phase: "ready" as const,
      catalog,
      selectedContractId: "CON-001",
      workflowRunId: "RUN-OLD",
      dashboard,
      lastUpdatedAt: 42,
    };

    const next = dashboardReducer(state, {
      type: "SELECT_CONTRACT",
      contractId: "CON-004",
    });

    expect(next.selectedContractId).toBe("CON-004");
    expect(next.workflowRunId).toBe("");
    expect(next.dashboard).toBeNull();
    expect(next.lastUpdatedAt).toBeNull();
  });

  it("xóa dữ liệu cũ trước khi tạo lượt workflow mới", () => {
    const state = {
      ...initialDashboardState,
      phase: "ready" as const,
      catalog,
      workflowRunId: "RUN-OLD",
      dashboard,
    };

    const next = dashboardReducer(state, {
      type: "RUN_REQUESTED",
      contractId: "CON-004",
    });

    expect(next.phase).toBe("starting");
    expect(next.workflowRunId).toBe("");
    expect(next.dashboard).toBeNull();
  });

  it("không giữ workflow khi snapshot TeamPack thay đổi", () => {
    const state = {
      ...initialDashboardState,
      phase: "ready" as const,
      catalog,
      selectedContractId: "CON-001",
      workflowRunId: "RUN-OLD",
      dashboard,
    };
    const changedCatalog = { ...catalog, snapshotHash: "snapshot-b" };

    const next = dashboardReducer(state, {
      type: "BOOTSTRAP_SUCCEEDED",
      catalog: changedCatalog,
      capabilities: {
        dataset_id: changedCatalog.datasetId,
        openai_enabled: false,
        openai_model: null,
      },
    });

    expect(next.workflowRunId).toBe("");
    expect(next.dashboard).toBeNull();
  });
});

describe("workflow storage scope", () => {
  it("chỉ khôi phục lượt thuộc đúng dataset, snapshot và contract", () => {
    const serialized = serializeWorkflowRef({
      datasetId: catalog.datasetId,
      snapshotHash: catalog.snapshotHash,
      workflowRunId: "RUN-001",
      contractId: "CON-001",
    });

    expect(restoreWorkflowRef(serialized, catalog)?.workflowRunId).toBe("RUN-001");
    expect(
      restoreWorkflowRef(serialized, { ...catalog, snapshotHash: "snapshot-new" }),
    ).toBeNull();
  });
});
