import { useEffect, useState } from "react";
import { stageLabel } from "../../shared/workflowLabels";

interface WorkflowEvent {
  event_id: string;
  workflow_run_id: string;
  sequence: number;
  event_type: string;
  node: string | null;
  created_at: string;
}

/** Read-only event view. No transition or action is inferred from these events. */
export function WorkflowEvents({ runId }: { runId: string }) {
  const [events, setEvents] = useState<readonly WorkflowEvent[]>([]);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    setEvents([]);
    setLoading(true);
    setError(false);
    async function refresh() {
      try {
        const response = await fetch(
          `/api/workflows/${encodeURIComponent(runId)}/events`,
          { signal: controller.signal },
        );
        if (!response.ok) throw new Error("Cannot read events");
        const data: unknown = await response.json();
        if (!Array.isArray(data)) throw new Error("Invalid events response");
        if (!controller.signal.aborted) {
          setEvents(
            data
              .filter((item): item is WorkflowEvent =>
                Boolean(
                  item &&
                  item.workflow_run_id === runId &&
                  typeof item.sequence === "number" &&
                  typeof item.event_type === "string" &&
                  typeof item.created_at === "string" &&
                  typeof item.event_id === "string",
                ),
              )
              .sort((a, b) => b.sequence - a.sequence),
          );
          setError(false);
        }
      } catch {
        if (!controller.signal.aborted) setError(true);
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
          timer = setTimeout(refresh, 1500);
        }
      }
    }
    void refresh();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [runId]);
  return (
    <section className="workflow-events" aria-labelledby="events-title">
      <div className="section-heading">
        <h2 id="events-title">Nhật ký quy trình</h2>
        <span>Sự kiện do máy chủ ghi nhận</span>
      </div>
      {loading && <p className="empty-copy">Đang tải nhật ký…</p>}
      {error && (
        <p role="status">Chưa cập nhật được nhật ký. Hệ thống sẽ thử lại.</p>
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
                <tr key={event.event_id}>
                  <td>{event.sequence}</td>
                  <td>{event.event_type}</td>
                  <td>{event.node ? stageLabel(event.node) : "—"}</td>
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
