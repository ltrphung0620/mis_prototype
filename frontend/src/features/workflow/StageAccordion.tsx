import { useEffect, useState, type CSSProperties } from "react";
import type { WorkflowMilestone, WorkflowStage } from "../../api/types";
import { StatusBadge } from "../../shared/components/StatusBadge";
import { isResolvedStatus, statusLabel } from "../../shared/workflowLabels";
import {
  parallelAssessmentLanes,
  shouldOpenStage,
  stageMilestoneProgress,
} from "./workflowModel";

interface StageAccordionProps {
  stage: WorkflowStage;
  index: number;
  onOpenAssessment?: (artifactIds: readonly string[]) => void;
  canOpenAssessment?: (artifactIds: readonly string[]) => boolean;
  revealedMilestoneIds?: readonly string[];
  activeMilestoneId?: string;
}

const OWNER_LABELS: Readonly<Record<string, string>> = {
  PLANNER: "Planner Skill",
  FINANCE: "Finance Agent",
  OPERATIONS: "Operations Skill",
  RISK: "Risk & Compliance Agent",
  DECISION: "Decision & Partner Agent",
  BANKING: "Banking Integration Skill",
  DOCUMENT: "Document Skill",
  GOVERNANCE: "Governance Components",
  ORCHESTRATOR: "Workflow Orchestrator",
};

export function ownerLabel(ownerId?: string): string {
  if (!ownerId) return "Chưa xác định đơn vị phụ trách";
  return OWNER_LABELS[ownerId.toUpperCase()] ?? "Thành phần nghiệp vụ";
}

function MilestoneRow({
  milestone,
  onOpenAssessment,
  canOpenAssessment,
}: {
  milestone: WorkflowMilestone;
  onOpenAssessment?: (artifactIds: readonly string[]) => void;
  canOpenAssessment?: (artifactIds: readonly string[]) => boolean;
}) {
  const notApplicable = milestone.applicability.toUpperCase() === "NOT_APPLICABLE";
  return (
    <li className={`milestone${notApplicable ? " milestone--muted" : ""}`}>
      <span className={`milestone__marker milestone__marker--${milestone.status.toLowerCase()}`} aria-hidden="true" />
      <div className="milestone__copy">
        <strong>{milestone.label}</strong>
        {milestone.ownerId ? (
          <span className="milestone__owner">
            Phụ trách: {ownerLabel(milestone.ownerId)}
          </span>
        ) : null}
        {milestone.description ? <p>{milestone.description}</p> : null}
        {milestone.applicabilityReason ? (
          <p className="milestone__applicability-reason">
            {milestone.applicabilityReason}
          </p>
        ) : null}
        {milestone.waitingFor.length ? (
          <p className="milestone__waiting">
            Đang chờ: {milestone.waitingFor.join(", ")}
          </p>
        ) : null}
      </div>
      <div className="milestone__actions">
        <span className="milestone__status">
          {milestone.statusLabel ??
            (notApplicable ? "Không áp dụng" : statusLabel(milestone.status))}
        </span>
        {milestone.artifactIds.length &&
        onOpenAssessment &&
        (canOpenAssessment?.(milestone.artifactIds) ?? true) ? (
          <button
            type="button"
            onClick={() => onOpenAssessment(milestone.artifactIds)}
          >
            Xem đánh giá
          </button>
        ) : null}
      </div>
    </li>
  );
}

function ParallelLanes({
  stage,
  onOpenAssessment,
  canOpenAssessment,
}: {
  stage: WorkflowStage;
  onOpenAssessment?: (artifactIds: readonly string[]) => void;
  canOpenAssessment?: (artifactIds: readonly string[]) => boolean;
}) {
  const lanes = parallelAssessmentLanes(stage);
  if (!lanes.length) return null;
  return (
    <div className="parallel-lanes" aria-label="Tài chính và Vận hành chạy song song">
      <div className="parallel-lanes__branch" aria-hidden="true">
        <span />
        <span />
      </div>
      {lanes.map((lane) => (
        <section className={`parallel-lane parallel-lane--${lane.id}`} key={lane.id}>
          <header>
            <span aria-hidden="true">{lane.id === "finance" ? "₫" : "◎"}</span>
            <strong>{lane.label}</strong>
            <small>Chạy đồng thời</small>
          </header>
          <ul>
            {lane.milestones.map((milestone) => (
              <MilestoneRow
                milestone={milestone}
                onOpenAssessment={onOpenAssessment}
                canOpenAssessment={canOpenAssessment}
                key={milestone.id}
              />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

export function StageAccordion({
  stage,
  index,
  onOpenAssessment,
  canOpenAssessment,
  revealedMilestoneIds,
  activeMilestoneId,
}: StageAccordionProps) {
  const revealedIdSet = new Set(revealedMilestoneIds ?? []);
  const displayMilestones = stage.milestones.map((milestone) => {
    const confirmedResolved = isResolvedStatus(
      milestone.resolutionStatus ?? milestone.status,
    );
    const revealed =
      revealedMilestoneIds === undefined ||
      revealedIdSet.has(milestone.id) ||
      !confirmedResolved;
    if (revealed) return milestone;
    return {
      ...milestone,
      status:
        activeMilestoneId === milestone.id
          ? "RUNNING"
          : "PENDING",
      statusLabel: undefined,
      resolutionStatus: undefined,
      artifactIds: [],
    };
  });
  const stageResolvedMilestones = stage.milestones.filter((milestone) =>
    isResolvedStatus(milestone.resolutionStatus ?? milestone.status),
  );
  const allResolvedMilestonesRevealed = stageResolvedMilestones.every((milestone) =>
    revealedIdSet.has(milestone.id),
  );
  const stageHasActiveMilestone = stage.milestones.some(
    (milestone) => milestone.id === activeMilestoneId,
  );
  const displayStatus =
    revealedMilestoneIds !== undefined &&
    isResolvedStatus(stage.status) &&
    !allResolvedMilestonesRevealed
      ? stageHasActiveMilestone
        ? "RUNNING"
        : "PENDING"
      : stage.status;
  const displayStatusLabel =
    displayStatus === stage.status ? stage.statusLabel : undefined;
  const displayStage = {
    ...stage,
    status: displayStatus,
    statusLabel: displayStatusLabel,
    milestones: displayMilestones,
  };
  const [open, setOpen] = useState(() => shouldOpenStage(displayStage, index));
  useEffect(() => {
    if (shouldOpenStage(displayStage, index)) setOpen(true);
  }, [displayStatus, index]);
  const progress = stageMilestoneProgress(displayStage);
  const lanes = parallelAssessmentLanes(displayStage);
  const notApplicable = stage.applicability.toUpperCase() === "NOT_APPLICABLE";
  const applicabilityReasons = Array.from(
    new Set(
      stage.milestones
        .map((item) => item.applicabilityReason?.trim())
        .filter((reason): reason is string => Boolean(reason)),
    ),
  );
  const applicabilitySummary = applicabilityReasons.length
    ? applicabilityReasons.join(" · ")
    : "Nhánh này không áp dụng cho hồ sơ hiện tại";
  const owners = Array.from(
    new Set(stage.milestones.map((item) => item.ownerId).filter(Boolean)),
  ).map((ownerId) => ownerLabel(ownerId));
  const contentId = `stage-content-${stage.id.replace(/[^a-zA-Z0-9_-]/g, "-")}`;

  return (
    <article
      className={`stage-card stage-card--enter${notApplicable ? " stage-card--muted" : ""}`}
      style={{ "--stage-delay": `${Math.min(index * 55, 880)}ms` } as CSSProperties}
    >
      <button
        className="stage-card__toggle"
        type="button"
        aria-expanded={open}
        aria-controls={contentId}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="stage-card__sequence">{String(index + 1).padStart(2, "0")}</span>
        <span className="stage-card__heading">
          <strong>{stage.label}</strong>
          {owners.length ? (
            <span className="stage-card__owners">Phụ trách: {owners.join(" · ")}</span>
          ) : null}
          <small>
            {notApplicable
              ? applicabilitySummary
              : progress.total
                ? `${progress.resolved}/${progress.total} mốc đã giải quyết`
                : "Chưa có mốc thực thi"}
          </small>
        </span>
        {stage.parallel ? <span className="parallel-chip">Chạy song song</span> : null}
        <StatusBadge
          compact
          status={displayStatus}
          label={displayStatusLabel}
        />
        <span className={`stage-card__chevron${open ? " stage-card__chevron--open" : ""}`} aria-hidden="true">
          ↓
        </span>
      </button>
      {open ? (
        <div className="stage-card__content" id={contentId}>
          {stage.description ? <p className="stage-card__description">{stage.description}</p> : null}
          {lanes.length ? (
            <ParallelLanes
              stage={displayStage}
              onOpenAssessment={onOpenAssessment}
              canOpenAssessment={canOpenAssessment}
            />
          ) : displayMilestones.length ? (
            <ul className="milestone-list">
              {displayMilestones.map((milestone) => (
                <MilestoneRow
                  milestone={milestone}
                  onOpenAssessment={onOpenAssessment}
                  canOpenAssessment={canOpenAssessment}
                  key={milestone.id}
                />
              ))}
            </ul>
          ) : (
            <p className="empty-copy">Giai đoạn chưa có công việc được ghi nhận.</p>
          )}
        </div>
      ) : null}
    </article>
  );
}
