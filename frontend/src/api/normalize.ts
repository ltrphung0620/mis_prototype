import type {
  ContractCatalog,
  ContractOption,
  ContractRequirementSummary,
  DashboardArtifactReferenceDto,
  DashboardDecisionCardDto,
  DashboardInputDto,
  DashboardMetricDto,
  DashboardPendingInteractionDto,
  DashboardStageDto,
  InputSummary,
  JsonRecord,
  LinkedRecordCount,
  NormalizedWorkflowDashboard,
  WorkflowDashboardResponse,
  WorkflowMilestone,
  WorkflowStage,
  WorkflowSummaryDto,
} from "./types";
import { milestoneLabel, stageLabel } from "../shared/workflowLabels";

const LINKED_RECORD_LABELS: Readonly<Record<string, string>> = {
  customer: "Khách hàng",
  customers: "Khách hàng",
  customer_count: "Khách hàng",
  order: "Đơn hàng",
  orders: "Đơn hàng",
  order_count: "Đơn hàng",
  invoice: "Hóa đơn",
  invoices: "Hóa đơn",
  invoice_count: "Hóa đơn",
  service: "Dịch vụ",
  services: "Dịch vụ",
  service_count: "Dịch vụ",
  credit_profile: "Hồ sơ tín dụng",
  credit_profiles: "Hồ sơ tín dụng",
  credit_profile_count: "Hồ sơ tín dụng",
};

const REQUIREMENT_LABELS: Readonly<Record<string, string>> = {
  PERFORMANCE_BOND: "Bảo lãnh thực hiện hợp đồng",
  ADVANCE_PAYMENT_GUARANTEE: "Bảo lãnh hoàn trả tạm ứng",
  BID_BOND: "Bảo lãnh dự thầu",
  LETTER_OF_CREDIT: "Thư tín dụng",
  TRADE_FINANCE_LC: "Thư tín dụng thương mại",
  WORKING_CAPITAL: "Vốn lưu động",
  FUNDING: "Nhu cầu vốn",
};

function isRecord(value: unknown): value is JsonRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function stringValue(...values: unknown[]): string {
  const match = values.find((value) => typeof value === "string" && value.trim());
  return typeof match === "string" ? match : "";
}

function numberValue(...values: unknown[]): number | undefined {
  const match = values.find(
    (value) => typeof value === "number" && Number.isFinite(value),
  );
  return typeof match === "number" ? match : undefined;
}

function stringList(value: unknown): readonly string[] {
  return Array.isArray(value)
    ? value
        .map((item) => {
          if (typeof item === "string") return item;
          if (!isRecord(item)) return "";
          return stringValue(item.message, item.detail, item.title, item.code);
        })
        .filter(Boolean)
    : [];
}

function recordList(value: unknown): readonly JsonRecord[] {
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

export function normalizeContractCatalog(payload: JsonRecord): ContractCatalog {
  const datasetId = stringValue(payload.dataset_id, payload.datasetId);
  const snapshotHash = stringValue(payload.snapshot_hash, payload.snapshotHash);
  const objectContracts = recordList(payload.contracts);
  const idContracts = Array.isArray(payload.contract_ids)
    ? payload.contract_ids.filter((item): item is string => typeof item === "string")
    : [];

  const contracts: readonly ContractOption[] = objectContracts.length
    ? objectContracts.map((item) => {
        const contractId = stringValue(item.contract_id, item.contractId, item.id);
        const name = stringValue(item.contract_name, item.name, item.title);
        return {
          contractId,
          label: name ? `${contractId} · ${name}` : contractId,
          customerName: stringValue(item.customer_name, item.customerName) || undefined,
        };
      })
    : idContracts.map((contractId) => ({ contractId, label: contractId }));

  return {
    datasetId,
    snapshotHash,
    contracts: contracts.filter((item) => item.contractId),
  };
}

function milestoneFromRecord(
  item: JsonRecord,
  stageCode: string,
  index: number,
): WorkflowMilestone {
  const code = stringValue(item.code, item.node, item.milestone_id, item.id) || `${stageCode}-${index + 1}`;
  const taskCode = stringValue(item.task_id, item.code, item.node, item.milestone_id, item.id) || code;
  const label = stringValue(item.title_vi, item.label, item.title, item.name) || milestoneLabel(taskCode);
  const laneHint = `${taskCode} ${stringValue(item.owner_id)}`.toUpperCase();
  const lane = laneHint.includes("FINANCE")
    ? "finance"
    : laneHint.includes("OPERATIONS")
      ? "operations"
      : undefined;
  return {
    id: stringValue(item.task_id, item.milestone_id, item.id) || `${stageCode}-${index + 1}`,
    code: taskCode,
    ownerId: stringValue(item.owner_id) || undefined,
    label,
    description: stringValue(item.description, item.detail) || undefined,
    status: stringValue(item.status, item.resolution_status) || "PENDING",
    statusLabel: stringValue(item.status_label_vi) || undefined,
    waitingFor: stringList(item.waiting_for),
    lane,
    applicability: stringValue(item.applicability) || "APPLICABLE",
    applicabilityReason: stringValue(item.applicability_reason_vi) || undefined,
    resolutionStatus: stringValue(item.resolution_status) || undefined,
    artifactIds: stringList(item.artifact_ids),
  };
}

function normalizeStage(item: DashboardStageDto, index: number): WorkflowStage {
  const code = stringValue(item.code, item.stage_id, item.id) || `STAGE-${index + 1}`;
  const rawMilestones = recordList(item.milestones).length
    ? recordList(item.milestones)
    : recordList(item.tasks).length
      ? recordList(item.tasks)
      : recordList(item.nodes);
  const milestones = rawMilestones.map((milestone, milestoneIndex) =>
    milestoneFromRecord(milestone, code, milestoneIndex),
  );
  const milestoneCodes = new Set(milestones.map((milestone) => milestone.code.toUpperCase()));
  const inferredParallel =
    milestoneCodes.has("FINANCE_ASSESSMENT") &&
    milestoneCodes.has("OPERATIONS_ASSESSMENT");

  return {
    id: stringValue(item.stage_id, item.id) || code,
    code,
    label: stringValue(item.title_vi, item.label, item.title) || stageLabel(code),
    description: stringValue(item.description) || undefined,
    status: stringValue(item.status) || inferStageStatus(milestones),
    statusLabel: stringValue(item.status_label_vi) || undefined,
    order: numberValue(item.sequence, item.order) ?? index + 1,
    parallel: item.parallel === true || Boolean(item.parallel_group) || inferredParallel,
    applicability: stringValue(item.applicability) || "APPLICABLE",
    milestones,
  };
}

function statusRank(status: string): number {
  switch (status.toUpperCase()) {
    case "FAILED_SAFE":
    case "BLOCKED":
      return 8;
    case "REJECTED":
      return 7;
    case "EXPIRED":
      return 6;
    case "WAITING_FOR_APPROVAL":
    case "WAITING_FOR_INPUT":
    case "WAITING_FOR_DEPENDENCIES":
      return 5;
    case "RUNNING":
      return 4;
    case "COMPLETED_WITH_WARNINGS":
      return 3;
    case "COMPLETED":
      return 2;
    case "SKIPPED":
      return 1;
    default:
      return 0;
  }
}

function inferStageStatus(milestones: readonly WorkflowMilestone[]): string {
  if (!milestones.length) return "PENDING";
  return milestones.reduce(
    (selected, item) =>
      statusRank(item.status) > statusRank(selected) ? item.status : selected,
    "PENDING",
  );
}

function stagesFromWorkflow(workflow: WorkflowSummaryDto): readonly WorkflowStage[] {
  const nodes = recordList(workflow.nodes);
  return nodes.map((node, index) => {
    const code = stringValue(node.node, node.code) || `NODE-${index + 1}`;
    const milestone = milestoneFromRecord(node, code, 0);
    return {
      id: code,
      code,
      label: stageLabel(code),
      status: milestone.status,
      statusLabel: milestone.statusLabel,
      order: index + 1,
      parallel: false,
      applicability: "APPLICABLE",
      milestones: [milestone],
    };
  });
}

function groupParallelAssessment(stages: readonly WorkflowStage[]): readonly WorkflowStage[] {
  const financeIndex = stages.findIndex((stage) => stage.code.toUpperCase() === "FINANCE_ASSESSMENT");
  const operationsIndex = stages.findIndex((stage) => stage.code.toUpperCase() === "OPERATIONS_ASSESSMENT");
  if (financeIndex < 0 || operationsIndex < 0 || financeIndex === operationsIndex) return stages;

  const firstIndex = Math.min(financeIndex, operationsIndex);
  const finance = stages[financeIndex];
  const operations = stages[operationsIndex];
  const combinedMilestones = [...finance.milestones, ...operations.milestones];
  const combined: WorkflowStage = {
    id: "INITIAL_ASSESSMENT_PARALLEL",
    code: "INITIAL_ASSESSMENT_PARALLEL",
    label: "Đánh giá ban đầu chạy song song",
    description: "Tài chính và Vận hành được điều phối đồng thời trên cùng hồ sơ đánh giá.",
    status: inferStageStatus(combinedMilestones),
    order: Math.min(finance.order, operations.order),
    parallel: true,
    applicability: "APPLICABLE",
    milestones: combinedMilestones,
  };
  const result = stages.filter((_, index) => index !== financeIndex && index !== operationsIndex);
  return [...result.slice(0, firstIndex), combined, ...result.slice(firstIndex)];
}

function linkedRecordCounts(input: DashboardInputDto): readonly LinkedRecordCount[] {
  const source = isRecord(input.linked_records)
    ? input.linked_records
    : isRecord(input.relationships)
      ? input.relationships
      : {};
  const nested = Object.entries(source)
    .map(([key, value]) => ({
      key,
      label: LINKED_RECORD_LABELS[key.toLowerCase()] ?? key,
      count: typeof value === "number" && Number.isFinite(value) ? value : 0,
    }))
    .filter((item) => item.count >= 0);
  if (nested.length) return nested;
  const directKeys = [
    "linked_customer_count",
    "linked_order_count",
    "linked_invoice_count",
    "linked_service_count",
    "linked_credit_profile_count",
  ] as const;
  return directKeys
    .filter((key) => typeof input[key] === "number")
    .map((key) => ({
      key,
      label: LINKED_RECORD_LABELS[key.replace("linked_", "")] ?? key,
      count: input[key] as number,
    }));
}

function contractRequirements(
  input: DashboardInputDto,
): readonly ContractRequirementSummary[] {
  return recordList(input.contract_requirements).map((item, index) => {
    const requirementType = stringValue(
      item.requirement_type,
      item.type,
      item.requirement_code,
    );
    return {
      id: stringValue(item.requirement_id, item.id) || `requirement-${index + 1}`,
      requirementType,
      requirementLabel:
        stringValue(item.requirement_label_vi, item.label_vi, item.title_vi) ||
        REQUIREMENT_LABELS[requirementType.toUpperCase()] ||
        "Yêu cầu theo hợp đồng",
      certainty: stringValue(item.certainty) || "NOT_EVALUABLE",
      amount: numberValue(item.requested_amount, item.amount, item.required_amount),
      currency: stringValue(item.requested_amount_currency, item.currency) || undefined,
      creditCaseId: stringValue(item.credit_case_id) || undefined,
    };
  });
}

function normalizeInput(
  payload: WorkflowDashboardResponse,
  workflow: WorkflowSummaryDto,
): InputSummary {
  const input = isRecord(payload.input) ? payload.input : {};
  const contract = isRecord(payload.contract) ? payload.contract : {};
  const blockingItems = stringList(input.blocking_items);
  const warnings = stringList(input.warnings);
  const contractId = stringValue(workflow.contract_id, contract.contract_id, contract.id);
  return {
    contractId,
    contractLabel: stringValue(contract.contract_name, contract.name, contract.title) || contractId,
    customerName: stringValue(contract.customer_name, input.customer_name) || undefined,
    evaluationCaseId: stringValue(workflow.evaluation_case_id) || undefined,
    readinessStatus: stringValue(
      input.readiness_status,
      input.status,
      payload.execution_status,
      workflow.status,
    ) || "PENDING",
    readinessLabel: stringValue(input.readiness_label_vi) || undefined,
    blockingCount: numberValue(input.blocking_missing_count, input.blocking_count) ?? blockingItems.length,
    warningCount: numberValue(input.warning_count) ?? warnings.length,
    linkedRecords: linkedRecordCounts(input),
    blockingItems,
    warnings,
    contractRequirements: contractRequirements(input),
  };
}

export function normalizeWorkflowDashboard(
  payload: WorkflowDashboardResponse,
  catalog?: ContractCatalog,
): NormalizedWorkflowDashboard {
  const workflow = isRecord(payload.workflow) ? payload.workflow : payload;
  const dataset = isRecord(payload.dataset) ? payload.dataset : {};
  const rawStages = recordList(payload.stages).length
    ? recordList(payload.stages)
    : isRecord(payload.timeline) && recordList(payload.timeline.stages).length
      ? recordList(payload.timeline.stages)
      : [];
  const normalizedStages = rawStages.length
    ? rawStages.map((stage, index) => normalizeStage(stage, index))
    : stagesFromWorkflow(workflow);
  const stages = groupParallelAssessment(
    [...normalizedStages].sort((left, right) => left.order - right.order),
  );
  const progress = isRecord(payload.progress) ? payload.progress : {};
  const interactions = recordList(payload.pending_interactions);
  const approvalInteractions = interactions.filter((item) =>
    stringValue(item.interaction_type).toUpperCase().includes("APPROVAL"),
  );
  const missingInteractions = interactions.filter(
    (item) =>
      !stringValue(item.interaction_type).toUpperCase().includes("APPROVAL") &&
      stringValue(item.interaction_type).toUpperCase() !==
        "NOT_EVALUABLE_REVIEW",
  );
  const runArtifacts: readonly DashboardArtifactReferenceDto[] = recordList(
    payload.run_artifacts,
  ).map((item) => ({
    artifact_id: stringValue(item.artifact_id),
    artifact_type: stringValue(item.artifact_type),
    version: numberValue(item.version) ?? 1,
    validation_status: stringValue(item.validation_status),
  }));
  const pendingInteractions: readonly DashboardPendingInteractionDto[] = interactions
    .map((item) => ({
      interaction_type: stringValue(
        item.interaction_type,
      ) as DashboardPendingInteractionDto["interaction_type"],
      title_vi: stringValue(item.title_vi),
      instruction_vi: stringValue(item.instruction_vi),
      request_ids: stringList(item.request_ids),
      approval_request_ids: stringList(item.approval_request_ids),
      protected_action: stringValue(item.protected_action) || null,
      endpoint: stringValue(item.endpoint) || null,
      subject_artifact_id: stringValue(item.subject_artifact_id) || null,
      subject_artifact_version: numberValue(item.subject_artifact_version),
      required_fields: stringList(item.required_fields),
    }))
    .filter((item) => Boolean(item.interaction_type));
  const metrics: readonly DashboardMetricDto[] = recordList(payload.metrics).map(
    (item) => ({
      code: stringValue(item.code),
      label_vi: stringValue(item.label_vi),
      value:
        typeof item.value === "string" ||
        typeof item.value === "number" ||
        typeof item.value === "boolean" ||
        item.value === null
          ? item.value
          : null,
      unit: stringValue(item.unit),
      scope: stringValue(item.scope),
      quality: stringValue(item.quality),
      note_vi: stringValue(item.note_vi) || null,
    }),
  );
  const rawDecisionCard: JsonRecord = isRecord(payload.decision_card)
    ? payload.decision_card
    : {};
  const decisionCard: DashboardDecisionCardDto = {
    available: rawDecisionCard.available === true,
    artifact_id: stringValue(rawDecisionCard.artifact_id) || null,
    decision_card_id: stringValue(rawDecisionCard.decision_card_id) || null,
    recommendation: stringValue(rawDecisionCard.recommendation) || null,
    recommendation_label_vi:
      stringValue(rawDecisionCard.recommendation_label_vi) ||
      "Chưa có Decision Card cho lượt xử lý này",
    confidence: stringValue(rawDecisionCard.confidence) || null,
    executive_summary: stringValue(rawDecisionCard.executive_summary) || null,
  };
  const hasProjectedInteractions = Array.isArray(payload.pending_interactions);

  return {
    datasetId: stringValue(dataset.dataset_id, payload.dataset_id, catalog?.datasetId),
    snapshotHash: stringValue(dataset.snapshot_hash, payload.snapshot_hash, catalog?.snapshotHash),
    workflowRunId: stringValue(workflow.workflow_run_id, payload.workflow_run_id),
    evaluationCaseId: stringValue(workflow.evaluation_case_id) || undefined,
    contractId: stringValue(workflow.contract_id, payload.contract_id),
    status: stringValue(payload.execution_status, workflow.status, payload.status) || "PENDING",
    statusLabel: stringValue(payload.execution_status_label_vi),
    currentStage: stringValue(workflow.current_stage, payload.current_stage),
    currentStageLabel: stringValue(payload.current_stage_label_vi),
    failureReason: stringValue(workflow.failure_reason, payload.failure_reason) || undefined,
    pendingApprovalCount: hasProjectedInteractions
      ? approvalInteractions.length
      : Array.isArray(workflow.pending_approval_ids)
        ? workflow.pending_approval_ids.length
        : numberValue(payload.pending_approval_count) ?? approvalInteractions.length,
    pendingMissingDataCount: hasProjectedInteractions
      ? missingInteractions.length
      : Array.isArray(workflow.pending_missing_data_ids)
        ? workflow.pending_missing_data_ids.length
        : numberValue(payload.pending_missing_data_count) ?? missingInteractions.length,
    businessStatus: stringValue(payload.business_status),
    businessStatusLabel: stringValue(payload.business_status_label_vi),
    resolvedMilestoneCount: numberValue(progress.resolved_task_count),
    totalMilestoneCount: numberValue(progress.total_task_count),
    progressPercent: numberValue(progress.percent),
    progressBasis: stringValue(progress.basis) || undefined,
    input: normalizeInput(payload, workflow),
    stages,
    runArtifacts,
    approvalRequestIds: stringList(payload.approval_request_ids),
    pendingInteractions,
    metrics,
    decisionCard,
  };
}
