import { useState } from "react";
import { usePreviewData } from "./data";
import {
  Badge,
  Icon,
  Link,
  money,
  PageHeading,
  SearchField,
  Section,
  Tabs,
} from "./components";
import { CashChart, DistributionChart } from "./Charts";
import type { PreviewRoute } from "./models";
import { navigatePreview } from "./navigation";

const sections = [
  { key: "overview", label: "Tổng quan" },
  { key: "finance", label: "Tài chính" },
  { key: "business", label: "Hợp đồng & đơn hàng" },
  { key: "invoices", label: "Hóa đơn" },
  { key: "alerts", label: "Cảnh báo & giới hạn" },
];
// Translate display copy only; keep original fixture records and values intact.
const displayAlertDetail = (detail: string) =>
  detail
    .replaceAll("projected closing cash", "tiền cuối kỳ dự kiến")
    .replaceAll("minimum reserve", "ngưỡng dự trữ tối thiểu");
export function Company({ route }: { route: PreviewRoute }) {
  const {
    alerts,
    contracts,
    invoiceDistribution,
    invoices,
    orderDistribution,
    orders,
    snapshot,
  } = usePreviewData();
  const [search, setSearch] = useState("");
  const section = route.section ?? "overview";
  const status = route.status ?? "all";
  const query = (next: Record<string, string>) =>
    navigatePreview(
      `/company?${new URLSearchParams({ section, period: route.period ?? "all", status, ...next })}`,
    );
  const invoiceRows = invoices.filter(
    (i) =>
      (status === "all" || i.status === status) &&
      `${i.id} ${i.contract} ${i.customer}`
        .toLocaleLowerCase("vi")
        .includes(search.toLocaleLowerCase("vi")),
  );
  const orderRows = orders.filter(
    (o) => status === "all" || o.status === status,
  );
  return (
    <>
      <PageHeading
        eyebrow="Phân tích doanh nghiệp"
        title="Tình hình công ty"
        description="Tài chính và hoạt động trong cùng một snapshot công ty."
        action={<Badge>Snapshot · {snapshot.period}</Badge>}
      />
      <Tabs
        label="Phân tích công ty"
        current={section}
        items={sections.map((s) => ({ ...s, to: `/company?section=${s.key}` }))}
      />
      <div className="pv-snapshot-context">
        <span>
          <strong>{snapshot.company}</strong> · Phạm vi công ty
        </span>
        <span>Kỳ nguồn: {snapshot.period}</span>
        <span>Nguồn: bộ dữ liệu giao diện minh họa</span>
        <span>Chưa có thời điểm chốt · Không phải realtime</span>
      </div>
      {section === "overview" && (
        <>
          <div className="pv-company-profile">
            <span className="pv-company-monogram">OPC</span>
            <div>
              <h2>{snapshot.company}</h2>
              <p>{snapshot.subtitle}</p>
            </div>
            <Link to="/company?section=alerts">
              Phạm vi & giới hạn <Icon />
            </Link>
          </div>
          <dl className="pv-kpi-strip">
            <div>
              <dt>Giá trị hợp đồng nguồn</dt>
              <dd>
                <Link to="/company?section=business">
                  {money(snapshot.kpis.contractValue)} <span>VND</span>
                  <Icon />
                </Link>
              </dd>
              <small>Không phải doanh thu đã ghi nhận</small>
            </div>
            <div>
              <dt>Hợp đồng</dt>
              <dd>
                <Link to="/contracts">
                  5<Icon />
                </Link>
              </dd>
              <small>Tất cả trạng thái trong snapshot</small>
            </div>
            <div>
              <dt>Hóa đơn ghi nguồn Open</dt>
              <dd>
                <Link to="/company?section=invoices&status=Open">
                  {money(snapshot.kpis.openInvoices)} <span>VND</span>
                  <Icon />
                </Link>
              </dd>
              <small>Không suy ra từ giao dịch ngân hàng</small>
            </div>
          </dl>
          <div className="pv-two-up">
            <CashChart
              period={route.period}
              onPeriodChange={(v) => query({ period: v })}
            />
            <DistributionChart
              title="Hóa đơn theo trạng thái nguồn"
              description="Giá trị hóa đơn · Toàn bộ snapshot"
              data={invoiceDistribution}
              unit="VND"
              onSelect={(v) =>
                navigatePreview(
                  `/company?section=invoices&status=${encodeURIComponent(v)}`,
                )
              }
            />
          </div>
          <Section
            title="Cần lưu ý"
            action={
              <Link to="/company?section=alerts">
                Xem toàn bộ <Icon />
              </Link>
            }
          >
            <div className="pv-alert-list">
              {alerts.slice(0, 2).map((a) => (
                <div key={a.id}>
                  <Icon name="failure" />
                  <div>
                    <h3>{a.title}</h3>
                    <p>{displayAlertDetail(a.detail)}</p>
                  </div>
                </div>
              ))}
            </div>
          </Section>
        </>
      )}
      {section === "finance" && (
        <>
          <CashChart
            period={route.period}
            onPeriodChange={(v) => query({ period: v })}
          />
          <CashChart period={route.period} closing />
          <div className="pv-inline-note">
            <Icon name="failure" />
            <p>
              Các điểm thuộc cùng một company snapshot. Không cộng lặp các facts
              OPC_GLOBAL từ Finance của nhiều hợp đồng. Dự kiến không đồng nghĩa
              tiền đã thu hoặc chi.
            </p>
          </div>
        </>
      )}
      {section === "business" && (
        <>
          <div className="pv-two-up">
            <DistributionChart
              title="Giá trị theo hợp đồng"
              description="Giá trị hợp đồng nguồn · Không phải doanh thu"
              unit="VND"
              data={contracts.map((c) => ({
                label: c.id,
                value: c.value,
                status: c.id,
              }))}
              onSelect={(v) =>
                v !== "all" && navigatePreview(`/contracts/${v}`)
              }
            />
            <DistributionChart
              title="Đơn hàng theo trạng thái nguồn"
              description="Số đơn hàng có liên kết rõ ràng"
              unit="đơn hàng"
              kind="donut"
              data={orderDistribution}
              selected={status}
              onSelect={(v) => query({ status: v })}
            />
          </div>
          <Section
            title="Đơn hàng"
            description="Đơn hàng có liên kết hợp đồng tường minh"
            action={
              <select
                aria-label="Trạng thái đơn hàng"
                value={status}
                onChange={(e) => query({ status: e.target.value })}
              >
                <option value="all">Tất cả trạng thái</option>
                {orderDistribution.map((d) => (
                  <option key={d.status} value={d.status}>
                    {d.label}
                  </option>
                ))}
              </select>
            }
          >
            <div
              className="pv-table-scroll"
              tabIndex={0}
              role="region"
              aria-label="Bảng dữ liệu có thể cuộn ngang"
            >
              <table>
                <caption className="pv-sr-only">
                  Danh sách đơn hàng minh họa
                </caption>
                <thead>
                  <tr>
                    <th>Đơn hàng</th>
                    <th>Dịch vụ</th>
                    <th>Hợp đồng</th>
                    <th>Trạng thái nguồn</th>
                    <th>Hạn nguồn</th>
                  </tr>
                </thead>
                <tbody>
                  {orderRows.map((o) => (
                    <tr key={o.id}>
                      <td className="pv-id">{o.id}</td>
                      <td>{o.service}</td>
                      <td>
                        <Link to={`/contracts/${o.contract}`}>
                          {o.contract}
                        </Link>
                      </td>
                      <td>
                        <Badge
                          tone={o.status === "At risk" ? "warning" : "neutral"}
                        >
                          {o.status}
                        </Badge>
                      </td>
                      <td>{o.due}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!orderRows.length && (
              <p className="pv-no-results">Không có đơn hàng khớp bộ lọc.</p>
            )}
          </Section>
        </>
      )}
      {section === "invoices" && (
        <>
          <DistributionChart
            title="Giá trị hóa đơn theo trạng thái nguồn"
            description="Mỗi hóa đơn được ghi nhận một lần trong snapshot"
            data={invoiceDistribution}
            unit="VND"
            selected={status}
            onSelect={(v) => query({ status: v })}
          />
          <Section
            title="Hóa đơn"
            description="Trạng thái nguyên gốc · Chưa đối soát với ngân hàng"
            action={
              <div className="pv-controls">
                <SearchField
                  label="Tìm hóa đơn"
                  value={search}
                  onChange={setSearch}
                  placeholder="Tìm ID, khách hàng…"
                />
                <select
                  aria-label="Trạng thái hóa đơn"
                  value={status}
                  onChange={(e) => query({ status: e.target.value })}
                >
                  <option value="all">Tất cả trạng thái</option>
                  <option>Open</option>
                  <option>Paid</option>
                  <option>Not issued</option>
                </select>
              </div>
            }
          >
            <div
              className="pv-table-scroll"
              tabIndex={0}
              role="region"
              aria-label="Bảng dữ liệu có thể cuộn ngang"
            >
              <table>
                <caption className="pv-sr-only">Hóa đơn minh họa · VND</caption>
                <thead>
                  <tr>
                    <th>Hóa đơn</th>
                    <th>Khách hàng / hợp đồng</th>
                    <th>Đơn hàng</th>
                    <th>Trạng thái nguồn</th>
                    <th>Ngày nguồn</th>
                    <th className="pv-numeric">Giá trị (VND)</th>
                  </tr>
                </thead>
                <tbody>
                  {invoiceRows.map((i) => (
                    <tr key={i.id}>
                      <td className="pv-id">{i.id}</td>
                      <td>
                        {i.customer}
                        <small>
                          <Link to={`/contracts/${i.contract}`}>
                            {i.contract}
                          </Link>
                        </small>
                      </td>
                      <td className="pv-id">{i.order}</td>
                      <td>
                        <Badge>{i.status}</Badge>
                      </td>
                      <td>{i.date ?? "Chưa có"}</td>
                      <td className="pv-numeric">
                        {new Intl.NumberFormat("vi-VN").format(i.amount)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!invoiceRows.length && (
              <p className="pv-no-results" role="status">
                Không có hóa đơn khớp bộ lọc.{" "}
                <button
                  onClick={() => {
                    setSearch("");
                    query({ status: "all" });
                  }}
                >
                  Xóa bộ lọc
                </button>
              </p>
            )}
          </Section>
        </>
      )}
      {section === "alerts" && (
        <>
          <Section
            title="Cảnh báo trong nguồn"
            description="Các cảnh báo minh họa có phạm vi riêng; không tạo Risk Score"
          >
            <div className="pv-alert-list">
              {alerts.map((a) => (
                <div key={a.id}>
                  <Icon name="failure" />
                  <div>
                    <h3>{a.title}</h3>
                    <p>{displayAlertDetail(a.detail)}</p>
                    <small>
                      {a.contract
                        ? `Contract scope · ${a.contract}`
                        : "Company scope"}
                    </small>
                  </div>
                  {a.contract && (
                    <Link to={`/contracts/${a.contract}?view=workflow`}>
                      Xem hợp đồng <Icon />
                    </Link>
                  )}
                </div>
              ))}
            </div>
          </Section>
          <Section title="Phạm vi & cách đọc dữ liệu">
            <dl className="pv-facts">
              <div>
                <dt>Nguồn</dt>
                <dd>Fixtures giao diện, không phải TeamPack hoặc backend</dd>
              </div>
              <div>
                <dt>Kỳ / thời điểm chốt</dt>
                <dd>{snapshot.period} / chưa có · Không phải realtime</dd>
              </div>
              <div>
                <dt>Company</dt>
                <dd>
                  Một snapshot duy nhất; không cộng facts OPC_GLOBAL theo
                  contract hoặc run
                </dd>
              </div>
              <div>
                <dt>Contract / Order / Invoice</dt>
                <dd>
                  Định danh riêng, liên kết rõ ràng; không join ngầm theo khách
                  hàng
                </dd>
              </div>
              <div>
                <dt>Run</dt>
                <dd>
                  Mỗi yêu cầu xem xét gắn đúng lượt xử lý, artifact và version
                </dd>
              </div>
              <div>
                <dt>Dữ liệu thiếu</dt>
                <dd>
                  Hiện “Chưa có” hoặc khoảng trống biểu đồ, không nội suy bằng 0
                </dd>
              </div>
            </dl>
          </Section>
        </>
      )}
    </>
  );
}
