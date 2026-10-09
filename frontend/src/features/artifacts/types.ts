export type DisplayScalar = string | number | boolean | null;

export interface ArtifactEnvelope<TPayload = Record<string, unknown>> {
  artifact_id: string;
  artifact_type: string;
  version: number;
  validation_status: string;
  payload: TPayload;
  /** Explicit upstream artifacts recorded by the Orchestrator. */
  input_artifact_ids?: readonly string[];
}

export interface AssessmentFact {
  fact_id?: string;
  metric?: string;
  code?: string;
  title?: string;
  value?: DisplayScalar;
  unit?: string;
  scope?: string;
  quality?: string;
  note?: string | null;
}

export interface AssessmentNote {
  code?: string;
  title?: string;
  detail?: string;
  description?: string;
  text?: string;
  scope?: string;
  severity?: string;
  status?: string;
  fact_ids?: string[];
}

export interface NarrativePayload {
  headline?: string;
  statements?: Array<{ text?: string; fact_ids?: string[] }>;
}

export interface FinanceArtifactPayload {
  assessment_status?: string;
  facts?: AssessmentFact[];
  observations?: AssessmentNote[];
  limitations?: AssessmentNote[];
  narrative?: NarrativePayload;
  narrative_source?: string;
}

export interface OperationsArtifactPayload {
  assessment_status?: string;
  as_of_date?: string | null;
  facts?: AssessmentFact[];
  observations?: AssessmentNote[];
  limitations?: AssessmentNote[];
  summary?: Array<{ text?: string; fact_ids?: string[] }>;
  order_schedules?: Array<{
    order_id?: string;
    due_date?: string;
    status_category?: string;
    past_due_days?: number | null;
    outside_contract_window?: boolean;
  }>;
}

export interface RiskArtifactPayload {
  assessment_status?: string;
  overall_risk_level?: string;
  risk_level?: string;
  initial_risk_level?: string;
  residual_risk_level?: string;
  conclusion?: "SAFE" | "ATTENTION_REQUIRED";
  major_exception_status?: string;
  major_exception_signal?: { detail: string; severity?: string } | null;
  findings?: AssessmentNote[];
  residual_findings?: AssessmentNote[];
  required_controls?: AssessmentNote[];
  limitations?: AssessmentNote[];
  human_confirmation_points?: Array<{
    reason_code?: string;
    question: string;
    severity?: string;
  }>;
  unresolved_approval_gates?: Array<{
    protected_action?: string;
    request_status?: string;
    reason: string;
  }>;
}

export interface RiskPreScanPayload {
  contract_id?: string;
  source_rule_ids?: string[];
  source_rules?: Array<{
    rule_id: string;
    risk_type: string;
    declared_condition: string;
    severity: string;
    required_action: string;
  }>;
  case_alerts?: Array<{
    alert_id?: string;
    alert_type?: string;
    severity?: string;
    description: string;
    recommended_action?: string;
    related_entity_ids?: string[];
  }>;
  global_alerts?: Array<{
    alert_id?: string;
    alert_type?: string;
    severity?: string;
    description: string;
    recommended_action?: string;
  }>;
  source_record_counts?: Record<string, number>;
}

export interface ApprovalCheckpointPayload {
  checkpoints?: Array<{
    checkpoint_id?: string;
    source_rule_id?: string;
    protected_action?: string;
    trigger_event?: string;
    approver_role?: string;
    status?: string;
  }>;
}

export interface BankingArtifactPayload {
  status?: string;
  authority?: string;
  external_bank_submission?: boolean;
  bank_approval_obtained?: boolean;
  options?: BankingOption[];
  results?: BankingOption[];
  candidates?: BankingOption[];
}

export interface BankingOption {
  option_id?: string;
  bank_product_id?: string;
  provider?: string;
  api_provider?: string;
  product_name?: string;
  description?: string;
  requested_amount?: number | null;
  supported_amount?: number | null;
  currency?: string;
  annual_rate_or_fee?: number | null;
  processing_fee_rate?: number | null;
  collateral_ratio?: number | null;
  minimum_amount?: number | null;
  minimum_amount_currency?: string;
  outcome?: string;
  authority?: string;
  non_binding?: boolean;
  approval_conditions?: string[];
  required_documents?: string[];
  criteria?: Array<{ code?: string; status?: string; detail?: string }>;
}

export interface BankingAdvicePayload {
  status?: string;
  overview?: string;
  suggestions?: Array<{ rationale: string }>;
}

export interface DocumentArtifactPayload {
  readiness?: string;
  recipient?: string;
  purpose?: string;
  document_codes?: string[];
  limitation_codes?: string[];
  approval_condition_codes?: string[];
  document_manifest?: Array<{
    document_code?: string;
    status?: string;
    limitation_codes?: string[];
  }>;
  release_authorized?: boolean;
  external_release_performed?: boolean;
  sanitized_payload?: Record<string, string | number | boolean | null>;
}

export interface PlannerWarningPayload {
  warning_code?: string;
  target_record?: string;
  field?: string;
  reason: string;
}

export interface ContractRequirementPayload {
  requirement_type: string;
  certainty: string;
  requested_amount?: number | null;
  requested_amount_currency?: string;
  amount_semantics?: string | null;
  credit_case_id?: string | null;
}

export interface EvaluationCasePayload {
  contract_id: string;
  customer_id: string;
  related_order_ids?: string[];
  related_invoice_ids?: string[];
  related_service_ids?: string[];
  related_credit_case_ids?: string[];
  evaluation_scope?: string[];
  cashflow_scope?: string;
  warnings?: PlannerWarningPayload[];
  contract_requirements?: ContractRequirementPayload[];
}

export interface PlannerResultPayload {
  evaluation_case?: EvaluationCasePayload | null;
  data_readiness?: {
    status: string;
    blocking_missing_fields?: string[];
    non_blocking_warnings?: PlannerWarningPayload[];
    validation_notes?: string[];
  };
  run_plan?: { parallel_initial_tasks?: string[]; plan_reason?: string };
  warnings?: PlannerWarningPayload[];
}

export interface BankingDiscoveryPayload {
  contract_id?: string;
  status?: string;
  discovery_status?: string;
  need_types?: string[];
  requested_need_types?: string[];
  requested_amount?: number | null;
  requested_amount_currency?: string;
  candidates?: BankingOption[];
  data_gaps?: Array<{ code?: string; detail: string; blocking_for_precheck?: boolean }>;
  candidate_option_ids?: string[];
}

export interface BankingReadinessPayload {
  status?: string;
  option_readiness?: Array<{
    option_id?: string;
    status: string;
    required_fields?: string[];
    missing_fields?: string[];
    unmapped_fields?: string[];
    failed_requirement_codes?: string[];
  }>;
  ready_option_ids?: string[];
  pending_option_ids?: string[];
  precheck_executed?: boolean;
}

export interface DocumentChecklistPayload {
  items?: Array<{
    document_code: string;
    status: string;
    reason: string;
    limitation_codes?: string[];
    source_reference_ids?: string[];
    missing_request_id?: string | null;
  }>;
  missing_document_codes?: string[];
  approval_condition_codes?: string[];
}

export interface InternalDecisionPackagePayload {
  contract_id?: string;
  assembly_path?: string;
  readiness?: string;
  finance_assessment?: { assessment_status?: string };
  operations_assessment?: { assessment_status?: string };
  risk_assessment?: { assessment_status?: string; risk_level?: string; overall_risk_level?: string };
  banking_option_matrix?: { discovery_status?: string; candidates?: unknown[] } | null;
  banking_precheck_readiness?: { status?: string } | null;
  banking_precheck_result_set?: { authority?: string; results?: unknown[]; bank_approval_obtained?: boolean } | null;
  document_release_package?: { recipient?: string; purpose?: string; document_codes?: string[]; release_authorized?: boolean; external_release_performed?: boolean } | null;
  missing_data_requests?: unknown[];
}

export interface DecisionPostPrecheckReviewPayload {
  outcome?: string;
  option_reviews?: Array<{
    option_id?: string;
    bank_product_id?: string;
    api_provider?: string;
    source_outcome?: string;
    disposition?: string;
    reason_codes?: string[];
    required_follow_up_fields?: string[];
  }>;
  candidate_option_ids?: string[];
  candidate_bank_product_ids?: string[];
  conditional_option_ids?: string[];
  evidence_required_option_ids?: string[];
  not_eligible_option_ids?: string[];
  required_input_fields?: string[];
}

export interface ExactArtifactRefPayload {
  artifact_id?: string;
  artifact_type?: string;
  version?: number;
}

export interface BankingPrecheckSubmissionProposalPayload {
  proposal_id?: string;
  requested_amount?: number;
  requested_amount_currency?: string;
  proposed_action?: string;
  candidate_option_ids?: string[];
  non_ready_option_ids?: string[];
  candidates?: Array<{
    option_id?: string;
    bank_product_id?: string;
    need_type?: string;
    provider?: string;
    product_name?: string;
    api_provider?: string;
    catalog_terms?: {
      annual_rate_or_fee?: number | null;
      processing_fee_rate?: number | null;
      collateral_ratio?: number | null;
      minimum_amount?: number | null;
      minimum_amount_currency?: string;
    };
    field_bindings?: Array<{ required_field?: string; source?: string }>;
  }>;
  precheck_executed?: boolean;
  submission_executed?: boolean;
}

export interface PostDecisionUpdatePayload {
  update_id?: string;
  decision_card_artifact?: ExactArtifactRefPayload;
  founder_approval?: {
    approval_request_id?: string;
    protected_action?: string;
    status?: string;
    decision?: string;
    decision_reason?: string;
    decided_at?: string;
    approver_role?: string;
  };
  recommendation?: string;
  outcome?: string;
  contract_execution_status?: string;
  approved_condition_ids?: string[];
  selected_option_ids?: string[];
  negotiation_outcome_artifact?: ExactArtifactRefPayload | null;
  external_document_release_required?: boolean;
  founder_decision_recorded?: boolean;
  external_action_performed?: boolean;
}

export interface NegotiationOutcomePayload {
  negotiation_outcome_id?: string;
  decision_card_artifact?: ExactArtifactRefPayload;
  condition_outcomes?: Array<{
    condition_id?: string;
    condition_code?: string;
    condition_title?: string;
    customer_accepted?: boolean;
    founder_note?: string | null;
  }>;
  all_conditions_accepted?: boolean;
  outcome_status?: string;
  founder_summary?: string | null;
  confirmation_requested?: boolean;
}

export interface ExternalDocumentSubmissionProposalPayload {
  proposal_id?: string;
  decision_card_artifact?: ExactArtifactRefPayload;
  post_decision_update_artifact?: ExactArtifactRefPayload;
  contract_execution_status?: string;
  recipient?: string;
  purpose?: string;
  document_codes?: string[];
  approval_condition_codes?: string[];
  limitation_codes?: string[];
  proposed_action?: string;
  approval_requested?: boolean;
  release_authorized?: boolean;
  external_submission_performed?: boolean;
}

export interface BankingInputSupplementPayload {
  supplement_id?: string;
  requested_amount?: number;
  requested_amount_currency?: string;
  provider?: string;
  note?: string;
}

export interface BankingPrecheckEvidenceSupplementPayload {
  supplement_id?: string;
  option_id?: string;
  bank_product_id?: string;
  required_field?: string;
  evidence_reference_id?: string;
  provided_by?: string;
  evidence_note?: string;
  source_outcome?: string;
  fresh_governed_precheck_required?: boolean;
  bank_approval_obtained?: boolean;
}

export interface DocumentEvidenceSupplementPayload {
  supplement_id?: string;
  document_reference_id?: string;
  content_sha256?: string;
  document_type?: string;
  provided_by?: string;
  evidence_note?: string;
}

export interface ApprovalConditionPayload {
  source_field?: string;
  operator?: string;
  threshold?: string | number | boolean | null;
}

export interface ApprovalCheckpointSetPayload {
  contract_id?: string;
  checkpoints?: Array<{
    checkpoint_id?: string;
    source_rule_id?: string;
    approval_type?: string;
    trigger_event?: string;
    protected_action?: string;
    condition?: ApprovalConditionPayload;
    status?: string;
    approver_role?: string;
    policy_coverage_ids?: string[];
  }>;
  policy_coverages?: Array<{
    coverage_id?: string;
    protected_action?: string;
    subject_artifact_id?: string;
    source_policy_ids?: string[];
    requires_human_approval?: boolean;
    approver_role?: string;
  }>;
}

export interface RiskRuleEvaluationSetPayload {
  contract_id?: string;
  evaluations?: Array<{
    evaluation_id?: string;
    rule_id?: string;
    risk_type?: string;
    declared_condition?: string;
    applicability_scope?: string;
    status?: string;
    severity?: string | null;
    source_field?: string | null;
    operator?: string | null;
    threshold?: string | number | boolean | null;
    actual_value?: string | number | boolean | null;
    explanation?: string;
  }>;
}

export interface DecisionRoutePlanPayload {
  route_plan_id?: string;
  route_outcome?: string;
  required_capabilities?: string[];
  banking_need_types?: string[];
  routing_reasons?: Array<{
    reason_id?: string;
    code?: string;
    banking_need_type?: string;
    requirement_id?: string;
    requirement_certainty?: string;
    requested_amount?: number;
    requested_amount_currency?: string;
  }>;
  conditional_approval_checkpoint_ids?: string[];
}

export interface DecisionPostBankingReviewPayload {
  review_id?: string;
  outcome?: string;
  candidate_option_ids?: string[];
  precheck_ready_option_ids?: string[];
  pending_option_ids?: string[];
  required_input_fields?: string[];
  missing_data_requests?: Array<{
    request_id?: string;
    field?: string;
    reason?: string;
    severity?: string;
    status?: string;
  }>;
  precheck_executed?: boolean;
}

export interface DocumentPreparationRequestPayload {
  request_id?: string;
  option_id?: string;
  bank_product_id?: string;
  provider?: string;
  provider_reference?: string;
  requested_amount?: number;
  supported_amount?: number;
  currency?: string;
  required_document_codes?: string[];
  approval_condition_codes?: string[];
  provider_result_authority?: string;
  non_binding?: boolean;
  selection_performed?: boolean;
  bank_approval_obtained?: boolean;
  documents_prepared?: boolean;
  external_release_performed?: boolean;
}

export interface AIDecisionAnalysisPayload {
  analysis_id?: string;
  recommendation?: string;
  confidence?: string;
  executive_summary?: string;
  reasons?: Array<{ reason_id?: string; code?: string; title?: string; detail?: string }>;
  conditions?: Array<{ condition_id?: string; code?: string; title?: string }>;
  human_attention_points?: Array<{ attention_point_id?: string; code?: string; text?: string }>;
  source?: string;
  model?: string;
  prompt_version?: string;
  fallback_reason?: string | null;
  internal_decision_package_artifact?: ExactArtifactRefPayload;
  final_risk_artifact?: ExactArtifactRefPayload;
  approval_requested?: boolean;
  external_action_performed?: boolean;
  calculations_performed_by_model?: boolean;
}
