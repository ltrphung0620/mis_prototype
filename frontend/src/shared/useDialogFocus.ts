import { useEffect, useRef } from "react";

const DIALOG_SELECTOR = '[role="dialog"][aria-modal="true"]';
const FOCUSABLE_SELECTOR = [
  "button",
  "a[href]",
  'input:not([type="hidden"])',
  "select",
  "textarea",
  "[tabindex]",
].join(", ");

/** The modal rendered last is the one on top. */
export function topmostDialog(): HTMLElement | null {
  const dialogs = document.querySelectorAll<HTMLElement>(DIALOG_SELECTOR);
  return dialogs.length ? dialogs[dialogs.length - 1] : null;
}

export function focusableWithin(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
    (element) =>
      element.getAttribute("tabindex") !== "-1" &&
      !element.matches(":disabled") &&
      !element.closest("[hidden], [inert]"),
  );
}

/** Make everything outside the dialog inert; returns a function that restores it. */
function isolate(dialog: HTMLElement): () => void {
  const changed: HTMLElement[] = [];
  let node: HTMLElement | null = dialog;
  while (node && node !== document.body) {
    const parent: HTMLElement | null = node.parentElement;
    for (const sibling of Array.from(parent?.children ?? [])) {
      if (sibling === node || !(sibling instanceof HTMLElement)) continue;
      if (sibling.hasAttribute("inert") || sibling.tagName === "SCRIPT") continue;
      sibling.setAttribute("inert", "");
      changed.push(sibling);
    }
    node = parent;
  }
  return () => changed.forEach((element) => element.removeAttribute("inert"));
}

/**
 * Focus scope for the topmost modal dialog: it follows dialog replacement, makes the
 * background inert, traps Tab, handles Escape and restores the original trigger.
 * Initial focus goes to `[data-autofocus]` or the dialog itself, never to an action button.
 * A dialog opened without a trigger (e.g. by workflow state) returns focus to `fallbackFocusId`.
 */
export function useDialogFocus(
  active: boolean,
  onEscape: () => void,
  {
    escapeDisabled = false,
    fallbackFocusId,
  }: { escapeDisabled?: boolean; fallbackFocusId?: string } = {},
) {
  const onEscapeRef = useRef(onEscape);
  const escapeDisabledRef = useRef(escapeDisabled);
  const fallbackFocusIdRef = useRef(fallbackFocusId);
  onEscapeRef.current = onEscape;
  escapeDisabledRef.current = escapeDisabled;
  fallbackFocusIdRef.current = fallbackFocusId;

  useEffect(() => {
    if (!active) return;
    const focused = document.activeElement;
    const trigger = focused instanceof HTMLElement && focused !== document.body ? focused : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    let current: HTMLElement | null = null;
    let restoreBackground: () => void = () => undefined;

    function enter(dialog: HTMLElement | null): void {
      if (dialog === current) return;
      restoreBackground();
      restoreBackground = () => undefined;
      current = dialog;
      if (!dialog) return;
      restoreBackground = isolate(dialog);
      if (!dialog.hasAttribute("tabindex")) dialog.setAttribute("tabindex", "-1");
      const target = dialog.querySelector<HTMLElement>("[data-autofocus]") ?? dialog;
      target.focus();
    }

    enter(topmostDialog());
    const observer = new MutationObserver(() => enter(topmostDialog()));
    observer.observe(document.body, { childList: true, subtree: true });

    function onKey(event: KeyboardEvent): void {
      const dialog = current;
      if (!dialog) return;
      if (event.key === "Escape") {
        event.preventDefault();
        if (!escapeDisabledRef.current) onEscapeRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const elements = focusableWithin(dialog);
      const first = elements[0];
      const last = elements.at(-1);
      if (!first || !last) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const inside = dialog.contains(document.activeElement);
      if (event.shiftKey && (!inside || document.activeElement === first || document.activeElement === dialog)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (!inside || document.activeElement === last)) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", onKey);

    return () => {
      observer.disconnect();
      document.removeEventListener("keydown", onKey);
      restoreBackground();
      document.body.style.overflow = previousOverflow;
      const fallback = fallbackFocusIdRef.current
        ? document.getElementById(fallbackFocusIdRef.current)
        : null;
      (trigger?.isConnected ? trigger : fallback)?.focus();
    };
  }, [active]);
}
