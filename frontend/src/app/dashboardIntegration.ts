import type {
  ApiApprovalRequest,
  ApiArtifactEnvelope,
  DashboardPendingInteractionDto,
  JsonRecord,
  NormalizedWorkflowDashboard,
} from "../api/types";
import type { ArtifactEnvelope } from "../features/artifacts";
import type {
  DecisionCardArtifact,
  DecisionCardPayload,
  DecisionDashboardData,
  DecisionMetric,
  PendingDecisionApproval,
} from "../features/decision";
import type {
  ApprovalRequestView,
  ApprovalSubjectSummary,
} from "../features/governance";
import type {
  DocumentRequirementCode,
  MissingDataInteraction,
} from "../features/missing-data";

const PRESENTABLE_ARTIFACT_TYPES = new Set([
  "PLANNER_RESULT",
  "EVALUATION_CASE",
  "FINANCE_FACTS",
  "FINANCE_ASSESSMENT",
  "OPERATIONS_FACTS",
  "OPERATIONS_ASSESSMENT",
  "RISK_PRE_SCAN",
  "INITIAL_RISK_ASSESSMENT",
  "FINAL_RISK_ASSESSMENT",
  "BANKING_DISCOVERY_REQUEST",
  "BANKING_OPTION_MATRIX",
  "BANKING_DISCOVERY_RESULT",
  "BANKING_OPTION_ADVICE",
  "BANKING_PRECHECK_READINESS",
  "BANKING_PRECHECK_RESULT_SET",
  "DOCUMENT_CHECKLIST",
  "DOCUMENT_PACKAGE_DRAFT",
  "DOCUMENT_RELEASE_PACKAGE",
  "INTERNAL_DECISION_PACKAGE",
]);

const ARTIFACT_PREFERENCE = [
  "PLANNER_RESULT",
  "FINANCE_ASSESSMENT",
  "OPERATIONS_ASSESSMENT",
  "RISK_PRE_SCAN",
  "INITIAL_RISK_ASSESSMENT",
  "BANKING_PRECHECK_RESULT_SET",
  "BANKING_DISCOVERY_RESULT",
  "BANKING_OPTION_MATRIX",
  "BANKING_OPTION_ADVICE",
  "BANKING_PRECHECK_READINESS",
  "DOCUMENT_CHECKLIST",
  "DOCUMENT_RELEASE_PACKAGE",
  "DOCUMENT_PACKAGE_DRAFT",
  "INTERNAL_DECISION_PACKAGE",
  "FINAL_RISK_ASSESSMENT",
  "EVALUATION_CASE",
  "BANKING_DISCOVERY_REQUEST",
  "FINANCE_FACTS",
  "OPERATIONS_FACTS",
] as const;

function record(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonRecord)
    : {};
}

function strings(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function number(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function envelope(item: ApiArtifactEnvelope): ArtifactEnvelope {
  return {
    artifact_id: item.artifact_id,
    artifact_type: item.artifact_type,
    version: item.version,
    validation_status: item.validation_status,
    payload: item.payload,
  };
}

function mergedAssessment(
  artifacts: readonly ApiArtifactEnvelope[],
  factType: string,
  assessmentType: string,
): ArtifactEnvelope | null {
  const facts = artifacts.find((item) => item.artifact_type === factType);
  const assessment = artifacts.find((item) => item.artifact_type === assessmentType);
  if (!facts && !assessment) return null;
  const primary = assessment ?? facts!;
  const factPayload = record(facts?.payload);
  const assessmentPayload = record(assessment?.payload);
  return {
    ...envelope(primary),
    artifact_type: assessmentType,
    payload: {
      ...factPayload,
      ...assessmentPayload,
      facts: factPayload.facts ?? assessmentPayload.facts,
      order_schedules:
        factPayload.order_schedules ?? assessmentPayload.order_schedules,
      observations:
        assessmentPayload.observations ?? factPayload.observations,
      limitations: assessmentPayload.limitations ?? factPayload.limitations,
      narrative: assessmentPayload.narrative ?? factPayload.narrative,
      summary: assessmentPayload.summary ?? factPayload.summary,
    },
  };
}

export function selectAssessmentArtifact(
  artifactIds: readonly string[],
  runArtifacts: readonly ApiArtifactEnvelope[],
): ArtifactEnvelope | null {
  const requested = new Set(artifactIds);
  const candidates = runArtifacts.filter(
    (item) =>
      requested.has(item.artifact_id) &&
      PRESENTABLE_ARTIFACT_TYPES.has(item.artifact_type),
  );
  const finance = mergedAssessment(
    candidates,
    "FINANCE_FACTS",
    "FINANCE_ASSESSMENT",
  );
  if (finance) return finance;
  const operations = mergedAssessment(
    candidates,
    "OPERATIONS_FACTS",
    "OPERATIONS_ASSESSMENT",
  );
  if (operations) return operations;
  for (const type of ARTIFACT_PREFERENCE) {
    const match = candidates.find((item) => item.artifact_type === type);
    if (match) return envelope(match);
  }
  return null;
}

export function hasAssessmentArtifact(
  artifactIds: readonly string[],
  runArtifacts: readonly ApiArtifactEnvelope[],
): boolean {
  const requested = new Set(artifactIds);
  return runArtifacts.some(
    (item) =>
      requested.has(item.artifact_id) &&
      PRESENTABLE_ARTIFACT_TYPES.has(item.artifact_type),
  );
}

export function decisionCardArtifact(
  dashboard: NormalizedWorkflowDashboard,
  artifacts: readonly ApiArtifactEnvelope[],
): DecisionCardArtifact | null {
  const artifactId = dashboard.decisionCard.artifact_id;
  if (!dashboard.decisionCard.available || !artifactId) return null;
  const currentReference = dashboard.runArtifacts.find(
    (candidate) =>
      candidate.artifact_id === artifactId &&
      candidate.artifact_type === "DECISION_CARD" &&
      candidate.validation_status === "VALID",
  );
  if (!currentReference) return null;
  const item = artifacts.find(
    (candidate) =>
      candidate.artifact_id === artifactId &&
      candidate.artifact_type === "DECISION_CARD" &&
      candidate.version === currentReference.version &&
      candidate.validation_status === "VALID",
  );
  if (!item) return null;
  return {
    artifact_id: item.artifact_id,
    version: item.version,
    payload: item.payload as unknown as DecisionCardPayload,
  };
}

export function decisionDashboardData(
  dashboard: NormalizedWorkflowDashboard,
  card: DecisionCardArtifact | null,
): DecisionDashboardData {
  const metrics: DecisionMetric[] = dashboard.metrics.map((item) => ({
    metric: item.code,
    label_vi: item.label_vi,
    value: item.value,
    unit: item.unit,
    quality: item.quality,
    scope: item.scope,
    contract_attributable: item.scope !== "OPC_GLOBAL",
  }));
  return {
    contract_id: dashboard.contractId,
    execution_status_label_vi: dashboard.statusLabel,
    business_status: dashboard.businessStatus,
    business_status_label_vi: dashboard.businessStatusLabel,
    current_stage_label_vi: dashboard.currentStageLabel,
    progress_percent: dashboard.progressPercent ?? 0,
    metrics,
    decision_card: {
      available: dashboard.decisionCard.available,
      artifact_id: dashboard.decisionCard.artifact_id,
      decision_card_id: dashboard.decisionCard.decision_card_id,
      recommendation: (dashboard.decisionCard.recommendation ?? undefined) as
        | DecisionCardPayload["recommendation"]
        | undefined,
      recommendation_label_vi: dashboard.decisionCard.recommendation_label_vi,
      confidence: (dashboard.decisionCard.confidence ?? undefined) as
        | DecisionCardPayload["confidence"]
        | undefined,
      executive_summary: dashboard.decisionCard.executive_summary,
    },
    condition_titles: card?.payload.conditions?.map((item) => item.title) ?? [],
    residual_risk_level: card?.payload.residual_risk_level ?? null,
    ready_for_external_submission:
      dashboard.businessStatus === "READY_FOR_EXTERNAL_SUBMISSION",
    external_submission_performed: false,
  };
}

export function pendingApproval(
  dashboard: NormalizedWorkflowDashboard,
  approvals: readonly ApiApprovalRequest[],
): ApiApprovalRequest | null {
  const pendingIds = new Set(
    dashboard.pendingInteractions
      .filter((item) => item.interaction_type === "APPROVAL")
      .flatMap((item) => item.approval_request_ids),
  );
  return (
    approvals.find(
      (item) => item.status === "PENDING" && pendingIds.has(item.request_id),
    ) ?? null
  );
}

export function approvalRequestView(
  request: ApiApprovalRequest | null,
): ApprovalRequestView | null {
  if (!request) return null;
  return {
    request_id: request.request_id,
    workflow_run_id: request.workflow_run_id,
    status: request.status,
    subject_artifact_id: request.subject_artifact_id,
    command: { action_type: request.command.action_type },
    protected_action: request.command.action_type,
    decision_record: request.decision_record ?? null,
  };
}

function actionInteraction(
  dashboard: NormalizedWorkflowDashboard,
  request: ApiApprovalRequest,
): DashboardPendingInteractionDto | undefined {
  return dashboard.pendingInteractions.find(
    (item) =>
      item.interaction_type === "APPROVAL" &&
      item.approval_request_ids.includes(request.request_id),
  );
}

export function approvalSubjectSummary(
  dashboard: NormalizedWorkflowDashboard,
  request: ApiApprovalRequest | null,
  artifacts: readonly ApiArtifactEnvelope[],
): ApprovalSubjectSummary | null {
  if (!request) return null;
  const interaction = actionInteraction(dashboard, request);
  const subject = artifacts.find(
    (item) => item.artifact_id === request.subject_artifact_id,
  );
  const payload = record(subject?.payload);
  const action = request.command.action_type;
  const selectedOptions = Array.isArray(payload.selected_options)
    ? payload.selected_options.map(record)
    : [];
  const firstOption = selectedOptions[0] ?? {};
  const releasePackage = record(payload.document_release_package);
  const title = interaction?.title_vi || "Yêu cầu Nhà sáng lập xác nhận";
  const descriptionByAction: Record<string, string> = {
    SUBMIT_BANKING_PRECHECK:
      "Cho phép quy trình gửi yêu cầu kiểm tra sơ bộ với ngân hàng; đây không phải phê duyệt cấp tín dụng hay bảo lãnh.",
    CONFIRM_FINAL_CONTRACT_DECISION:
      typeof payload.executive_summary === "string"
        ? payload.executive_summary
        : "Xác nhận quyết định cuối cùng trên đúng Decision Card hiện hành.",
    SEND_DOCUMENT_TO_EXTERNAL_PARTNER:
      "Cho phép phát hành đúng gói hồ sơ đã chuẩn bị tới đối tác bên ngoài. Trước phê duyệt, hồ sơ chưa được gửi.",
    COMMIT_LARGE_FINANCIAL_DECISION:
      "Xác nhận cam kết tài chính trong đúng phạm vi được trình duyệt.",
  };
  return {
    title,
    description:
      descriptionByAction[action] ??
      interaction?.instruction_vi ??
      "Quy trình đang tạm dừng để Nhà sáng lập xem xét hành động được bảo vệ.",
    recommendation:
      typeof payload.recommendation === "string"
        ? payload.recommendation
        : null,
    amount:
      number(payload.requested_amount) ??
      number(firstOption.requested_amount) ??
      number(firstOption.supported_amount),
    currency:
      typeof payload.currency === "string"
        ? payload.currency
        : typeof firstOption.currency === "string"
          ? firstOption.currency
          : "VND",
    recipient:
      typeof releasePackage.recipient === "string"
        ? releasePackage.recipient
        : typeof payload.recipient === "string"
          ? payload.recipient
          : null,
    document_codes:
      strings(releasePackage.document_codes).length > 0
        ? strings(releasePackage.document_codes)
        : strings(payload.document_codes),
  };
}

export function pendingDecisionApproval(
  request: ApiApprovalRequest | null,
): PendingDecisionApproval | null {
  if (!request) return null;
  return {
    request_id: request.request_id,
    status: request.status,
    subject_artifact_id: request.subject_artifact_id,
    subject_artifact_version: request.subject_artifact_version,
    protected_action: request.command.action_type,
  };
}

export function pendingMissingInteraction(
  dashboard: NormalizedWorkflowDashboard,
): MissingDataInteraction | null {
  const missingInteractionTypes = new Set([
    "DOCUMENT_EVIDENCE",
    "BANKING_PRECHECK_EVIDENCE",
    "BANKING_AMOUNT_INPUT",
    "UNSUPPORTED_INPUT",
  ]);
  const interaction = dashboard.pendingInteractions.find(
    (item) => missingInteractionTypes.has(item.interaction_type),
  );
  if (!interaction) return null;
  return {
    interaction_type: interaction.interaction_type,
    title_vi: interaction.title_vi,
    instruction_vi: interaction.instruction_vi,
    request_ids: [...interaction.request_ids],
    required_fields: [...interaction.required_fields],
  } as MissingDataInteraction;
}

export function pendingNotEvaluableReview(
  dashboard: NormalizedWorkflowDashboard,
): DashboardPendingInteractionDto | null {
  return (
    dashboard.pendingInteractions.find(
      (item) => item.interaction_type === "NOT_EVALUABLE_REVIEW",
    ) ?? null
  );
}

const DOCUMENT_TYPES = new Set<DocumentRequirementCode>([
  "SIGNED_CONTRACT",
  "COMPANY_PROFILE",
  "PERFORMANCE_BOND_REQUEST_FORM",
  "CASHFLOW_BUFFER_EVIDENCE",
]);

export function allowedDocumentTypes(
  artifacts: readonly ApiArtifactEnvelope[],
): DocumentRequirementCode[] {
  const checklist = [...artifacts]
    .reverse()
    .find((item) => item.artifact_type === "DOCUMENT_CHECKLIST");
  const missing = strings(record(checklist?.payload).missing_document_codes).filter(
    (item): item is DocumentRequirementCode =>
      DOCUMENT_TYPES.has(item as DocumentRequirementCode),
  );
  return missing.length ? missing : [...DOCUMENT_TYPES];
}
