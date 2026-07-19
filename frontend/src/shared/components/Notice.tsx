import type { ReactNode } from "react";

interface NoticeProps {
  tone?: "info" | "warning" | "danger";
  title: string;
  children?: ReactNode;
}

export function Notice({ tone = "info", title, children }: NoticeProps) {
  return (
    <div className={`notice notice--${tone}`} role={tone === "danger" ? "alert" : "status"}>
      <span className="notice__mark" aria-hidden="true" />
      <div>
        <strong>{title}</strong>
        {children ? <p>{children}</p> : null}
      </div>
    </div>
  );
}
