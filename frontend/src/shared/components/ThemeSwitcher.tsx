import { useId, type ReactNode } from "react";
import { useThemePreference, type ThemePreference } from "../theme";

const OPTIONS: { value: ThemePreference; label: string; icon: ReactNode }[] = [
  {
    value: "system",
    label: "Theo hệ thống",
    icon: <path d="M3 4h18v12H3zM8 20h8M12 16v4" />,
  },
  {
    value: "light",
    label: "Sáng",
    icon: (
      <>
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
      </>
    ),
  },
  {
    value: "dark",
    label: "Tối",
    icon: <path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5Z" />,
  },
];

/** Dify-style segmented theme control, shared by the connected workspace and the preview shell. */
export function ThemeSwitcher({ className = "" }: { className?: string }) {
  const [preference, setPreference] = useThemePreference();
  const labelId = useId();
  return (
    <div className={`theme-switcher ${className}`.trim()}>
      <span className="theme-switcher__label" id={labelId}>
        Giao diện
      </span>
      <div className="theme-switcher__options" role="group" aria-labelledby={labelId}>
        {OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            className="theme-switcher__option"
            aria-pressed={preference === option.value}
            aria-label={option.label}
            title={option.label}
            onClick={() => setPreference(option.value)}
          >
            <svg
              aria-hidden="true"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              {option.icon}
            </svg>
          </button>
        ))}
      </div>
    </div>
  );
}
