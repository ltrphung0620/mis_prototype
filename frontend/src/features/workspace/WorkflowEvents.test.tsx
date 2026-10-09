import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EVENT_POLL_INTERVAL_MS, WorkflowEvents, mergeEvents } from "./WorkflowEvents";

function event(sequence: number, eventType: string, runId = "RUN", node: string | null = null) {
  return {
    event_id: `${runId}-e${sequence}`,
    workflow_run_id: runId,
    sequence,
    event_type: eventType,
    node,
    created_at: "2026-10-08T08:00:00Z",
  };
}

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status < 400,
    status,
    headers: { get: () => "application/json" },
    json: async () => body,
  };
}

function requestedUrl(fetchMock: ReturnType<typeof vi.fn>, call: number): URL {
  return new URL(String(fetchMock.mock.calls[call][0]), "http://localhost");
}

const flush = () => act(() => vi.advanceTimersByTimeAsync(0));
const advance = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("Workflow event view", () => {
  it("labels known codes, shows unknown codes verbatim and ignores other runs", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse([
        event(1, "NODE_COMPLETED", "RUN", "FINANCE_ASSESSMENT"),
        event(2, "STALE_EVENT", "OTHER"),
        event(3, "SOMETHING_NEW", "RUN", "UNMAPPED_NODE"),
      ]),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { unmount } = render(<WorkflowEvents runId="RUN" />);
    await flush();

    expect(requestedUrl(fetchMock, 0).pathname).toBe("/api/workflows/RUN/events");
    expect(requestedUrl(fetchMock, 0).searchParams.get("after_sequence")).toBe("0");
    expect(screen.getByText("Tác vụ đã chạy xong")).toBeInTheDocument();
    expect(screen.getByText("Đánh giá tài chính")).toBeInTheDocument();
    expect(screen.getByText("SOMETHING_NEW")).toBeInTheDocument();
    expect(screen.getByText("UNMAPPED_NODE")).toBeInTheDocument();
    expect(screen.queryByText("NODE_COMPLETED")).not.toBeInTheDocument();
    expect(screen.queryByText("STALE_EVENT")).not.toBeInTheDocument();

    const signal = fetchMock.mock.calls[0][1].signal as AbortSignal;
    unmount();
    expect(signal.aborted).toBe(true);
  });

  it("fetches only newer events and merges them by sequence", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse([event(1, "WORKFLOW_STARTED"), event(2, "NODE_STARTED")]))
      .mockResolvedValueOnce(jsonResponse([event(2, "NODE_STARTED"), event(3, "NODE_COMPLETED")]))
      .mockResolvedValue(jsonResponse([]));
    vi.stubGlobal("fetch", fetchMock);
    render(<WorkflowEvents runId="RUN" />);
    await flush();
    await advance(EVENT_POLL_INTERVAL_MS);

    expect(requestedUrl(fetchMock, 1).searchParams.get("after_sequence")).toBe("2");
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows.map((row) => row.querySelector("td")?.textContent)).toEqual(["3", "2", "1"]);

    await advance(EVENT_POLL_INTERVAL_MS);
    expect(requestedUrl(fetchMock, 2).searchParams.get("after_sequence")).toBe("3");
    expect(screen.getAllByRole("row")).toHaveLength(4);
  });

  it("stops polling after one catch-up read when the run is terminal", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([event(1, "WORKFLOW_COMPLETED")]));
    vi.stubGlobal("fetch", fetchMock);
    const { rerender } = render(<WorkflowEvents runId="RUN" live />);
    await flush();
    expect(fetchMock).toHaveBeenCalledTimes(1);

    rerender(<WorkflowEvents runId="RUN" live={false} />);
    await flush();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(requestedUrl(fetchMock, 1).searchParams.get("after_sequence")).toBe("1");

    await advance(EVENT_POLL_INTERVAL_MS * 5);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(screen.getByText("Quy trình đã chạy xong")).toBeInTheDocument();
  });

  it("resets the log and cursor when the run changes", async () => {
    const fetchMock = vi.fn((input: string, _init?: RequestInit) =>
      Promise.resolve(
        jsonResponse(
          input.includes("/RUN-B/")
            ? [event(1, "WORKFLOW_CREATED", "RUN-B")]
            : [event(1, "WORKFLOW_STARTED", "RUN-A"), event(2, "APPROVAL_REQUESTED", "RUN-A")],
        ),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { rerender } = render(<WorkflowEvents runId="RUN-A" />);
    await flush();
    expect(screen.getByText("Tạo yêu cầu phê duyệt")).toBeInTheDocument();
    const firstSignal = fetchMock.mock.calls[0][1]?.signal as AbortSignal;

    rerender(<WorkflowEvents runId="RUN-B" />);
    await flush();

    expect(firstSignal.aborted).toBe(true);
    const lastCall = requestedUrl(fetchMock, fetchMock.mock.calls.length - 1);
    expect(lastCall.pathname).toBe("/api/workflows/RUN-B/events");
    expect(lastCall.searchParams.get("after_sequence")).toBe("0");
    expect(screen.getByText("Tạo lượt xử lý")).toBeInTheDocument();
    expect(screen.queryByText("Tạo yêu cầu phê duyệt")).not.toBeInTheDocument();
  });

  it("keeps loaded events on error and recovers from the same cursor", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse([event(1, "WORKFLOW_STARTED")]))
      .mockResolvedValueOnce(jsonResponse({ detail: "unavailable" }, 503))
      .mockResolvedValueOnce(jsonResponse([event(2, "WORKFLOW_PAUSED")]))
      .mockResolvedValue(jsonResponse([]));
    vi.stubGlobal("fetch", fetchMock);
    render(<WorkflowEvents runId="RUN" />);
    await flush();
    await advance(EVENT_POLL_INTERVAL_MS);

    expect(screen.getByRole("status")).toHaveTextContent("Chưa cập nhật được sự kiện mới");
    expect(screen.getByText("Bắt đầu quy trình")).toBeInTheDocument();

    await advance(EVENT_POLL_INTERVAL_MS);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    await advance(EVENT_POLL_INTERVAL_MS);

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(requestedUrl(fetchMock, 2).searchParams.get("after_sequence")).toBe("1");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.getByText("Tạm dừng chờ Founder")).toBeInTheDocument();
  });

  it("shows an honest initial error and keeps retrying a terminal run until it loads", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("network"))
      .mockResolvedValue(jsonResponse([]));
    vi.stubGlobal("fetch", fetchMock);
    render(<WorkflowEvents runId="RUN" live={false} />);
    await flush();
    expect(screen.getByRole("status")).toHaveTextContent("Chưa cập nhật được nhật ký");

    await advance(EVENT_POLL_INTERVAL_MS * 2);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(screen.getByText("Chưa có sự kiện cho lượt xử lý này.")).toBeInTheDocument();

    await advance(EVENT_POLL_INTERVAL_MS * 5);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

describe("mergeEvents", () => {
  it("dedupes by sequence and sorts newest first", () => {
    const merged = mergeEvents(
      [{ sequence: 2, id: "old-2" }, { sequence: 1, id: "1" }],
      [{ sequence: 3, id: "3" }, { sequence: 2, id: "new-2" }],
    );
    expect(merged.map((item) => item.id)).toEqual(["3", "new-2", "1"]);
  });
});
