import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { WorkflowStage } from "../../api/types";
import { StageAccordion } from "./StageAccordion";

const completedStage: WorkflowStage = {
  id: "FINANCE_ASSESSMENT",
  code: "FINANCE_ASSESSMENT",
  label: "Đánh giá tài chính",
  status: "COMPLETED",
  statusLabel: "Backend xác nhận đã hoàn tất",
  order: 1,
  parallel: false,
  applicability: "APPLICABLE",
  milestones: [
    {
      id: "FINANCE_ASSESSMENT",
      code: "FINANCE_ASSESSMENT",
      ownerId: "FINANCE",
      label: "Tính toán và diễn giải tài chính",
      status: "COMPLETED",
      statusLabel: "Tác vụ đã hoàn tất theo backend",
      resolutionStatus: "COMPLETED",
      waitingFor: [],
      applicability: "APPLICABLE",
      artifactIds: ["ART-FINANCE"],
    },
  ],
};

describe("StageAccordion playback", () => {
  it("shows the responsible skill or agent on the stage and its task", () => {
    render(<StageAccordion stage={completedStage} index={0} />);

    expect(screen.getAllByText(/Phụ trách: Finance Agent/)).toHaveLength(2);
  });

  it("does not reveal a completed task or its assessment before its paced turn", () => {
    const openAssessment = vi.fn();
    const { rerender } = render(
      <StageAccordion
        stage={completedStage}
        index={0}
        activeMilestoneId="FINANCE_ASSESSMENT"
        revealedMilestoneIds={[]}
        onOpenAssessment={openAssessment}
        canOpenAssessment={() => true}
      />,
    );

    expect(screen.getAllByText("Đang xử lý").length).toBeGreaterThan(0);
    expect(screen.queryByText("Backend xác nhận đã hoàn tất")).not.toBeInTheDocument();
    expect(screen.queryByText("Tác vụ đã hoàn tất theo backend")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Xem đánh giá" })).not.toBeInTheDocument();

    rerender(
      <StageAccordion
        stage={completedStage}
        index={0}
        revealedMilestoneIds={["FINANCE_ASSESSMENT"]}
        onOpenAssessment={openAssessment}
        canOpenAssessment={() => true}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Xem đánh giá" }));
    expect(openAssessment).toHaveBeenCalledWith(["ART-FINANCE"]);
    expect(screen.getByText("Backend xác nhận đã hoàn tất")).toBeInTheDocument();
    expect(screen.getByText("Tác vụ đã hoàn tất theo backend")).toBeInTheDocument();
  });

  it("treats an approved Founder task as resolved during playback", () => {
    const approvedStage: WorkflowStage = {
      ...completedStage,
      id: "FINAL_DECISION_APPROVAL",
      code: "FINAL_DECISION_APPROVAL",
      milestones: [
        {
          ...completedStage.milestones[0],
          id: "FINAL_DECISION_APPROVAL_TASK",
          code: "FINAL_DECISION_APPROVAL_TASK",
          statusLabel: "Founder đã phê duyệt",
          resolutionStatus: "APPROVED",
        },
      ],
    };

    render(
      <StageAccordion
        stage={approvedStage}
        index={3}
        activeMilestoneId="FINAL_DECISION_APPROVAL_TASK"
        revealedMilestoneIds={[]}
      />,
    );

    expect(screen.queryByText("Founder đã phê duyệt")).not.toBeInTheDocument();
    expect(screen.getAllByText("Đang xử lý").length).toBeGreaterThan(0);
  });

  it("renders exact rejected and expired labels, applicability reasons, and tones", () => {
    const rejectedStage: WorkflowStage = {
      ...completedStage,
      id: "FINAL_DECISION_APPROVAL",
      code: "FINAL_DECISION_APPROVAL",
      status: "REJECTED",
      statusLabel: "Founder đã từ chối yêu cầu này",
      milestones: [
        {
          ...completedStage.milestones[0],
          id: "FINAL_DECISION_APPROVAL_TASK",
          code: "FINAL_DECISION_APPROVAL_TASK",
          status: "REJECTED",
          statusLabel: "Yêu cầu quyết định đã bị từ chối",
          resolutionStatus: "REJECTED",
          applicabilityReason: "Không tiếp tục vì quyết định hiện hành không được xác nhận.",
        },
      ],
    };
    const { container, rerender } = render(
      <StageAccordion stage={rejectedStage} index={3} />,
    );

    expect(screen.getByText("Founder đã từ chối yêu cầu này")).toBeInTheDocument();
    expect(screen.getByText("Yêu cầu quyết định đã bị từ chối")).toBeInTheDocument();
    expect(
      screen.getByText("Không tiếp tục vì quyết định hiện hành không được xác nhận."),
    ).toBeInTheDocument();
    expect(container.querySelector(".status-badge--danger")).toBeInTheDocument();
    expect(container.querySelector(".milestone__marker--rejected")).toBeInTheDocument();

    const expiredStage: WorkflowStage = {
      ...rejectedStage,
      status: "EXPIRED",
      statusLabel: "Yêu cầu đã hết hiệu lực theo backend",
      milestones: [
        {
          ...rejectedStage.milestones[0],
          status: "EXPIRED",
          statusLabel: "Tác vụ đã hết hiệu lực",
          resolutionStatus: "EXPIRED",
        },
      ],
    };
    rerender(<StageAccordion stage={expiredStage} index={3} />);

    expect(screen.getByText("Yêu cầu đã hết hiệu lực theo backend")).toBeInTheDocument();
    expect(screen.getByText("Tác vụ đã hết hiệu lực")).toBeInTheDocument();
    expect(container.querySelector(".status-badge--warning")).toBeInTheDocument();
    expect(container.querySelector(".milestone__marker--expired")).toBeInTheDocument();
  });

  it("shows the exact shared backend reason on a collapsed not-applicable stage", () => {
    const backendReason =
      "Phiếu quyết định chưa đủ cơ sở nên không mở tuyến phát hành bên ngoài.";
    const notApplicableStage: WorkflowStage = {
      ...completedStage,
      id: "EXTERNAL_RELEASE",
      code: "EXTERNAL_RELEASE",
      status: "NOT_APPLICABLE",
      statusLabel: "Không áp dụng",
      applicability: "NOT_APPLICABLE",
      milestones: [
        {
          ...completedStage.milestones[0],
          id: "EXTERNAL_PROPOSAL",
          code: "EXTERNAL_PROPOSAL",
          status: "NOT_APPLICABLE",
          statusLabel: "Không áp dụng",
          applicability: "NOT_APPLICABLE",
          applicabilityReason: backendReason,
        },
        {
          ...completedStage.milestones[0],
          id: "EXTERNAL_APPROVAL",
          code: "EXTERNAL_APPROVAL",
          status: "NOT_APPLICABLE",
          statusLabel: "Không áp dụng",
          applicability: "NOT_APPLICABLE",
          applicabilityReason: backendReason,
        },
      ],
    };

    render(<StageAccordion stage={notApplicableStage} index={11} />);

    expect(screen.getByRole("button", { expanded: false })).toBeInTheDocument();
    expect(screen.getByText(backendReason)).toBeInTheDocument();
    expect(
      screen.queryByText("Nhánh này không áp dụng cho hồ sơ hiện tại"),
    ).not.toBeInTheDocument();
  });
});
