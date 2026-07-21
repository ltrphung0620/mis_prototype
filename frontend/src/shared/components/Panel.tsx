import type { ReactNode } from "react";

interface PanelProps {
  eyebrow: string;
  title: string;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function Panel({ eyebrow, title, aside, children, className = "" }: PanelProps) {
  return (
    <section className={`panel ${className}`.trim()}>
      <header className="panel__header">
        <div>
          <p className="panel__eyebrow">{eyebrow}</p>
          <h2>{title}</h2>
        </div>
        {aside ? <div className="panel__aside">{aside}</div> : null}
      </header>
      <div className="panel__body">{children}</div>
    </section>
  );
}
