import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  ApiApprovalRequest,
  ApiArtifactEnvelope,
  NormalizedWorkflowDashboard,
} from "../api/types";
import { App } from "./App";

const dashboardHookMock = vi.hoisted(() => vi.fn());
const NOT_EVALUABLE_INSTRUCTION =
  "Decision Card chỉ để xem; quyết định cuối và hậu quyết định chưa được mở.";

vi.mock("../hooks/useWorkflowDashboard", () => ({
  useWorkflowDashboard: dashboardHookMock,
}));

function dashboard(
  pendingInteractions: NormalizedWorkflowDashboard["pendingInteractions"],
): NormalizedWorkflowDashboard {
  return {
    datasetId: "DATASET",
    snapshotHash: "HASH",
    workflowRunId: "RUN-1",
    evaluationCaseId: "CASE-1",
    contractId: "CON-004",
    status: "WAITING_FOR_APPROVAL",
    statusLabel: "Đang chờ Nhà sáng lập",
    currentStage: "WAITING_FOR_APPROVAL",
    currentStageLabel: "Điểm dừng có kiểm soát",
    pendingApprovalCount: pendingInteractions.some(
      (item) => item.interaction_type === "APPROVAL",
    )
      ? 1
      : 0,
    pendingMissingDataCount: pendingInteractions.some(
      (item) => item.interaction_type !== "APPROVAL",
    )
      ? 1
      : 0,
    businessStatus: "AWAITING_FOUNDER_ACTION",
    businessStatusLabel: "Đang chờ Nhà sáng lập xử lý",
    resolvedMilestoneCount: 0,
    totalMilestoneCount: 1,
    progressPercent: 0,
    input: {
      contractId: "CON-004",
      contractLabel: "CON-004",
      readinessStatus: "READY",
      blockingCount: 0,
      warningCount: 0,
      linkedRecords: [],
      blockingItems: [],
      warnings: [],
      contractRequirements: [],
    },
    stages: [],
    runArtifacts: [
      {
        artifact_id: "ART-PROPOSAL",
        artifact_type: "BANKING_PRECHECK_SUBMISSION_PROPOSAL",
        version: 1,
        validation_status: "VALID",
      },
    ],
    approvalRequestIds: ["APR-1"],
    pendingInteractions,
    metrics: [],
    decisionCard: {
      available: false,
      recommendation_label_vi: "Chưa có Decision Card",
    },
  };
}

function artifact(): ApiArtifactEnvelope {
  return {
    artifact_id: "ART-PROPOSAL",
    artifact_type: "BANKING_PRECHECK_SUBMISSION_PROPOSAL",
    evaluation_case_id: "CASE-1",
    producer: "BANKING",
    version: 1,
    status: "CREATED",
    validation_status: "VALID",
    payload: { requested_amount: 420_000_000, currency: "VND" },
  };
}

function hookValue(
  currentDashboard: NormalizedWorkflowDashboard,
  approvals: readonly ApiApprovalRequest[] = [],
  artifacts: readonly ApiArtifactEnvelope[] = [artifact()],
) {
  return {
    state: {
      phase: "ready",
      catalog: {
        datasetId: "DATASET",
        snapshotHash: "HASH",
        contracts: [{ contractId: "CON-004", label: "CON-004" }],
      },
      capabilities: {
        dataset_id: "DATASET",
        openai_enabled: true,
        openai_model: "configured-model",
      },
      selectedContractId: "CON-004",
      workflowRunId: "RUN-1",
      dashboard: currentDashboard,
      errorMessage: null,
    },
    selectContract: vi.fn(),
    runSelectedContract: vi.fn(),
    clearError: vi.fn(),
    runArtifacts: artifacts,
    approvalRequests: approvals,
    submittingInteraction: false,
    decideApproval: vi.fn(),
    submitBankingAmount: vi.fn(),
    submitPrecheckEvidence: vi.fn(),
    submitDocument: vi.fn(),
  };
}

function decisionCard(
  recommendation = "NEGOTIATE_CONDITIONS_TO_ACCEPT",
): ApiArtifactEnvelope {
  return {
    artifact_id: "ART-DECISION-CARD",
    artifact_type: "DECISION_CARD",
    evaluation_case_id: "CASE-1",
    producer: "DECISION",
    version: 3,
    status: "CREATED",
    validation_status: "VALID",
    payload: {
      decision_card_id: "DCARD-1",
      contract_id: "CON-004",
      recommendation,
      executive_summary: "Chỉ tiếp tục khi các điều kiện thương mại đã được đáp ứng.",
      confidence: recommendation === "NOT_EVALUABLE" ? "NOT_EVALUABLE" : "MEDIUM",
      reasons: [],
      finance_metrics: [],
      operations_metrics: [],
      calculations: [],
      selected_options: [],
      conditions: [],
      residual_risk_level: "MEDIUM",
      residual_findings: [],
      required_controls: [],
      limitations: [],
      human_attention_points: [],
    },
  };
}

function finalDecisionDashboard(
  recommendation = "NEGOTIATE_CONDITIONS_TO_ACCEPT",
): NormalizedWorkflowDashboard {
  const currentDashboard = dashboard([
    {
      interaction_type: "APPROVAL",
      title_vi: "Xem xét quyết định cuối cùng",
      instruction_vi: "Xem Decision Card hiện hành trước khi quyết định.",
      request_ids: [],
      approval_request_ids: ["APR-FINAL"],
      protected_action: "CONFIRM_FINAL_CONTRACT_DECISION",
      required_fields: ["decision"],
    },
  ]);
  return {
    ...currentDashboard,
    resolvedMilestoneCount: 2,
    totalMilestoneCount: 4,
    progressPercent: 50,
    runArtifacts: [
      {
        artifact_id: "ART-DECISION-CARD",
        artifact_type: "DECISION_CARD",
        version: 3,
        validation_status: "VALID",
      },
    ],
    approvalRequestIds: ["APR-FINAL"],
    decisionCard: {
      available: true,
      artifact_id: "ART-DECISION-CARD",
      decision_card_id: "DCARD-1",
      recommendation,
      recommendation_label_vi:
        recommendation === "NOT_EVALUABLE"
          ? "Chưa đủ cơ sở để đề xuất"
          : "Đàm phán điều kiện để chấp nhận",
      confidence: recommendation === "NOT_EVALUABLE" ? "NOT_EVALUABLE" : "MEDIUM",
      executive_summary: "Chỉ tiếp tục khi các điều kiện thương mại đã được đáp ứng.",
    },
  };
}

function finalApproval(
  overrides: Partial<ApiApprovalRequest> = {},
): ApiApprovalRequest {
  return {
    request_id: "APR-FINAL",
    workflow_run_id: "RUN-1",
    evaluation_case_id: "CASE-1",
    subject_artifact_id: "ART-DECISION-CARD",
    subject_artifact_version: 3,
    command: { action_type: "CONFIRM_FINAL_CONTRACT_DECISION" },
    status: "PENDING",
    ...overrides,
  };
}

function notEvaluableReviewDashboard(
  subjectArtifactVersion = 3,
): NormalizedWorkflowDashboard {
  const currentDashboard = finalDecisionDashboard("NOT_EVALUABLE");
  return {
    ...currentDashboard,
    status: "WAITING_FOR_REVIEW",
    currentStage: "NOT_EVALUABLE_REVIEW",
    pendingApprovalCount: 0,
    pendingMissingDataCount: 0,
    approvalRequestIds: [],
    pendingInteractions: [
      {
        interaction_type: "NOT_EVALUABLE_REVIEW",
        title_vi: "Founder xem giới hạn đánh giá",
        instruction_vi: NOT_EVALUABLE_INSTRUCTION,
        request_ids: [],
        approval_request_ids: [],
        required_fields: [],
        protected_action: null,
        endpoint: null,
        subject_artifact_id: "ART-DECISION-CARD",
        subject_artifact_version: subjectArtifactVersion,
      },
    ],
  };
}

beforeEach(() => {
  dashboardHookMock.mockReset();
});

describe("Founder interaction popups", () => {
  it("automatically opens and keeps a launcher for a real pending approval", async () => {
    const currentDashboard = dashboard([
      {
        interaction_type: "APPROVAL",
        title_vi: "Cho phép gửi yêu cầu kiểm tra sơ bộ tới ngân hàng",
        instruction_vi: "Xem nội dung trước khi quyết định.",
        request_ids: [],
        approval_request_ids: ["APR-1"],
        protected_action: "SUBMIT_BANKING_PRECHECK",
        required_fields: ["decision"],
      },
    ]);
    dashboardHookMock.mockReturnValue(
      hookValue(currentDashboard, [
        {
          request_id: "APR-1",
          workflow_run_id: "RUN-1",
          evaluation_case_id: "CASE-1",
          subject_artifact_id: "ART-PROPOSAL",
          subject_artifact_version: 1,
          command: { action_type: "SUBMIT_BANKING_PRECHECK" },
          status: "PENDING",
        },
      ]),
    );

    render(<App />);

    expect(
      await screen.findByRole("dialog", {
        name: "Cho phép gửi yêu cầu kiểm tra sơ bộ tới ngân hàng",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Mở yêu cầu xác nhận/phê duyệt" }),
    ).toBeInTheDocument();
  });

  it("automatically opens the typed missing-data form", async () => {
    const currentDashboard = {
      ...dashboard([
        {
          interaction_type: "BANKING_AMOUNT_INPUT",
          title_vi: "Bổ sung số tiền yêu cầu",
          instruction_vi: "Nhập số tiền VND để quy trình tiếp tục.",
          request_ids: ["MDR-1"],
          approval_request_ids: [],
          required_fields: ["requested_amount"],
        },
      ]),
      status: "WAITING_FOR_INPUT",
    };
    dashboardHookMock.mockReturnValue(hookValue(currentDashboard));

    render(<App />);

    await waitFor(() =>
      expect(
        screen.getByRole("dialog", { name: "Bổ sung số tiền yêu cầu" }),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByRole("button", { name: "Mở biểu mẫu bổ sung dữ liệu" }),
    ).toBeInTheDocument();
  });

  it("opens the exact current final-decision control while workflow playback is still catching up", async () => {
    const currentDashboard = finalDecisionDashboard();
    dashboardHookMock.mockReturnValue(
      hookValue(currentDashboard, [finalApproval()], [decisionCard()]),
    );

    render(<App />);

    const dialog = await screen.findByRole("dialog", { name: /Decision Card/ });
    expect(
      within(dialog).getByRole("button", { name: "Ph\u00ea duy\u1ec7t" }),
    ).toBeEnabled();
    expect(
      within(dialog).getByRole("button", { name: "T\u1eeb ch\u1ed1i" }),
    ).toBeEnabled();
  });

  it("keeps a stale final-decision request non-actionable", async () => {
    const currentDashboard = finalDecisionDashboard();
    const decideApproval = vi.fn();
    dashboardHookMock.mockReturnValue({
      ...hookValue(
        currentDashboard,
        [finalApproval({ subject_artifact_version: 2 })],
        [decisionCard()],
      ),
      decideApproval,
    });

    render(<App />);

    expect(screen.queryByRole("dialog", { name: /Decision Card/ })).not.toBeInTheDocument();
    const lockedControls = screen.getAllByRole("button", {
      name: /Decision Card/,
    });
    expect(lockedControls.length).toBeGreaterThan(0);
    for (const control of lockedControls) {
      expect(control).toBeDisabled();
      fireEvent.click(control);
    }
    expect(decideApproval).not.toHaveBeenCalled();
  });

  it("does not expose a final-decision control for NOT_EVALUABLE", () => {
    const currentDashboard = finalDecisionDashboard("NOT_EVALUABLE");
    dashboardHookMock.mockReturnValue(
      hookValue(
        currentDashboard,
        [finalApproval()],
        [decisionCard("NOT_EVALUABLE")],
      ),
    );

    render(<App />);

    expect(screen.queryByRole("dialog", { name: /Decision Card/ })).not.toBeInTheDocument();
    for (const control of screen.getAllByRole("button", { name: /Decision Card/ })) {
      expect(control).toBeDisabled();
    }
  });

  it("auto-opens an exact NOT_EVALUABLE review as view-only even while playback is behind", async () => {
    const decideApproval = vi.fn();
    dashboardHookMock.mockReturnValue({
      ...hookValue(
        notEvaluableReviewDashboard(),
        [],
        [decisionCard("NOT_EVALUABLE")],
      ),
      decideApproval,
    });

    render(<App />);

    const dialog = await screen.findByRole("dialog", { name: /Decision Card/ });
    expect(within(dialog).getByText(NOT_EVALUABLE_INSTRUCTION)).toBeInTheDocument();
    expect(
      within(dialog).getByText(
        /Phê duyệt quyết định cuối và các nhánh hậu quyết định không được mở/,
      ),
    ).toBeInTheDocument();
    expect(
      within(dialog).queryByRole("button", { name: "Ph\u00ea duy\u1ec7t" }),
    ).not.toBeInTheDocument();
    expect(
      within(dialog).queryByRole("button", { name: "T\u1eeb ch\u1ed1i" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /bổ sung dữ liệu/i }),
    ).not.toBeInTheDocument();

    fireEvent.click(
      within(dialog).getByRole("button", { name: "\u0110\u00f3ng" }),
    );
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: /Decision Card/ })).not.toBeInTheDocument(),
    );
    const launchers = screen.getAllByRole("button", { name: /Mở Decision Card/ });
    expect(launchers.length).toBeGreaterThan(0);
    fireEvent.click(launchers[0]);
    expect(await screen.findByRole("dialog", { name: /Decision Card/ })).toBeInTheDocument();
    expect(decideApproval).not.toHaveBeenCalled();
  });

  it("does not open a NOT_EVALUABLE review for a stale artifact version", () => {
    const decideApproval = vi.fn();
    dashboardHookMock.mockReturnValue({
      ...hookValue(
        notEvaluableReviewDashboard(2),
        [],
        [decisionCard("NOT_EVALUABLE")],
      ),
      decideApproval,
    });

    render(<App />);

    expect(screen.queryByRole("dialog", { name: /Decision Card/ })).not.toBeInTheDocument();
    const lockedLaunchers = screen.getAllByRole("button", {
      name: /Decision Card hiện hành không khớp/,
    });
    expect(lockedLaunchers.length).toBeGreaterThan(0);
    for (const launcher of lockedLaunchers) {
      expect(launcher).toBeDisabled();
      fireEvent.click(launcher);
    }
    expect(decideApproval).not.toHaveBeenCalled();
  });
});
