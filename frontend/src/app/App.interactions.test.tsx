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
    statusLabel: "Đang chờ Founder",
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
    businessStatusLabel: "Đang chờ Founder xử lý",
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
      ai_analysis_id: "AIDA-1",
      ai_analysis_artifact: {
        artifact_id: "ART-AI-ANALYSIS",
        version: 2,
      },
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

function decisionArtifacts(
  recommendation = "NEGOTIATE_CONDITIONS_TO_ACCEPT",
): ApiArtifactEnvelope[] {
  return [
    decisionCard(recommendation),
    {
      artifact_id: "ART-AI-ANALYSIS",
      artifact_type: "AI_DECISION_ANALYSIS",
      evaluation_case_id: "CASE-1",
      producer: "OPENAI_DECISION_ANALYSIS",
      version: 2,
      status: "CREATED",
      validation_status: "VALID",
      payload: {
        analysis_id: "AIDA-1",
        source: "OPENAI",
      },
    },
  ];
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

  it("keeps the dashboard visible until Founder opens the missing-data form", async () => {
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

    expect(screen.queryByRole("dialog", { name: "Bổ sung số tiền yêu cầu" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Mở biểu mẫu bổ sung dữ liệu" }));
    expect(await screen.findByRole("dialog", { name: "Bổ sung số tiền yêu cầu" })).toBeInTheDocument();
  });

  it("opens the exact current final-decision control while workflow playback is still catching up", async () => {
    const currentDashboard = finalDecisionDashboard();
    dashboardHookMock.mockReturnValue(
      hookValue(currentDashboard, [finalApproval()], decisionArtifacts()),
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

  it("renders founder-facing negotiation condition wording with decision-card numbers", async () => {
    const currentDashboard = {
      ...finalDecisionDashboard(),
      status: "WAITING_FOR_INPUT",
      currentStage: "NEGOTIATION_TERMS_SENT",
      pendingApprovalCount: 0,
      pendingMissingDataCount: 1,
      pendingInteractions: [
        {
          interaction_type: "NEGOTIATION_TERMS_SENT_CONFIRMATION",
          title_vi: "X\u00e1c nh\u1eadn \u0111\u00e3 g\u1eedi \u0111i\u1ec1u ki\u1ec7n \u0111\u00e0m ph\u00e1n",
          instruction_vi: "Xem l\u1ea1i \u0111i\u1ec1u ki\u1ec7n tr\u01b0\u1edbc khi x\u00e1c nh\u1eadn.",
          request_ids: ["NTS-1"],
          approval_request_ids: [],
          required_fields: ["workflow_run_id", "decision_card_artifact_id"],
        },
      ],
    } satisfies NormalizedWorkflowDashboard;
    const card = decisionCard();
    card.payload = {
      ...card.payload,
      analysis_source: "OPENAI",
      reasons: [
        {
          code: "LOW_GROSS_MARGIN",
          title: "Contract-attributable gross margin is below OPC target",
          detail: "Gross margin is below target.",
          recommended_action: "Negotiate the selected margin strategy.",
        },
        {
          code: "CONTRACT_VALUE_NOT_COVERED_BY_EXPLICIT_ORDERS",
          title: "Part of the contract value lacks explicit order coverage",
          detail: "Linked orders do not cover the full contract value.",
          recommended_action: "Verify explicit order links.",
        },
        {
          code: "FINAL_RISK_CLOSING_CASH_LIMITATION",
          title: "\u0110\u00e1nh gi\u00e1 R\u1ee7i ro cu\u1ed1i b\u1ecb gi\u1edbi h\u1ea1n b\u1edfi d\u1eef li\u1ec7u hi\u1ec7n c\u00f3",
          detail: "Missing closing cash at contract level.",
          recommended_action: "Request closing cash evidence.",
        },
        {
          code: "AL-003",
          title: "Source alert AL-003: Contract execution risk",
          detail: "Contract execution risk.",
          recommended_action: "C\u1ea3nh b\u00e1o ngu\u1ed3n AL-003: Contract execution risk. L\u1eadp k\u1ebf ho\u1ea1ch n\u0103ng l\u1ef1c tri\u1ec3n khai theo t\u1eebng khu v\u1ef1c.",
        },
      ],
      selected_negotiation_strategies: [
        {
          strategy_id: "STR-1",
          strategy_type: "INCREASE_CUSTOMER_PRICE",
          title: "T\u0103ng revenue",
          founder_instruction: "T\u0103ng revenue.",
          required_adjustment_value: 172_222_223,
          resulting_revenue: 3_272_222_223,
          target_margin: 0.28,
          currency: "VND",
        },
      ],
      finance_metrics: [
        { metric: "ORDER_REVENUE_TOTAL", value: 3_100_000_000, unit: "VND" },
        { metric: "CONTRACT_VALUE", value: 4_200_000_000, unit: "VND" },
        { metric: "ORDER_COVERAGE_RATIO", value: 0.738095238, unit: "RATIO" },
        { metric: "UNCOVERED_CONTRACT_VALUE", value: 1_100_000_000, unit: "VND" },
        { metric: "WORST_RESERVE_GAP_MONTH", value: "2026-09", unit: "TEXT" },
        { metric: "WORST_RESERVE_GAP", value: 500_000_000, unit: "VND" },
      ],
      calculations: [
        {
          code: "MINIMUM_REVENUE_INCREASE_FOR_TARGET_MARGIN",
          result_value: 172_222_223,
          result_unit: "VND",
        },
      ],
    };
    dashboardHookMock.mockReturnValue(
      hookValue(currentDashboard, [], [
        card,
        {
          artifact_id: "ART-AI-ANALYSIS",
          artifact_type: "AI_DECISION_ANALYSIS",
          evaluation_case_id: "CASE-1",
          producer: "OPENAI_DECISION_ANALYSIS",
          version: 2,
          status: "CREATED",
          validation_status: "VALID",
          payload: {
            analysis_id: "AIDA-1",
            source: "OPENAI",
          },
        },
      ]),
    );

    render(<App />);

    const dialog = await screen.findByRole("dialog", {
      name: /X\u00e1c nh\u1eadn \u0111\u00e3 g\u1eedi \u0111i\u1ec1u ki\u1ec7n \u0111\u00e0m ph\u00e1n/,
    });
    expect(within(dialog).getByText(/t\u0103ng revenue.*172\.222\.223.*3\.272\.222\.223/)).toBeInTheDocument();
    expect(within(dialog).getByText(/T\u1ed5ng gi\u00e1 tr\u1ecb \u0111\u01a1n h\u00e0ng li\u00ean k\u1ebft.*3\.100\.000\.000/)).toBeInTheDocument();
    expect(within(dialog).getByText(/4\.200\.000\.000.*73,8%/)).toBeInTheDocument();
    expect(within(dialog).getByText(/closing cash ri\u00eang cho t\u1eebng h\u1ee3p \u0111\u1ed3ng/)).toBeInTheDocument();
    expect(within(dialog).getByText("Đề xuất của OPC về năng lực triển khai")).toBeInTheDocument();
    expect(within(dialog).queryByText(/AL-003: Contract execution risk/)).not.toBeInTheDocument();
  });

  it("keeps a stale final-decision request non-actionable", async () => {
    const currentDashboard = finalDecisionDashboard();
    const decideApproval = vi.fn();
    dashboardHookMock.mockReturnValue({
      ...hookValue(
        currentDashboard,
        [finalApproval({ subject_artifact_version: 2 })],
        decisionArtifacts(),
      ),
      decideApproval,
    });

    render(<App />);

    expect(screen.queryByRole("dialog", { name: /Decision Card/ })).not.toBeInTheDocument();
    const lockedControls = screen.getAllByRole("button", {
      name: /\u0110ang ho\u00e0n thi\u1ec7n Decision Card|kh\u00f4ng kh\u1edbp/,
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
        decisionArtifacts("NOT_EVALUABLE"),
      ),
    );

    render(<App />);

    expect(screen.queryByRole("dialog", { name: /Decision Card/ })).not.toBeInTheDocument();
    for (const control of screen.getAllByRole("button", {
      name: /\u0110ang ho\u00e0n thi\u1ec7n Decision Card|kh\u00f4ng kh\u1edbp/,
    })) {
      expect(control).toBeDisabled();
    }
  });

  it("auto-opens an exact NOT_EVALUABLE review as view-only even while playback is behind", async () => {
    const decideApproval = vi.fn();
    dashboardHookMock.mockReturnValue({
      ...hookValue(
        notEvaluableReviewDashboard(),
        [],
        decisionArtifacts("NOT_EVALUABLE"),
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
        decisionArtifacts("NOT_EVALUABLE"),
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
