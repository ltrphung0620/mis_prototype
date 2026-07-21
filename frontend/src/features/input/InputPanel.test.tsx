import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { InputPanel } from "./InputPanel";
import type { NormalizedWorkflowDashboard } from "../../api/types";

const completedDashboard: NormalizedWorkflowDashboard = {
  datasetId: "TEAM-PACK-V3",
  snapshotHash: "snapshot-a",
  workflowRunId: "CWF-OLD",
  evaluationCaseId: "CASE-OLD",
  contractId: "CON-004",
  status: "COMPLETED",
  statusLabel: "Hoàn tất",
  currentStage: "FINAL_DECISION_RECORDED",
  currentStageLabel: "Hoàn tất lượt đánh giá",
  pendingApprovalCount: 0,
  pendingMissingDataCount: 0,
  businessStatus: "COMPLETED",
  businessStatusLabel: "Hoàn tất",
  input: {
    contractId: "CON-004",
    contractLabel: "CON-004",
    readinessStatus: "COMPLETED",
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

describe("InputPanel", () => {
  it("shows only the server-configured dataset identifier in the dataset summary", () => {
    render(
      <InputPanel
        catalog={{
          datasetId: "MISTalent2026_OPC_AgenticAI_TeamPack_v3.xlsx",
          snapshotHash: "83a9e7bfe88ce2",
          contracts: [{ contractId: "CON-004", label: "CON-004" }],
        }}
        selectedContractId="CON-004"
        dashboard={null}
        bootstrapping={false}
        starting={false}
        onSelectContract={vi.fn()}
        onStart={vi.fn()}
      />,
    );

    const datasetSummary = screen.getByText("Bộ dữ liệu").closest("dl");
    expect(datasetSummary).not.toBeNull();
    expect(within(datasetSummary!).getAllByRole("term")).toHaveLength(1);
    expect(
      within(datasetSummary!).getByText("MISTalent2026_OPC_AgenticAI_TeamPack_v3.xlsx"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Dấu vân tay dữ liệu")).not.toBeInTheDocument();
    expect(screen.queryByText("Hồ sơ đánh giá")).not.toBeInTheDocument();
    expect(screen.queryByText("Lượt xử lý")).not.toBeInTheDocument();
  });

  it("labels the action on an existing dashboard as a new evaluation cycle", () => {
    render(
      <InputPanel
        catalog={{
          datasetId: "TEAM-PACK-V3",
          snapshotHash: "snapshot-a",
          contracts: [{ contractId: "CON-004", label: "CON-004" }],
        }}
        selectedContractId="CON-004"
        dashboard={completedDashboard}
        bootstrapping={false}
        starting={false}
        onSelectContract={vi.fn()}
        onStart={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("button", { name: /Bắt đầu lượt đánh giá mới/i }),
    ).toBeEnabled();
    expect(
      screen.queryByRole("button", { name: /Chạy lại với hợp đồng này/i }),
    ).not.toBeInTheDocument();
  });

  it("does not start another cycle while Founder approval is pending", () => {
    render(
      <InputPanel
        catalog={{
          datasetId: "TEAM-PACK-V3",
          snapshotHash: "snapshot-a",
          contracts: [{ contractId: "CON-004", label: "CON-004" }],
        }}
        selectedContractId="CON-004"
        dashboard={{
          ...completedDashboard,
          status: "WAITING_FOR_APPROVAL",
          statusLabel: "Chờ Founder phê duyệt",
          currentStage: "WAITING_FOR_APPROVAL",
          currentStageLabel: "Chờ Founder phê duyệt",
          pendingApprovalCount: 1,
        }}
        bootstrapping={false}
        starting={false}
        onSelectContract={vi.fn()}
        onStart={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("button", { name: /Bắt đầu lượt đánh giá mới/i }),
    ).toBeDisabled();
  });
});
