import { useState } from "react";
import { usePreviewData } from "./data";
import {
  Badge,
  Icon,
  Link,
  money,
  PageHeading,
  Section,
  SourceNote,
} from "./components";
import { CashChart } from "./Charts";
import { navigatePreview } from "./navigation";

export function Dashboard({ period = "all" }: { period?: string }) {
  const { actions, alerts, contracts, snapshot } = usePreviewData();
  const [filter, setFilter] = useState("all");
  const visibleActions = actions.filter(
    (a) => filter === "all" || a.kind === filter,
  );
  return (
    <>
      <PageHeading
        eyebrow="OPC Technology"
        title="Bảng điều hành"
        description="Những việc cần bạn xem xét, trong bối cảnh hoạt động của công ty."
        action={
          <Link className="pv-button" to="/company">
            Tình hình công ty <Icon />
          </Link>
        }
      />
      <div className="pv-dashboard-top">
        <Section
          title="Cần Founder xử lý"
          action={<Badge tone="lavender">3 việc</Badge>}
        >
          <div className="pv-filter-tabs" aria-label="Lọc việc cần xử lý">
            {[
              { key: "all", label: "Tất cả" },
              { key: "approval", label: "Phê duyệt" },
              { key: "input", label: "Dữ liệu" },
              { key: "failure", label: "Bị chặn" },
            ].map((f) => (
              <button
                key={f.key}
                className={filter === f.key ? "is-active" : ""}
                aria-pressed={filter === f.key}
                onClick={() => setFilter(f.key)}
              >
                {f.label}
              </button>
            ))}
          </div>
          <div className="pv-action-list">
            {visibleActions.map((a) => (
              <div
                key={a.id}
                className={`pv-action-row pv-action-row--${a.kind}`}
              >
                <span className={`pv-action-icon pv-action-icon--${a.kind}`}>
                  <Icon name={a.kind} />
                </span>
                <div>
                  <Link to={`/contracts/${a.contractId}`} className="pv-kicker">
                    {a.contractId}
                  </Link>
                  <h3>{a.title}</h3>
                  <p>{a.description}</p>
                </div>
                <Link
                  to={a.link}
                  className={
                    a.kind === "approval"
                      ? "pv-button pv-button--primary"
                      : "pv-button"
                  }
                >
                  {a.label}
                  <Icon />
                </Link>
              </div>
            ))}
          </div>
        </Section>
        <Section
          title="Hợp đồng cần chú ý"
          action={
            <Link to="/contracts">
              Tất cả <Icon />
            </Link>
          }
        >
          <div className="pv-attention-list">
            {contracts
              .filter((c) => c.attention)
              .map((c) => (
                <Link to={`/contracts/${c.id}`} key={c.id}>
                  <div>
                    <span className="pv-kicker">
                      {c.id} <span>· {c.customer}</span>
                    </span>
                    <h3>{c.statusLabel}</h3>
                    <p>{c.attention}</p>
                  </div>
                  <Icon />
                </Link>
              ))}
          </div>
        </Section>
      </div>
      <div className="pv-summary-heading">
        <h2>Tổng quan trong kỳ</h2>
        <span>Snapshot công ty · {snapshot.period}</span>
      </div>
      <dl className="pv-kpi-strip">
        <div>
          <dt>Hợp đồng trong snapshot</dt>
          <dd>
            <Link to="/contracts">
              {snapshot.kpis.contracts}
              <Icon />
            </Link>
          </dd>
          <small>Toàn bộ trạng thái hợp đồng nguồn</small>
        </div>
        <div>
          <dt>Tổng giá trị hợp đồng</dt>
          <dd>
            <Link to="/company?section=business">
              {money(snapshot.kpis.contractValue)} <span>VND</span>
              <Icon />
            </Link>
          </dd>
          <small>Giá trị nguồn · Không phải doanh thu</small>
        </div>
        <div>
          <dt>Hóa đơn ghi nguồn Open</dt>
          <dd>
            <Link to="/company?section=invoices&status=Open">
              {money(snapshot.kpis.openInvoices)} <span>VND</span>
              <Icon />
            </Link>
          </dd>
          <small>Chưa đối soát thanh toán</small>
        </div>
      </dl>
      <CashChart
        period={period}
        compact
        onPeriodChange={(p) => navigatePreview(`/dashboard?period=${p}`)}
      />
      <div className="pv-alert-strip">
        <Icon name="failure" />
        <div>
          <strong>{alerts[0].title}</strong>
          <p>Tháng 9 · Dự kiến thấp hơn ngưỡng dự trữ trong nguồn minh họa.</p>
        </div>
        <Link to="/company?section=alerts">
          Xem cảnh báo <Icon />
        </Link>
      </div>
      <SourceNote>
        Snapshot minh họa · Chưa có thời điểm chốt dữ liệu nguồn · Không phải
        realtime · Không cộng OPC_GLOBAL theo hợp đồng
      </SourceNote>
    </>
  );
}
