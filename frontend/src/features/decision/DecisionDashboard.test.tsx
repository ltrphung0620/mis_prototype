import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DecisionDashboard } from "./DecisionDashboard";

describe("DecisionDashboard", () => {
  it("distinguishes external readiness from an actual send", () => {
    render(<DecisionDashboard data={{ contract_id: "CON-004", execution_status_label_vi: "Hoàn thành", business_status: "READY_FOR_EXTERNAL_SUBMISSION", business_status_label_vi: "Sẵn sàng gửi hồ sơ", current_stage_label_vi: "Chờ tích hợp ngoài", progress_percent: 100, decision_card: { available: true, recommendation_label_vi: "Chấp nhận hợp đồng", recommendation: "ACCEPT", executive_summary: "Có thể tiếp tục." }, ready_for_external_submission: true, external_submission_performed: false }} />);
    expect(screen.getByRole("heading", { name: "Decision Dashboard" })).toBeInTheDocument();
    expect(screen.getByText(/sẵn sàng để gửi; chưa có xác nhận đã gửi/i)).toBeInTheDocument();
    expect(screen.queryByText("Hệ thống ghi nhận hồ sơ đã được gửi ra ngoài.")).not.toBeInTheDocument();
  });

  it("renders decision, risk, and post-decision enums in Vietnamese", () => {
    render(
      <DecisionDashboard
        data={{
          contract_id: "CON-004",
          execution_status_label_vi: "Đã hoàn tất",
          business_status: "NEGOTIATION_IN_PROGRESS",
          business_status_label_vi: "Đang thực hiện đàm phán",
          current_stage_label_vi: "Cập nhật sau quyết định",
          progress_percent: 100,
          decision_card: {
            available: true,
            recommendation_label_vi: "Đàm phán điều kiện trước khi chấp nhận",
            recommendation: "NEGOTIATE_CONDITIONS_TO_ACCEPT",
            confidence: "MEDIUM",
            executive_summary: "Cần hoàn tất các điều kiện trước khi chấp nhận.",
          },
          residual_risk_level: "HIGH",
          post_decision_outcome: "NEGOTIATION_AUTHORIZED",
        }}
      />,
    );

    expect(screen.getByText("Độ tin cậy")).toBeInTheDocument();
    expect(screen.getByText("Trung bình")).toBeInTheDocument();
    expect(screen.getByText("Rủi ro còn lại")).toBeInTheDocument();
    expect(screen.getByText("Cao")).toBeInTheDocument();
    expect(
      screen.getByText("Kết quả sau quyết định: Đã cho phép tiến hành đàm phán."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/MEDIUM|HIGH|NEGOTIATION_AUTHORIZED/)).not.toBeInTheDocument();
  });

  it("separates a card waiting for playback from a missing card", () => {
    const base = { contract_id: "CON-1", execution_status_label_vi: "Chờ Founder", business_status: "WAITING_FOR_FINAL_DECISION", business_status_label_vi: "Chờ duyệt quyết định cuối", current_stage_label_vi: "Founder xem xét", progress_percent: 40 };
    const { rerender } = render(<DecisionDashboard data={{ ...base, decision_card: { available: false, reveal_pending: true, recommendation_label_vi: "Đang chờ" } }} />);
    expect(screen.getByRole("status")).toHaveTextContent("đã được tạo; đang hiển thị lần lượt");
    expect(screen.queryByText(/chưa sẵn sàng/)).not.toBeInTheDocument();

    rerender(<DecisionDashboard data={{ ...base, decision_card: { available: false, recommendation_label_vi: "Chưa có" } }} />);
    expect(screen.getByText("Decision Card của lượt chạy hiện tại chưa sẵn sàng.")).toBeInTheDocument();
    expect(screen.queryByText(/đã được tạo/)).not.toBeInTheDocument();
  });
});
