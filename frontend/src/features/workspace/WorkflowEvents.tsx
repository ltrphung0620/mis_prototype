import { useEffect, useRef, useState } from "react";

import { getWorkflowEvents } from "../../api/client";
import { eventTypeLabel } from "../../shared/eventLabels";
import { knownWorkflowLabel } from "../../shared/workflowLabels";

export const EVENT_POLL_INTERVAL_MS = 1_500;
const EVENT_RETRY_INTERVAL_MS = EVENT_POLL_INTERVAL_MS * 2;

interface WorkflowEvent {
  event_id: string;
  workflow_run_id: string;
  sequence: number;
  event_type: string;
  node: string | null;
  created_at: string;
}

function runEvents(data: unknown, runId: string): WorkflowEvent[] {
  if (!Array.isArray(data)) throw new Error("Invalid events response");
  return data.filter((item): item is WorkflowEvent =>
    Boolean(
      item &&
      item.workflow_run_id === runId &&
      Number.isInteger(item.sequence) &&
      typeof item.event_type === "string" &&
      typeof item.created_at === "string" &&
      typeof item.event_id === "string",
    ),
  );
}

/** Merge an incremental page into the log; sequence is the append-only identity. */
export function mergeEvents<T extends { sequence: number }>(
  current: readonly T[],
  incoming: readonly T[],
): readonly T[] {
  if (!incoming.length) return current;
  const bySequence = new Map(current.map((item) => [item.sequence, item]));
  for (const item of incoming) bySequence.set(item.sequence, item);
  return [...bySequence.values()].sort((a, b) => b.sequence - a.sequence);
}

function CodeLabel({ code, label }: { code: string; label: string | null }) {
  return label ? <>{label}</> : <span className="artifact-id">{code}</span>;
}

/**
 * Read-only event view. No transition or action is inferred from these events;
 * `live` comes from the dashboard projection and only controls polling.
 */
export function WorkflowEvents({
  runId,
  live = true,
}: {
  runId: string;
  live?: boolean;
}) {
  const [events, setEvents] = useState<readonly WorkflowEvent[]>([]);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  const cursor = useRef({ runId, sequence: 0 });

  useEffect(() => {
    cursor.current = { runId, sequence: 0 };
    setEvents([]);
    setLoading(true);
    setError(false);
  }, [runId]);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function refresh() {
      const after =
        cursor.current.runId === runId ? cursor.current.sequence : 0;
      let failed = false;
      try {
        const page = runEvents(
          await getWorkflowEvents(runId, after, controller.signal),
          runId,
        );
        if (controller.signal.aborted) return;
        cursor.current = {
          runId,
          sequence: page.reduce((max, item) => Math.max(max, item.sequence), after),
        };
        setEvents((current) => mergeEvents(current, page));
        setError(false);
      } catch {
        if (controller.signal.aborted) return;
        failed = true;
        setError(true);
      }
      setLoading(false);
      // A terminal run still gets this one catch-up read; failures keep retrying.
      if (failed) timer = setTimeout(refresh, EVENT_RETRY_INTERVAL_MS);
      else if (live) timer = setTimeout(refresh, EVENT_POLL_INTERVAL_MS);
    }
    void refresh();
    return () => {
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [live, runId]);

  return (
    <section className="workflow-events" aria-labelledby="events-title">
      <div className="section-heading">
        <h2 id="events-title">Nhật ký quy trình</h2>
        <span>Sự kiện do máy chủ ghi nhận</span>
      </div>
      {loading && !events.length && (
        <p className="empty-copy">Đang tải nhật ký…</p>
      )}
      {error && (
        <p role="status">
          {events.length
            ? "Chưa cập nhật được sự kiện mới. Nhật ký bên dưới có thể chưa đầy đủ; hệ thống sẽ thử lại."
            : "Chưa cập nhật được nhật ký. Hệ thống sẽ thử lại."}
        </p>
      )}
      {!loading && !error && !events.length && (
        <p className="empty-copy">Chưa có sự kiện cho lượt xử lý này.</p>
      )}
      {!!events.length && (
        <div className="table-scroll">
          <table className="evidence-table">
            <thead>
              <tr>
                <th>Thứ tự</th>
                <th>Sự kiện</th>
                <th>Tác vụ</th>
                <th>Thời gian</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event) => (
                <tr key={event.sequence}>
                  <td>{event.sequence}</td>
                  <td>
                    <CodeLabel
                      code={event.event_type}
                      label={eventTypeLabel(event.event_type)}
                    />
                  </td>
                  <td>
                    {event.node ? (
                      <CodeLabel
                        code={event.node}
                        label={knownWorkflowLabel(event.node)}
                      />
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>
                    {Number.isNaN(Date.parse(event.created_at))
                      ? "Chưa xác định"
                      : new Date(event.created_at).toLocaleString("vi-VN")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
