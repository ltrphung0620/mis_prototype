import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import {
  decideApprovalRequest,
  getApprovalRequests,
  getCaseArtifacts,
  getContractCatalog,
  getSystemCapabilities,
  getWorkflowDashboard,
  resumeCaseWorkflow,
  startCaseWorkflow,
  submitBankingAmountSupplement,
  submitBankingPrecheckEvidence,
  submitDocumentEvidence,
  confirmNegotiationTermsSent,
  submitNegotiationOutcome,
} from "../api/client";
import { createRunRequestId } from "../api/runRequestId";
import type {
  BankingAmountSupplementPayload,
  BankingPrecheckEvidencePayload,
  DocumentEvidencePayload,
  NegotiationOutcomePayload,
  NegotiationTermsSentPayload,
} from "../api/client";
import type { ApiApprovalRequest, ApiArtifactEnvelope } from "../api/types";
import { normalizeWorkflowDashboard } from "../api/normalize";
import {
  dashboardReducer,
  initialDashboardState,
  workflowStorageKey,
} from "../app/dashboardState";
import { isTerminalExecutionStatus } from "../shared/workflowLabels";

const DEFAULT_POLL_INTERVAL_MS = 1_500;

function errorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : "Không thể kết nối với máy chủ. Vui lòng thử lại.";
}

export function useWorkflowDashboard() {
  const [state, dispatch] = useReducer(dashboardReducer, initialDashboardState);
  const [refreshSequence, requestImmediateRefresh] = useReducer(
    (value: number) => value + 1,
    0,
  );
  const [runArtifacts, setRunArtifacts] = useState<readonly ApiArtifactEnvelope[]>([]);
  const [approvalRequests, setApprovalRequests] = useState<
    readonly ApiApprovalRequest[]
  >([]);
  const [submittingInteraction, setSubmittingInteraction] = useState(false);
  const pendingStartRef = useRef<{
    contractId: string;
    runRequestId: string;
  } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void Promise.all([
      getSystemCapabilities(controller.signal),
      getContractCatalog(controller.signal),
    ])
      .then(([capabilities, catalog]) => {
        dispatch({ type: "BOOTSTRAP_SUCCEEDED", capabilities, catalog });
        localStorage.removeItem(workflowStorageKey(catalog.datasetId));
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          dispatch({
            type: "REQUEST_FAILED",
            message: errorMessage(error),
            retainDashboard: false,
          });
        }
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!state.workflowRunId || !state.catalog) return undefined;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let requestController: AbortController | undefined;

    const poll = async () => {
      dispatch({ type: "REFRESH_STARTED" });
      requestController = new AbortController();
      try {
        const response = await getWorkflowDashboard(
          state.workflowRunId,
          requestController.signal,
        );
        if (stopped) return;
        const dashboard = normalizeWorkflowDashboard(response, state.catalog ?? undefined);
        let artifacts: readonly ApiArtifactEnvelope[] = [];
        let approvals: readonly ApiApprovalRequest[] = [];
        if (dashboard.evaluationCaseId) {
          const [caseArtifacts, caseApprovals] = await Promise.all([
            getCaseArtifacts(dashboard.evaluationCaseId, requestController.signal),
            getApprovalRequests(dashboard.evaluationCaseId, requestController.signal),
          ]);
          const runArtifactIds = new Set(
            dashboard.runArtifacts.map((item) => item.artifact_id),
          );
          const runApprovalIds = new Set(dashboard.approvalRequestIds);
          artifacts = caseArtifacts.filter(
            (item) =>
              item.evaluation_case_id === dashboard.evaluationCaseId &&
              runArtifactIds.has(item.artifact_id),
          );
          approvals = caseApprovals.filter(
            (item) =>
              item.workflow_run_id === dashboard.workflowRunId &&
              runApprovalIds.has(item.request_id),
          );
        }
        dispatch({ type: "DASHBOARD_RECEIVED", dashboard, receivedAt: Date.now() });
        setRunArtifacts(artifacts);
        setApprovalRequests(approvals);
        if (!isTerminalExecutionStatus(dashboard.status)) {
          const interval = Math.max(
            750,
            state.capabilities?.recommended_poll_interval_ms ?? DEFAULT_POLL_INTERVAL_MS,
          );
          timer = setTimeout(poll, interval);
        }
      } catch (error: unknown) {
        if (stopped || requestController.signal.aborted) return;
        dispatch({
          type: "REQUEST_FAILED",
          message: errorMessage(error),
          retainDashboard: true,
        });
        timer = setTimeout(poll, DEFAULT_POLL_INTERVAL_MS * 2);
      }
    };

    void poll();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
      requestController?.abort();
    };
  }, [
    refreshSequence,
    state.capabilities?.recommended_poll_interval_ms,
    state.catalog,
    state.workflowRunId,
  ]);

  useEffect(() => {
    setRunArtifacts([]);
    setApprovalRequests([]);
  }, [state.workflowRunId]);

  const selectContract = useCallback(
    (contractId: string) => {
      if (pendingStartRef.current?.contractId !== contractId) {
        pendingStartRef.current = null;
      }
      if (state.catalog) {
        localStorage.removeItem(workflowStorageKey(state.catalog.datasetId));
      }
      dispatch({ type: "SELECT_CONTRACT", contractId });
    },
    [state.catalog],
  );

  const runSelectedContract = useCallback(async () => {
    if (!state.selectedContractId || !state.catalog) return;
    const contractId = state.selectedContractId;
    const recoverableRun =
      state.dashboard?.status.toUpperCase() === "FAILED_SAFE" &&
      state.dashboard.contractId === contractId
        ? state.dashboard
        : null;
    const pendingStart = pendingStartRef.current;
    const runRequestId =
      pendingStart?.contractId === contractId
        ? pendingStart.runRequestId
        : createRunRequestId();
    pendingStartRef.current = { contractId, runRequestId };
    dispatch({ type: "RUN_REQUESTED", contractId });
    try {
      const result = recoverableRun
        ? await resumeCaseWorkflow(recoverableRun.workflowRunId)
        : await startCaseWorkflow(contractId, runRequestId);
      pendingStartRef.current = null;
      dispatch({
        type: "RUN_ACCEPTED",
        workflowRunId: result.workflow_run_id,
        contractId: result.contract_id,
      });
    } catch (error: unknown) {
      dispatch({
        type: "REQUEST_FAILED",
        message: errorMessage(error),
        retainDashboard: false,
      });
    }
  }, [state.catalog, state.dashboard, state.selectedContractId]);

  const clearError = useCallback(() => dispatch({ type: "CLEAR_ERROR" }), []);

  const runMutation = useCallback(
    async (operation: () => Promise<unknown>) => {
      setSubmittingInteraction(true);
      try {
        await operation();
        requestImmediateRefresh();
        return true;
      } catch (error: unknown) {
        dispatch({
          type: "REQUEST_FAILED",
          message: errorMessage(error),
          retainDashboard: true,
        });
        return false;
      } finally {
        setSubmittingInteraction(false);
      }
    },
    [],
  );

  const decideApproval = useCallback(
    (requestId: string, decision: "APPROVE" | "REJECT") =>
      runMutation(() => decideApprovalRequest(requestId, decision)),
    [runMutation],
  );

  const submitBankingAmount = useCallback(
    (payload: BankingAmountSupplementPayload) => {
      const caseId = state.dashboard?.evaluationCaseId;
      if (!caseId) return Promise.resolve(false);
      return runMutation(() => submitBankingAmountSupplement(caseId, payload));
    },
    [runMutation, state.dashboard?.evaluationCaseId],
  );

  const submitPrecheckEvidence = useCallback(
    (payload: BankingPrecheckEvidencePayload) => {
      const caseId = state.dashboard?.evaluationCaseId;
      if (!caseId) return Promise.resolve(false);
      return runMutation(() => submitBankingPrecheckEvidence(caseId, payload));
    },
    [runMutation, state.dashboard?.evaluationCaseId],
  );

  const submitDocument = useCallback(
    (payload: DocumentEvidencePayload) => {
      const caseId = state.dashboard?.evaluationCaseId;
      if (!caseId) return Promise.resolve(false);
      return runMutation(() => submitDocumentEvidence(caseId, payload));
    },
    [runMutation, state.dashboard?.evaluationCaseId],
  );

  const confirmTermsSent = useCallback(
    (payload: NegotiationTermsSentPayload) => {
      const caseId = state.dashboard?.evaluationCaseId;
      if (!caseId) return Promise.resolve(false);
      return runMutation(() => confirmNegotiationTermsSent(caseId, payload));
    },
    [runMutation, state.dashboard?.evaluationCaseId],
  );

  const submitNegotiation = useCallback(
    (payload: NegotiationOutcomePayload) => {
      const caseId = state.dashboard?.evaluationCaseId;
      if (!caseId) return Promise.resolve(false);
      return runMutation(() => submitNegotiationOutcome(caseId, payload));
    },
    [runMutation, state.dashboard?.evaluationCaseId],
  );

  return {
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
  };
}
