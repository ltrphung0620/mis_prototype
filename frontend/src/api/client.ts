import type {
  ApiApprovalRequest,
  ApiArtifactEnvelope,
  ContractCatalog,
  JsonRecord,
  SystemCapabilities,
  WorkflowDashboardResponse,
  WorkflowStartResponse,
} from "./types";
import { normalizeContractCatalog } from "./normalize";

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function requestJson<T>(
  path: string,
  init: RequestInit = {},
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(path, {
    ...init,
    signal,
    headers: {
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
  });

  const contentType = response.headers.get("content-type") ?? "";
  const body = contentType.includes("application/json")
    ? ((await response.json()) as unknown)
    : null;

  if (!response.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body
        ? String((body as JsonRecord).detail)
        : `Máy chủ trả về lỗi ${response.status}.`;
    throw new ApiError(detail, response.status);
  }

  return body as T;
}

export function getSystemCapabilities(signal?: AbortSignal): Promise<SystemCapabilities> {
  return requestJson<SystemCapabilities>("/api/system/capabilities", {}, signal);
}

export async function getContractCatalog(signal?: AbortSignal): Promise<ContractCatalog> {
  const response = await requestJson<JsonRecord>("/api/contracts", {}, signal);
  return normalizeContractCatalog(response);
}

export function startCaseWorkflow(
  contractId: string,
  runRequestId: string,
  signal?: AbortSignal,
): Promise<WorkflowStartResponse> {
  return requestJson<WorkflowStartResponse>(
    "/api/cases/run",
    {
      method: "POST",
      body: JSON.stringify({
        contract_id: contractId,
        evaluation_scope: ["FINANCE", "OPERATIONS", "RISK"],
        run_request_id: runRequestId,
      }),
    },
    signal,
  );
}

export async function getWorkflowDashboard(
  workflowRunId: string,
  signal?: AbortSignal,
): Promise<WorkflowDashboardResponse> {
  const encodedId = encodeURIComponent(workflowRunId);
  try {
    return await requestJson<WorkflowDashboardResponse>(
      `/api/workflows/${encodedId}/dashboard`,
      {},
      signal,
    );
  } catch (error) {
    // The consolidated projection is the primary API. This compatibility path can
    // be removed once every deployment exposes it.
    if (!(error instanceof ApiError) || error.status !== 404) {
      throw error;
    }
    const workflow = await requestJson<JsonRecord>(
      `/api/workflows/${encodedId}`,
      {},
      signal,
    );
    return { workflow };
  }
}

export function getCaseArtifacts(
  evaluationCaseId: string,
  signal?: AbortSignal,
): Promise<readonly ApiArtifactEnvelope[]> {
  return requestJson<readonly ApiArtifactEnvelope[]>(
    `/api/cases/${encodeURIComponent(evaluationCaseId)}/artifacts`,
    {},
    signal,
  );
}

export function getApprovalRequests(
  evaluationCaseId: string,
  signal?: AbortSignal,
): Promise<readonly ApiApprovalRequest[]> {
  return requestJson<readonly ApiApprovalRequest[]>(
    `/api/cases/${encodeURIComponent(evaluationCaseId)}/approval-requests`,
    {},
    signal,
  );
}

export function decideApprovalRequest(
  requestId: string,
  decision: "APPROVE" | "REJECT",
): Promise<JsonRecord> {
  return requestJson<JsonRecord>(
    `/api/approval-requests/${encodeURIComponent(requestId)}/decision`,
    {
      method: "POST",
      body: JSON.stringify({
        decision,
        decided_by: "FOUNDER",
        reason: "HUMAN_REVIEW_COMPLETED",
      }),
    },
  );
}

export interface BankingAmountSupplementPayload {
  workflow_run_id: string;
  missing_request_id: string;
  requested_amount: number;
  requested_amount_currency: "VND";
  evidence_note: string;
}

export interface BankingPrecheckEvidencePayload {
  workflow_run_id: string;
  missing_request_id: string;
  evidence_reference_id: string;
  evidence_note: string;
}

export interface DocumentEvidencePayload {
  workflow_run_id: string;
  missing_request_id: string;
  document_reference_id: string;
  content_sha256: string;
  document_type: string;
  evidence_note: "REQUESTED_DOCUMENT_REFERENCE_SUPPLIED";
}

export function submitBankingAmountSupplement(
  evaluationCaseId: string,
  payload: BankingAmountSupplementPayload,
): Promise<JsonRecord> {
  return requestJson<JsonRecord>(
    `/api/cases/${encodeURIComponent(evaluationCaseId)}/banking/input-supplements`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export function submitBankingPrecheckEvidence(
  evaluationCaseId: string,
  payload: BankingPrecheckEvidencePayload,
): Promise<JsonRecord> {
  return requestJson<JsonRecord>(
    `/api/cases/${encodeURIComponent(evaluationCaseId)}/banking/precheck-evidence-supplements`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export function submitDocumentEvidence(
  evaluationCaseId: string,
  payload: DocumentEvidencePayload,
): Promise<JsonRecord> {
  return requestJson<JsonRecord>(
    `/api/cases/${encodeURIComponent(evaluationCaseId)}/documents/evidence-supplements`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}
