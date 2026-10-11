import { useState } from "react";
import { Company } from "./Company";
import { Contracts } from "./Contracts";
import { Dashboard } from "./Dashboard";
import { Badge, Icon, Link, StateView } from "./components";
import type { PreviewMode } from "./models";
import { usePreviewRoute } from "./navigation";
import "./preview.css";

const navigation = [
  {
    key: "dashboard",
    label: "Bảng điều hành",
    icon: "dashboard",
    to: "/dashboard",
  },
  {
    key: "company",
    label: "Tình hình công ty",
    icon: "company",
    to: "/company",
  },
  { key: "contracts", label: "Hợp đồng", icon: "contracts", to: "/contracts" },
];
export default function PreviewApp() {
  const route = usePreviewRoute();
  const [mode, setMode] = useState<PreviewMode>("ready");
  const [menu, setMenu] = useState(false);
  const pageLabel =
    navigation.find((n) => n.key === route.page)?.label ?? "Không tìm thấy";
  return (
    <div className="pv-app">
      <a
        href="#workspace-content"
        onClick={(e) => {
          e.preventDefault();
          document.getElementById("workspace-content")?.focus();
        }}
        className="skip-link"
      >
        Đến nội dung chính
      </a>
      <aside className={`pv-sidebar ${menu ? "is-open" : ""}`}>
        <Link to="/dashboard" className="pv-brand">
          <span className="pv-wordmark">
            opc<span>.</span>
          </span>
          <span>MIS</span>
        </Link>
        <div className="pv-company-switch">
          <span className="pv-company-avatar">O</span>
          <div>
            <strong>OPC Technology</strong>
            <small>Không gian Founder</small>
          </div>
        </div>
        <nav aria-label="Điều hướng chính">
          {navigation.map((n) => (
            <Link
              key={n.key}
              to={n.to}
              className={route.page === n.key ? "is-active" : ""}
              current={route.page === n.key}
              onClick={() => setMenu(false)}
            >
              <span>
                <Icon name={n.icon} />
                {n.label}
              </span>
            </Link>
          ))}
        </nav>
        <div className="pv-sidebar-footer">
          <span className="pv-preview-dot" />
          Bản xem trước <small>Không kết nối backend</small>
        </div>
      </aside>
      <div className="pv-shell">
        <header className="pv-topbar">
          <button
            className="pv-menu-toggle"
            aria-label="Mở navigation"
            aria-expanded={menu}
            onClick={() => setMenu(!menu)}
          >
            <Icon name={menu ? "close" : "menu"} />
          </button>
          <div className="pv-topbar-context">
            <span>OPC MIS</span>
            <Icon size={12} />
            <strong>{pageLabel}</strong>
          </div>
          <div className="pv-topbar-right">
            <Badge tone="lavender">Dữ liệu minh họa</Badge>
            <label className="pv-mode-label">
              <span>Kiểm thử trạng thái</span>
              <select
                aria-label="Trạng thái preview"
                value={mode}
                onChange={(e) => setMode(e.target.value as PreviewMode)}
              >
                <option value="ready">Sẵn sàng</option>
                <option value="loading">Đang tải</option>
                <option value="empty">Trống</option>
                <option value="error">Lỗi</option>
              </select>
            </label>
          </div>
        </header>
        <main id="workspace-content" tabIndex={-1} className="pv-main">
          <StateView mode={mode} onRetry={() => setMode("ready")}>
            {route.page === "dashboard" ? (
              <Dashboard period={route.period} />
            ) : route.page === "company" ? (
              <Company route={route} />
            ) : route.page === "contracts" ? (
              <Contracts route={route} />
            ) : (
              <section className="pv-state">
                <h1>Không tìm thấy trang</h1>
                <Link to="/dashboard">Về Bảng điều hành</Link>
              </section>
            )}
          </StateView>
        </main>
        <footer className="pv-page-footer">
          <span>OPC MIS · Bản xem trước giao diện</span>
          <span>Dữ liệu minh họa · Không kết nối backend</span>
        </footer>
      </div>
    </div>
  );
}
