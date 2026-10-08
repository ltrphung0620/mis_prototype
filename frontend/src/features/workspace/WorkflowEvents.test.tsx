import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { WorkflowEvents } from "./WorkflowEvents";

afterEach(() => vi.unstubAllGlobals());
describe("Workflow event view", () => {
  it("shows only this run's events and aborts requests on unmount", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [
        {
          event_id: "e1",
          workflow_run_id: "RUN",
          sequence: 1,
          event_type: "NODE_COMPLETED",
          node: "FINANCE_ASSESSMENT",
          created_at: "2026-10-08T08:00:00Z",
        },
        {
          event_id: "e2",
          workflow_run_id: "OTHER",
          sequence: 2,
          event_type: "STALE_EVENT",
          node: null,
          created_at: "2026-10-08T08:00:00Z",
        },
      ],
    });
    vi.stubGlobal("fetch", fetchMock);
    const { unmount } = render(<WorkflowEvents runId="RUN" />);
    expect(await screen.findByText("NODE_COMPLETED")).toBeInTheDocument();
    expect(screen.queryByText("STALE_EVENT")).not.toBeInTheDocument();
    const signal = fetchMock.mock.calls[0][1].signal as AbortSignal;
    unmount();
    expect(signal.aborted).toBe(true);
  });
});
