/** Presentation contracts for isolated UI fixtures; these are not new public API schemas. */
export type PreviewMode = "ready" | "loading" | "empty" | "error";
export type CompanySection =
  "overview" | "finance" | "business" | "invoices" | "alerts";
export type ContractSection =
  "overview" | "assessments" | "workflow" | "evidence" | "history";
export interface PreviewRoute {
  page: "dashboard" | "company" | "contracts" | "not-found";
  section?: CompanySection;
  contractId?: string;
  view?: ContractSection;
  period?: string;
  status?: string;
  request?: string;
  workflowScenario?: string;
  workflowPhase?: string;
}
export interface PreviewContract {
  id: string;
  customer: string;
  title: string;
  value: number;
  margin: number;
  sourceStatus: string;
  businessStatus: string;
  statusLabel: string;
  runId: string | null;
  date: string;
  attention?: string;
}
export interface CashPoint {
  month: string;
  label: string;
  cashIn: number | null;
  cashOut: number | null;
  closing: number | null;
  reserve: number;
}
export interface PreviewAction {
  id: string;
  kind: "approval" | "input" | "failure";
  title: string;
  description: string;
  contractId: string;
  label: string;
  link: string;
}
export interface InvoiceRow {
  id: string;
  order: string;
  contract: string;
  customer: string;
  amount: number;
  status: "Paid" | "Open" | "Not issued";
  date: string | null;
}
export interface OrderRow {
  id: string;
  contract: string;
  service: string;
  status: string;
  due: string;
}
export interface SourceAlert {
  id: string;
  title: string;
  detail: string;
  severity: string;
  contract?: string;
}
export interface StatusPoint {
  label: string;
  value: number;
  status: string;
}
