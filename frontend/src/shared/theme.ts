import { useCallback, useEffect, useState } from "react";

/** Viewer-local presentation preference; never sent to the backend. */
export type ThemePreference = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

// index.html reads the same key before first paint; keep both in sync.
export const THEME_STORAGE_KEY = "opc-mis-theme";
const DARK_QUERY = "(prefers-color-scheme: dark)";

export function readThemePreference(): ThemePreference {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return stored === "light" || stored === "dark" ? stored : "system";
  } catch {
    return "system";
  }
}

function writeThemePreference(preference: ThemePreference) {
  try {
    if (preference === "system") {
      window.localStorage.removeItem(THEME_STORAGE_KEY);
    } else {
      window.localStorage.setItem(THEME_STORAGE_KEY, preference);
    }
  } catch {
    // Storage can be blocked; the choice still applies for this page view.
  }
}

function darkQuery(): MediaQueryList | null {
  return typeof window.matchMedia === "function" ? window.matchMedia(DARK_QUERY) : null;
}

export function resolveTheme(preference: ThemePreference): ResolvedTheme {
  if (preference !== "system") return preference;
  return darkQuery()?.matches ? "dark" : "light";
}

export function applyTheme(theme: ResolvedTheme) {
  document.documentElement.dataset.theme = theme;
}

/** Applies the preference to <html data-theme> and follows OS changes while on "system". */
export function useThemePreference(): [ThemePreference, (next: ThemePreference) => void] {
  const [preference, setPreference] = useState<ThemePreference>(readThemePreference);

  useEffect(() => {
    applyTheme(resolveTheme(preference));
    const query = preference === "system" ? darkQuery() : null;
    if (!query) return;
    const followSystem = () => applyTheme(resolveTheme("system"));
    query.addEventListener("change", followSystem);
    return () => query.removeEventListener("change", followSystem);
  }, [preference]);

  const update = useCallback((next: ThemePreference) => {
    writeThemePreference(next);
    setPreference(next);
  }, []);

  return [preference, update];
}
