import { afterEach, describe, expect, it, vi } from "vitest";

import { startCaseWorkflow } from "./client";
import { createRunRequestId } from "./runRequestId";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("startCaseWorkflow", () => {
  it("sends the client evaluation-cycle id in the workflow start payload", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          workflow_run_id: "CWF-NEW",
          evaluation_case_id: "CASE-1",
          contract_id: "CON-004",
          execution_status: "RUNNING",
          current_stage: "PLANNER_INTAKE",
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await startCaseWorkflow("CON-004", "UI-CYCLE-004-02");

    expect(fetchMock).toHaveBeenCalledOnce();
    const [path, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/cases/run");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({
      contract_id: "CON-004",
      evaluation_scope: ["FINANCE", "OPERATIONS", "RISK"],
      run_request_id: "UI-CYCLE-004-02",
    });
  });
});

describe("createRunRequestId", () => {
  it("creates a distinct opaque id for each explicit evaluation cycle", () => {
    const first = createRunRequestId();
    const second = createRunRequestId();

    expect(first).toMatch(/^UI-[A-Za-z0-9-]+$/);
    expect(second).toMatch(/^UI-[A-Za-z0-9-]+$/);
    expect(second).not.toBe(first);
  });
});
