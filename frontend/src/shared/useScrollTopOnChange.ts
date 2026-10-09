import { useEffect, useRef } from "react";

/**
 * Scrolls the page back to its top when `key` changes after the first render, so a newly
 * selected local view starts at its beginning instead of mid-page. Focus is left untouched:
 * the control that changed the view keeps it and the skip link keeps working.
 */
export function useScrollTopOnChange(key: string): void {
  const previous = useRef(key);
  useEffect(() => {
    if (previous.current === key) return;
    previous.current = key;
    if (window.scrollY > 0) window.scrollTo({ top: 0, left: 0 });
  }, [key]);
}
