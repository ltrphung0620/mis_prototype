import type { CSSProperties } from "react";

import type { NormalizedWorkflowDashboard } from "../../api/types";
import { LoadingBlock } from "../../shared/components/LoadingBlock";
import { Notice } from "../../shared/components/Notice";
import { Panel } from "../../shared/components/Panel";
import { StatusBadge } from "../../shared/components/StatusBadge";
import { stageLabel, statusLabel } from "../../shared/workflowLabels";
import { StageAccordion } from "./StageAccordion";
import { workflowMilestoneProgress } from "./workflowModel";
import type { WorkflowPlayback } from "./useWorkflowPlayback";

interface WorkflowTimelineProps {
  dashboard: NormalizedWorkflowDashboard | null;
  loading: boolean;
  onOpenAssessment?: (artifactIds: readonly string[]) => void;
  canOpenAssessment?: (artifactIds: readonly string[]) => boolean;
  playback?: WorkflowPlayback;
}

function MilestoneTrack({ resolved, total }: { resolved: number; total: number }) {
  if (!total) return <p className="empty-copy">Chưa có mốc thực thi từ quy trình.</p>;
  return (
    <div className="milestone-track" aria-label={`${resolved} trên ${total} mốc đã giải quyết`}>
      {Array.from({ length: total }, (_, index) => (
        <span
          className={index < resolved ? "milestone-track__item milestone-track__item--resolved" : "milestone-track__item"}
          key={index}
          style={{ "--milestone-delay": `${index * 45}ms` } as CSSProperties}
        />
      ))}
    </div>
  );
}

export function WorkflowTimeline({
  dashboard,
  loading,
  onOpenAssessment,
  canOpenAssessment,
  playback,
}: WorkflowTimelineProps) {
  const backendProgress = dashboard ? workflowMilestoneProgress(dashboard) : null;
  const progress = playback ?? backendProgress;
  const displayPercent =
    playback?.percent ??
    dashboard?.progressPercent ??
    (progress?.total ? Math.round((progress.resolved / progress.total) * 100) : 0);
  const currentStageLabel = dashboard
    ? dashboard.currentStageLabel || stageLabel(dashboard.currentStage)
    : "Chưa bắt đầu";

  return (
    <Panel
      eyebrow="02 · QUY TRÌNH"
      title="Tiến trình xử lý"
      className="workflow-panel"
      aside={
        dashboard ? (
          <StatusBadge status={dashboard.status} label={dashboard.statusLabel || undefined} />
        ) : null
      }
    >
      {loading && !dashboard ? (
        <LoadingBlock label="Đang tải tiến trình xử lý" rows={6} />
      ) : !dashboard ? (
        <div className="workflow-empty">
          <span className="workflow-empty__glyph" aria-hidden="true">↳</span>
          <h3>Chưa có lượt đánh giá</h3>
          <p>Chọn một hợp đồng ở bảng bên trái để bắt đầu quy trình.</p>
        </div>
      ) : (
        <>
          <section className="workflow-overview" aria-label="Tổng quan tiến trình">
            <div>
              <span>Giai đoạn hiện tại</span>
              <strong>{currentStageLabel}</strong>
            </div>
            <div className="workflow-overview__count">
              {progress ? (
                <strong>{Math.round(Math.max(0, Math.min(100, displayPercent)))}%</strong>
              ) : null}
              <span>{progress?.resolved ?? 0}/{progress?.total ?? 0} mốc đã giải quyết</span>
            </div>
          </section>

          {progress ? <MilestoneTrack resolved={progress.resolved} total={progress.total} /> : null}

          {playback?.isPlaying ? (
            <div className="workflow-playback" role="status" aria-live="polite">
              <span aria-hidden="true" />
              Đang hiển thị tuần tự các bước đã được backend xác nhận.
            </div>
          ) : null}

          {dashboard.businessStatusLabel ? (
            <div className="business-status">
              <span>Trạng thái nghiệp vụ</span>
              <strong>{dashboard.businessStatusLabel}</strong>
            </div>
          ) : null}

          {dashboard.failureReason ? (
            <Notice tone="danger" title="Quy trình đã dừng an toàn">
              {dashboard.failureReason}
            </Notice>
          ) : null}

          {dashboard.status.toUpperCase() === "WAITING_FOR_DEPENDENCIES" ? (
            <Notice tone="info" title="Hệ thống đang tự chờ tác vụ liên quan">
              Không cần Founder thao tác ở thời điểm này.
            </Notice>
          ) : null}

          <div className="stage-list">
            {(() => {
              let milestoneOffset = 0;
              return dashboard.stages.map((stage, index) => {
                const stageStart = milestoneOffset;
                const stageSize = Math.max(1, stage.milestones.length);
                const stageEnd = stageStart + stageSize;
                milestoneOffset = stageEnd;
                const revealedMilestoneCount = playback
                  ? Math.max(
                      0,
                      Math.min(stageSize, playback.resolved - stageStart),
                    )
                  : undefined;
                const playbackState = !playback
                  ? undefined
                  : playback.resolved >= stageEnd
                    ? "REVEALED"
                    : playback.isPlaying && playback.resolved >= stageStart
                      ? "ACTIVE"
                      : "QUEUED";
                return (
                  <StageAccordion
                    stage={stage}
                    index={index}
                    playbackState={playbackState}
                    revealedMilestoneCount={revealedMilestoneCount}
                    onOpenAssessment={onOpenAssessment}
                    canOpenAssessment={canOpenAssessment}
                    key={stage.id}
                  />
                );
              });
            })()}
          </div>

          <footer className="workflow-footer">
            <span>Trạng thái thực thi: {dashboard.statusLabel || statusLabel(dashboard.status)}</span>
            <span>Mã lượt xử lý: {dashboard.workflowRunId}</span>
          </footer>
        </>
      )}
    </Panel>
  );
}
