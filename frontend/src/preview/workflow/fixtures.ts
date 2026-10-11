import { dependencies, topology, type Phase } from "./topology";

/** Only UI fixtures. Never imported by a connected feature or an API client. */
export type ExecutionStatus =
  | "PENDING"
  | "RUNNING"
  | "WAITING_FOR_DEPENDENCIES"
  | "WAITING_FOR_INPUT"
  | "WAITING_FOR_APPROVAL"
  | "COMPLETED"
  | "FAILED_SAFE";
export type Applicability = "applicable" | "not-applicable" | "undetermined";
export interface ArtifactReference {
  artifactId: string;
  type: string;
  version: number;
  validation: "VALID" | "VALID_WITH_WARNINGS";
}
export interface NodeSnapshot {
  status: ExecutionStatus | null;
  applicability: Applicability;
  inputs: ArtifactReference[];
  outputs: ArtifactReference[];
  evidence: { label: string; reference: string }[];
  events: { label: string; code: string }[];
  blocker?: string;
  pending?: { requestId: string; action: string; subject?: ArtifactReference };
}
export const scenarios = [
  {
    id: "approval",
    label: "Chờ duyệt Decision Card",
    phase: "decision",
    description:
      "Nhánh trực tiếp đã tạo Card. Dừng tại gate xác nhận cuối; chưa ghi quyết định.",
  },
  {
    id: "assessment",
    label: "Đánh giá song song",
    phase: "assessment",
    description:
      "Finance đang chạy, Operations hoàn tất. Risk còn chờ FinanceFacts.",
  },
  {
    id: "banking",
    label: "Chờ duyệt precheck",
    phase: "banking",
    description:
      "Route cần Banking, proposal sẵn sàng. Precheck chưa được thực thi.",
  },
  {
    id: "document",
    label: "Document · Chờ dữ liệu",
    phase: "banking",
    description:
      "Precheck mô phỏng đã có authorization minh họa và conditional options. Document cần bổ sung.",
  },
  {
    id: "input",
    label: "Intake · Chờ dữ liệu",
    phase: "assessment",
    description:
      "Planner tạm dừng trước đánh giá. Chưa biết applicability của nhánh Banking.",
  },
  {
    id: "failed",
    label: "Failed-safe",
    phase: "decision",
    description:
      "Hồ sơ nội bộ sẵn sàng, Final Risk dừng an toàn. Chưa tạo Card hay approval request.",
  },
  {
    id: "completed",
    label: "Hoàn tất · NOT_EVALUABLE",
    phase: "decision",
    description:
      "Lượt xử lý kết thúc tại Card NOT_EVALUABLE. Không có đề xuất để phê duyệt; không đồng nghĩa chấp nhận hợp đồng.",
  },
  {
    id: "negotiation",
    label: "Chờ kết quả đàm phán",
    phase: "followup",
    description:
      "Ví dụ riêng: Card có điều kiện đã được xác nhận; đang chờ kết quả khớp Card. Không gửi điều khoản từ viewer.",
  },
  {
    id: "release",
    label: "Chờ gate chia sẻ hồ sơ",
    phase: "followup",
    description:
      "Ví dụ riêng: đã xác nhận quyết định nhưng chưa được phép chia sẻ. External release chưa xảy ra.",
  },
] as const satisfies readonly {
  id: string;
  label: string;
  phase: Phase;
  description: string;
}[];
export type ScenarioId = (typeof scenarios)[number]["id"];
export const isScenario = (value: string | undefined): value is ScenarioId =>
  scenarios.some((s) => s.id === value);
export const defaultScenario = (status: string): ScenarioId =>
  status === "WAITING_FOR_INPUT"
    ? "input"
    : status === "FAILED_SAFE"
      ? "failed"
      : status === "NOT_EVALUABLE"
        ? "completed"
        : "approval";
const initial = topology
  .filter((n) => n.phase === "assessment")
  .map((n) => n.id);
const bank = topology.filter((n) => n.phase === "banking").map((n) => n.id);
const decision = topology
  .filter((n) => n.phase === "decision")
  .map((n) => n.id);
const done = (status: ExecutionStatus | null) => status === "COMPLETED";
export function workflowFixture(scenario: ScenarioId, contractId: string) {
  const scenarioInfo = scenarios.find((s) => s.id === scenario)!;
  const states: Record<string, NodeSnapshot> = Object.fromEntries(
    topology.map((n) => [
      n.id,
      {
        status: "PENDING",
        applicability: "undetermined",
        inputs: [],
        outputs: [],
        evidence: [],
        events: [],
      } satisfies NodeSnapshot,
    ]),
  );
  const complete = (ids: readonly string[]) =>
    ids.forEach((id) => {
      states[id].status = "COMPLETED";
      states[id].applicability = "applicable";
    });
  const exclude = (ids: readonly string[]) =>
    ids.forEach((id) => {
      states[id].status = null;
      states[id].applicability = "not-applicable";
    });
  const active = (id: string, status: ExecutionStatus) => {
    states[id].status = status;
    states[id].applicability = "applicable";
  };
  let current: string;
  if (scenario === "input") {
    current = "PLANNER_INTAKE";
    active(current, "WAITING_FOR_INPUT");
    states[current].blocker =
      "Thiếu dữ liệu intake cần thiết. Không suy quan hệ giữa hợp đồng và đơn hàng.";
    states[current].pending = {
      requestId: `UI-WF-INPUT-${contractId}`,
      action: "Bổ sung intake qua workflow hiện có",
    };
  } else if (scenario === "assessment") {
    complete(initial.slice(0, 2));
    complete(["OPERATIONS_ASSESSMENT"]);
    current = "FINANCE_ASSESSMENT";
    active(current, "RUNNING");
    active("INITIAL_RISK_FINALIZATION", "WAITING_FOR_DEPENDENCIES");
    states.INITIAL_RISK_FINALIZATION.blocker =
      "Đợi FinanceFacts. OperationsFacts đã sẵn sàng.";
  } else {
    complete(initial);
    const usesBank = ["banking", "document", "release"].includes(scenario);
    if (usesBank) {
      complete(bank.slice(0, 5));
      active("PRECHECK_GATE", "WAITING_FOR_APPROVAL");
      bank.slice(6).forEach((id) => {
        states[id].applicability = "undetermined";
      });
    } else exclude(bank);
    if (scenario === "banking") {
      current = "PRECHECK_GATE";
      states[current].blocker =
        "Chờ authorization cho proposal precheck hiện hành. Chưa chạy precheck.";
      states[current].pending = {
        requestId: `UI-WF-PRECHECK-${contractId}`,
        action: "SUBMIT_BANKING_PRECHECK",
      };
    } else if (scenario === "document") {
      complete(bank.slice(0, -1));
      current = "DOCUMENT_PREPARATION";
      active(current, "WAITING_FOR_INPUT");
      states[current].blocker =
        "Thiếu thành phần hồ sơ được yêu cầu. Không tự tạo hoặc gửi tài liệu.";
      states[current].pending = {
        requestId: `UI-WF-DOCUMENT-${contractId}`,
        action: "Bổ sung hồ sơ qua Document input flow",
      };
    } else {
      if (usesBank) complete(bank);
      complete(["INTERNAL_DECISION_PACKAGE_ASSEMBLY"]);
      if (scenario === "failed") {
        current = "FINAL_RISK_CHECK";
        active(current, "FAILED_SAFE");
        states[current].blocker =
          "Minh họa: output Final Risk không khớp exact Internal Decision Package input. Workflow dừng an toàn; chưa có output được chấp nhận.";
      } else {
        complete(decision.slice(0, 3));
        if (scenario === "completed") {
          current = "DECISION_CARD_COMPOSITION";
          exclude([
            "FINAL_DECISION_APPROVAL",
            ...topology.filter((n) => n.phase === "followup").map((n) => n.id),
          ]);
        } else if (scenario === "approval") {
          current = "FINAL_DECISION_APPROVAL";
          active(current, "WAITING_FOR_APPROVAL");
          states[current].blocker =
            "Chờ Founder xác nhận đúng Card v1. Xem workflow không phê duyệt hoặc resume.";
          states[current].pending = {
            requestId: `UI-WF-DECISION-${contractId}`,
            action: "CONFIRM_FINAL_CONTRACT_DECISION",
          };
        } else {
          complete(["FINAL_DECISION_APPROVAL", "POST_DECISION_UPDATE"]);
          if (scenario === "negotiation") {
            complete(["NEGOTIATION_TERMS_SENT"]);
            current = "NEGOTIATION_OUTCOME_RECEIVED";
            active(current, "WAITING_FOR_INPUT");
            states[current].pending = {
              requestId: `UI-WF-NEGOTIATION-${contractId}`,
              action: "Ghi nhận NegotiationOutcome khớp Card",
            };
            states[current].blocker =
              "Đang chờ kết quả đàm phán. Gate xác nhận kết quả là một bước riêng.";
          } else {
            exclude([
              "NEGOTIATION_TERMS_SENT",
              "NEGOTIATION_OUTCOME_RECEIVED",
              "NEGOTIATION_FINAL_CONFIRMATION",
            ]);
            complete(["EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL"]);
            current = "EXTERNAL_GATE";
            active(current, "WAITING_FOR_APPROVAL");
            states[current].pending = {
              requestId: `UI-WF-RELEASE-${contractId}`,
              action: "SEND_DOCUMENT_TO_EXTERNAL_PARTNER",
            };
            states[current].blocker =
              "Chờ authorization riêng. external_submission_performed = false; chưa có biên nhận.";
          }
        }
      }
    }
  }
  const runId = `UI-WF-${contractId}-${scenario.toUpperCase()}`;
  // References are deliberately synthetic and scenario-scoped, never full backend envelopes.
  for (const n of topology) {
    const state = states[n.id];
    if (done(state.status)) {
      state.outputs = n.outputs.map((type) => ({
        type,
        artifactId: `${runId}-${type}`,
        version: 1,
        validation: "VALID",
      }));
      if (state.outputs.length)
        state.evidence = [
          {
            label: "Lineage artifact minh họa",
            reference: `${runId} / ${n.sourceNode}`,
          },
        ];
    }
    if (state.status !== null && state.status !== "PENDING") {
      state.inputs = dependencies
        .filter((d) => d.to === n.id)
        .flatMap((d) => states[d.from].outputs);
      state.events =
        n.kind === "gate"
          ? [
              {
                label: done(state.status)
                  ? "Authorization minh họa đã ghi nhận"
                  : "Chờ Governance xử lý",
                code: done(state.status)
                  ? "PROTECTED_ACTION_AUTHORIZED"
                  : "WORKFLOW_WAITING_FOR_APPROVAL",
              },
            ]
          : [
              { label: "Bắt đầu node", code: "NODE_STARTED" },
              ...(done(state.status)
                ? [{ label: "Hoàn tất node", code: "NODE_COMPLETED" }]
                : state.status === "FAILED_SAFE"
                  ? [{ label: "Dừng an toàn", code: "NODE_FAILED_SAFE" }]
                  : state.status !== "RUNNING"
                    ? [{ label: "Node đang chờ", code: "NODE_WAITING" }]
                    : []),
            ];
    }
  }
  // Selected artifact references, not inferred solely from control-flow arrows.
  // Assembly's allowlist follows _internal_decision_source_artifacts.
  const packageTypes = new Set([
    "EVALUATION_CASE",
    "FINANCE_FACTS",
    "FINANCE_ASSESSMENT",
    "OPERATIONS_FACTS",
    "OPERATIONS_ASSESSMENT",
    "INITIAL_RISK_ASSESSMENT",
    "APPROVAL_CHECKPOINTS",
    "DECISION_ROUTE_PLAN",
    "BANKING_DISCOVERY_REQUEST",
    "BANKING_OPTION_MATRIX",
    "BANKING_DISCOVERY_RESULT",
    "BANKING_PRECHECK_READINESS",
    "DECISION_POST_BANKING_REVIEW",
    "BANKING_PRECHECK_SUBMISSION_PROPOSAL",
    "BANKING_PRECHECK_RESULT_SET",
    "DECISION_POST_PRECHECK_REVIEW",
    "DOCUMENT_PREPARATION_REQUEST",
    "DOCUMENT_RELEASE_PACKAGE",
  ]);
  const packageState = states.INTERNAL_DECISION_PACKAGE_ASSEMBLY;
  if (done(packageState.status))
    packageState.inputs = topology
      .filter((n) => n.phase === "assessment" || n.phase === "banking")
      .flatMap((n) => states[n.id].outputs)
      .filter((ref) => packageTypes.has(ref.type));
  for (const [id, types] of [
    ["FINANCE_ASSESSMENT", ["EVALUATION_CASE"]],
    ["OPERATIONS_ASSESSMENT", ["EVALUATION_CASE"]],
    [
      "INITIAL_RISK_FINALIZATION",
      ["EVALUATION_CASE", "RISK_PRE_SCAN", "FINANCE_FACTS", "OPERATIONS_FACTS"],
    ],
    ["FINAL_DECISION_APPROVAL", ["DECISION_CARD"]],
    ["POST_DECISION_UPDATE", ["DECISION_CARD"]],
    ["NEGOTIATION_TERMS_SENT", ["DECISION_CARD"]],
    ["NEGOTIATION_OUTCOME_RECEIVED", ["DECISION_CARD"]],
  ] as const) {
    if (states[id].status !== null && states[id].status !== "PENDING")
      states[id].inputs = topology
        .flatMap((n) => states[n.id].outputs)
        .filter((ref) => (types as readonly string[]).includes(ref.type));
  }
  const cardOutputs = states.DECISION_CARD_COMPOSITION.outputs;
  if (states.FINAL_DECISION_APPROVAL.pending)
    states.FINAL_DECISION_APPROVAL.pending.subject = cardOutputs.find(
      (a) => a.type === "DECISION_CARD",
    );
  if (states.PRECHECK_GATE.pending)
    states.PRECHECK_GATE.pending.subject =
      states.BANKING_PRECHECK_SUBMISSION_PROPOSAL.outputs[0];
  if (states.EXTERNAL_GATE.pending)
    states.EXTERNAL_GATE.pending.subject =
      states.EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL.outputs[0];
  return {
    runId,
    contractId,
    scenario: scenarioInfo,
    current,
    states,
    completed: scenario === "completed",
  };
}
export function statusPresentation(state: NodeSnapshot) {
  if (state.applicability === "not-applicable")
    return { label: "Không áp dụng", tone: "neutral", symbol: "−" };
  switch (state.status) {
    case "COMPLETED":
      return { label: "Hoàn tất", tone: "complete", symbol: "✓" };
    case "RUNNING":
      return { label: "Đang chạy", tone: "running", symbol: "◌" };
    case "WAITING_FOR_INPUT":
      return { label: "Chờ dữ liệu", tone: "waiting", symbol: "!" };
    case "WAITING_FOR_APPROVAL":
      return { label: "Chờ phê duyệt", tone: "waiting", symbol: "!" };
    case "WAITING_FOR_DEPENDENCIES":
      return { label: "Chờ dependencies", tone: "waiting", symbol: "·" };
    case "FAILED_SAFE":
      return { label: "Dừng an toàn", tone: "failed", symbol: "!" };
    default:
      return { label: "Chưa bắt đầu", tone: "neutral", symbol: "·" };
  }
}
