import type { ReactElement } from "react";

import { BankingAmountForm } from "./BankingAmountForm";
import { DocumentSupplementForm } from "./DocumentSupplementForm";
import { PrecheckEvidenceForm } from "./PrecheckEvidenceForm";
import type { BankingAmountSubmission, BankingPrecheckEvidenceSubmission, DocumentEvidenceSubmission, DocumentRequirementCode, MissingDataInteraction } from "./types";

export interface MissingDataDialogProps {
  open: boolean;
  workflow_run_id: string;
  interaction: MissingDataInteraction | null;
  allowed_document_types?: DocumentRequirementCode[];
  submitting?: boolean;
  onClose: () => void;
  onDocumentSubmit: (payload: DocumentEvidenceSubmission) => void | Promise<void>;
  onPrecheckEvidenceSubmit: (payload: BankingPrecheckEvidenceSubmission) => void | Promise<void>;
  onBankingAmountSubmit: (payload: BankingAmountSubmission) => void | Promise<void>;
}

export function MissingDataDialog({ open, workflow_run_id, interaction, allowed_document_types, submitting = false, onClose, onDocumentSubmit, onPrecheckEvidenceSubmit, onBankingAmountSubmit }: MissingDataDialogProps): ReactElement | null {
  if (!open) return null;
  const requestId = interaction?.request_ids[0];
  return (
    <div role="dialog" aria-modal="true" aria-labelledby="missing-data-title" className="missing-data-dialog">
      <article>
        <header><h2 id="missing-data-title">{interaction?.title_vi ?? "Bổ sung dữ liệu"}</h2></header>
        <p>{interaction?.instruction_vi ?? "Quy trình chưa cung cấp yêu cầu bổ sung có cấu trúc."}</p>
        {!interaction || !requestId ? <p role="alert">Không có yêu cầu đang mở để tiếp nhận dữ liệu.</p> : interaction.interaction_type === "DOCUMENT_EVIDENCE" ? (
          <DocumentSupplementForm workflow_run_id={workflow_run_id} missing_request_id={requestId} allowed_document_types={allowed_document_types} submitting={submitting} onSubmit={onDocumentSubmit} />
        ) : interaction.interaction_type === "BANKING_PRECHECK_EVIDENCE" ? (
          <PrecheckEvidenceForm workflow_run_id={workflow_run_id} missing_request_id={requestId} submitting={submitting} onSubmit={onPrecheckEvidenceSubmit} />
        ) : interaction.interaction_type === "BANKING_AMOUNT_INPUT" ? (
          <BankingAmountForm workflow_run_id={workflow_run_id} missing_request_id={requestId} submitting={submitting} onSubmit={onBankingAmountSubmit} />
        ) : <p role="alert">Loại dữ liệu này chưa có biểu mẫu an toàn. Không nhập dữ liệu tự do; cần bổ sung hợp đồng dữ liệu có kiểu rõ ràng.</p>}
        <footer><button type="button" onClick={onClose}>Đóng</button></footer>
      </article>
    </div>
  );
}
