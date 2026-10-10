import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { usePreviewData } from "./data";
import type { StatusPoint } from "./models";
import {
  billionTick,
  Link,
  money,
  number,
  Section,
  SourceNote,
} from "./components";

const COLORS = [
  "var(--pv-chart-primary)",
  "var(--pv-chart-secondary)",
  "var(--pv-chart-tertiary)",
  "var(--pv-chart-warning)",
  "var(--pv-chart-neutral)",
];
function ChartTooltip({
  active,
  payload,
  label,
  unit = "VND",
}: {
  active?: boolean;
  payload?: readonly { name?: string | number; value?: unknown }[];
  label?: unknown;
  unit?: "VND" | "đơn hàng";
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="pv-chart-tooltip">
      <p>
        {typeof label === "string" || typeof label === "number"
          ? label
          : "Phân bố nguồn"}{" "}
        · Dữ liệu minh họa
      </p>
      {payload.map((item, index) => (
        <div key={index}>
          <span>{item.name}</span>
          <strong>
            {typeof item.value === "number"
              ? unit === "VND"
                ? `${money(item.value)} VND`
                : `${number(item.value)} đơn hàng`
              : "Chưa có dữ liệu"}
          </strong>
          {unit === "VND" && typeof item.value === "number" && (
            <small>{number(item.value)} VND</small>
          )}
        </div>
      ))}
    </div>
  );
}
export function CashChart({
  period = "all",
  closing = false,
  onPeriodChange,
  compact = false,
}: {
  period?: string;
  closing?: boolean;
  compact?: boolean;
  onPeriodChange?: (value: string) => void;
}) {
  const { cashflow } = usePreviewData();
  const [table, setTable] = useState(false);
  const [hidden, setHidden] = useState<string[]>([]);
  const series = closing
    ? [
        { key: "closing", label: "Tiền cuối kỳ dự kiến", color: COLORS[0] },
        { key: "reserve", label: "Ngưỡng dự trữ nguồn", color: "#9D896A" },
      ]
    : [
        { key: "cashIn", label: "Thu dự kiến", color: COLORS[0] },
        { key: "cashOut", label: "Chi dự kiến", color: COLORS[1] },
      ];
  const data =
    period === "empty"
      ? []
      : period === "recent"
        ? cashflow.slice(-3)
        : [...cashflow];
  const toggle = (key: string) =>
    setHidden((old) =>
      old.includes(key) ? old.filter((x) => x !== key) : [...old, key],
    );
  return (
    <Section
      title={closing ? "Tiền cuối kỳ & dự trữ" : "Dòng tiền dự kiến"}
      description={
        closing
          ? "Giá trị dự kiến, không phải số dư ngân hàng"
          : "Snapshot công ty · Thu và chi theo kỳ nguồn"
      }
      className="pv-chart-section"
      action={
        <div className="pv-controls">
          {onPeriodChange && (
            <select
              aria-label="Kỳ biểu đồ dòng tiền"
              value={period}
              onChange={(e) => onPeriodChange(e.target.value)}
            >
              <option value="all">06–11/2026</option>
              <option value="recent">09–11/2026</option>
              <option value="empty">Kỳ chưa có dữ liệu</option>
            </select>
          )}
          <button onClick={() => setTable(!table)} aria-pressed={table}>
            {table ? "Biểu đồ" : "Bảng dữ liệu"}
          </button>
        </div>
      }
    >
      <div className="pv-chart-meta">
        <span>Đơn vị: tỷ VND</span>
        <div className="pv-legend">
          {series.map((s) => (
            <button
              key={s.key}
              className={hidden.includes(s.key) ? "is-hidden" : ""}
              aria-pressed={!hidden.includes(s.key)}
              onClick={() => toggle(s.key)}
            >
              <span style={{ background: s.color }} />
              {s.label}
            </button>
          ))}
        </div>
      </div>
      {!data.length ? (
        <div className="pv-chart-empty" role="status">
          Chưa có dữ liệu dự kiến cho kỳ này. Không suy ra bằng 0.
        </div>
      ) : table ? (
        <div
          className="pv-table-scroll"
          tabIndex={0}
          role="region"
          aria-label="Bảng dữ liệu có thể cuộn ngang"
        >
          <table>
            <caption className="pv-sr-only">
              Dòng tiền minh họa theo kỳ, đơn vị VND
            </caption>
            <thead>
              <tr>
                <th>Kỳ</th>
                {series
                  .filter((s) => !hidden.includes(s.key))
                  .map((s) => (
                    <th key={s.key} className="pv-numeric">
                      {s.label} (VND)
                    </th>
                  ))}
              </tr>
            </thead>
            <tbody>
              {data.map((p) => (
                <tr key={p.month}>
                  <td>{p.label}</td>
                  {series
                    .filter((s) => !hidden.includes(s.key))
                    .map((s) => (
                      <td key={s.key} className="pv-numeric">
                        {p[s.key as keyof typeof p] == null
                          ? "Chưa xác định"
                          : new Intl.NumberFormat("vi-VN").format(
                              Number(p[s.key as keyof typeof p]),
                            )}
                      </td>
                    ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div
          className={`pv-chart ${compact ? "pv-chart--compact" : ""}`}
          role="img"
          aria-label={
            closing
              ? "Tiền cuối kỳ dự kiến so với ngưỡng dự trữ. Có bảng dữ liệu thay thế."
              : "Thu và chi dự kiến tháng 6 đến tháng 11. Có bảng dữ liệu thay thế."
          }
        >
          <ResponsiveContainer
            width="100%"
            height="100%"
            initialDimension={{ width: 640, height: 240 }}
          >
            <LineChart
              data={data}
              margin={{ top: 20, right: 18, bottom: 6, left: -18 }}
              accessibilityLayer
            >
              <CartesianGrid vertical={false} stroke="#EDEEF1" />
              <XAxis
                dataKey="label"
                axisLine={false}
                tickLine={false}
                tick={{ fill: "var(--color-ink-600)", fontSize: 13 }}
                dy={8}
              />
              <YAxis
                axisLine={false}
                tickLine={false}
                tickFormatter={billionTick}
                tick={{ fill: "var(--color-ink-600)", fontSize: 13 }}
              />
              <Tooltip
                content={<ChartTooltip />}
                wrapperStyle={{ zIndex: 5 }}
              />
              {series.map((s) => (
                <Line
                  key={s.key}
                  hide={hidden.includes(s.key)}
                  type="linear"
                  dataKey={s.key}
                  name={s.label}
                  stroke={s.color}
                  strokeWidth={2}
                  dot={{ r: 3, strokeWidth: 0, fill: s.color }}
                  activeDot={{ r: 5 }}
                  strokeDasharray={s.key === "reserve" ? "5 5" : undefined}
                  isAnimationActive={false}
                  connectNulls={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
      <footer className="pv-chart-footer">
        <SourceNote>Nguồn minh họa · Toàn bộ giá trị là dự kiến</SourceNote>
        {compact && (
          <Link to="/company?section=finance">Phân tích dòng tiền →</Link>
        )}
      </footer>
    </Section>
  );
}
export function DistributionChart({
  title,
  description,
  data,
  unit,
  kind = "bar",
  onSelect,
  selected = "all",
}: {
  title: string;
  description: string;
  data: readonly StatusPoint[];
  unit: "VND" | "đơn hàng";
  kind?: "bar" | "donut";
  onSelect?: (status: string) => void;
  selected?: string;
}) {
  const [table, setTable] = useState(false);
  const chartData = [...data];
  return (
    <Section
      title={title}
      description={description}
      className="pv-chart-section"
      action={
        <button onClick={() => setTable(!table)} aria-pressed={table}>
          {table ? "Biểu đồ" : "Bảng dữ liệu"}
        </button>
      }
    >
      <div className="pv-chart-meta">
        Đơn vị: {unit === "VND" ? "tỷ VND" : unit}
      </div>
      {table ? (
        <div
          className="pv-table-scroll"
          tabIndex={0}
          role="region"
          aria-label="Bảng dữ liệu có thể cuộn ngang"
        >
          <table>
            <caption className="pv-sr-only">{title} · Dữ liệu minh họa</caption>
            <thead>
              <tr>
                <th>Nhóm nguồn</th>
                <th className="pv-numeric">Giá trị ({unit})</th>
              </tr>
            </thead>
            <tbody>
              {data.map((d) => (
                <tr key={d.status}>
                  <td>{d.label}</td>
                  <td className="pv-numeric">
                    {new Intl.NumberFormat("vi-VN").format(d.value)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div
          className="pv-chart pv-chart--distribution"
          role="img"
          aria-label={`${title}. Dữ liệu minh họa; có bảng thay thế.`}
        >
          <ResponsiveContainer
            width="100%"
            height="100%"
            initialDimension={{ width: 480, height: 225 }}
          >
            {kind === "donut" ? (
              <PieChart accessibilityLayer>
                <Pie
                  data={chartData}
                  dataKey="value"
                  nameKey="label"
                  innerRadius={62}
                  outerRadius={86}
                  paddingAngle={3}
                  isAnimationActive={false}
                  onClick={(_, index) => onSelect?.(chartData[index].status)}
                >
                  {chartData.map((d, i) => (
                    <Cell key={d.status} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  content={<ChartTooltip unit={unit} />}
                  wrapperStyle={{ zIndex: 5 }}
                />
              </PieChart>
            ) : (
              <BarChart
                data={chartData}
                layout="vertical"
                margin={{ top: 10, right: 30, bottom: 5, left: 5 }}
                accessibilityLayer
              >
                <CartesianGrid horizontal={false} stroke="#EDEEF1" />
                <XAxis
                  type="number"
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={unit === "VND" ? billionTick : undefined}
                  tick={{ fill: "var(--color-ink-600)", fontSize: 13 }}
                />
                <YAxis
                  type="category"
                  dataKey="label"
                  axisLine={false}
                  tickLine={false}
                  width={118}
                  tick={{ fill: "var(--color-ink-600)", fontSize: 13 }}
                />
                <Tooltip
                  content={<ChartTooltip unit={unit} />}
                  wrapperStyle={{ zIndex: 5 }}
                />
                <Bar
                  dataKey="value"
                  name={title}
                  barSize={20}
                  radius={[0, 3, 3, 0]}
                  isAnimationActive={false}
                  onClick={(_, index) => onSelect?.(chartData[index].status)}
                >
                  {chartData.map((d, i) => (
                    <Cell key={d.status} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            )}
          </ResponsiveContainer>
        </div>
      )}
      <div className="pv-distribution-legend">
        {data.map((d, i) => (
          <button
            key={d.status}
            aria-pressed={selected === d.status}
            onClick={() => onSelect?.(selected === d.status ? "all" : d.status)}
            disabled={!onSelect}
          >
            <span style={{ background: COLORS[i % COLORS.length] }} />
            {d.label}
            <strong>{unit === "VND" ? money(d.value) : d.value}</strong>
          </button>
        ))}
      </div>
      <SourceNote>
        Trạng thái giữ theo nguồn · Không suy ra thanh toán hoặc doanh thu
      </SourceNote>
    </Section>
  );
}
