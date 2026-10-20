/// <reference types="node" />
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import WorkflowViewer from "./WorkflowViewer";
import { contracts } from "../fixtures";
import { parsePreviewRoute } from "../navigation";
import { dependencies, topology } from "./topology";
import { scenarios, workflowFixture } from "./fixtures";

const contract = contracts.find((c) => c.id === "CON-004")!;
function viewer(scenario = "approval") {
  return render(
    <WorkflowViewer
      contract={contract}
      route={{
        page: "contracts",
        view: "workflow",
        workflowScenario: scenario,
        workflowPhase: "all",
      }}
    />,
  );
}
beforeEach(() => {
  window.history.replaceState({}, "", "/?ui_test=1");
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.reject(new Error("No API in preview"))),
  );
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("orchestration-grounded workflow snapshots", () => {
  it("uses existing backend node, status and artifact identifiers without importing runtime code", () => {
    const nodeSource = readFileSync("../src/opc_mis/domain/workflow.py", "utf8");
    const enums = readFileSync("../src/opc_mis/domain/enums.py", "utf8");
    for (const node of topology) {
      expect(nodeSource).toMatch(new RegExp(`\\b${node.sourceNode}\\b`));
      for (const type of node.outputs) expect(enums).toContain(`"${type}"`);
    }
    for (const scenario of scenarios)
      for (const state of Object.values(
        workflowFixture(scenario.id, contract.id).states,
      ))
        if (state.status) expect(enums).toContain(`"${state.status}"`);
  });
  it("requires both parallel facts without inventing Finance → Operations ordering", () => {
    expect(dependencies).toContainEqual({
      from: "FINANCE_ASSESSMENT",
      to: "INITIAL_RISK_FINALIZATION",
      condition: undefined,
    });
    expect(dependencies).toContainEqual({
      from: "OPERATIONS_ASSESSMENT",
      to: "INITIAL_RISK_FINALIZATION",
      condition: undefined,
    });
    expect(
      dependencies.some(
        (e) =>
          e.from === "FINANCE_ASSESSMENT" && e.to === "OPERATIONS_ASSESSMENT",
      ),
    ).toBe(false);
    const run = workflowFixture("assessment", contract.id);
    expect(run.states.FINANCE_ASSESSMENT.status).toBe("RUNNING");
    expect(run.states.OPERATIONS_ASSESSMENT.status).toBe("COMPLETED");
    expect(run.states.INITIAL_RISK_FINALIZATION.status).toBe(
      "WAITING_FOR_DEPENDENCIES",
    );
    expect(run.states.FINANCE_ASSESSMENT.outputs).toEqual([]);
  });
  it("keeps control-flow references valid and acyclic", () => {
    const ids = topology.map((n) => n.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const edge of dependencies) {
      expect(ids).toContain(edge.from);
      expect(ids).toContain(edge.to);
    }
    const visiting = new Set<string>(),
      visited = new Set<string>();
    const visit = (id: string) => {
      expect(visiting.has(id)).toBe(false);
      if (visited.has(id)) return;
      visiting.add(id);
      dependencies.filter((e) => e.from === id).forEach((e) => visit(e.to));
      visiting.delete(id);
      visited.add(id);
    };
    ids.forEach(visit);
  });
  it.each(scenarios.map((s) => [s.id] as const))(
    "isolates %s identity and withholds non-completed outputs",
    (scenario) => {
      const run = workflowFixture(scenario, contract.id);
      for (const state of Object.values(run.states)) {
        if (state.status !== "COMPLETED") expect(state.outputs).toEqual([]);
        if (state.applicability === "not-applicable")
          expect(state.status).toBeNull();
        for (const ref of [...state.inputs, ...state.outputs])
          expect(ref.artifactId.startsWith(run.runId)).toBe(true);
      }
      expect(workflowFixture(scenario, "CON-002").runId).not.toBe(run.runId);
    },
  );
  it("does not equate NOT_EVALUABLE completion with approval", () => {
    const run = workflowFixture("completed", contract.id);
    expect(run.completed).toBe(true);
    expect(run.current).toBe("DECISION_CARD_COMPOSITION");
    expect(run.states.FINAL_DECISION_APPROVAL.applicability).toBe(
      "not-applicable",
    );
    expect(run.states.POST_DECISION_UPDATE.outputs).toEqual([]);
    expect(run.states.FINAL_DECISION_APPROVAL.pending).toBeUndefined();
  });
  it("binds each pending authorization to its own exact versioned subject", () => {
    for (const [scenario, id, type] of [
      ["approval", "FINAL_DECISION_APPROVAL", "DECISION_CARD"],
      ["banking", "PRECHECK_GATE", "BANKING_PRECHECK_SUBMISSION_PROPOSAL"],
      ["release", "EXTERNAL_GATE", "EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL"],
    ] as const) {
      const gate = workflowFixture(scenario, contract.id).states[id];
      expect(gate.pending?.subject?.type).toBe(type);
      expect(gate.pending?.subject?.version).toBe(1);
      expect(gate.status).toBe("WAITING_FOR_APPROVAL");
    }
    expect(
      workflowFixture("banking", contract.id).states.BANKING_PRECHECK_EXECUTION
        .outputs,
    ).toEqual([]);
    expect(
      workflowFixture("release", contract.id).states
        .READY_FOR_EXTERNAL_SUBMISSION.outputs,
    ).toEqual([]);
    expect(
      workflowFixture(
        "approval",
        contract.id,
      ).states.FINAL_DECISION_APPROVAL.inputs.map((ref) => ref.type),
    ).toEqual(["DECISION_CARD"]);
    expect(
      workflowFixture(
        "approval",
        contract.id,
      ).states.INTERNAL_DECISION_PACKAGE_ASSEMBLY.inputs.map((ref) => ref.type),
    ).not.toContain("PLANNER_RESULT");
  });
});

describe("read-only inspector and navigation", () => {
  it("hides scenario controls in the normal view while retaining the simulation notice", () => {
    window.history.replaceState({}, "", "/?preview=1");
    viewer();
    expect(screen.queryByRole("combobox", { name: "Kịch bản quy trình" })).not.toBeInTheDocument();
    expect(screen.getByText("QUY TRÌNH MÔ PHỎNG · CHỈ XEM")).toBeVisible();
    expect(fetch).not.toHaveBeenCalled();
  });
  it("opens inspection from keyboard-operable list controls, restores focus, and never calls API", () => {
    viewer();
    fireEvent.click(screen.getByRole("button", { name: "Danh sách" }));
    const listButton = screen
      .getAllByRole("button", { name: /Duyệt quyết định/ })
      .find((b) => b.closest(".wf-list"))!;
    listButton.focus();
    fireEvent.click(listButton);
    const inspector = screen.getByRole("complementary", {
      name: "Chi tiết bước Duyệt quyết định",
    });
    expect(inspector).toHaveFocus();
    expect(
      within(inspector).getByText("Xác nhận quyết định hợp đồng"),
    ).toBeInTheDocument();
    expect(
      within(inspector).getByText(/Kết quả cần xem xét:.*DECISION_CARD.*v1/),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Phê duyệt|Resume|Run node/ }),
    ).not.toBeInTheDocument();
    fireEvent.keyDown(inspector, { key: "Escape" });
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });
  it("exposes cross-phase dependencies without deriving them from events", () => {
    viewer("banking");
    fireEvent.click(screen.getByRole("button", { name: "Danh sách" }));
    const button = screen
      .getAllByRole("button", { name: /Duyệt kiểm tra sơ bộ/ })
      .find((b) => b.closest(".wf-list"))!;
    fireEvent.click(button);
    const panel = screen.getByRole("complementary");
    expect(within(panel).getByText("Không được chấp thuận")).toBeInTheDocument();
    fireEvent.click(
      within(panel).getByRole("button", { name: "→ Hồ sơ quyết định" }),
    );
    expect(
      screen.getByRole("complementary", {
        name: "Chi tiết bước Hồ sơ quyết định",
      }),
    ).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });
  it("handles invalid URL options safely and maintains scenario/phase on deep links", () => {
    const route = parsePreviewRoute(
      "#/contracts/CON-004?view=workflow&scenario=document&phase=banking",
    );
    expect(route.workflowScenario).toBe("document");
    expect(route.workflowPhase).toBe("banking");
    render(
      <WorkflowViewer
        contract={contract}
        route={{
          ...route,
          workflowScenario: "invalid",
          workflowPhase: "invalid",
        }}
      />,
    );
    expect(
      screen.getByRole("combobox", { name: "Kịch bản quy trình" }),
    ).toHaveValue("approval");
    expect(screen.getByRole("button", { name: "Quyết định" })).toHaveAttribute(
      "aria-current",
      "true",
    );
    fireEvent.change(
      screen.getByRole("combobox", { name: "Kịch bản quy trình" }),
      { target: { value: "document" } },
    );
    expect(window.location.hash).toBe(
      "#/contracts/CON-004?view=workflow&scenario=document&phase=banking",
    );
    expect(fetch).not.toHaveBeenCalled();
  });
  it("leaves contracts with no run empty rather than borrowing another run", () => {
    render(
      <WorkflowViewer
        contract={contracts.find((c) => !c.runId)!}
        route={{ page: "contracts", view: "workflow" }}
      />,
    );
    expect(
      screen.getByRole("heading", { name: "Chưa có lần xử lý" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("combobox", { name: "Kịch bản quy trình" }),
    ).not.toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });
  it("displays failure with no fabricated output or approval subject", () => {
    viewer("failed");
    fireEvent.click(screen.getByRole("button", { name: "Danh sách" }));
    fireEvent.click(
      screen
        .getAllByRole("button", { name: /Rủi ro · Kiểm tra cuối/ })
        .find((b) => b.closest(".wf-list"))!,
    );
    const panel = screen.getByRole("complementary");
    expect(within(panel).getByText("Trạng thái xử lý").closest("div")).toHaveTextContent("Đã dừng xử lý");
    expect(within(panel).getByText("Lý do dừng xử lý")).toBeInTheDocument();
    expect(
      within(panel).queryByText("Việc đang chờ xử lý"),
    ).not.toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });
});
