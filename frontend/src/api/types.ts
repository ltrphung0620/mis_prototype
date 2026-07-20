export type JsonRecord = Record<string, unknown>;

export interface SystemCapabilities {
  dataset_id: string;
  snapshot_hash?: string;
  openai_enabled: boolean;
  openai_model: string | null;
  workflow_transport?: string;
  recommended_poll_interval_ms?: number;
}

export interface ContractOption {
  contractId: string;
  label: string;
  customerName?: string;
}

export interface ContractCatalog {
  datasetId: string;
  snapshotHash: string;
  contracts: readonly ContractOption[];
}

export interface WorkflowStartResponse {
  workflow_run_id: string;
  evaluation_case_id: string | null;
  contract_id: string;
  status: string;
  status_url: string;
}

export interface WorkflowNodeDto extends JsonRecord {
  node?: string;
  code?: string;
  status?: string;
  waiting_for?: unknown;
}

export interface WorkflowSummaryDto extends JsonRecord {
  workflow_run_id?: string;
  evaluation_case_id?: string | null;
  contract_id?: string;
  status?: string;
  current_stage?: string;
  nodes?: readonly WorkflowNodeDto[];
  pending_approval_ids?: readonly string[];
  pending_missing_data_ids?: readonly string[];
  failure_reason?: string | null;
}

export interface DashboardStageDto extends JsonRecord {
  stage_id?: string;
  id?: string;
  code?: string;
  label?: string;
  title?: string;
  title_vi?: string;
  description?: string;
  status?: string;
  status_label_vi?: string;
  sequence?: number;
  order?: number;
  parallel?: boolean;
  parallel_group?: string | null;
  applicability?: string;
  milestones?: readonly JsonRecord[];
  tasks?: readonly JsonRecord[];
  nodes?: readonly JsonRecord[];
}

export interface DashboardInputDto extends JsonRecord {
  readiness_status?: string;
  readiness_label_vi?: string;
  blocking_missing_count?: number;
  warning_count?: number;
  linked_records?: JsonRecord;
  relationships?: JsonRecord;
  blocking_items?: readonly unknown[];
  warnings?: readonly unknown[];
  contract_requirements?: readonly JsonRecord[];
}

export interface DashboardArtifactReferenceDto extends JsonRecord {
  artifact_id: string;
  artifact_type: string;
  version: number;
  validation_status: string;
}

export type DashboardInteractionType =
  | "APPROVAL"
  | "NOT_EVALUABLE_REVIEW"
  | "BANKING_AMOUNT_INPUT"
  | "BANKING_PRECHECK_EVIDENCE"
  | "DOCUMENT_EVIDENCE"
  | "NEGOTIATION_TERMS_SENT_CONFIRMATION"
  | "NEGOTIATION_OUTCOME_INPUT"
  | "UNSUPPORTED_INPUT";

export interface DashboardPendingInteractionDto extends JsonRecord {
  interaction_type: DashboardInteractionType;
  title_vi: string;
  instruction_vi: string;
  request_ids: readonly string[];
  approval_request_ids: readonly string[];
  protected_action?: string | null;
  endpoint?: string | null;
  subject_artifact_id?: string | null;
  subject_artifact_version?: number | null;
  required_fields: readonly string[];
}

export interface DashboardMetricDto extends JsonRecord {
  code: string;
  label_vi: string;
  value: string | number | boolean | null;
  unit: string;
  scope: string;
  quality: string;
  note_vi?: string | null;
}

export interface DashboardDecisionCardDto extends JsonRecord {
  available: boolean;
  artifact_id?: string | null;
  decision_card_id?: string | null;
  recommendation?: string | null;
  recommendation_label_vi: string;
  confidence?: string | null;
  executive_summary?: string | null;
}

export interface WorkflowDashboardResponse extends JsonRecord {
  dataset?: JsonRecord;
  workflow?: WorkflowSummaryDto;
  contract?: JsonRecord;
  input?: DashboardInputDto;
  stages?: readonly DashboardStageDto[];
  milestones?: readonly JsonRecord[];
  execution_status?: string;
  execution_status_label_vi?: string;
  business_status?: string;
  business_status_label_vi?: string;
  current_stage_label_vi?: string;
  progress?: JsonRecord;
  run_artifacts?: readonly DashboardArtifactReferenceDto[];
  approval_request_ids?: readonly string[];
  pending_interactions?: readonly DashboardPendingInteractionDto[];
  metrics?: readonly DashboardMetricDto[];
  decision_card?: DashboardDecisionCardDto;
}

export interface ApiArtifactEnvelope extends JsonRecord {
  artifact_id: string;
  artifact_type: string;
  evaluation_case_id: string;
  producer: string;
  version: number;
  status: string;
  payload: JsonRecord;
  validation_status: string;
}

export interface ApiApprovalRequest extends JsonRecord {
  request_id: string;
  workflow_run_id: string;
  evaluation_case_id: string;
  subject_artifact_id: string;
  subject_artifact_version: number;
  command: {
    action_type: string;
  } & JsonRecord;
  status: string;
  decision_record?: {
    decision: "APPROVE" | "REJECT";
    decided_by: string;
    reason: string;
    decided_at: string;
  } | null;
}

export interface WorkflowMilestone {
  id: string;
  code: string;
  ownerId?: string;
  label: string;
  description?: string;
  status: string;
  statusLabel?: string;
  waitingFor: readonly string[];
  lane?: "finance" | "operations";
  applicability: string;
  applicabilityReason?: string;
  resolutionStatus?: string;
  artifactIds: readonly string[];
}

export interface WorkflowStage {
  id: string;
  code: string;
  label: string;
  description?: string;
  status: string;
  statusLabel?: string;
  order: number;
  parallel: boolean;
  applicability: string;
  milestones: readonly WorkflowMilestone[];
}

export interface LinkedRecordCount {
  key: string;
  label: string;
  count: number;
}

export interface ContractRequirementSummary {
  id: string;
  requirementType: string;
  requirementLabel: string;
  certainty: string;
  amount?: number;
  currency?: string;
  creditCaseId?: string;
}

export interface InputSummary {
  contractId: string;
  contractLabel: string;
  customerName?: string;
  evaluationCaseId?: string;
  readinessStatus: string;
  blockingCount: number;
  warningCount: number;
  linkedRecords: readonly LinkedRecordCount[];
  blockingItems: readonly string[];
  warnings: readonly string[];
  contractRequirements: readonly ContractRequirementSummary[];
  readinessLabel?: string;
}

export interface NormalizedWorkflowDashboard {
  datasetId: string;
  snapshotHash: string;
  workflowRunId: string;
  evaluationCaseId?: string;
  contractId: string;
  status: string;
  statusLabel: string;
  currentStage: string;
  currentStageLabel: string;
  failureReason?: string;
  pendingApprovalCount: number;
  pendingMissingDataCount: number;
  businessStatus: string;
  businessStatusLabel: string;
  resolvedMilestoneCount?: number;
  totalMilestoneCount?: number;
  progressPercent?: number;
  progressBasis?: string;
  input: InputSummary;
  stages: readonly WorkflowStage[];
  runArtifacts: readonly DashboardArtifactReferenceDto[];
  approvalRequestIds: readonly string[];
  pendingInteractions: readonly DashboardPendingInteractionDto[];
  metrics: readonly DashboardMetricDto[];
  decisionCard: DashboardDecisionCardDto;
}
