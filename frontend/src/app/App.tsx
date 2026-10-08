import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArtifactDetailDialog,
  type ArtifactEnvelope,
} from "../features/artifacts";
import { DecisionCardModal, DecisionDashboard } from "../features/decision";
import { ApprovalDialog, type ApprovalDecision } from "../features/governance";
import {
  NegotiationConfirmDialog,
  NegotiationOutcomeForm,
} from "../features/negotiation";
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
import { StatusBadge } from "../shared/components/StatusBadge";
import { useDialogFocus } from "../shared/useDialogFocus";
import { useScrollTopOnChange } from "../shared/useScrollTopOnChange";
import { isTerminalExecutionStatus } from "../shared/workflowLabels";
import { WorkflowEvents } from "../features/workspace/WorkflowEvents";
import {
  AssessmentIndex,
  ContractMetrics,
  DecisionLimits,
  EvidenceIndex,
  WorkspaceIcon,
  workspaceViews,
  type WorkspaceView,
} from "../features/workspace/ContractWorkspace";
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
    submitNegotiation,
  } = useWorkflowDashboard();
  const [assessment, setAssessment] = useState<ArtifactEnvelope | null>(null);
  const [decisionCardOpen, setDecisionCardOpen] = useState(false);
  const [approvalOpen, setApprovalOpen] = useState(false);
  const [missingDataOpen, setMissingDataOpen] = useState(false);
  const [negotiationOpen, setNegotiationOpen] = useState(false);
  const [negotiationConfirmOpen, setNegotiationConfirmOpen] = useState(false);
  const [lastAutoApprovalId, setLastAutoApprovalId] = useState<string | null>(
    null,
  );
  const [lastAutoReviewKey, setLastAutoReviewKey] = useState<string | null>(
    null,
  );
  const [view, setView] = useState<WorkspaceView>("decision");
  useScrollTopOnChange(view);

  const dashboard = state.dashboard;
  const playback = useWorkflowPlayback(dashboard);
  const currentCard = useMemo(
    () => (dashboard ? decisionCardArtifact(dashboard, runArtifacts) : null),
    [dashboard, runArtifacts],
  );
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
  const decisionData = useMemo(
    () =>
      dashboard
        ? decisionDashboardData(
            { ...dashboard, progressPercent: playback.percent },
            presentationCard,
            { revealPending: !playback.canRevealDecisionCard },
          )
        : null,
    [dashboard, playback.canRevealDecisionCard, playback.percent, presentationCard],
  );
  const isFinalDecisionAction =
    activeApproval?.command.action_type === "CONFIRM_FINAL_CONTRACT_DECISION";
  const isNegotiationOutcomeApproval =
    activeApproval?.command.action_type === "CONFIRM_NEGOTIATION_OUTCOME";
  const negotiationOutcomeArtifact = useMemo(
    () =>
      isNegotiationOutcomeApproval && activeApproval
        ? (runArtifacts.find(
            (item) =>
              item.artifact_id === activeApproval.subject_artifact_id &&
              item.artifact_type === "NEGOTIATION_OUTCOME" &&
              item.version === activeApproval.subject_artifact_version &&
              item.input_hash === activeApproval.subject_input_hash &&
              ["VALID", "VALID_WITH_WARNINGS"].includes(item.validation_status),
          ) ?? null)
        : null,
    [activeApproval, isNegotiationOutcomeApproval, runArtifacts],
  );
  const currentCardReference = useMemo(
    () =>
      dashboard && currentCard
        ? (dashboard.runArtifacts.find(
            (item) =>
              item.artifact_id === currentCard.artifact_id &&
              item.artifact_type === "DECISION_CARD" &&
              item.version === currentCard.version,
          ) ?? null)
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
  const handleNegotiationOutcome = useCallback(
    async (payload: Parameters<typeof submitNegotiation>[0]) => {
      const succeeded = await submitNegotiation(payload);
      if (succeeded) setNegotiationOpen(false);
    },
    [submitNegotiation],
  );

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

  const closeDialogs = useCallback(() => {
    setAssessment(null);
    setDecisionCardOpen(false);
    setApprovalOpen(false);
    setMissingDataOpen(false);
    setNegotiationOpen(false);
    setNegotiationConfirmOpen(false);
  }, []);
  useDialogFocus(
    Boolean(
      assessment ||
      decisionCardOpen ||
      approvalOpen ||
      missingDataOpen ||
      negotiationOpen ||
      negotiationConfirmOpen,
    ),
    closeDialogs,
    { escapeDisabled: submittingInteraction, fallbackFocusId: "workspace-content" },
  );

  return (
    <div className="app-shell">
      <a className="skip-link" href="#workspace-content">
        Đi đến nội dung
      </a>
      <aside className="workspace-sidebar">
        <a className="brand" href="/dashboard" aria-label="OPC MIS">
          <span className="brand__mark">O</span>
          <span>
            OPC <strong>MIS</strong>
          </span>
        </a>
        <div className="sidebar-section-label">KHÔNG GIAN LÀM VIỆC</div>
        <nav aria-label="Điều hướng hợp đồng">
          {workspaceViews.map((item) => (
            <button
              key={item.id}
              type="button"
              className={
                view === item.id
                  ? "sidebar-link sidebar-link--active"
                  : "sidebar-link"
              }
              aria-pressed={view === item.id}
              onClick={() => setView(item.id)}
            >
              <WorkspaceIcon name={item.icon} />
              {item.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-context">
          <span>Hợp đồng đang chọn</span>
          <strong>{state.selectedContractId || "Chưa chọn"}</strong>
          <p>{dashboard?.input.customerName || "Dữ liệu do máy chủ quản lý"}</p>
        </div>
        <div className="sidebar-footer">
          <span className="sidebar-footer__mark">OPC</span>
          <div>
            <strong>Founder workspace</strong>
            <small>Quyết định có kiểm soát</small>
          </div>
        </div>
      </aside>
      <div className="workspace-body">
        <header className="app-header">
          <div className="breadcrumb">
            <span>Hợp đồng</span>
            <span aria-hidden="true">/</span>
            <strong>{state.selectedContractId || "Chưa chọn hợp đồng"}</strong>
          </div>
          <div className="system-badges">
            <span>{state.catalog ? "Đã kết nối máy chủ" : "Đang kết nối"}</span>
            <span>
              {state.capabilities?.openai_enabled
                ? "OpenAI đã cấu hình"
                : "OpenAI chưa được cấu hình"}
            </span>
          </div>
        </header>
        <main id="workspace-content" className="workspace" tabIndex={-1}>
          <div className="page-heading">
            <div>
              <p>KHÔNG GIAN QUYẾT ĐỊNH</p>
              <h1>
                {state.selectedContractId ? (
                  <>
                    Hợp đồng{" "}
                    <span className="page-heading__id">
                      {state.selectedContractId}
                    </span>
                  </>
                ) : (
                  "Đánh giá hợp đồng"
                )}
              </h1>
              <span>
                {dashboard?.input.customerName ||
                  "Từ dữ liệu và bằng chứng đến quyết định của Founder."}
              </span>
            </div>
            <div className="page-heading__actions">
              {dashboard && (
                <StatusBadge
                  status={dashboard.businessStatus}
                  label={dashboard.businessStatusLabel}
                />
              )}
              <button type="button" onClick={() => setView("input")}>
                Chọn hợp đồng <span aria-hidden="true">⌄</span>
              </button>
            </div>
          </div>
          <nav className="workspace-tabs" aria-label="Các phần của hợp đồng">
            {workspaceViews.map((item) => (
              <button
                type="button"
                key={item.id}
                aria-pressed={view === item.id}
                className={
                  view === item.id
                    ? "workspace-tab workspace-tab--active"
                    : "workspace-tab"
                }
                onClick={() => setView(item.id)}
              >
                {item.label}
              </button>
            ))}
          </nav>
          {state.errorMessage ? (
            <div className="global-notice">
              <Notice tone="danger" title="Không thể cập nhật dữ liệu">
                {state.errorMessage}
              </Notice>
              <button
                type="button"
                onClick={clearError}
                aria-label="Đóng thông báo"
              >
                ×
              </button>
            </div>
          ) : null}

          {activeApproval ||
          notEvaluableReview ||
          missingInteraction ||
          negotiationInteraction ? (
            <section
              className="workflow-attention"
              role="status"
              aria-live="polite"
            >
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
                      : (negotiationInteraction?.instruction_vi ??
                        missingInteraction?.instruction_vi)}
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

          {!dashboard || view === "input" ? (
            <InputPanel
              catalog={state.catalog}
              selectedContractId={state.selectedContractId}
              dashboard={dashboard}
              bootstrapping={bootstrapping}
              starting={starting}
              onSelectContract={selectContract}
              onStart={() => void runSelectedContract()}
            />
          ) : null}
          {dashboard && view === "decision" && (
            <>
              <ContractMetrics dashboard={dashboard} />
              <section
                className="decision-workspace"
                aria-labelledby="decision-workspace-title"
              >
                <div className="section-heading">
                  <h2 id="decision-workspace-title">Đề xuất quyết định</h2>
                  <span>Decision Card · lượt xử lý hiện hành</span>
                </div>
                {decisionData ? (
                  <DecisionDashboard data={decisionData} />
                ) : (
                  <p className="empty-copy">Chưa có kết quả quyết định.</p>
                )}
                <DecisionLimits
                  limitations={presentationCard?.payload.limitations ?? []}
                />
                <div className="decision-workspace__actions">
                  {presentationCard && (
                    <button
                      type="button"
                      className="primary-action"
                      disabled={
                        (isFinalDecisionAction && !isFinalDecisionApproval) ||
                        Boolean(
                          notEvaluableReview && !isExactNotEvaluableReview,
                        )
                      }
                      onClick={() => setDecisionCardOpen(true)}
                    >
                      Xem Decision Card hiện hành{" "}
                      <span aria-hidden="true">↗</span>
                    </button>
                  )}
                  <button type="button" onClick={() => setView("evidence")}>
                    Xem bằng chứng
                  </button>
                  <p>
                    Đề xuất của hệ thống không thay thế quyết định của Founder.
                  </p>
                </div>
              </section>
              <AssessmentIndex
                dashboard={dashboard}
                artifacts={runArtifacts}
                compact
                onOpen={openAssessment}
                canOpen={canOpenAssessment}
              />
              <div className="workspace-footnote">
                <WorkspaceIcon name="evidence" />
                <p>
                  Precheck ngân hàng là mô phỏng, không ràng buộc. Phê duyệt
                  quyết định không đồng nghĩa cho phép gửi hồ sơ.
                </p>
              </div>
            </>
          )}
          {dashboard && view === "assessments" && (
            <>
              <ContractMetrics dashboard={dashboard} />
              <AssessmentIndex
                dashboard={dashboard}
                artifacts={runArtifacts}
                onOpen={openAssessment}
                canOpen={canOpenAssessment}
              />
              <EvidenceIndex
                artifacts={runArtifacts.filter((item) =>
                  /FINANCE|OPERATIONS|RISK/.test(item.artifact_type),
                )}
                onOpen={openAssessment}
                canOpen={canOpenAssessment}
              />
            </>
          )}
          {dashboard && view === "evidence" && (
            <EvidenceIndex
              artifacts={runArtifacts}
              onOpen={openAssessment}
              canOpen={canOpenAssessment}
            />
          )}
          {dashboard && view === "workflow" && (
            <>
              <WorkflowTimeline
                dashboard={dashboard}
                loading={loadingWorkflow}
                playback={playback}
                onOpenAssessment={openAssessment}
                canOpenAssessment={canOpenAssessment}
              />
              <WorkflowEvents
                runId={dashboard.workflowRunId}
                live={!isTerminalExecutionStatus(dashboard.status)}
              />
            </>
          )}
          {dashboard?.failureReason && view !== "workflow" && (
            <Notice tone="danger" title="Quy trình đã dừng an toàn">
              {dashboard.failureReason}
            </Notice>
          )}
          <footer className="app-footer">
            <span>
              {dashboard
                ? `Giai đoạn hiện tại: ${dashboard.currentStageLabel}`
                : "Chọn hợp đồng để bắt đầu lượt đánh giá."}
            </span>
            <span>TeamPack · nguồn dữ liệu tại máy chủ</span>
          </footer>
        </main>
      </div>

      <ArtifactDetailDialog
        artifact={assessment}
        runArtifacts={runArtifacts}
        onClose={() => setAssessment(null)}
      />
      <DecisionCardModal
        open={decisionCardOpen}
        card={modalCard}
        current_decision_card_artifact_id={
          dashboard?.decisionCard.artifact_id ?? null
        }
        pending_approval={pendingDecisionApproval(
          isFinalDecisionApproval ? activeApproval : null,
        )}
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
      {negotiationOpen &&
      negotiationInteraction?.interaction_type ===
        "NEGOTIATION_TERMS_SENT_CONFIRMATION" ? (
        <div
          className="approval-dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby="terms-sent-title"
        >
          <article>
            <header>
              <p>Vòng đàm phán có điều kiện</p>
              <h2 id="terms-sent-title">Xác nhận đã gửi điều kiện đàm phán</h2>
            </header>
            <p>
              Hãy xem lại các điều kiện trên Decision Card trước khi xác nhận.
              Thao tác này chỉ ghi nhận việc đã gửi; hệ thống không tự gửi email
              hoặc cập nhật CRM.
            </p>
            <ul>
              {(currentCard?.payload.conditions ?? []).map((condition) => (
                <li key={condition.condition_id ?? condition.title}>
                  <strong>{condition.title}</strong>: {condition.description}
                </li>
              ))}
            </ul>
            <footer>
              <button
                type="button"
                disabled={submittingInteraction}
                onClick={() => setNegotiationOpen(false)}
              >
                Đóng
              </button>
              <button
                type="button"
                disabled={submittingInteraction || !currentCard}
                onClick={() => void handleTermsSent()}
              >
                Xác nhận đã gửi cho khách hàng
              </button>
            </footer>
          </article>
        </div>
      ) : null}
      {negotiationOpen &&
      negotiationInteraction?.interaction_type ===
        "NEGOTIATION_OUTCOME_INPUT" &&
      currentCard ? (
        <NegotiationOutcomeForm
          workflowRunId={dashboard?.workflowRunId ?? ""}
          decisionCardArtifactId={currentCard.artifact_id}
          conditions={currentCard.payload.conditions ?? []}
          submitting={submittingInteraction}
          onClose={() => setNegotiationOpen(false)}
          onSubmit={handleNegotiationOutcome}
        />
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
