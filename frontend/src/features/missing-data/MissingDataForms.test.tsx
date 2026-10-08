import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BankingAmountForm } from "./BankingAmountForm";
import { DocumentSupplementForm } from "./DocumentSupplementForm";
import { PrecheckEvidenceForm } from "./PrecheckEvidenceForm";

describe("typed missing-data forms", () => {
  it("derives opaque document metadata from an uploaded PDF", async () => {
    const submit = vi.fn();
    render(<DocumentSupplementForm workflow_run_id="RUN-1" missing_request_id="MDR-1" allowed_document_types={["PERFORMANCE_BOND_REQUEST_FORM"]} onSubmit={submit} />);
    const file = new File(["bank form"], "don-de-nghi.pdf", { type: "application/pdf" });
    Object.defineProperty(file, "arrayBuffer", { value: async () => new TextEncoder().encode("bank form").buffer });
    fireEvent.change(screen.getByLabelText(/Chọn tệp Đơn đề nghị bảo lãnh thực hiện/i), { target: { files: [file] } });
    await waitFor(() => expect(screen.getByText("don-de-nghi.pdf")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Bổ sung tệp và tiếp tục quy trình" }));
    expect(submit).toHaveBeenCalledWith(expect.objectContaining({ workflow_run_id: "RUN-1", missing_request_id: "MDR-1", document_reference_id: expect.stringMatching(/^DOCREF-/), content_sha256: expect.stringMatching(/^[a-f0-9]{64}$/), document_type: "PERFORMANCE_BOND_REQUEST_FORM", evidence_note: "REQUESTED_DOCUMENT_REFERENCE_SUPPLIED" }));
  });

  it("rejects file types other than PDF and DOCX", async () => {
    const submit = vi.fn();
    render(<DocumentSupplementForm workflow_run_id="RUN-1" missing_request_id="MDR-1" onSubmit={submit} />);
    const file = new File(["bad"], "malware.exe", { type: "application/octet-stream" });
    fireEvent.change(screen.getByLabelText(/Chọn tệp/i), { target: { files: [file] } });
    expect(await screen.findByRole("alert")).toHaveTextContent(/chỉ chấp nhận tệp PDF hoặc DOCX/i);
    expect(submit).not.toHaveBeenCalled();
  });

  it("refuses to fabricate a reference or hash when browser hashing is unavailable", async () => {
    const submit = vi.fn();
    vi.stubGlobal("crypto", { randomUUID: () => "11111111-1111-4111-8111-111111111111" });
    try {
      render(<DocumentSupplementForm workflow_run_id="RUN-1" missing_request_id="MDR-1" allowed_document_types={["PERFORMANCE_BOND_REQUEST_FORM"]} onSubmit={submit} />);
      const file = new File(["bank form"], "don-de-nghi.pdf", { type: "application/pdf" });
      fireEvent.change(screen.getByLabelText(/Chọn tệp/i), { target: { files: [file] } });
      expect(await screen.findByRole("alert")).toHaveTextContent(/không hỗ trợ tính mã băm SHA-256/i);
      expect(screen.getByLabelText(/Chọn tệp/i)).toHaveAttribute("aria-invalid", "true");
      expect(screen.getByRole("button", { name: "Bổ sung tệp và tiếp tục quy trình" })).toBeDisabled();
      expect(submit).not.toHaveBeenCalled();
    } finally {
      vi.unstubAllGlobals();
    }
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
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(/số nguyên VND dương/i);
    expect(screen.getByLabelText("Số tiền cần hỗ trợ (VND)")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Số tiền cần hỗ trợ (VND)")).toHaveAttribute("aria-describedby", alert.id);
    expect(screen.getByLabelText("Căn cứ nhập liệu")).not.toHaveAttribute("aria-invalid");
    expect(submit).not.toHaveBeenCalled();
  });

  it("marks only the missing precheck evidence field as invalid", () => {
    const submit = vi.fn();
    render(<PrecheckEvidenceForm workflow_run_id="RUN-2" missing_request_id="MDR-2" onSubmit={submit} />);
    fireEvent.change(screen.getByLabelText("Mã tham chiếu tài liệu bổ sung"), { target: { value: "DOC-REF-22" } });
    fireEvent.submit(screen.getByRole("form", { name: "Bổ sung căn cứ cho kiểm tra sơ bộ với ngân hàng" }));
    const alert = screen.getByRole("alert");
    expect(screen.getByLabelText("Nội dung bổ sung")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Nội dung bổ sung")).toHaveAttribute("aria-describedby", alert.id);
    expect(screen.getByLabelText("Mã tham chiếu tài liệu bổ sung")).not.toHaveAttribute("aria-invalid");
    expect(submit).not.toHaveBeenCalled();
  });

});
