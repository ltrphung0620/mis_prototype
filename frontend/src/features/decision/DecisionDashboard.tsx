import type { ReactElement } from "react";

import { businessValueLabel } from "../../shared/businessLabels";
import { translateText } from "../../shared/translate";
import type { DecisionDashboardData, DecisionMetric } from "./types";

export interface DecisionDashboardProps {
  data: DecisionDashboardData;
  onOpenDecisionCard?: () => void;
}

function visibleMetrics(metrics: DecisionMetric[] = []): DecisionMetric[] {
  return metrics.filter(
    (metric) => metric.scope !== "OPC_GLOBAL" && metric.contract_attributable !== false && metric.role !== "POLICY_TARGET",
  );
}

const METRIC_LABELS: Record<string, string> = {
  CONTRACT_VALUE: "Giá trị hợp đồng",
  RELATED_ORDER_REVENUE: "Doanh thu của các order liên kết",
  RELATED_ORDER_ESTIMATED_COST: "Chi phí ước tính của các order liên kết",
  RELATED_ORDER_GROSS_PROFIT: "Lợi nhuận gộp của các order liên kết",
  ORDER_GROSS_MARGIN: "Biên lợi nhuận gộp của các order liên kết",
};

function value(metric: DecisionMetric): string {
  if (metric.value === null) return "Chưa xác định";
  if (typeof metric.value === "number" && metric.unit === "VND") {
    return new Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND", maximumFractionDigits: 0 }).format(metric.value);
  }
  if (typeof metric.value === "number" && metric.unit === "RATIO") {
    return `${new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 }).format(metric.value * 100)}%`;
  }
  return String(metric.value);
}

function externalState(data: DecisionDashboardData): string | null {
  if (data.external_submission_performed) return "Hệ thống ghi nhận hồ sơ đã được gửi ra ngoài.";
  if (data.ready_for_external_submission || data.business_status === "READY_FOR_EXTERNAL_SUBMISSION") {
    return "Hồ sơ đã được phép và sẵn sàng để gửi; chưa có xác nhận đã gửi ra ngoài.";
  }
  return null;
}

export function DecisionDashboard({ data, onOpenDecisionCard }: DecisionDashboardProps): ReactElement {
  const metrics = visibleMetrics(data.metrics);
  const externalStatus = externalState(data);
  return (
    <section aria-labelledby="decision-dashboard-title" className="decision-dashboard">
      <header>
        <p>Hợp đồng {data.contract_id}</p>
        <h2 id="decision-dashboard-title">Decision Dashboard</h2>
        <p>{data.business_status_label_vi}</p>
      </header>
      <p>Giai đoạn hiện tại: <strong>{data.current_stage_label_vi}</strong></p>
      <p>Tiến độ: {data.progress_percent}% · {data.execution_status_label_vi}</p>

      {!!metrics.length && <dl>{metrics.map((metric) => <div key={metric.metric}><dt>{metric.label_vi ?? METRIC_LABELS[metric.metric] ?? "Chỉ số hợp đồng"}</dt><dd>{value(metric)}</dd></div>)}</dl>}

      {data.decision_card.available ? (
        <article>
          <h3>{data.decision_card.recommendation_label_vi}</h3>
          {data.decision_card.executive_summary && <p>{data.decision_card.executive_summary}</p>}
          {data.decision_card.confidence && <p>Độ tin cậy: {businessValueLabel(data.decision_card.confidence)}</p>}
          {data.residual_risk_level && <p>Rủi ro còn lại: {businessValueLabel(data.residual_risk_level)}</p>}
          {!!data.condition_titles?.length && <><h4>Điều kiện chính</h4><ul>{data.condition_titles.map((title) => <li key={title}>{translateText(title)}</li>)}</ul></>}
          {onOpenDecisionCard && <button type="button" onClick={onOpenDecisionCard}>Xem Decision Card hiện hành</button>}
        </article>
      ) : <p>Decision Card của lượt chạy hiện tại chưa sẵn sàng.</p>}

      {data.post_decision_outcome && <p>Kết quả sau quyết định: {businessValueLabel(data.post_decision_outcome)}.</p>}
      {externalStatus && <p role="status">{externalStatus}</p>}
    </section>
  );
}
