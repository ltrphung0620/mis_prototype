import { useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  BackgroundVariant,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  useViewport,
  type Node,
  type NodeProps,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Icon, SourceNote } from "../components";
import { navigatePreview } from "../navigation";
import type { PreviewContract, PreviewRoute } from "../models";
import { artifactTypeLabel } from "../../shared/artifactLabels";
import { statusLabel } from "../../shared/workflowLabels";
import { previewTestingEnabled } from "../testing";
import { workflowDetailLabel } from "./labels";
import {
  defaultScenario,
  isScenario,
  scenarios,
  statusPresentation,
  workflowFixture,
  type ArtifactReference,
  type NodeSnapshot,
} from "./fixtures";
import {
  dependencies,
  phases,
  topology,
  type NodeDefinition,
  type View,
} from "./topology";
import "./workflow.css";

type FlowData = {
  definition: NodeDefinition;
  snapshot: NodeSnapshot;
  open: (id: string) => void;
};
type FlowNode = Node<FlowData, "workflow">;
const kindLabel = {
  agent: "Bước đánh giá",
  gate: "Bước phê duyệt",
  system: "Xử lý tự động",
  interaction: "Thao tác trong quy trình",
};
function Status({ state }: { state: NodeSnapshot }) {
  const status = statusPresentation(state);
  return (
    <span className={`wf-status is-${status.tone}`}>
      <span aria-hidden="true">{status.symbol}</span>
      {status.label}
    </span>
  );
}
function WorkflowNode({ data, selected }: NodeProps<FlowNode>) {
  const { definition: n, snapshot: state, open } = data;
  return (
    <div
      className={`wf-node ${selected ? "is-selected" : ""} ${state.applicability === "not-applicable" ? "is-inactive" : ""}`}
    >
      <Handle
        type="target"
        position={Position.Left}
        id="in-left"
        isConnectable={false}
      />
      <Handle
        type="target"
        position={Position.Right}
        id="in-right"
        isConnectable={false}
      />
      <Handle
        type="target"
        position={Position.Top}
        id="in-top"
        isConnectable={false}
      />
      <Handle
        type="source"
        position={Position.Right}
        id="out-right"
        isConnectable={false}
      />
      <Handle
        type="source"
        position={Position.Left}
        id="out-left"
        isConnectable={false}
      />
      <Handle
        type="source"
        position={Position.Bottom}
        id="out-bottom"
        isConnectable={false}
      />
      <button
        data-wf-select={n.id}
        className="wf-node-button nodrag"
        onClick={(event) => {
          event.stopPropagation();
          open(n.id);
        }}
        aria-pressed={selected}
        aria-label={`${n.title} · ${statusPresentation(state).label}`}
      >
        <span className={`wf-node-icon ${n.kind === "gate" ? "is-gate" : ""}`}>
          <Icon
            name={
              n.kind === "gate"
                ? "approval"
                : n.id.includes("RISK")
                  ? "risk"
                  : n.id.includes("FINANCE")
                    ? "finance"
                    : "operations"
            }
            size={16}
          />
        </span>
        <span className="wf-node-title">{n.title}</span>
        <span className="wf-node-kind">
          {n.kind === "gate"
            ? "Duyệt riêng"
            : n.phase === "banking"
              ? "Ngân hàng và hồ sơ"
              : kindLabel[n.kind]}
        </span>
        <Status state={state} />
      </button>
    </div>
  );
}
const nodeTypes = { workflow: WorkflowNode };
type Snapshot = ReturnType<typeof workflowFixture>;
function Canvas({
  snapshot,
  view,
  selected,
  onSelect,
}: {
  snapshot: Snapshot;
  view: View;
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const flow = useReactFlow<FlowNode>();
  const viewport = useViewport();
  const visible = topology.filter((n) => view === "all" || n.phase === view);
  const nodes: FlowNode[] = visible.map((n) => ({
    id: n.id,
    type: "workflow",
    position: {
      x:
        n.x +
        (view === "all" ? phases.findIndex((p) => p.id === n.phase) * 1320 : 0),
      y: n.y + (view === "all" && n.phase === "banking" ? 320 : 0),
    },
    data: { definition: n, snapshot: snapshot.states[n.id], open: onSelect },
    selected: n.id === selected,
    draggable: false,
    connectable: false,
    focusable: false,
  }));
  const edges: Edge[] = dependencies
    .filter(
      (d) =>
        visible.some((n) => n.id === d.from) &&
        visible.some((n) => n.id === d.to),
    )
    .map((d) => {
      const from = nodes.find((n) => n.id === d.from)!,
        to = nodes.find((n) => n.id === d.to)!;
      const touching = selected === d.from || selected === d.to;
      const inactive =
        snapshot.states[d.from].applicability === "not-applicable" ||
        snapshot.states[d.to].applicability === "not-applicable";
      const vertical =
        from.position.x === to.position.x && to.position.y > from.position.y;
      const backwards = to.position.x < from.position.x;
      return {
        id: `${d.from}:${d.to}`,
        source: d.from,
        target: d.to,
        type: "smoothstep",
        sourceHandle: vertical
          ? "out-bottom"
          : backwards
            ? "out-left"
            : "out-right",
        targetHandle: vertical ? "in-top" : backwards ? "in-right" : "in-left",
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 16,
          height: 16,
          color: touching
            ? "var(--color-primary-strong)"
            : "var(--color-ink-450)",
        },
        className: `${touching ? "is-highlighted" : ""} ${inactive ? "is-inactive" : ""} ${d.condition ? "is-conditional" : ""}`,
        style: {
          stroke: touching
            ? "var(--color-primary-strong)"
            : "var(--color-line-strong)",
          strokeWidth: touching ? 2 : 1.6,
        },
        selectable: false,
        focusable: false,
        reconnectable: false,
      };
    });
  useEffect(() => {
    if (!selected) return;
    const node = nodes.find((n) => n.id === selected);
    if (!node) return;
    const zoom = Math.max(flow.getViewport().zoom, 0.85);
    void flow.setCenter(
      node.position.x + 98 + 180 / zoom,
      node.position.y + 60,
      { zoom, duration: 0 },
    );
  }, [selected]);
  const fit = () =>
    void flow.fitView({ padding: 0.08, maxZoom: 1, duration: 0 });
  return (
    <div
      className="wf-canvas"
      role="region"
      aria-label="Sơ đồ quy trình chỉ xem"
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.target !== event.currentTarget) return;
        const movement: Record<string, [number, number]> = {
          ArrowLeft: [80, 0],
          ArrowRight: [-80, 0],
          ArrowUp: [0, 80],
          ArrowDown: [0, -80],
        };
        if (movement[event.key]) {
          event.preventDefault();
          const [x, y] = movement[event.key];
          void flow.setViewport({
            ...viewport,
            x: viewport.x + x,
            y: viewport.y + y,
          });
        }
        if (event.key.toLowerCase() === "f") {
          event.preventDefault();
          fit();
        }
      }}
    >
      <ReactFlow<FlowNode>
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeClick={(_event, node) => onSelect(node.id)}
        fitView
        fitViewOptions={{ padding: 0.08, maxZoom: 1 }}
        minZoom={0.15}
        maxZoom={1.6}
        nodesDraggable={false}
        nodesConnectable={false}
        nodesFocusable={false}
        edgesFocusable={false}
        edgesReconnectable={false}
        elementsSelectable={false}
        deleteKeyCode={null}
        selectionKeyCode={null}
        multiSelectionKeyCode={null}
        zoomOnDoubleClick={false}
        zoomOnScroll={false}
        panOnScroll={false}
        zoomOnPinch
        panOnDrag
        ariaLabelConfig={{
          "node.a11yDescription.default":
            "Chỉ xem quy trình; chọn một bước để mở chi tiết.",
        }}
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={20}
          size={1}
          color="var(--color-line-strong)"
        />
        {view === "all" && (
          <MiniMap
            ariaLabel="Bản đồ toàn quy trình"
            nodeColor="var(--color-lavender)"
            nodeStrokeColor="var(--color-ink-450)"
            pannable
            zoomable
          />
        )}
      </ReactFlow>
      <div className="wf-canvas-context">
        <span className="wf-context-mark" />
        <div>
          <strong>
            {view === "all"
              ? "Toàn quy trình"
              : phases.find((p) => p.id === view)?.label}
          </strong>
          <span>
            {visible.length} bước · {edges.length} liên kết
            {view === "all"
              ? " · Tổng quan, phóng to để đọc"
              : " · Xem các bước liên quan trong phần chi tiết"}
          </span>
        </div>
      </div>
      <div className="wf-canvas-controls" aria-label="Điều khiển sơ đồ">
        <button
          aria-label="Thu nhỏ quy trình"
          disabled={viewport.zoom <= 0.151}
          onClick={() => void flow.zoomOut({ duration: 0 })}
        >
          −
        </button>
        <output aria-label="Mức phóng to">
          {Math.round(viewport.zoom * 100)}%
        </output>
        <button
          aria-label="Phóng to quy trình"
          disabled={viewport.zoom >= 1.599}
          onClick={() => void flow.zoomIn({ duration: 0 })}
        >
          +
        </button>
        <span className="wf-control-divider" />
        <button onClick={fit} aria-label="Vừa khung">
          Vừa khung <span aria-hidden="true">⌗</span>
        </button>
      </div>
      <span className="wf-canvas-hint">
        Kéo để di chuyển · Dùng + / − để thu phóng · Khi chọn sơ đồ: ↑↓←→ để di
        chuyển, F để vừa khung
      </span>
    </div>
  );
}
function References({
  items,
  empty,
}: {
  items: ArtifactReference[];
  empty: string;
}) {
  return items.length ? (
    <ul className="wf-artifacts">
      {items.map((item) => (
        <li key={item.artifactId}>
          <strong>{artifactTypeLabel(item.type)}</strong>
          <code>{item.artifactId}</code>
          <span>
            v{item.version} ·{" "}
            {item.validation === "VALID"
              ? "Hợp lệ (mô phỏng)"
              : "Hợp lệ, có cảnh báo (mô phỏng)"}
          </span>
        </li>
      ))}
    </ul>
  ) : (
    <p className="wf-empty-detail">{empty}</p>
  );
}
function Inspector({
  snapshot,
  nodeId,
  onClose,
  onSelect,
}: {
  snapshot: Snapshot;
  nodeId: string;
  onClose: () => void;
  onSelect: (id: string) => void;
}) {
  const n = topology.find((n) => n.id === nodeId)!;
  const state = snapshot.states[nodeId];
  const panel = useRef<HTMLElement>(null);
  useEffect(() => {
    panel.current?.focus({ preventScroll: true });
  }, [nodeId]);
  const connections = dependencies.filter(
    (d) => d.from === nodeId || d.to === nodeId,
  );
  return (
    <aside
      ref={panel}
      tabIndex={-1}
      className="wf-inspector"
      aria-label={`Chi tiết bước ${n.title}`}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.stopPropagation();
          onClose();
        }
      }}
    >
      <header>
        <div>
          <span className="wf-eyebrow">CHI TIẾT BƯỚC XỬ LÝ</span>
          <h3>{n.title}</h3>
        </div>
        <button aria-label="Đóng chi tiết bước" onClick={onClose}>
          <Icon name="close" size={18} />
        </button>
      </header>
      <div className="wf-inspector-body">
        <Status state={state} />
        <p className="wf-description">{n.description}</p>
        <dl className="wf-node-meta">
          <div>
            <dt>Trạng thái xử lý</dt>
            <dd>
              {state.status
                ? statusLabel(state.status)
                : "Không có trạng thái xử lý"}
            </dd>
          </div>
          <div>
            <dt>Có áp dụng không?</dt>
            <dd>
              {state.applicability === "undetermined"
                ? "Chưa xác định trong kịch bản"
                : state.applicability === "not-applicable"
                  ? "Không áp dụng trong tình huống này"
                  : "Áp dụng trong kịch bản"}
            </dd>
          </div>
          <div>
            <dt>Kiểm tra dữ liệu</dt>
            <dd>
              {state.outputs.length
                ? "Đã kiểm tra · mô phỏng"
                : "Chưa có kết quả được kiểm tra"}
            </dd>
          </div>
        </dl>
        {state.blocker && (
          <div
            className={`wf-blocker ${state.status === "FAILED_SAFE" ? "is-failed" : ""}`}
          >
            <strong>
              {state.status === "FAILED_SAFE" ? "Lý do dừng xử lý" : "Đang chờ"}
            </strong>
            <p>{state.blocker}</p>
          </div>
        )}
        {state.pending && (
          <section>
            <h4>Việc đang chờ xử lý</h4>
            <code>{state.pending.requestId}</code>
            <p>{workflowDetailLabel(state.pending.action)}</p>
            {state.pending.subject && (
              <p className="wf-binding">
                Kết quả cần xem xét: {state.pending.subject.artifactId} · v
                {state.pending.subject.version}
              </p>
            )}
            <small>Chỉ xem thông tin tại đây, chưa xử lý yêu cầu.</small>
          </section>
        )}
        <section>
          <h4>
            Dữ liệu đầu vào <span>{state.inputs.length}</span>
          </h4>
          <References
            items={state.inputs}
            empty="Chưa có dữ liệu đầu vào để hiển thị."
          />
        </section>
        <section>
          <h4>
            Kết quả đầu ra <span>{state.outputs.length}</span>
          </h4>
          <References
            items={state.outputs}
            empty={
              n.kind === "gate"
                ? "Bước phê duyệt không tạo kết quả đánh giá mới."
                : "Chưa có kết quả được chấp nhận."
            }
          />
        </section>
        <section>
          <h4>Dữ liệu tham chiếu</h4>
          {state.evidence.length ? (
            state.evidence.map((e) => (
              <p key={e.reference}>
                <strong>{e.label}</strong>
                <code>{e.reference}</code>
              </p>
            ))
          ) : (
            <p className="wf-empty-detail">
              Bước này chưa có dữ liệu tham chiếu.
            </p>
          )}
          <small>
            Nguồn gốc dữ liệu đang được mô phỏng, chưa đối chiếu từng bản ghi
            thực tế.
          </small>
        </section>
        <section>
          <h4>Sự kiện liên quan</h4>
          {state.events.length ? (
            <ol className="wf-events">
              {state.events.map((e, index) => (
                <li key={e.code}>
                  <span>{index + 1}</span>
                  <div>
                    <strong>{e.label}</strong>
                    <code>{e.code}</code>
                  </div>
                </li>
              ))}
            </ol>
          ) : (
            <p className="wf-empty-detail">Chưa có sự kiện để hiển thị.</p>
          )}
          <small>Chưa có thời điểm hoặc thời gian xử lý thực tế.</small>
        </section>
        <section>
          <h4>Các bước liên quan và điều kiện</h4>
          <ul className="wf-connections">
            {connections.map((d) => {
              const other = d.to === nodeId ? d.from : d.to;
              return (
                <li key={`${d.from}:${d.to}`}>
                  <button onClick={() => onSelect(other)}>
                    {d.to === nodeId ? "←" : "→"}{" "}
                    {topology.find((t) => t.id === other)!.title}
                  </button>
                  {d.condition && (
                    <span>{workflowDetailLabel(d.condition)}</span>
                  )}
                </li>
              );
            })}
          </ul>
          <small>
            Mũi tên thể hiện thứ tự xử lý. Dữ liệu đầu vào có thể đến từ nhiều
            bước.
          </small>
        </section>
        <details className="wf-source">
          <summary>Mã bước để tra cứu</summary>
          <code>{n.sourceNode}</code>
          {["PRECHECK_GATE", "EXTERNAL_GATE"].includes(n.id) && (
            <p>Đây là bước phê duyệt trong quy trình.</p>
          )}
        </details>
      </div>
    </aside>
  );
}
export default function WorkflowViewer({
  contract,
  route,
}: {
  contract: PreviewContract;
  route: PreviewRoute;
}) {
  const scenario = isScenario(route.workflowScenario)
    ? route.workflowScenario
    : defaultScenario(contract.businessStatus);
  const snapshot = useMemo(
    () => workflowFixture(scenario, contract.id),
    [scenario, contract.id],
  );
  const view: View =
    route.workflowPhase === "all" ||
    phases.some((p) => p.id === route.workflowPhase)
      ? (route.workflowPhase as View)
      : snapshot.scenario.phase;
  const [selected, setSelected] = useState<string | null>(null);
  const [display, setDisplay] = useState<"canvas" | "list">("canvas");
  const trigger = useRef<HTMLElement | null>(null);
  const triggerNode = useRef<string | null>(null);
  const select = (id: string) => {
    trigger.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    triggerNode.current = id;
    setSelected(id);
  };
  const close = () => {
    setSelected(null);
    // React Flow can replace its node DOM when controlled selection changes.
    // Restore to the current visible control, after that commit, rather than a stale element.
    requestAnimationFrame(() =>
      requestAnimationFrame(() => {
        const target = Array.from(
          document.querySelectorAll<HTMLButtonElement>("[data-wf-select]"),
        ).find(
          (button) =>
            button.dataset.wfSelect === triggerNode.current &&
            button.getClientRects().length > 0,
        );
        (
          target ??
          (trigger.current?.isConnected
            ? trigger.current
            : document.querySelector<HTMLElement>(".wf-canvas"))
        )?.focus({ preventScroll: true });
      }),
    );
  };
  useEffect(() => {
    setSelected(null);
  }, [scenario, contract.id, view]);
  const update = (newScenario: string, newView: string) =>
    navigatePreview(
      `/contracts/${contract.id}?view=workflow&scenario=${newScenario}&phase=${newView}`,
    );
  if (!contract.runId)
    return (
      <section className="wf-no-run">
        <Icon name="operations" size={28} />
        <h2>Chưa có lần xử lý</h2>
        <p>Hợp đồng này chưa có lần xử lý để hiển thị.</p>
        <SourceNote>Dữ liệu mô phỏng</SourceNote>
      </section>
    );
  const visible = topology.filter((n) => view === "all" || n.phase === view);
  const completed = topology.filter(
    (n) => snapshot.states[n.id].status === "COMPLETED",
  ).length;
  const current = topology.find((n) => n.id === snapshot.current)!;
  return (
    <section className="wf-viewer" aria-label="Quy trình xử lý">
      <div className="wf-heading">
        <div>
          <h2>Quy trình xử lý</h2>
          <p>Theo dõi các bước xử lý, kết quả và việc đang chờ quyết định.</p>
        </div>
        {previewTestingEnabled() && (
          <label className="wf-scenario">
            <span>Tình huống mô phỏng</span>
            <select
              aria-label="Kịch bản quy trình"
              value={scenario}
              onChange={(e) =>
                update(
                  e.target.value,
                  scenarios.find((s) => s.id === e.target.value)!.phase,
                )
              }
            >
              {scenarios.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      <div className="wf-run-summary" role="status">
        <span
          className={`wf-run-mark ${snapshot.completed ? "is-complete" : ""}`}
        >
          <Icon
            name={
              snapshot.completed
                ? "check"
                : snapshot.states[snapshot.current].status === "FAILED_SAFE"
                  ? "failure"
                  : "operations"
            }
            size={19}
          />
        </span>
        <div>
          <strong>
            {snapshot.completed
              ? "Đã xử lý xong · Chưa có quyết định được phê duyệt"
              : `${statusPresentation(snapshot.states[snapshot.current]).label} · ${current.title}`}
          </strong>
          <p>{snapshot.scenario.description}</p>
        </div>
        <span className="wf-run-count">
          {completed}
          <small>bước hoàn tất</small>
        </span>
      </div>
      <p className="wf-fixture-note">
        <span>QUY TRÌNH MÔ PHỎNG · CHỈ XEM</span> Lần xử lý: {snapshot.runId}.
        Thông tin tại đây không thay đổi quyết định của hợp đồng.
      </p>
      <div className="wf-toolbar">
        <nav aria-label="Vùng xem quy trình">
          <button
            aria-current={view === "all" ? "true" : undefined}
            onClick={() => update(scenario, "all")}
          >
            Toàn quy trình
          </button>
          {phases.map((p) => (
            <button
              key={p.id}
              aria-current={view === p.id ? "true" : undefined}
              onClick={() => update(scenario, p.id)}
            >
              {p.label}
            </button>
          ))}
        </nav>
        <div className="wf-display-switch" aria-label="Cách xem">
          <button
            aria-pressed={display === "canvas"}
            onClick={() => setDisplay("canvas")}
          >
            Sơ đồ
          </button>
          <button
            aria-pressed={display === "list"}
            onClick={() => setDisplay("list")}
          >
            Danh sách
          </button>
        </div>
      </div>
      <div className={`wf-workspace ${selected ? "has-inspector" : ""}`}>
        <div
          className={`wf-desktop-canvas ${display === "list" ? "is-hidden" : ""}`}
        >
          <ReactFlowProvider key={`${scenario}:${view}`}>
            <Canvas
              snapshot={snapshot}
              view={view}
              selected={selected}
              onSelect={select}
            />
          </ReactFlowProvider>
        </div>
        <div className={`wf-list ${display === "list" ? "is-visible" : ""}`}>
          <p className="wf-mobile-note">
            Chọn một bước để xem dữ liệu, kết quả và các bước liên quan.
          </p>
          <ol>
            {visible.map((n) => (
              <li key={n.id}>
                <button
                  data-wf-select={n.id}
                  onClick={() => select(n.id)}
                  aria-pressed={selected === n.id}
                >
                  <span className="wf-list-icon">
                    <Icon
                      name={n.kind === "gate" ? "approval" : "operations"}
                    />
                  </span>
                  <span>
                    <strong>{n.title}</strong>
                    <small>{phases.find((p) => p.id === n.phase)?.label}</small>
                    <Status state={snapshot.states[n.id]} />
                  </span>
                  <Icon size={14} />
                </button>
              </li>
            ))}
          </ol>
        </div>
        {selected && (
          <Inspector
            snapshot={snapshot}
            nodeId={selected}
            onClose={close}
            onSelect={select}
          />
        )}
      </div>
      <div className="wf-legend" aria-label="Chú giải trạng thái">
        {[
          { text: "Hoàn tất", tone: "complete" },
          { text: "Đang chạy", tone: "running" },
          { text: "Đang chờ", tone: "waiting" },
          { text: "Đã dừng xử lý", tone: "failed" },
          { text: "Chưa bắt đầu / không áp dụng", tone: "neutral" },
        ].map((l) => (
          <span key={l.tone}>
            <i className={`is-${l.tone}`} />
            {l.text}
          </span>
        ))}
        <span className="wf-edge-legend">
          ── Thứ tự xử lý <span>┄┄ Có điều kiện</span>
        </span>
      </div>
      <details className="wf-limitations">
        <summary>Cách đọc quy trình</summary>
        <p>
          {view === "all"
            ? "Sơ đồ thể hiện các bước đánh giá, xử lý và phê duyệt."
            : phases.find((p) => p.id === view)?.description}{" "}
          Chi tiết từng bước cho biết cả các bước liên quan ngoài vùng đang xem.
        </p>
        <p>
          Bước chưa xác định có áp dụng hay không được ghi rõ. Không áp dụng
          khác với chưa bắt đầu xử lý.
        </p>
        <p>
          Các kết quả đang được mô phỏng. Hoàn tất xử lý chưa có nghĩa hợp đồng
          an toàn hoặc đã được phê duyệt. Kiểm tra sơ bộ chưa phải chấp thuận
          của ngân hàng. Chưa gửi hồ sơ ra ngoài.
        </p>
      </details>
    </section>
  );
}
