import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { NormalizedWorkflowDashboard } from "../../api/types";
import {
  DEFAULT_WORKFLOW_STEP_DELAY_MS,
  advancePlayback,
  useWorkflowPlayback,
} from "./useWorkflowPlayback";

function dashboard(resolved: number, total = 4): NormalizedWorkflowDashboard {
  return {
    datasetId: "DATASET",
    snapshotHash: "HASH",
    workflowRunId: "RUN-1",
    contractId: "CON-004",
    status: "RUNNING",
    statusLabel: "Đang xử lý",
    currentStage: "FINANCE_ASSESSMENT",
    currentStageLabel: "Đánh giá tài chính",
    pendingApprovalCount: 0,
    pendingMissingDataCount: 0,
    businessStatus: "ASSESSMENT_IN_PROGRESS",
    businessStatusLabel: "Đang đánh giá cơ hội",
    resolvedMilestoneCount: resolved,
    totalMilestoneCount: total,
    progressPercent: Math.round((resolved / total) * 100),
    input: {
      contractId: "CON-004",
      contractLabel: "CON-004",
      readinessStatus: "READY",
      blockingCount: 0,
      warningCount: 0,
      linkedRecords: [],
      blockingItems: [],
      warnings: [],
      contractRequirements: [],
    },
    stages: [],
    runArtifacts: [],
    approvalRequestIds: [],
    pendingInteractions: [],
    metrics: [],
    decisionCard: {
      available: resolved === total,
      recommendation_label_vi: "Chưa có Decision Card",
    },
  };
}

afterEach(() => {
  vi.useRealTimers();
});

describe("workflow playback", () => {
  it("uses a one-second delay between visible workflow steps", () => {
    expect(DEFAULT_WORKFLOW_STEP_DELAY_MS).toBe(1_000);
  });

  it("advances one confirmed backend step at a time", () => {
    expect(advancePlayback(0, 3)).toBe(1);
    expect(advancePlayback(2, 3)).toBe(3);
    expect(advancePlayback(3, 3)).toBe(3);
    expect(advancePlayback(1, 4, [1, 3, 4])).toBe(3);
  });

  it("paces visual progress and reveals Decision Card only after catching up", () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useWorkflowPlayback(dashboard(3), 200));

    expect(result.current.resolved).toBe(0);
    expect(result.current.isPlaying).toBe(true);
    expect(result.current.canRevealDecisionCard).toBe(false);

    act(() => vi.advanceTimersByTime(200));
    expect(result.current.resolved).toBe(1);
    act(() => vi.advanceTimersByTime(200));
    expect(result.current.resolved).toBe(2);
    act(() => vi.advanceTimersByTime(200));

    expect(result.current.resolved).toBe(3);
    expect(result.current.percent).toBe(75);
    expect(result.current.isPlaying).toBe(false);
    expect(result.current.canRevealDecisionCard).toBe(true);
  });
});
