import { useCallback, useEffect, useMemo, useState } from "react";
import { ArtifactAssessmentView, type ArtifactEnvelope } from "../features/artifacts";
import {
  DecisionCardModal,
  DecisionDashboard,
  type DecisionCardArtifact,
  type DecisionCondition,
  type DecisionMetric,
  type DecisionReason,
} from "../features/decision";
import { ApprovalDialog, type ApprovalDecision } from "../features/governance";
import { NegotiationConfirmDialog } from "../features/negotiation";
import { InputPanel } from "../features/input/InputPanel";
import {
  MissingDataDialog,
  type BankingAmountSubmission,
  type BankingPrecheckEvidenceSubmission,
  type DocumentEvidenceSubmission,
} from "../features/missing-data";
import { WorkflowTimeline } from "../features/workflow/WorkflowTimeline";
import { useWorkflowPlayback } from "../features/workflow/useWorkflowPlayback";
import { useWorkflowDashboard } from "../hooks/useWorkflowDashboard";
import { Notice } from "../shared/components/Notice";
import { Panel } from "../shared/components/Panel";
import { translateText } from "../shared/translate";
import {
  allowedDocumentTypes,
  approvalRequestView,
  approvalSubjectSummary,
  decisionCardArtifact,
  decisionDashboardData,
  hasAssessmentArtifact,
  pendingApproval,
  pendingDecisionApproval,
  pendingMissingInteraction,
  pendingNegotiationInteraction,
  pendingNotEvaluableReview,
  selectAssessmentArtifact,
} from "./dashboardIntegration";

function documentRequirementLabel(code: string): string {
  const labels: Record<string, string> = {
    SIGNED_CONTRACT: "Hợp đồng đã ký",
    COMPANY_PROFILE: "Hồ sơ doanh nghiệp",
    PERFORMANCE_BOND_REQUEST_FORM: "Đơn đề nghị bảo lãnh thực hiện",
    CASHFLOW_BUFFER_EVIDENCE: "Tài liệu chứng minh nguồn bù dòng tiền",
  };
  return labels[code] ?? code;
}

function AssessmentDialog({
  artifact,
  runArtifacts = [],
  onClose,
}: {
  artifact: ArtifactEnvelope | null;
  runArtifacts?: readonly ArtifactEnvelope[];
  onClose: () => void;
}) {
  if (!artifact) return null;
  return (
    <div
      className="assessment-dialog modal-layer"
      role="dialog"
      aria-modal="true"
      aria-labelledby="assessment-dialog-title"
    >
      <article className="modal-card">
        <header className="modal-card__header">
          <div>
            <p>Kết quả nghiệp vụ</p>
            <h2 id="assessment-dialog-title">Chi tiết đánh giá</h2>
          </div>
          <button type="button" onClick={onClose} aria-label="Đóng chi tiết đánh giá">
            ×
          </button>
        </header>
        <div className="modal-card__body">
          <ArtifactAssessmentView artifact={artifact} runArtifacts={runArtifacts} />
        </div>
      </article>
    </div>
  );
}

function recommendedActionConditions(
  card: DecisionCardArtifact,
  reasons: readonly DecisionReason[] = [],
  fallbackConditions: readonly DecisionCondition[] = [],
): DecisionCondition[] {
  const recommendations = reasons
    .map((reason, index) => ({
      reason,
      recommendationText:
        reason.recommended_action && reason.recommended_action.trim(),
      index,
    }))
    .filter((item): item is { reason: DecisionReason; recommendationText: string; index: number } =>
      Boolean(item.recommendationText),
    );
  if (!recommendations.length) return [...fallbackConditions];
  return recommendations.map(({ reason, recommendationText, index }) => ({
    condition_id: reason.code ?? `OPENAI_RECOMMENDATION_${index + 1}`,
    title: negotiationConditionTitle(reason),
    description: negotiationConditionDescription(card, reason, recommendationText),
    status: "OPEN",
    enforcement_point: "BEFORE_ACCEPTANCE",
    category: "AI_RECOMMENDATION",
  }));
}

function metricValue(
  metrics: readonly DecisionMetric[] = [],
  code: string,
): string | number | boolean | null | undefined {
  return metrics.find((item) => item.metric === code)?.value;
}

function calculationValue(card: DecisionCardArtifact, code: string): number | null {
  const value = card.payload.calculations?.find((item) => item.code === code)?.result_value;
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatVnd(value: string | number | boolean | null | undefined): string | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return new Intl.NumberFormat("vi-VN", {
    style: "currency",
    currency: "VND",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatPercent(value: string | number | boolean | null | undefined): string | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  const normalized = Math.abs(value) <= 1 ? value * 100 : value;
  return `${new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 1 }).format(normalized)}%`;
}

function reasonText(reason: DecisionReason): string {
  return `${reason.code ?? ""} ${reason.title} ${reason.detail}`.toLowerCase();
}

function isMarginReason(reason: DecisionReason): boolean {
  const text = reasonText(reason);
  return (
    text.includes("gross margin") ||
    text.includes("biên lợi nhuận") ||
    text.includes("margin")
  );
}

function isOrderCoverageReason(reason: DecisionReason): boolean {
  const text = reasonText(reason);
  return (
    text.includes("contract_value_not_covered") ||
    text.includes("order coverage") ||
    text.includes("chưa cover") ||
    text.includes("chưa được đơn hàng")
  );
}

function isClosingCashReason(reason: DecisionReason): boolean {
  return reasonText(reason).includes("closing cash");
}

function isExecutionCapacityReason(reason: DecisionReason): boolean {
  const text = reasonText(reason);
  return (
    text.includes("al-003") ||
    text.includes("contract execution risk") ||
    text.includes("năng lực triển khai")
  );
}

function negotiationConditionTitle(reason: DecisionReason): string {
  if (isOrderCoverageReason(reason)) {
    return "Tổng giá trị các đơn hàng bên trong hợp đồng chưa cover hết toàn bộ giá trị hợp đồng";
  }
  if (isClosingCashReason(reason)) {
    return "Final Risk chưa có closing cash cấp hợp đồng";
  }
  if (isExecutionCapacityReason(reason)) {
    return "Đề xuất của OPC về năng lực triển khai";
  }
  return translateText(reason.title) || "Đề xuất xử lý";
}

function marginConditionDescription(card: DecisionCardArtifact): string | null {
  const strategy = card.payload.selected_negotiation_strategies?.[0];
  if (!strategy) return null;
  const adjustment =
    formatVnd(strategy.required_adjustment_value) ??
    formatVnd(calculationValue(card, "MINIMUM_REVENUE_INCREASE_FOR_TARGET_MARGIN")) ??
    formatVnd(calculationValue(card, "MINIMUM_COST_REDUCTION_FOR_TARGET_MARGIN"));
  const targetMargin = formatPercent(strategy.target_margin);
  const type = (strategy.strategy_type ?? strategy.title ?? "").toUpperCase();
  const isCostStrategy =
    type.includes("COST") ||
    (strategy.resulting_cost != null &&
      strategy.baseline_cost != null &&
      strategy.resulting_cost < strategy.baseline_cost);
  if (isCostStrategy) {
    const resultingCost = formatVnd(strategy.resulting_cost);
    return [
      `OpenAI đề xuất xử lý phần chênh lệch biên lợi nhuận bằng cách giảm cost${adjustment ? ` tối thiểu ${adjustment}` : ""}`,
      resultingCost ? `để cost sau điều chỉnh còn ${resultingCost}` : null,
      targetMargin ? `và hướng tới biên lợi nhuận mục tiêu ${targetMargin}` : null,
    ].filter(Boolean).join(", ") + ".";
  }
  const resultingRevenue = formatVnd(strategy.resulting_revenue);
  return [
    `OpenAI đề xuất xử lý phần chênh lệch biên lợi nhuận bằng cách tăng revenue${adjustment ? ` tối thiểu ${adjustment}` : ""}`,
    resultingRevenue ? `để doanh thu sau điều chỉnh đạt ${resultingRevenue}` : null,
    targetMargin ? `và hướng tới biên lợi nhuận mục tiêu ${targetMargin}` : null,
  ].filter(Boolean).join(", ") + ".";
}

function orderCoverageDescription(card: DecisionCardArtifact): string | null {
  const metrics = card.payload.finance_metrics ?? [];
  const orderTotal = formatVnd(metricValue(metrics, "ORDER_REVENUE_TOTAL"));
  const contractTotal = formatVnd(metricValue(metrics, "CONTRACT_VALUE"));
  const coverage = formatPercent(metricValue(metrics, "ORDER_COVERAGE_RATIO"));
  const uncovered = formatVnd(metricValue(metrics, "UNCOVERED_CONTRACT_VALUE"));
  if (!orderTotal && !contractTotal && !coverage) return null;
  return [
    `Tổng giá trị đơn hàng liên kết hiện là ${orderTotal ?? "chưa xác định"}`,
    `tổng giá trị hợp đồng là ${contractTotal ?? "chưa xác định"}`,
    `đang cover được ${coverage ?? "chưa xác định"} giá trị hợp đồng`,
    uncovered ? `phần chưa được đơn hàng cover là ${uncovered}` : null,
    "cần bổ sung hoặc xác minh lại các liên kết đơn hàng/phụ lục/giai đoạn trước khi chấp nhận.",
  ].filter(Boolean).join("; ");
}

function closingCashDescription(card: DecisionCardArtifact): string {
  const metrics = card.payload.finance_metrics ?? [];
  const worstMonth = metricValue(metrics, "WORST_RESERVE_GAP_MONTH");
  const worstGap = formatVnd(metricValue(metrics, "WORST_RESERVE_GAP"));
  const pressure =
    typeof worstMonth === "string" && worstMonth && worstGap
      ? ` Tín hiệu áp lực dòng tiền hiện có cho thấy worst-gap ở ${worstMonth} là ${worstGap} ở phạm vi dữ liệu hiện có.`
      : "";
  return (
    "Yêu cầu bổ sung thông tin về closing cash riêng cho từng hợp đồng; khi chưa có số này, Final Risk chỉ dùng được tín hiệu áp lực dòng tiền đang có và không tự thay thế bằng projected_closing_cash hoặc dữ liệu tương đương." +
    pressure
  );
}

function executionCapacityDescription(recommendationText: string): string {
  return translateText(recommendationText).replace(
    /^Cảnh báo nguồn\s+AL-003:\s*Contract execution risk\.?\s*/i,
    "",
  );
}

function negotiationConditionDescription(
  card: DecisionCardArtifact,
  reason: DecisionReason,
  recommendationText: string,
): string {
  if (isMarginReason(reason)) {
    return marginConditionDescription(card) ?? translateText(recommendationText);
  }
  if (isOrderCoverageReason(reason)) {
    return orderCoverageDescription(card) ?? translateText(recommendationText);
  }
  if (isClosingCashReason(reason)) {
    return closingCashDescription(card);
  }
  if (isExecutionCapacityReason(reason)) {
    return executionCapacityDescription(recommendationText);
  }
  return translateText(recommendationText);
}

export function App() {
  const {
    state,
    selectContract,
    runSelectedContract,
    clearError,
    runArtifacts,
    approvalRequests,
    submittingInteraction,
    decideApproval,
    submitBankingAmount,
    submitPrecheckEvidence,
    submitDocument,
    confirmTermsSent,
    demoPauseWorkflow,
    demoResumeWorkflow,
  } = useWorkflowDashboard();
  const [assessment, setAssessment] = useState<ArtifactEnvelope | null>(null);
  const [decisionCardOpen, setDecisionCardOpen] = useState(false);
  const [approvalOpen, setApprovalOpen] = useState(false);
  const [missingDataOpen, setMissingDataOpen] = useState(false);
  const [negotiationOpen, setNegotiationOpen] = useState(false);
  const [negotiationConfirmOpen, setNegotiationConfirmOpen] = useState(false);
  const [lastAutoApprovalId, setLastAutoApprovalId] = useState<string | null>(null);
  const [lastAutoReviewKey, setLastAutoReviewKey] = useState<string | null>(null);

  const dashboard = state.dashboard;
  const playback = useWorkflowPlayback(dashboard);
  const currentCard = useMemo(
    () => (dashboard ? decisionCardArtifact(dashboard, runArtifacts) : null),
    [dashboard, runArtifacts],
  );
  const negotiationConditions = useMemo(() => {
    if (!currentCard) return [];
    const sourceConditions = currentCard.payload.conditions ?? [];
    if (currentCard.payload.analysis_source !== "OPENAI") {
      return sourceConditions;
    }
    return recommendedActionConditions(currentCard, currentCard.payload.reasons ?? [], sourceConditions);
  }, [currentCard]);
  const presentationCard = playback.canRevealDecisionCard ? currentCard : null;
  const activeApproval = useMemo(
    () => (dashboard ? pendingApproval(dashboard, approvalRequests) : null),
    [approvalRequests, dashboard],
  );
  const approvalView = useMemo(
    () => approvalRequestView(activeApproval),
    [activeApproval],
  );
  const approvalSubject = useMemo(
    () =>
      dashboard
        ? approvalSubjectSummary(dashboard, activeApproval, runArtifacts)
        : null,
    [activeApproval, dashboard, runArtifacts],
  );
  const missingInteraction = useMemo(
    () => (dashboard ? pendingMissingInteraction(dashboard) : null),
    [dashboard],
  );
  const negotiationInteraction = useMemo(
    () => (dashboard ? pendingNegotiationInteraction(dashboard) : null),
    [dashboard],
  );
  const notEvaluableReview = useMemo(
    () => (dashboard ? pendingNotEvaluableReview(dashboard) : null),
    [dashboard],
  );
  const currentMissingRequestId = missingInteraction?.request_ids[0] ?? null;
  const documentTypes = useMemo(
    () => allowedDocumentTypes(runArtifacts, currentMissingRequestId),
    [currentMissingRequestId, runArtifacts],
  );
  const decisionDashboard = useMemo(() => {
    if (!dashboard) return null;
    return {
      ...dashboard,
      progressPercent: playback.percent,
      decisionCard: playback.canRevealDecisionCard
        ? dashboard.decisionCard
        : {
            ...dashboard.decisionCard,
            available: false,
            recommendation_label_vi: "Decision Card đang được đồng bộ theo tiến trình",
          },
    };
  }, [dashboard, playback.canRevealDecisionCard, playback.percent]);
  const decisionData = useMemo(
    () =>
      decisionDashboard
        ? decisionDashboardData(decisionDashboard, presentationCard)
        : null,
    [decisionDashboard, presentationCard],
  );
  const isFinalDecisionAction =
    activeApproval?.command.action_type === "CONFIRM_FINAL_CONTRACT_DECISION";
  const isNegotiationOutcomeApproval =
    activeApproval?.command.action_type === "CONFIRM_NEGOTIATION_OUTCOME";
  const negotiationOutcomeArtifact = useMemo(
    () =>
      isNegotiationOutcomeApproval && activeApproval
        ? runArtifacts.find(
            (item) =>
              item.artifact_id === activeApproval.subject_artifact_id &&
              item.artifact_type === "NEGOTIATION_OUTCOME" &&
              item.version === activeApproval.subject_artifact_version &&
              item.input_hash === activeApproval.subject_input_hash &&
              ["VALID", "VALID_WITH_WARNINGS"].includes(item.validation_status),
          ) ?? null
        : null,
    [activeApproval, isNegotiationOutcomeApproval, runArtifacts],
  );
  const currentCardReference = useMemo(
    () =>
      dashboard && currentCard
        ? dashboard.runArtifacts.find(
            (item) =>
              item.artifact_id === currentCard.artifact_id &&
              item.artifact_type === "DECISION_CARD" &&
              item.version === currentCard.version,
          ) ?? null
        : null,
    [currentCard, dashboard],
  );
  const isFinalDecisionApproval = Boolean(
    isFinalDecisionAction &&
      activeApproval &&
      dashboard &&
      currentCard &&
      currentCardReference &&
      currentCard.payload.analysis_source === "OPENAI" &&
      currentCard.payload.recommendation !== "NOT_EVALUABLE" &&
      dashboard.decisionCard.recommendation !== "NOT_EVALUABLE" &&
      activeApproval.workflow_run_id === dashboard.workflowRunId &&
      dashboard.approvalRequestIds.includes(activeApproval.request_id) &&
      activeApproval.subject_artifact_id === currentCard.artifact_id &&
      activeApproval.subject_artifact_version === currentCard.version &&
      dashboard.decisionCard.artifact_id === currentCard.artifact_id,
  );
  const isExactNotEvaluableReview = Boolean(
    dashboard &&
      currentCard &&
      currentCardReference &&
      currentCardReference.validation_status === "VALID" &&
      notEvaluableReview &&
      currentCard.payload.recommendation === "NOT_EVALUABLE" &&
      dashboard.decisionCard.recommendation === "NOT_EVALUABLE" &&
      dashboard.decisionCard.artifact_id === currentCard.artifact_id &&
      notEvaluableReview.subject_artifact_id === currentCard.artifact_id &&
      notEvaluableReview.subject_artifact_version === currentCard.version &&
      currentCardReference.artifact_id ===
        notEvaluableReview.subject_artifact_id &&
      currentCardReference.version ===
        notEvaluableReview.subject_artifact_version,
  );
  const modalCard =
    isFinalDecisionApproval || isExactNotEvaluableReview
      ? currentCard
      : presentationCard;

  useEffect(() => {
    setAssessment(null);
    setDecisionCardOpen(false);
    setApprovalOpen(false);
    setMissingDataOpen(false);
    setNegotiationOpen(false);
    setNegotiationConfirmOpen(false);
    setLastAutoApprovalId(null);
    setLastAutoReviewKey(null);
  }, [state.workflowRunId]);

  useEffect(() => {
    const requestId = activeApproval?.request_id ?? null;
    if (requestId && requestId !== lastAutoApprovalId) {
      if (isFinalDecisionAction && !isFinalDecisionApproval) return;
      if (isNegotiationOutcomeApproval) {
        setNegotiationConfirmOpen(true);
        setDecisionCardOpen(false);
        setApprovalOpen(false);
        setMissingDataOpen(false);
      } else if (isFinalDecisionApproval) {
        setDecisionCardOpen(true);
        setApprovalOpen(false);
        setMissingDataOpen(false);
      } else {
        setDecisionCardOpen(false);
        setMissingDataOpen(false);
        setApprovalOpen(true);
      }
      setLastAutoApprovalId(requestId);
    }
  }, [
    activeApproval?.request_id,
    isFinalDecisionAction,
    isFinalDecisionApproval,
    isNegotiationOutcomeApproval,
    lastAutoApprovalId,
  ]);

  const negotiationInteractionKey = negotiationInteraction
    ? `${negotiationInteraction.interaction_type}:${negotiationInteraction.request_ids.join(",")}`
    : null;
  useEffect(() => {
    if (negotiationInteractionKey) setNegotiationOpen(true);
  }, [negotiationInteractionKey]);

  useEffect(() => {
    if (!dashboard || !notEvaluableReview || !isExactNotEvaluableReview) return;
    const reviewKey = `${dashboard.workflowRunId}:${notEvaluableReview.subject_artifact_id}:${notEvaluableReview.subject_artifact_version}`;
    if (reviewKey === lastAutoReviewKey) return;
    setDecisionCardOpen(true);
    setApprovalOpen(false);
    setMissingDataOpen(false);
    setLastAutoReviewKey(reviewKey);
  }, [
    dashboard,
    isExactNotEvaluableReview,
    lastAutoReviewKey,
    notEvaluableReview,
  ]);

  const openAssessment = useCallback(
    (artifactIds: readonly string[]) => {
      const selected = selectAssessmentArtifact(artifactIds, runArtifacts);
      if (selected) setAssessment(selected);
    },
    [runArtifacts],
  );
  const canOpenAssessment = useCallback(
    (artifactIds: readonly string[]) =>
      hasAssessmentArtifact(artifactIds, runArtifacts),
    [runArtifacts],
  );

  const handleApprovalDecision = useCallback(
    async (requestId: string, decision: ApprovalDecision) => {
      const succeeded = await decideApproval(requestId, decision);
      if (succeeded) {
        setApprovalOpen(false);
        setDecisionCardOpen(false);
        setNegotiationConfirmOpen(false);
      }
    },
    [decideApproval],
  );

  const handleBankingAmount = useCallback(
    async (payload: BankingAmountSubmission) => {
      const succeeded = await submitBankingAmount(payload);
      if (succeeded) setMissingDataOpen(false);
    },
    [submitBankingAmount],
  );
  const handlePrecheckEvidence = useCallback(
    async (payload: BankingPrecheckEvidenceSubmission) => {
      const succeeded = await submitPrecheckEvidence(payload);
      if (succeeded) setMissingDataOpen(false);
    },
    [submitPrecheckEvidence],
  );
  const handleDocument = useCallback(
    async (payload: DocumentEvidenceSubmission) => {
      const succeeded = await submitDocument(payload);
      if (succeeded) setMissingDataOpen(false);
    },
    [submitDocument],
  );
  const handleTermsSent = useCallback(async () => {
    if (!dashboard || !currentCard) return;
    const succeeded = await confirmTermsSent({
      workflow_run_id: dashboard.workflowRunId,
      decision_card_artifact_id: currentCard.artifact_id,
    });
    if (succeeded) setNegotiationOpen(false);
  }, [confirmTermsSent, currentCard, dashboard]);
  const bootstrapping = state.phase === "bootstrapping";
  const starting = state.phase === "starting";
  const loadingWorkflow = state.phase === "refreshing" || starting;
  const isCurrentApprovalSubject = Boolean(
    dashboard &&
      activeApproval &&
      activeApproval.workflow_run_id === dashboard.workflowRunId &&
      dashboard.runArtifacts.some(
        (item) =>
          item.artifact_id === activeApproval.subject_artifact_id &&
          item.version === activeApproval.subject_artifact_version,
      ),
  );

  return (
    <div className="app-shell">
      <header className="app-header">
        <a className="brand" href="/" aria-label="Trang chủ OPC MIS">
          <span className="brand__mark">OPC</span>
          <span className="brand__copy">
            <strong>MIS Agentic AI</strong>
            <small>Bảng điều hành dành cho Founder</small>
          </span>
        </a>
        <div className="system-badges" aria-label="Tình trạng hệ thống">
          <span className={`system-badge ${state.catalog ? "system-badge--live" : ""}`}>
            <i aria-hidden="true" />
            {state.catalog ? "Máy chủ đang hoạt động" : "Đang kết nối máy chủ"}
          </span>
          <span
            className={`system-badge ${state.capabilities?.openai_enabled ? "system-badge--ai" : ""}`}
          >
            <i aria-hidden="true" />
            {state.capabilities?.openai_enabled
              ? "OpenAI đã cấu hình"
              : "OpenAI chưa được cấu hình"}
          </span>
        </div>
      </header>

      <div className="page-heading">
        <div>
          <p>OPC · CƠ HỘI KINH DOANH</p>
          <h1>Từ hợp đồng đến quyết định, trong một luồng kiểm soát</h1>
        </div>
        <span className="page-heading__contract">
          {state.selectedContractId || "Chưa chọn hợp đồng"}
        </span>
      </div>

      {state.errorMessage ? (
        <div className="global-notice">
          <Notice tone="danger" title="Không thể cập nhật dữ liệu">
            {state.errorMessage}
          </Notice>
          <button type="button" onClick={clearError} aria-label="Đóng thông báo">
            ×
          </button>
        </div>
      ) : null}

      {activeApproval || notEvaluableReview || missingInteraction || negotiationInteraction ? (
        <section className="workflow-attention" role="status" aria-live="polite">
          <div>
            <strong>
              {activeApproval
                ? "Quy trình đang chờ Founder xác nhận hoặc phê duyệt"
                : notEvaluableReview
                  ? notEvaluableReview.title_vi
                  : negotiationInteraction
                    ? negotiationInteraction.title_vi
                    : "Quy trình đang chờ bổ sung dữ liệu"}
            </strong>
            <p>
              {activeApproval
                ? "Hành động được bảo vệ chưa được thực hiện. Bạn có thể mở lại yêu cầu nếu đã đóng popup."
                : notEvaluableReview
                  ? notEvaluableReview.instruction_vi
                  : negotiationInteraction?.instruction_vi ?? missingInteraction?.instruction_vi}
            </p>
          </div>
          {activeApproval ? (
            <button
              type="button"
              disabled={isFinalDecisionAction && !isFinalDecisionApproval}
              onClick={() =>
                isNegotiationOutcomeApproval
                  ? setNegotiationConfirmOpen(true)
                  : isFinalDecisionApproval
                  ? setDecisionCardOpen(true)
                  : setApprovalOpen(true)
              }
            >
              {isFinalDecisionAction && !isFinalDecisionApproval
                ? "Đang hoàn thiện Decision Card…"
                : "Mở yêu cầu xác nhận/phê duyệt"}
            </button>
          ) : notEvaluableReview ? (
            <button
              type="button"
              disabled={!isExactNotEvaluableReview}
              onClick={() => setDecisionCardOpen(true)}
            >
              {isExactNotEvaluableReview
                ? "Mở Decision Card để xem xét"
                : "Decision Card hiện hành không khớp yêu cầu xem xét"}
            </button>
          ) : negotiationInteraction ? (
            <button type="button" onClick={() => setNegotiationOpen(true)}>
              Mở bước đàm phán đang chờ
            </button>
          ) : (
            <button type="button" onClick={() => setMissingDataOpen(true)}>
              Mở biểu mẫu bổ sung dữ liệu
            </button>
          )}
        </section>
      ) : null}

      <main className="workspace">
        <InputPanel
          catalog={state.catalog}
          selectedContractId={state.selectedContractId}
          dashboard={dashboard}
          bootstrapping={bootstrapping}
          starting={starting}
          demoControlBusy={submittingInteraction}
          onSelectContract={selectContract}
          onStart={() => void runSelectedContract()}
          onDemoPause={() => void demoPauseWorkflow()}
          onDemoResume={() => void demoResumeWorkflow()}
        />
        <WorkflowTimeline
          dashboard={dashboard}
          loading={loadingWorkflow}
          playback={playback}
          onOpenAssessment={openAssessment}
          canOpenAssessment={canOpenAssessment}
        />
        <Panel
          eyebrow="03 · QUYẾT ĐỊNH"
          title="Decision Dashboard"
          className="decision-panel"
        >
          {decisionData ? (
            <>
              <DecisionDashboard
                data={decisionData}
              />
              <section className="founder-actions" aria-labelledby="founder-actions-title">
                <header>
                  <span>ĐIỂM DỪNG CÓ KIỂM SOÁT</span>
                  <h3 id="founder-actions-title">Những chỗ đang chờ Founder phê duyệt</h3>
                </header>

                <div className="pending-actions-list" style={{ marginBottom: "16px", display: "flex", flexDirection: "column", gap: "10px" }}>
                  {activeApproval && (
                    <div style={{ background: "rgba(224, 86, 36, 0.05)", padding: "12px", borderRadius: "8px", borderLeft: "4px solid var(--color-red-650)" }}>
                      <strong style={{ display: "block", color: "var(--color-red-700)", marginBottom: "4px" }}>Yêu cầu phê duyệt đang chờ</strong>
                      <span style={{ fontSize: "12px", display: "block", fontWeight: 600 }}>{approvalSubject?.title}</span>
                      <span style={{ fontSize: "11px", color: "var(--color-ink-500)", marginTop: "2px", display: "block" }}>
                        {approvalSubject?.description}
                      </span>
                    </div>
                  )}
                  {notEvaluableReview && (
                    <div style={{ background: "rgba(217, 119, 6, 0.05)", padding: "12px", borderRadius: "8px", borderLeft: "4px solid var(--color-amber-600)" }}>
                      <strong style={{ display: "block", color: "var(--color-amber-700)", marginBottom: "4px" }}>Yêu cầu xem xét tài liệu/sơ đồ quyết định</strong>
                      <span style={{ fontSize: "12px", display: "block" }}>{notEvaluableReview.title_vi || "Yêu cầu Founder xem xét hồ sơ quyết định"}</span>
                      <span style={{ fontSize: "11px", color: "var(--color-ink-500)", marginTop: "2px", display: "block" }}>
                        {notEvaluableReview.instruction_vi}
                      </span>
                    </div>
                  )}
                  {missingInteraction && (
                    <div style={{ background: "rgba(37, 99, 235, 0.05)", padding: "12px", borderRadius: "8px", borderLeft: "4px solid var(--color-blue-500)" }}>
                      <strong style={{ display: "block", color: "var(--color-blue-700)", marginBottom: "4px" }}>Yêu cầu bổ sung dữ liệu/tài liệu</strong>
                      <span style={{ fontSize: "12px", display: "block", fontWeight: 600 }}>{missingInteraction.title_vi}</span>
                      <span style={{ fontSize: "11px", color: "var(--color-ink-500)", marginTop: "2px", display: "block" }}>
                        {missingInteraction.instruction_vi}
                      </span>
                      {/* Hiển thị chi tiết từng loại tài liệu cần bổ sung */}
                      {!!documentTypes.length && (
                        <div style={{ marginTop: "6px", fontSize: "11px" }}>
                          <span style={{ fontWeight: 600, color: "var(--color-ink-700)" }}>Danh sách tài liệu cần bổ sung:</span>
                          <ul style={{ margin: "2px 0 0 0", paddingLeft: "1.2rem", color: "var(--color-red-650)", fontWeight: 600 }}>
                            {documentTypes.map((type) => (
                              <li key={type}>{documentRequirementLabel(type)}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}
                  {!activeApproval && !notEvaluableReview && !missingInteraction && (
                    <p style={{ fontSize: "12px", color: "var(--color-ink-450)", margin: 0 }}>
                      Hiện không có yêu cầu nào cần Founder xử lý.
                    </p>
                  )}
                </div>

                {isFinalDecisionAction && !isFinalDecisionApproval ? (
                  <button type="button" disabled>
                    Đang hoàn thiện Decision Card theo tiến trình…
                  </button>
                ) : activeApproval ? (
                  <button
                    type="button"
                    onClick={() =>
                      isNegotiationOutcomeApproval
                        ? setNegotiationConfirmOpen(true)
                        : isFinalDecisionApproval
                        ? setDecisionCardOpen(true)
                        : setApprovalOpen(true)
                    }
                  >
                    {isNegotiationOutcomeApproval
                      ? "Mở xác nhận kết quả đàm phán"
                      : isFinalDecisionApproval
                      ? "Mở Decision Card để xem xét"
                      : "Mở yêu cầu xác nhận/phê duyệt đang chờ"}
                  </button>
                ) : notEvaluableReview ? (
                  <button
                    type="button"
                    disabled={!isExactNotEvaluableReview}
                    onClick={() => setDecisionCardOpen(true)}
                  >
                    {isExactNotEvaluableReview
                      ? "Mở Decision Card chỉ để xem xét"
                      : "Decision Card hiện hành không khớp yêu cầu xem xét"}
                  </button>
                ) : missingInteraction ? (
                  <button type="button" onClick={() => setMissingDataOpen(true)}>
                    Bổ sung dữ liệu để quy trình tiếp tục
                  </button>
                ) : null}

                {/* Nút xem Decision Card — chỉ hiện khi có card và không trùng với nút hành động ở trên */}
                {presentationCard && !isFinalDecisionApproval && !isExactNotEvaluableReview && (
                  <button
                    type="button"
                    style={{ marginTop: activeApproval || notEvaluableReview || missingInteraction ? "8px" : undefined, background: "var(--color-ink-100)", color: "var(--color-ink-800)", border: "1px solid var(--color-line-strong)" }}
                    onClick={() => setDecisionCardOpen(true)}
                  >
                    Xem Decision Card hiện hành
                  </button>
                )}
              </section>
            </>
          ) : (
            <div className="decision-empty">
              <span aria-hidden="true">◇</span>
              <h3>Chưa có lượt đánh giá</h3>
              <p>
                Decision Dashboard và Decision Card chỉ xuất hiện theo đúng tiến độ của quy trình.
              </p>
            </div>
          )}
        </Panel>
      </main>

      <footer className="app-footer">
        <span>OPC MIS · Quy trình có kiểm soát và có thể kiểm toán</span>
        <span>Dữ liệu TeamPack được cấu hình tại máy chủ</span>
      </footer>

      <AssessmentDialog artifact={assessment} runArtifacts={runArtifacts} onClose={() => setAssessment(null)} />
      <DecisionCardModal
        open={decisionCardOpen}
        card={modalCard}
        current_decision_card_artifact_id={
          dashboard?.decisionCard.artifact_id ?? null
        }
        pending_approval={
          pendingDecisionApproval(isFinalDecisionApproval ? activeApproval : null)
        }
        review_instruction={
          isExactNotEvaluableReview ? notEvaluableReview?.instruction_vi : null
        }
        submitting={submittingInteraction}
        onClose={() => setDecisionCardOpen(false)}
        onApprove={(requestId) => handleApprovalDecision(requestId, "APPROVE")}
        onReject={(requestId) => handleApprovalDecision(requestId, "REJECT")}
      />
      <ApprovalDialog
        open={approvalOpen && !isNegotiationOutcomeApproval}
        request={approvalView}
        subject={approvalSubject}
        is_current_subject={isCurrentApprovalSubject}
        submitting={submittingInteraction}
        onClose={() => setApprovalOpen(false)}
        onDecision={handleApprovalDecision}
      />
        {negotiationOpen && negotiationInteraction?.interaction_type === "NEGOTIATION_TERMS_SENT_CONFIRMATION" ? (
          <div className="approval-dialog" role="dialog" aria-modal="true" aria-labelledby="terms-sent-title">
          <article>
            <header>
              <p>Vòng đàm phán có điều kiện</p>
              <h2 id="terms-sent-title">Xác nhận đã gửi điều kiện đàm phán</h2>
            </header>
            <p>Hãy xem lại các điều kiện trên Decision Card trước khi xác nhận. Thao tác này chỉ ghi nhận việc đã gửi; hệ thống không tự gửi email hoặc cập nhật CRM.</p>
            <ul>
              {negotiationConditions.map((condition) => (
                <li key={condition.condition_id ?? condition.title}><strong>{condition.title}</strong>: {condition.description}</li>
              ))}
            </ul>
            <footer>
              <button type="button" disabled={submittingInteraction} onClick={() => setNegotiationOpen(false)}>Đóng</button>
              <button type="button" disabled={submittingInteraction || !currentCard} onClick={() => void handleTermsSent()}>Xác nhận đã gửi cho khách hàng</button>
            </footer>
          </article>
        </div>
      ) : null}
      <NegotiationConfirmDialog
        open={negotiationConfirmOpen}
        request={isNegotiationOutcomeApproval ? activeApproval : null}
        artifact={negotiationOutcomeArtifact}
        submitting={submittingInteraction}
        onClose={() => setNegotiationConfirmOpen(false)}
        onDecision={handleApprovalDecision}
      />
      <MissingDataDialog
        open={missingDataOpen}
        workflow_run_id={dashboard?.workflowRunId ?? ""}
        interaction={missingInteraction}
        allowed_document_types={documentTypes}
        submitting={submittingInteraction}
        onClose={() => setMissingDataOpen(false)}
        onDocumentSubmit={handleDocument}
        onPrecheckEvidenceSubmit={handlePrecheckEvidence}
        onBankingAmountSubmit={handleBankingAmount}
      />
    </div>
  );
}
