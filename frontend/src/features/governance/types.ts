export type ApprovalDecision = "APPROVE" | "REJECT";

export type ProtectedAction =
  | "CONFIRM_FINAL_CONTRACT_DECISION"
  | "SUBMIT_BANKING_PRECHECK"
  | "SEND_DOCUMENT_TO_EXTERNAL_PARTNER"
  | "COMMIT_LARGE_FINANCIAL_DECISION"
  | string;

export interface ApprovalRequestView {
  request_id: string;
  workflow_run_id?: string;
  status: "PENDING" | "APPROVED" | "REJECTED" | "EXPIRED" | "AUTHORIZED_WITHOUT_HUMAN" | string;
  subject_artifact_id: string;
  command?: { action_type: ProtectedAction };
  protected_action?: ProtectedAction;
  decision_record?: {
    decision: ApprovalDecision;
    decided_by: string;
    reason: string;
    decided_at: string;
  } | null;
}

export interface ApprovalSubjectSummary {
  title: string;
  description: string;
  recommendation?: string | null;
  amount?: number | null;
  currency?: string;
  recipient?: string | null;
  document_codes?: string[];
}
