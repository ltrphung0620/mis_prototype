import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApprovalDialog } from "./ApprovalDialog";

describe("ApprovalDialog", () => {
  it("offers only approve and reject for an exact pending subject", () => {
    const decide = vi.fn();
    render(<ApprovalDialog open request={{ request_id: "APR-1", status: "PENDING", subject_artifact_id: "ART-1", protected_action: "SUBMIT_BANKING_PRECHECK" }} subject={{ title: "Cho phép precheck", description: "Khảo sát phương án bảo lãnh.", amount: 420_000_000 }} onClose={vi.fn()} onDecision={decide} />);
    expect(screen.getByText(/không phải chấp thuận cấp tín dụng/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /yêu cầu sửa/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Từ chối" }));
    expect(decide).toHaveBeenCalledWith("APR-1", "REJECT");
  });

  it("does not claim that an external package was sent", () => {
    render(<ApprovalDialog open request={{ request_id: "APR-2", status: "PENDING", subject_artifact_id: "ART-2", protected_action: "SEND_DOCUMENT_TO_EXTERNAL_PARTNER" }} subject={{ title: "Cho phép gửi hồ sơ", description: "Gói hồ sơ đã masking.", recipient: "VietinBank" }} onClose={vi.fn()} onDecision={vi.fn()} />);
    expect(screen.getByText(/trước khi phê duyệt, hồ sơ chưa được gửi/i)).toBeInTheDocument();
    expect(screen.queryByText(/đã gửi thành công/i)).not.toBeInTheDocument();
  });

  it("locks a stale approval request", () => {
    render(<ApprovalDialog open request={{ request_id: "APR-OLD", status: "PENDING", subject_artifact_id: "ART-OLD", protected_action: "CONFIRM_FINAL_CONTRACT_DECISION" }} subject={{ title: "Quyết định cũ", description: "Không còn hiện hành.", recommendation: "NEGOTIATE_CONDITIONS_TO_ACCEPT" }} is_current_subject={false} onClose={vi.fn()} onDecision={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Phê duyệt" })).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/không còn khớp/i);
    expect(screen.getByText(/ACCEPT_WITH_CONDITIONS · Chấp nhận có điều kiện/)).toBeInTheDocument();
    expect(screen.queryByText("NEGOTIATE_CONDITIONS_TO_ACCEPT")).not.toBeInTheDocument();
  });
});
