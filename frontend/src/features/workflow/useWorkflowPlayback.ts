import { useEffect, useMemo, useState } from "react";

import type { NormalizedWorkflowDashboard } from "../../api/types";
import { workflowMilestoneProgress } from "./workflowModel";

export const DEFAULT_WORKFLOW_STEP_DELAY_MS = 1_000;

interface PlaybackCursor {
  workflowRunId: string;
  resolved: number;
}

export interface WorkflowPlayback {
  resolved: number;
  total: number;
  percent: number;
  isPlaying: boolean;
  canRevealDecisionCard: boolean;
}

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

export function advancePlayback(
  current: number,
  target: number,
  stageBoundaries: readonly number[] = [],
): number {
  const normalizedCurrent = Math.max(0, current);
  const normalizedTarget = Math.max(0, target);
  const nextBoundary = stageBoundaries.find(
    (boundary) =>
      boundary > normalizedCurrent && boundary <= normalizedTarget,
  );
  return nextBoundary ?? Math.min(normalizedCurrent + 1, normalizedTarget);
}

export function useWorkflowPlayback(
  dashboard: NormalizedWorkflowDashboard | null,
  stepDelayMs = DEFAULT_WORKFLOW_STEP_DELAY_MS,
): WorkflowPlayback {
  const progress = useMemo(
    () => (dashboard ? workflowMilestoneProgress(dashboard) : null),
    [dashboard],
  );
  const workflowRunId = dashboard?.workflowRunId ?? "";
  const targetResolved = progress?.resolved ?? 0;
  const total = progress?.total ?? 0;
  const stageBoundaries = useMemo(() => {
    let cumulative = 0;
    return (dashboard?.stages ?? []).map((stage) => {
      cumulative += Math.max(1, stage.milestones.length);
      return cumulative;
    });
  }, [dashboard?.stages]);
  const reducedMotion = prefersReducedMotion();
  const [cursor, setCursor] = useState<PlaybackCursor>({
    workflowRunId: "",
    resolved: 0,
  });

  const resolved =
    cursor.workflowRunId === workflowRunId
      ? Math.min(cursor.resolved, targetResolved)
      : 0;

  useEffect(() => {
    if (!workflowRunId) {
      setCursor({ workflowRunId: "", resolved: 0 });
      return undefined;
    }
    if (cursor.workflowRunId !== workflowRunId) {
      setCursor({
        workflowRunId,
        resolved: reducedMotion ? targetResolved : 0,
      });
      return undefined;
    }
    if (reducedMotion || cursor.resolved > targetResolved) {
      setCursor({ workflowRunId, resolved: targetResolved });
      return undefined;
    }
    if (cursor.resolved >= targetResolved) return undefined;

    const timer = window.setTimeout(() => {
      setCursor((current) =>
        current.workflowRunId === workflowRunId
          ? {
              workflowRunId,
              resolved: advancePlayback(
                current.resolved,
                targetResolved,
                stageBoundaries,
              ),
            }
          : current,
      );
    }, Math.max(120, stepDelayMs));
    return () => window.clearTimeout(timer);
  }, [
    cursor.resolved,
    cursor.workflowRunId,
    reducedMotion,
    stageBoundaries,
    stepDelayMs,
    targetResolved,
    workflowRunId,
  ]);

  const isPlaying = resolved < targetResolved;
  return {
    resolved,
    total,
    percent: total > 0 ? Math.round((resolved / total) * 100) : 0,
    isPlaying,
    canRevealDecisionCard: !isPlaying,
  };
}
