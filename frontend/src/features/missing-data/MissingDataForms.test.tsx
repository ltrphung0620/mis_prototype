import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BankingAmountForm } from "./BankingAmountForm";
import { DocumentSupplementForm } from "./DocumentSupplementForm";
import { PrecheckEvidenceForm } from "./PrecheckEvidenceForm";

describe("typed missing-data forms", () => {
  it("submits only opaque document metadata and a content hash", () => {
    const submit = vi.fn();
    const { container } = render(<DocumentSupplementForm workflow_run_id="RUN-1" missing_request_id="MDR-1" allowed_document_types={["SIGNED_CONTRACT"]} onSubmit={submit} />);
    fireEvent.change(screen.getByLabelText("Mã tham chiếu tài liệu"), { target: { value: "DOCREF-12345678-1234-4abc-8def-1234567890ab" } });
    fireEvent.change(screen.getByLabelText("SHA-256 của nội dung"), { target: { value: "a".repeat(64) } });
    fireEvent.click(screen.getByRole("button", { name: "Gửi tham chiếu bổ sung" }));
    expect(submit).toHaveBeenCalledWith({ workflow_run_id: "RUN-1", missing_request_id: "MDR-1", document_reference_id: "DOCREF-12345678-1234-4abc-8def-1234567890ab", content_sha256: "a".repeat(64), document_type: "SIGNED_CONTRACT", evidence_note: "REQUESTED_DOCUMENT_REFERENCE_SUPPLIED" });
    expect(container.querySelector('input[type="file"]')).toBeNull();
  });

  it("rejects paths and invalid hashes", () => {
    const submit = vi.fn();
    render(<DocumentSupplementForm workflow_run_id="RUN-1" missing_request_id="MDR-1" onSubmit={submit} />);
    fireEvent.change(screen.getByLabelText("Mã tham chiếu tài liệu"), { target: { value: "C:\\secret\\contract.pdf" } });
    fireEvent.change(screen.getByLabelText("SHA-256 của nội dung"), { target: { value: "bad" } });
    fireEvent.submit(screen.getByRole("form", { name: "Bổ sung tham chiếu tài liệu" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/không nhập đường dẫn/i);
    expect(submit).not.toHaveBeenCalled();
  });

  it("binds precheck evidence to the exact workflow request", () => {
    const submit = vi.fn();
    render(<PrecheckEvidenceForm workflow_run_id="RUN-2" missing_request_id="MDR-2" onSubmit={submit} />);
    fireEvent.change(screen.getByLabelText("Mã tham chiếu tài liệu bổ sung"), { target: { value: "DOC-REF-22" } });
    fireEvent.change(screen.getByLabelText("Nội dung bổ sung"), { target: { value: "Đã cung cấp hồ sơ pháp lý còn thiếu." } });
    fireEvent.click(screen.getByRole("button", { name: "Gửi thông tin bổ sung" }));
    expect(submit).toHaveBeenCalledWith({ workflow_run_id: "RUN-2", missing_request_id: "MDR-2", evidence_reference_id: "DOC-REF-22", evidence_note: "Đã cung cấp hồ sơ pháp lý còn thiếu." });
  });

  it("does not invent or accept an invalid Banking amount", () => {
    const submit = vi.fn();
    render(<BankingAmountForm workflow_run_id="RUN-3" missing_request_id="MDR-3" onSubmit={submit} />);
    fireEvent.change(screen.getByLabelText("Số tiền cần hỗ trợ (VND)"), { target: { value: "420.5" } });
    fireEvent.change(screen.getByLabelText("Căn cứ nhập liệu"), { target: { value: "Founder cung cấp cho yêu cầu legacy." } });
    fireEvent.submit(screen.getByRole("form", { name: "Bổ sung số tiền ngân hàng" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/số nguyên VND dương/i);
    expect(submit).not.toHaveBeenCalled();
  });
});
