import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type {
  DashboardMetricDto,
  NormalizedWorkflowDashboard,
} from "../../api/types";
import { businessValueLabel } from "../../shared/businessLabels";
import { statusTone } from "../../shared/workflowLabels";
import {
  AssessmentIndex,
  DecisionLimits,
  EvidenceIndex,
  metricDisplay,
} from "./ContractWorkspace";

describe("Contract decision workspace", () => {
  it("keeps unknown risk and non-evaluable business outcomes separate from execution completion", () => {
    expect(businessValueLabel("UNKNOWN")).toBe("Chưa xác định");
    expect(statusTone("NOT_EVALUABLE")).toBe("warning");
    expect(statusTone("WAITING_FOR_FINAL_DECISION")).toBe("warning");
    expect(statusTone("COMPLETED")).toBe("success");
  });
  it("preserves missing values and formats ratio units rather than guessing magnitude", () => {
    const metric: DashboardMetricDto = {
      code: "M",
      label_vi: "Margin",
      value: null,
      unit: "RATIO",
      scope: "CASE_SPECIFIC",
      quality: "NOT_AVAILABLE",
    };
    expect(metricDisplay(metric)).toBe("Chưa có dữ liệu");
    expect(metricDisplay({ ...metric, value: 0 })).toBe("0%");
    expect(metricDisplay({ ...metric, value: 1.5 })).toBe("150%");
  });
  it("uses the current task's validated assessment summary even when raw facts arrive first", () => {
    const projection = {
      stages: [
        {
          milestones: [
            {
              id: "OPS",
              code: "OPERATIONS_ASSESSMENT",
              label: "Operations",
              status: "COMPLETED",
              artifactIds: ["FACTS", "ASSESSMENT"],
            },
          ],
        },
      ],
    } as unknown as NormalizedWorkflowDashboard;
    const envelope = {
      version: 1,
      validation_status: "VALID",
      evaluation_case_id: "CASE",
      producer: "OPS",
      status: "CREATED",
    };
    render(
      <AssessmentIndex
        dashboard={projection}
        artifacts={[
          {
            ...envelope,
            artifact_id: "OLD",
            artifact_type: "OPERATIONS_ASSESSMENT",
            payload: { summary: [{ text: "Kết quả cũ." }] },
          },
          {
            ...envelope,
            artifact_id: "FACTS",
            artifact_type: "OPERATIONS_FACTS",
            payload: { facts: [] },
          },
          {
            ...envelope,
            artifact_id: "ASSESSMENT",
            artifact_type: "OPERATIONS_ASSESSMENT",
            payload: { summary: [{ text: "Lịch triển khai hiện hành." }] },
          },
        ]}
        onOpen={vi.fn()}
        canOpen={() => true}
      />,
    );
    expect(screen.getByText("Lịch triển khai hiện hành.")).toBeInTheDocument();
    expect(screen.queryByText("Kết quả cũ.")).not.toBeInTheDocument();
  });
  it("does not open unsupported evidence and binds supported details to exact artifact ID", () => {
    const onOpen = vi.fn();
    render(
      <EvidenceIndex
        artifacts={[
          {
            artifact_id: "EXACT-FINANCE",
            artifact_type: "FINANCE_FACTS",
            version: 3,
            validation_status: "VALID",
            evaluation_case_id: "CASE",
            producer: "FINANCE",
            status: "CREATED",
            payload: {},
          },
          {
            artifact_id: "UNSUPPORTED",
            artifact_type: "UNKNOWN",
            version: 1,
            validation_status: "VALID",
            evaluation_case_id: "CASE",
            producer: "UNKNOWN",
            status: "CREATED",
            payload: {},
          },
        ]}
        onOpen={onOpen}
        canOpen={(ids) => ids.includes("EXACT-FINANCE")}
      />,
    );
    const buttons = screen.getAllByRole("button", { name: "Xem chi tiết" });
    fireEvent.click(buttons[0]);
    expect(onOpen).toHaveBeenCalledWith(["EXACT-FINANCE"]);
    expect(buttons[1]).toBeDisabled();
    expect(screen.getByText("v3")).toBeInTheDocument();
    expect(screen.getAllByText("Đã kiểm tra bằng chứng")).toHaveLength(2);
  });
  it("keeps decision limitations available through progressive disclosure", () => {
    render(
      <DecisionLimits
        limitations={[{ detail: "Thiếu quan hệ giao dịch theo hợp đồng." }]}
      />,
    );
    expect(
      screen
        .getByText("Thiếu quan hệ giao dịch theo hợp đồng.")
        .closest("details"),
    ).not.toHaveAttribute("open");
  });
});
