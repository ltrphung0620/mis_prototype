import { lazy, Suspense } from "react";

const PreviewApp = lazy(() => import("./PreviewApp"));
export function PreviewEntry() {
  return (
    <Suspense fallback={<p role="status">Đang tải UI preview…</p>}>
      <PreviewApp />
    </Suspense>
  );
}
