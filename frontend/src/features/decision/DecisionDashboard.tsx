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
      <header>
        <p>Hợp đồng {data.contract_id}</p>
        <h2 id="decision-dashboard-title">Decision Dashboard</h2>
        <p>{data.business_status_label_vi}</p>
      </header>
      <p>Giai đoạn hiện tại: <strong>{data.current_stage_label_vi}</strong></p>
      <p>Tiến độ: {data.progress_percent}% · {data.execution_status_label_vi}</p>

      {data.decision_card.available ? (
        <article>
          <h3>{data.decision_card.recommendation_label_vi}</h3>
          {data.decision_card.executive_summary && <p>{translateText(data.decision_card.executive_summary)}</p>}
          {data.decision_card.confidence && <p>Độ tin cậy: {businessValueLabel(data.decision_card.confidence)}</p>}
          {data.residual_risk_level && <p>Rủi ro còn lại: {businessValueLabel(data.residual_risk_level)}</p>}
        </article>
      ) : <p>Decision Card của lượt chạy hiện tại chưa sẵn sàng.</p>}

      {data.post_decision_outcome && <p>Kết quả sau quyết định: {businessValueLabel(data.post_decision_outcome)}.</p>}
      {externalStatus && <p role="status">{externalStatus}</p>}
    </section>
  );
}
