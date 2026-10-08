import type { ReactElement } from "react";

import { businessValueLabel } from "../../shared/businessLabels";
import { translateText } from "../../shared/translate";
import type { DecisionDashboardData } from "./types";

export interface DecisionDashboardProps {
  data: DecisionDashboardData;
}



function externalState(data: DecisionDashboardData): string | null {
  if (data.external_submission_performed) return "Hệ thống ghi nhận hồ sơ đã được gửi ra ngoài.";
  if (data.ready_for_external_submission || data.business_status === "READY_FOR_EXTERNAL_SUBMISSION") {
    return "Hồ sơ đã được phép và sẵn sàng để gửi; chưa có xác nhận đã gửi ra ngoài.";
  }
  return null;
}

export function DecisionDashboard({ data }: DecisionDashboardProps): ReactElement {
  const externalStatus = externalState(data);
  return (
    <section aria-labelledby="decision-dashboard-title" className="decision-dashboard">
      <header className="decision-dashboard__status">
        <h2 id="decision-dashboard-title" className="sr-only">Decision Dashboard</h2>
        <span>{data.business_status_label_vi}</span>
        <span>{data.execution_status_label_vi}</span>
      </header>

      {data.decision_card.available ? (
        <article>
          <p className="decision-proposal-label">Khuyến nghị từ hệ thống</p>
          <h3>{data.decision_card.recommendation_label_vi}</h3>
          {data.decision_card.executive_summary && <p>{translateText(data.decision_card.executive_summary)}</p>}
          <div className="decision-properties">{data.decision_card.confidence && <p><span>Độ tin cậy</span><strong>{businessValueLabel(data.decision_card.confidence)}</strong></p>}
          {data.residual_risk_level && <p><span>Rủi ro còn lại</span><strong>{businessValueLabel(data.residual_risk_level)}</strong></p>}</div>
        </article>
      ) : <p>Decision Card của lượt chạy hiện tại chưa sẵn sàng.</p>}

      {data.post_decision_outcome && <p>Kết quả sau quyết định: {businessValueLabel(data.post_decision_outcome)}.</p>}
      {externalStatus && <p role="status">{externalStatus}</p>}
    </section>
  );
}
