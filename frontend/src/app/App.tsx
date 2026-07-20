import { useCallback, useEffect, useMemo, useState } from "react";

import { ArtifactAssessmentView, type ArtifactEnvelope } from "../features/artifacts";
import { DecisionCardModal, DecisionDashboard } from "../features/decision";
import { ApprovalDialog, type ApprovalDecision } from "../features/governance";
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
  pendingNotEvaluableReview,
  selectAssessmentArtifact,
} from "./dashboardIntegration";

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
  } = useWorkflowDashboard();
  const [assessment, setAssessment] = useState<ArtifactEnvelope | null>(null);
  const [decisionCardOpen, setDecisionCardOpen] = useState(false);
  const [approvalOpen, setApprovalOpen] = useState(false);
  const [missingDataOpen, setMissingDataOpen] = useState(false);
  const [lastAutoApprovalId, setLastAutoApprovalId] = useState<string | null>(null);
  const [lastAutoReviewKey, setLastAutoReviewKey] = useState<string | null>(null);

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
    setLastAutoApprovalId(null);
    setLastAutoReviewKey(null);
  }, [state.workflowRunId]);

  useEffect(() => {
    const requestId = activeApproval?.request_id ?? null;
    if (requestId && requestId !== lastAutoApprovalId) {
      if (isFinalDecisionAction && !isFinalDecisionApproval) return;
      if (isFinalDecisionApproval) {
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
    lastAutoApprovalId,
  ]);

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
            <small>Bảng điều hành dành cho Nhà sáng lập</small>
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

      {activeApproval || notEvaluableReview || missingInteraction ? (
        <section className="workflow-attention" role="status" aria-live="polite">
          <div>
            <strong>
              {activeApproval
                ? "Quy trình đang chờ Nhà sáng lập xác nhận hoặc phê duyệt"
                : notEvaluableReview
                  ? notEvaluableReview.title_vi
                : "Quy trình đang chờ bổ sung dữ liệu"}
            </strong>
            <p>
              {activeApproval
                ? "Hành động được bảo vệ chưa được thực hiện. Bạn có thể mở lại yêu cầu nếu đã đóng popup."
                : notEvaluableReview
                  ? notEvaluableReview.instruction_vi
                : missingInteraction?.instruction_vi}
            </p>
          </div>
          {activeApproval ? (
            <button
              type="button"
              disabled={isFinalDecisionAction && !isFinalDecisionApproval}
              onClick={() =>
                isFinalDecisionApproval
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
          onSelectContract={selectContract}
          onStart={() => void runSelectedContract()}
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
                onOpenDecisionCard={
                  presentationCard ? () => setDecisionCardOpen(true) : undefined
                }
              />
              <section className="founder-actions" aria-labelledby="founder-actions-title">
                <header>
                  <span>ĐIỂM DỪNG CÓ KIỂM SOÁT</span>
                  <h3 id="founder-actions-title">Hành động của Nhà sáng lập</h3>
                </header>
                {isFinalDecisionAction && !isFinalDecisionApproval ? (
                  <button type="button" disabled>
                    Đang hoàn thiện Decision Card theo tiến trình…
                  </button>
                ) : activeApproval ? (
                  <button
                    type="button"
                    onClick={() =>
                      isFinalDecisionApproval
                        ? setDecisionCardOpen(true)
                        : setApprovalOpen(true)
                    }
                  >
                    {isFinalDecisionApproval
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
                ) : (
                  <p>Hiện không có yêu cầu nào cần Nhà sáng lập xử lý.</p>
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
        open={approvalOpen}
        request={approvalView}
        subject={approvalSubject}
        is_current_subject={isCurrentApprovalSubject}
        submitting={submittingInteraction}
        onClose={() => setApprovalOpen(false)}
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
