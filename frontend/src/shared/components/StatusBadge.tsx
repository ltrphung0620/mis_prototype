import { statusLabel, statusTone } from "../workflowLabels";

interface StatusBadgeProps {
  status: string;
  label?: string;
  compact?: boolean;
}

export function StatusBadge({ status, label, compact = false }: StatusBadgeProps) {
  const tone = statusTone(status);
  return (
    <span className={`status-badge status-badge--${tone}${compact ? " status-badge--compact" : ""}`}>
      <span className="status-badge__dot" aria-hidden="true" />
      {label ?? statusLabel(status)}
    </span>
  );
}
