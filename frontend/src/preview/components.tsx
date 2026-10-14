import type { ReactNode } from "react";
import type { PreviewMode } from "./models";

export function Icon({
  name = "arrow",
  size = 18,
}: {
  name?: string;
  size?: number;
}) {
  const paths: Record<string, ReactNode> = {
    dashboard: (
      <>
        <rect x="3" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="3" width="7" height="7" rx="1" />
        <rect x="3" y="14" width="7" height="7" rx="1" />
        <rect x="14" y="14" width="7" height="7" rx="1" />
      </>
    ),
    company: (
      <>
        <path d="M4 21V5h10v16M14 10h6v11M8 9h2m-2 4h2m-2 4h2M2 21h20" />
      </>
    ),
    contracts: (
      <>
        <path d="M6 3h8l4 4v14H6zM14 3v5h4M9 12h6m-6 4h6" />
      </>
    ),
    arrow: <path d="m9 5 7 7-7 7" />,
    "chevron-down": <path d="m6 9 6 6 6-6" />,
    check: <path d="m5 12 4 4L19 6" />,
    approval: (
      <>
        <rect x="5" y="4" width="14" height="17" rx="2" />
        <path d="M9 3h6v4H9zm-1 11 3 3 5-6" />
      </>
    ),
    input: (
      <>
        <path d="M5 4h14v16H5zM9 8h6m-6 4h3M16 16h6m-3-3v6" />
      </>
    ),
    failure: (
      <>
        <path d="m12 3 10 18H2zM12 9v5m0 3v.1" />
      </>
    ),
    search: (
      <>
        <circle cx="10" cy="10" r="6" />
        <path d="m15 15 6 6" />
      </>
    ),
    menu: <path d="M4 6h16M4 12h16M4 18h16" />,
    close: <path d="m6 6 12 12M6 18 18 6" />,
    finance: (
      <>
        <path d="M3 20h18M5 16v-4m7 4V7m7 9V3" />
      </>
    ),
    operations: (
      <>
        <rect x="3" y="5" width="18" height="16" rx="2" />
        <path d="M7 3v4m10-4v4M3 10h18m-13 5h3m3 0h3" />
      </>
    ),
    risk: (
      <>
        <path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6zM12 8v5m0 3v.1" />
      </>
    ),
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name] ?? paths.arrow}
    </svg>
  );
}
export const money = (value: number) =>
  `${new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 }).format(value / 1e9)} tỷ`;
export const number = (value: number) =>
  new Intl.NumberFormat("vi-VN").format(value);
// Presentation units only: inputs always remain VND, never re-aggregated here.
export const billionTick = (value: number) =>
  new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 }).format(
    value / 1e9,
  );
const sourceStatuses: Record<string, string> = {
  Negotiation: "Đang đàm phán",
  Active: "Đang hoạt động",
  "Pending expansion": "Chờ mở rộng",
};
export const sourceStatusLabel = (status: string) =>
  sourceStatuses[status] ?? status;
export function Link({
  to,
  children,
  className = "",
  current = false,
  onClick,
  "aria-label": ariaLabel,
}: {
  to: string;
  children: ReactNode;
  className?: string;
  current?: boolean;
  onClick?: () => void;
  "aria-label"?: string;
}) {
  return (
    <a
      href={`#${to}`}
      className={className}
      aria-current={current ? "page" : undefined}
      onClick={onClick}
      aria-label={ariaLabel}
    >
      {children}
    </a>
  );
}
/** Badge tone for a contract's workflow status; presentation only. */
export function contractTone(status: string) {
  return status === "FAILED_SAFE"
    ? "error"
    : status === "WAITING_FOR_FINAL_DECISION"
      ? "lavender"
      : status === "WAITING_FOR_INPUT"
        ? "warning"
        : "neutral";
}
export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return <span className={`pv-badge pv-badge--${tone}`}>{children}</span>;
}
export function PageHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <header className="pv-page-heading">
      <div>
        {eyebrow && <p className="pv-eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {action}
    </header>
  );
}
export function Section({
  title,
  description,
  action,
  children,
  className = "",
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`pv-section ${className}`}>
      <header className="pv-section-heading">
        <div>
          <h2>{title}</h2>
          {description && <p>{description}</p>}
        </div>
        {action}
      </header>
      {children}
    </section>
  );
}
export function SourceNote({ children }: { children?: ReactNode }) {
  return (
    <p className="pv-source">
      {children ?? "Nguồn: bộ dữ liệu giao diện minh họa"}
    </p>
  );
}
export function Tabs({
  items,
  current,
  label,
}: {
  items: { key: string; label: string; to: string }[];
  current: string;
  label: string;
}) {
  return (
    <nav className="pv-tabs" aria-label={label}>
      {items.map((item) => (
        <Link
          key={item.key}
          to={item.to}
          className={current === item.key ? "is-active" : ""}
          current={current === item.key}
        >
          <span aria-current={current === item.key ? "page" : undefined}>
            {item.label}
          </span>
        </Link>
      ))}
    </nav>
  );
}
export function StateView({
  mode,
  onRetry,
  children,
}: {
  mode: PreviewMode;
  onRetry: () => void;
  children: ReactNode;
}) {
  if (mode === "ready") return <>{children}</>;
  if (mode === "loading")
    return (
      <div className="pv-loading" role="status" aria-live="polite">
        <p>Đang tải bản xem trước…</p>
        <div />
        <div />
        <div />
      </div>
    );
  return (
    <section className="pv-state" role={mode === "error" ? "alert" : "status"}>
      <Icon name={mode === "error" ? "failure" : "contracts"} size={28} />
      <h2>
        {mode === "error"
          ? "Chưa thể tải dữ liệu"
          : "Chưa có dữ liệu trong phạm vi này"}
      </h2>
      <p>
        {mode === "error"
          ? "Lỗi kết nối được mô phỏng để kiểm thử giao diện. Không có request backend nào thất bại."
          : "Trạng thái trống được mô phỏng. Không thay thế giá trị chưa biết bằng số 0."}
      </p>
      <button onClick={onRetry}>
        {mode === "error" ? "Thử lại" : "Quay về dữ liệu minh họa"}
      </button>
    </section>
  );
}
export function SearchField({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}) {
  return (
    <label className="pv-search">
      <Icon name="search" />
      <span className="pv-sr-only">{label}</span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
      />
    </label>
  );
}
