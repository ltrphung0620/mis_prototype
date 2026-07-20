import { useEffect, useMemo, useState } from "react";

import type { NormalizedWorkflowDashboard } from "../../api/types";
import { isResolvedStatus } from "../../shared/workflowLabels";
import { workflowMilestoneProgress } from "./workflowModel";

export const DEFAULT_WORKFLOW_STEP_DELAY_MS = 1_000;

interface PlaybackCursor {
  workflowRunId: string;
  revealedMilestoneIds: readonly string[];
}

export interface WorkflowPlayback {
  resolved: number;
  total: number;
  percent: number;
  isPlaying: boolean;
  canRevealDecisionCard: boolean;
  revealedMilestoneIds: readonly string[];
  activeMilestoneId?: string;
}

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/** Advance one confirmed milestone at a time; stages must never create a jump. */
export function advancePlayback(current: number, target: number): number {
  return Math.min(Math.max(0, current) + 1, Math.max(0, target));
}

function resolvedMilestoneIds(
  dashboard: NormalizedWorkflowDashboard | null,
): readonly string[] {
  if (!dashboard) return [];
  return dashboard.stages
    .filter((stage) => stage.applicability.toUpperCase() !== "NOT_APPLICABLE")
    .flatMap((stage) => stage.milestones)
    .filter(
      (milestone) =>
        milestone.applicability.toUpperCase() !== "NOT_APPLICABLE" &&
        milestone.status.toUpperCase() !== "SKIPPED" &&
        isResolvedStatus(milestone.resolutionStatus ?? milestone.status),
    )
    .map((milestone) => milestone.id);
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
  const targetIds = useMemo(() => resolvedMilestoneIds(dashboard), [dashboard]);
  const targetIdSet = useMemo(() => new Set(targetIds), [targetIds]);
  const reducedMotion = prefersReducedMotion();
  const [cursor, setCursor] = useState<PlaybackCursor>({
    workflowRunId: "",
    revealedMilestoneIds: [],
  });

  const revealedMilestoneIds =
    cursor.workflowRunId === workflowRunId
      ? cursor.revealedMilestoneIds.filter((id) => targetIdSet.has(id))
      : [];
  const revealedIdSet = useMemo(
    () => new Set(revealedMilestoneIds),
    [revealedMilestoneIds],
  );
  const activeMilestoneId = targetIds.find((id) => !revealedIdSet.has(id));

  useEffect(() => {
    if (!workflowRunId) {
      setCursor({ workflowRunId: "", revealedMilestoneIds: [] });
      return undefined;
    }
    if (cursor.workflowRunId !== workflowRunId) {
      setCursor({
        workflowRunId,
        revealedMilestoneIds: reducedMotion ? targetIds : [],
      });
      return undefined;
    }
    if (reducedMotion) {
      if (targetIds.some((id) => !revealedIdSet.has(id))) {
        setCursor({ workflowRunId, revealedMilestoneIds: targetIds });
      }
      return undefined;
    }
    const nextId = targetIds.find((id) => !revealedIdSet.has(id));
    if (!nextId) return undefined;

    const timer = window.setTimeout(() => {
      setCursor((current) =>
        current.workflowRunId === workflowRunId &&
        !current.revealedMilestoneIds.includes(nextId)
          ? {
              workflowRunId,
              revealedMilestoneIds: [
                ...current.revealedMilestoneIds,
                nextId,
              ],
            }
          : current,
      );
    }, Math.max(120, stepDelayMs));
    return () => window.clearTimeout(timer);
  }, [
    cursor.workflowRunId,
    reducedMotion,
    revealedIdSet,
    stepDelayMs,
    targetIds,
    workflowRunId,
  ]);

  const resolved = revealedMilestoneIds.length;
  const total = progress?.total ?? 0;
  const isPlaying = resolved < targetIds.length;
  return {
    resolved,
    total,
    percent: total > 0 ? Math.round((resolved / total) * 100) : 0,
    isPlaying,
    canRevealDecisionCard: !isPlaying,
    revealedMilestoneIds,
    activeMilestoneId,
  };
}
