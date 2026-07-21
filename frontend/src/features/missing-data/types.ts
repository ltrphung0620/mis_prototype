export type DocumentRequirementCode =
  | "SIGNED_CONTRACT"
  | "COMPANY_PROFILE"
  | "PERFORMANCE_BOND_REQUEST_FORM"
  | "CASHFLOW_BUFFER_EVIDENCE";

export interface DocumentEvidenceSubmission {
  workflow_run_id: string;
  missing_request_id: string;
  document_reference_id: string;
  content_sha256: string;
  document_type: DocumentRequirementCode;
  evidence_note: "REQUESTED_DOCUMENT_REFERENCE_SUPPLIED";
}

export interface BankingPrecheckEvidenceSubmission {
  workflow_run_id: string;
  missing_request_id: string;
  evidence_reference_id: string;
  evidence_note: string;
}

export interface BankingAmountSubmission {
  workflow_run_id: string;
  missing_request_id: string;
  requested_amount: number;
  requested_amount_currency: "VND";
  evidence_note: string;
}

export type MissingDataInteractionType =
  | "DOCUMENT_EVIDENCE"
  | "BANKING_PRECHECK_EVIDENCE"
  | "BANKING_AMOUNT_INPUT"
  | "UNSUPPORTED_INPUT";

export interface MissingDataInteraction {
  interaction_type: MissingDataInteractionType;
  title_vi: string;
  instruction_vi: string;
  request_ids: string[];
  required_fields?: string[];
}

