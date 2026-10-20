/** Explicit opt-in for presentation scenarios; never changes business permissions. */
export function previewTestingEnabled(): boolean {
  return new URLSearchParams(window.location.search).get("ui_test") === "1";
}
