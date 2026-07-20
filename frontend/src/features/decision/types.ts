export type DecisionRecommendation =
  | "ACCEPT"
  | "NEGOTIATE_CONDITIONS_TO_ACCEPT"
  | "DO_NOT_ACCEPT"
  | "NOT_EVALUABLE";

export type DecisionConfidence = "HIGH" | "MEDIUM" | "LOW" | "NOT_EVALUABLE";

export interface DecisionMetric {
  metric: string;
  label_vi?: string;
  value: string | number | boolean | null;
  unit: string;
  quality?: string;
  role?: string;
  contract_attributable?: boolean;
  scope?: string;
}

export interface DecisionTarget {
  metric: string;
  operator: "GTE" | "LTE" | "EQ" | string;
  current_value?: number | null;
  target_value: number;
  unit: string;
  currency?: string | null;
}

export interface DecisionReason {
  code?: string;
  title: string;
  detail: string;
}

export interface DecisionCondition {
  condition_id?: string;
  code?: string;
  category?: string;
  title: string;
  description: string;
  status: string;
  enforcement_point: string;
  target?: DecisionTarget | null;
  expected_risk_effect?: string;
}

export interface NegotiationStrategy {
  strategy_id?: string;
  title: string;
  founder_instruction: string;
  assumptions?: string[];
  required_adjustment_value?: number;
  resulting_revenue?: number;
  resulting_cost?: number;
  target_margin?: number;
  currency?: string;
}

export interface DecisionOption {
  option_id?: string;
  product_name: string;
  provider: string;
  requested_amount?: number | null;
  supported_amount?: number | null;
  currency?: string;
  annual_rate_or_fee?: number | null;
  processing_fee_rate?: number | null;
  collateral_ratio?: number | null;
  precheck_outcome?: string | null;
  non_binding?: boolean;
}

export interface DecisionCalculation {
  calculation_id?: string;
  code: string;
  formula?: string;
  result_value: number;
  result_unit: string;
}

export interface DecisionFinding {
  code?: string;
  title: string;
  detail: string;
  severity?: string;
  status?: string;
}

export interface DecisionControl {
  code?: string;
  description: string;
  protected_action?: string | null;
}

export interface DecisionLimitation {
  code?: string;
  detail: string;
}

export interface DecisionAttentionPoint {
  code?: string;
  text: string;
}

export interface DecisionDocumentPackage {
  recipient: string;
  purpose: string;
  document_codes: string[];
  limitation_codes?: string[];
  release_authorized?: boolean;
}

export interface DecisionCardPayload {
  decision_card_id: string;
  contract_id: string;
  ai_analysis_id?: string;
  ai_analysis_artifact?: {
    artifact_id: string;
    version: number;
    input_hash?: string;
  };
  /** Enriched from the exact AI_DECISION_ANALYSIS artifact, never trusted from the card itself. */
  analysis_source?: "OPENAI" | "DETERMINISTIC_FALLBACK";
  recommendation: DecisionRecommendation;
  executive_summary: string;
  confidence: DecisionConfidence;
  reasons: DecisionReason[];
  conditions?: DecisionCondition[];
  selected_negotiation_strategies?: NegotiationStrategy[];
  selected_options?: DecisionOption[];
  finance_metrics?: DecisionMetric[];
  operations_metrics?: DecisionMetric[];
  calculations?: DecisionCalculation[];
  residual_risk_level: string;
  major_exception_status?: string;
  residual_findings?: DecisionFinding[];
  required_controls?: DecisionControl[];
  limitations?: DecisionLimitation[];
  human_attention_points?: DecisionAttentionPoint[];
  document_release_package?: DecisionDocumentPackage | null;
}

export interface DecisionCardArtifact {
  artifact_id: string;
  version: number;
  payload: DecisionCardPayload;
}

export interface PendingDecisionApproval {
  request_id: string;
  status: string;
  subject_artifact_id: string;
  subject_artifact_version: number;
  protected_action?: string;
}

export interface DecisionCardSummary {
  available: boolean;
  artifact_id?: string | null;
  decision_card_id?: string | null;
  recommendation?: DecisionRecommendation | null;
  recommendation_label_vi: string;
  confidence?: DecisionConfidence | null;
  executive_summary?: string | null;
}

export interface DecisionDashboardData {
  contract_id: string;
  execution_status_label_vi: string;
  business_status: string;
  business_status_label_vi: string;
  current_stage_label_vi: string;
  progress_percent: number;
  metrics?: DecisionMetric[];
  decision_card: DecisionCardSummary;
  condition_titles?: string[];
  residual_risk_level?: string | null;
  post_decision_outcome?: string | null;
  ready_for_external_submission?: boolean;
  external_submission_performed?: boolean;
}
