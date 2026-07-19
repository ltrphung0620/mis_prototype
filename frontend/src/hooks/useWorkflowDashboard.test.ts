import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  decideApprovalRequest: vi.fn(),
  getApprovalRequests: vi.fn(),
  getCaseArtifacts: vi.fn(),
  getContractCatalog: vi.fn(),
  getSystemCapabilities: vi.fn(),
  getWorkflowDashboard: vi.fn(),
  startCaseWorkflow: vi.fn(),
  submitBankingAmountSupplement: vi.fn(),
  submitBankingPrecheckEvidence: vi.fn(),
  submitDocumentEvidence: vi.fn(),
}));

vi.mock("../api/client", () => api);
vi.mock("../api/runRequestId", () => ({
  createRunRequestId: vi.fn(() => "UI-RETRY-SAFE-CYCLE"),
}));

import { useWorkflowDashboard } from "./useWorkflowDashboard";

describe("useWorkflowDashboard workflow start", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    api.getSystemCapabilities.mockResolvedValue({
      dataset_id: "TEAM-PACK-V3",
      openai_enabled: true,
      openai_model: "configured-by-server",
    });
    api.getContractCatalog.mockResolvedValue({
      datasetId: "TEAM-PACK-V3",
      snapshotHash: "snapshot-a",
      contracts: [{ contractId: "CON-004", label: "CON-004" }],
    });
    api.getWorkflowDashboard.mockImplementation(
      () => new Promise(() => undefined),
    );
  });

  it("reuses the same cycle id when retrying a start request that was not accepted", async () => {
    api.startCaseWorkflow
      .mockRejectedValueOnce(new Error("Mất kết nối tạm thời"))
      .mockResolvedValueOnce({
        workflow_run_id: "CWF-NEW",
        evaluation_case_id: null,
        contract_id: "CON-004",
        status: "RUNNING",
        status_url: "/api/workflows/CWF-NEW",
      });

    const { result, unmount } = renderHook(() => useWorkflowDashboard());
    await waitFor(() => expect(result.current.state.phase).toBe("ready"));

    await act(async () => {
      await result.current.runSelectedContract();
    });
    expect(result.current.state.phase).toBe("error");

    await act(async () => {
      await result.current.runSelectedContract();
    });

    expect(api.startCaseWorkflow).toHaveBeenNthCalledWith(
      1,
      "CON-004",
      "UI-RETRY-SAFE-CYCLE",
    );
    expect(api.startCaseWorkflow).toHaveBeenNthCalledWith(
      2,
      "CON-004",
      "UI-RETRY-SAFE-CYCLE",
    );
    unmount();
  });
});
