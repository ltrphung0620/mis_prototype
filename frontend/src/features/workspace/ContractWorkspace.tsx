import type { ReactNode } from "react";
import type {
  ApiArtifactEnvelope,
  DashboardMetricDto,
  NormalizedWorkflowDashboard,
} from "../../api/types";
import { businessValueLabel } from "../../shared/businessLabels";
import { formatVndCompact } from "../../shared/formatters";
import { StatusBadge } from "../../shared/components/StatusBadge";
import { translateText } from "../../shared/translate";

export type WorkspaceView =
  "decision" | "assessments" | "evidence" | "workflow" | "input";
export const workspaceViews: {
  id: WorkspaceView;
  label: string;
  icon: string;
}[] = [
  { id: "decision", label: "Quyết định", icon: "decision" },
  { id: "assessments", label: "Đánh giá", icon: "assessment" },
  { id: "evidence", label: "Bằng chứng", icon: "evidence" },
  { id: "workflow", label: "Quy trình", icon: "workflow" },
  { id: "input", label: "Dữ liệu đầu vào", icon: "input" },
];

const artifactLabels: Record<string, string> = {
  FINANCE_ASSESSMENT: "Finance · Đánh giá tài chính",
  FINANCE_FACTS: "Finance · Số liệu tài chính",
  OPERATIONS_ASSESSMENT: "Operations · Đánh giá vận hành",
  OPERATIONS_FACTS: "Operations · Số liệu vận hành",
  INITIAL_RISK_ASSESSMENT: "Risk · Đánh giá ban đầu",
  FINAL_RISK_ASSESSMENT: "Risk · Kiểm tra cuối",
  RISK_PRE_SCAN: "Risk · Quét sơ bộ",
  AI_DECISION_ANALYSIS: "Phân tích quyết định",
  DECISION_CARD: "Decision Card",
  EVALUATION_CASE: "Hồ sơ đánh giá",
  PLANNER_RESULT: "Kết quả tiếp nhận",
  DOCUMENT_RELEASE_PACKAGE: "Gói hồ sơ nội bộ",
  INTERNAL_DECISION_PACKAGE: "Hồ sơ quyết định nội bộ",
  BANKING_PRECHECK_RESULT_SET: "Kết quả precheck mô phỏng",
};

const validationLabels: Record<string, string> = {
  VALID: "Đã kiểm tra bằng chứng",
  VALID_WITH_WARNINGS: "Đã kiểm tra · có cảnh báo",
  INVALID: "Không đạt kiểm tra",
  BLOCKED: "Bị chặn bởi kiểm tra",
  PENDING: "Chưa kiểm tra",
};

export function WorkspaceIcon({ name }: { name: string }) {
  const paths: Record<string, ReactNode> = {
    decision: (
      <>
        <path d="M5 4h14v16H5zM8 8h8M8 12h5M8 16h3" />
        <path d="m14 16 2 2 4-4" />
      </>
    ),
    assessment: (
      <>
        <path d="M4 20h16M7 16V9M12 16V4M17 16v-5" />
      </>
    ),
    evidence: (
      <>
        <path d="M4 6h6l2 2h8v12H4zM8 12h8M8 16h5" />
      </>
    ),
    workflow: (
      <>
        <path d="M8 5h12M8 12h12M8 19h12" />
        <circle cx="4" cy="5" r="1" />
        <circle cx="4" cy="12" r="1" />
        <circle cx="4" cy="19" r="1" />
      </>
    ),
    input: (
      <>
        <path d="M4 5h16v14H4zM4 10h16M9 10v9M14 10v9" />
      </>
    ),
  };
  return (
    <svg
      aria-hidden="true"
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {paths[name] ?? paths.decision}
    </svg>
  );
}

export function metricDisplay(metric: DashboardMetricDto): string {
  if (metric.value === null) return "Chưa có dữ liệu";
  if (typeof metric.value === "boolean") return metric.value ? "Có" : "Không";
  if (typeof metric.value !== "number") return metric.value;
  if (metric.unit === "VND") return formatVndCompact(metric.value);
  if (metric.unit === "RATIO")
    return `${new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 }).format(metric.value * 100)}%`;
  return `${new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 }).format(metric.value)}${metric.unit === "DAYS" ? " ngày" : ""}`;
}

export function ContractMetrics({
  dashboard,
}: {
  dashboard: NormalizedWorkflowDashboard;
}) {
  const metrics = dashboard.metrics.filter(
    (metric) => metric.scope === "CASE_SPECIFIC",
  );
  return metrics.length ? (
    <dl className="contract-metrics" aria-label="Chỉ số của hợp đồng">
      {metrics.map((metric) => (
        <div key={metric.code}>
          <dt>{metric.label_vi}</dt>
          <dd>{metricDisplay(metric)}</dd>
          {metric.note_vi && <p>{metric.note_vi}</p>}
          {metric.quality !== "VERIFIED" && (
            <small>{businessValueLabel(metric.quality)}</small>
          )}
        </div>
      ))}
    </dl>
  ) : null;
}

export function AssessmentIndex({
  dashboard,
  artifacts = [],
  compact = false,
  onOpen,
  canOpen,
}: {
  dashboard: NormalizedWorkflowDashboard;
  artifacts?: readonly ApiArtifactEnvelope[];
  compact?: boolean;
  onOpen: (ids: readonly string[]) => void;
  canOpen: (ids: readonly string[]) => boolean;
}) {
  const tasks = dashboard.stages
    .flatMap((stage) => stage.milestones)
    .filter((task) =>
      [
        "FINANCE_ASSESSMENT",
        "OPERATIONS_ASSESSMENT",
        "INITIAL_RISK_FINALIZATION",
        "FINAL_RISK_CHECK",
      ].includes(task.code),
    );
  const hasFinalRisk = tasks.some((task) => task.code === "FINAL_RISK_CHECK");
  const visibleTasks =
    compact && hasFinalRisk
      ? tasks.filter((task) => task.code !== "INITIAL_RISK_FINALIZATION")
      : tasks;
  function summary(ids: readonly string[]): string {
    const matches = artifacts.filter(
      (artifact) =>
        ids.includes(artifact.artifact_id) &&
        ["VALID", "VALID_WITH_WARNINGS"].includes(artifact.validation_status),
    );
    const payload = (
      matches.find((artifact) =>
        artifact.artifact_type.endsWith("_ASSESSMENT"),
      ) ?? matches[0]
    )?.payload;
    if (!payload) return "Kết quả chưa sẵn sàng để xem.";
    const level = payload.residual_risk_level ?? payload.overall_risk_level;
    if (typeof level === "string")
      return `Mức rủi ro được ghi nhận: ${businessValueLabel(level)}. Xem findings và giới hạn bằng chứng.`;
    const narrative = payload.narrative as { headline?: unknown } | undefined;
    if (typeof narrative?.headline === "string")
      return translateText(narrative.headline);
    const statements = payload.summary;
    if (Array.isArray(statements) && typeof statements[0]?.text === "string")
      return translateText(statements[0].text);
    return "Xem kết quả và giới hạn bằng chứng của tác vụ.";
  }
  return (
    <section
      className="assessment-index"
      aria-labelledby="assessment-index-title"
    >
      <div className="section-heading">
        <h2 id="assessment-index-title">Cơ sở đánh giá</h2>
        <span>Kết quả theo từng nghiệp vụ</span>
      </div>
      {visibleTasks.length ? (
        <div className="assessment-rows">
          {visibleTasks.map((task) => (
            <div className="assessment-row" key={task.id}>
              <span className="assessment-row__icon">
                <WorkspaceIcon name="assessment" />
              </span>
              <div>
                <strong>{task.label}</strong>
                <p>{summary(task.artifactIds)}</p>
              </div>
              <StatusBadge
                compact
                status={task.status}
                label={task.statusLabel}
              />
              <button
                type="button"
                className="text-action"
                disabled={!canOpen(task.artifactIds)}
                onClick={() => onOpen(task.artifactIds)}
              >
                Xem chi tiết <span aria-hidden="true">↗</span>
              </button>
            </div>
          ))}
        </div>
      ) : (
        <p className="empty-copy">
          Kết quả đánh giá sẽ xuất hiện khi quy trình tiếp nhận hợp đồng.
        </p>
      )}
    </section>
  );
}

export function EvidenceIndex({
  artifacts,
  onOpen,
  canOpen,
}: {
  artifacts: readonly ApiArtifactEnvelope[];
  onOpen: (ids: readonly string[]) => void;
  canOpen: (ids: readonly string[]) => boolean;
}) {
  return (
    <section className="evidence-index" aria-labelledby="evidence-index-title">
      <div className="section-heading">
        <div>
          <h2 id="evidence-index-title">Hồ sơ & bằng chứng</h2>
          <p>
            Artifacts của lượt xử lý hiện hành. Validation nội bộ không xác nhận
            tính pháp lý của tài liệu.
          </p>
        </div>
        <span>{artifacts.length} artifacts</span>
      </div>
      {artifacts.length ? (
        <div className="table-scroll">
          <table className="evidence-table">
            <thead>
              <tr>
                <th>Nguồn</th>
                <th>Phiên bản</th>
                <th>Kiểm tra nội bộ</th>
                <th>
                  <span className="sr-only">Chi tiết</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {artifacts.map((artifact) => (
                <tr key={artifact.artifact_id}>
                  <td>
                    <strong>
                      {artifactLabels[artifact.artifact_type] ??
                        businessValueLabel(
                          artifact.artifact_type,
                          artifact.artifact_type,
                        )}
                    </strong>
                    <small>{artifact.artifact_id}</small>
                  </td>
                  <td>v{artifact.version}</td>
                  <td>
                    <StatusBadge
                      compact
                      status={artifact.validation_status}
                      label={
                        validationLabels[artifact.validation_status] ??
                        artifact.validation_status
                      }
                    />
                  </td>
                  <td>
                    <button
                      className="text-action"
                      type="button"
                      disabled={!canOpen([artifact.artifact_id])}
                      onClick={() => onOpen([artifact.artifact_id])}
                    >
                      Xem chi tiết
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="empty-copy">
          Chưa có artifact được xác minh cho lượt xử lý này.
        </p>
      )}
    </section>
  );
}

export function DecisionLimits({
  limitations,
}: {
  limitations: readonly { code?: string; detail: string }[];
}) {
  return limitations.length ? (
    <details className="decision-limits">
      <summary>
        Giới hạn bằng chứng <span>{limitations.length}</span>
      </summary>
      <ul>
        {limitations.map((item, index) => (
          <li key={item.code ?? index}>{translateText(item.detail)}</li>
        ))}
      </ul>
    </details>
  ) : null;
}
