import type {
  ContractCatalog,
  NormalizedWorkflowDashboard,
  SystemCapabilities,
} from "../api/types";

export type DashboardPhase =
  | "bootstrapping"
  | "ready"
  | "starting"
  | "refreshing"
  | "error";

export interface DashboardState {
  phase: DashboardPhase;
  capabilities: SystemCapabilities | null;
  catalog: ContractCatalog | null;
  selectedContractId: string;
  workflowRunId: string;
  dashboard: NormalizedWorkflowDashboard | null;
  lastUpdatedAt: number | null;
  errorMessage: string | null;
}

export const initialDashboardState: DashboardState = {
  phase: "bootstrapping",
  capabilities: null,
  catalog: null,
  selectedContractId: "",
  workflowRunId: "",
  dashboard: null,
  lastUpdatedAt: null,
  errorMessage: null,
};

export type DashboardAction =
  | {
      type: "BOOTSTRAP_SUCCEEDED";
      catalog: ContractCatalog;
      capabilities: SystemCapabilities;
    }
  | { type: "SELECT_CONTRACT"; contractId: string }
  | { type: "RESTORE_RUN"; workflowRunId: string; contractId: string }
  | { type: "RUN_REQUESTED"; contractId: string }
  | { type: "RUN_ACCEPTED"; workflowRunId: string; contractId: string }
  | { type: "REFRESH_STARTED" }
  | { type: "DASHBOARD_RECEIVED"; dashboard: NormalizedWorkflowDashboard; receivedAt: number }
  | { type: "REQUEST_FAILED"; message: string; retainDashboard: boolean }
  | { type: "CLEAR_ERROR" };

function sameDataset(
  current: ContractCatalog | null,
  incoming: ContractCatalog,
): boolean {
  return Boolean(
    current &&
      current.datasetId === incoming.datasetId &&
      current.snapshotHash === incoming.snapshotHash,
  );
}

export function dashboardReducer(
  state: DashboardState,
  action: DashboardAction,
): DashboardState {
  switch (action.type) {
    case "BOOTSTRAP_SUCCEEDED": {
      const preserveRun = sameDataset(state.catalog, action.catalog);
      const contractStillExists = action.catalog.contracts.some(
        (item) => item.contractId === state.selectedContractId,
      );
      return {
        ...state,
        phase: "ready",
        catalog: action.catalog,
        capabilities: action.capabilities,
        selectedContractId: contractStillExists
          ? state.selectedContractId
          : action.catalog.contracts[0]?.contractId ?? "",
        workflowRunId: preserveRun ? state.workflowRunId : "",
        dashboard: preserveRun ? state.dashboard : null,
        lastUpdatedAt: preserveRun ? state.lastUpdatedAt : null,
        errorMessage: null,
      };
    }
    case "SELECT_CONTRACT":
      return {
        ...state,
        phase: "ready",
        selectedContractId: action.contractId,
        workflowRunId: "",
        dashboard: null,
        lastUpdatedAt: null,
        errorMessage: null,
      };
    case "RESTORE_RUN":
      return {
        ...state,
        workflowRunId: action.workflowRunId,
        selectedContractId: action.contractId,
        dashboard: null,
        lastUpdatedAt: null,
        errorMessage: null,
      };
    case "RUN_REQUESTED":
      return {
        ...state,
        phase: "starting",
        selectedContractId: action.contractId,
        workflowRunId: "",
        dashboard: null,
        lastUpdatedAt: null,
        errorMessage: null,
      };
    case "RUN_ACCEPTED":
      return {
        ...state,
        phase: "refreshing",
        workflowRunId: action.workflowRunId,
        selectedContractId: action.contractId,
        dashboard: null,
        lastUpdatedAt: null,
        errorMessage: null,
      };
    case "REFRESH_STARTED":
      return state.phase === "starting"
        ? state
        : { ...state, phase: "refreshing", errorMessage: null };
    case "DASHBOARD_RECEIVED":
      return {
        ...state,
        phase: "ready",
        dashboard: action.dashboard,
        selectedContractId: action.dashboard.contractId || state.selectedContractId,
        workflowRunId: action.dashboard.workflowRunId || state.workflowRunId,
        lastUpdatedAt: action.receivedAt,
        errorMessage: null,
      };
    case "REQUEST_FAILED":
      return {
        ...state,
        phase: "error",
        dashboard: action.retainDashboard ? state.dashboard : null,
        lastUpdatedAt: action.retainDashboard ? state.lastUpdatedAt : null,
        errorMessage: action.message,
      };
    case "CLEAR_ERROR":
      return { ...state, phase: "ready", errorMessage: null };
  }
}

export interface StoredWorkflowRef {
  datasetId: string;
  snapshotHash: string;
  workflowRunId: string;
  contractId: string;
}

export function workflowStorageKey(datasetId: string): string {
  return `opc-mis:workflow:${encodeURIComponent(datasetId)}`;
}

export function serializeWorkflowRef(value: StoredWorkflowRef): string {
  return JSON.stringify(value);
}

export function restoreWorkflowRef(
  serialized: string | null,
  catalog: ContractCatalog,
): StoredWorkflowRef | null {
  if (!serialized) return null;
  try {
    const candidate = JSON.parse(serialized) as Partial<StoredWorkflowRef>;
    const contractExists = catalog.contracts.some(
      (item) => item.contractId === candidate.contractId,
    );
    if (
      candidate.datasetId !== catalog.datasetId ||
      candidate.snapshotHash !== catalog.snapshotHash ||
      !candidate.workflowRunId ||
      !candidate.contractId ||
      !contractExists
    ) {
      return null;
    }
    return candidate as StoredWorkflowRef;
  } catch {
    return null;
  }
}
