import type {
  NormalizedWorkflowDashboard,
  WorkflowMilestone,
  WorkflowStage,
} from "../../api/types";
import { isResolvedStatus } from "../../shared/workflowLabels";

export interface MilestoneProgress {
  resolved: number;
  total: number;
  pending: number;
}

function applicableMilestones(
  stages: readonly WorkflowStage[],
): readonly WorkflowMilestone[] {
  return stages
    .filter((stage) => stage.applicability.toUpperCase() !== "NOT_APPLICABLE")
    .flatMap((stage) => stage.milestones)
    .filter(
      (milestone) =>
        milestone.applicability.toUpperCase() !== "NOT_APPLICABLE" &&
        milestone.status.toUpperCase() !== "SKIPPED",
    );
}

export function workflowMilestoneProgress(
  dashboard: NormalizedWorkflowDashboard,
): MilestoneProgress {
  const milestones = applicableMilestones(dashboard.stages);
  const resolved = milestones.filter((milestone) =>
    isResolvedStatus(milestone.resolutionStatus ?? milestone.status),
  ).length;
  return { resolved, total: milestones.length, pending: milestones.length - resolved };
}

export function stageMilestoneProgress(stage: WorkflowStage): MilestoneProgress {
  const milestones = stage.milestones.filter(
    (item) =>
      item.applicability.toUpperCase() !== "NOT_APPLICABLE" &&
      item.status.toUpperCase() !== "SKIPPED",
  );
  const resolved = milestones.filter((item) =>
    isResolvedStatus(item.resolutionStatus ?? item.status),
  ).length;
  return { resolved, total: milestones.length, pending: milestones.length - resolved };
}

export interface ParallelLane {
  id: "finance" | "operations";
  label: string;
  milestones: readonly WorkflowMilestone[];
}

export function parallelAssessmentLanes(stage: WorkflowStage): readonly ParallelLane[] {
  if (!stage.parallel) return [];
  const finance = stage.milestones.filter((item) => item.lane === "finance");
  const operations = stage.milestones.filter((item) => item.lane === "operations");
  if (!finance.length || !operations.length) return [];
  return [
    { id: "finance", label: "Tài chính", milestones: finance },
    { id: "operations", label: "Vận hành", milestones: operations },
  ];
}

export function shouldOpenStage(stage: WorkflowStage, index: number): boolean {
  const status = stage.status.toUpperCase();
  return (
    index === 0 ||
    status === "RUNNING" ||
    status.startsWith("WAITING") ||
    status === "BLOCKED" ||
    status === "FAILED_SAFE" ||
    status === "REJECTED" ||
    status === "EXPIRED"
  );
}
