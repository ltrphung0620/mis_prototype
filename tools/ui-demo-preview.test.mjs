import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { createServer } from "node:net";
import { fileURLToPath } from "node:url";
import test from "node:test";

const script = fileURLToPath(new URL("./ui-demo-preview.mjs", import.meta.url));

test("fixture API is isolated and protected mutations are blocked", async () => {
  const reservation = createServer();
  reservation.listen(0, "127.0.0.1");
  await once(reservation, "listening");
  const port = reservation.address().port;
  await new Promise((resolve) => reservation.close(resolve));
  const child = spawn(process.execPath, [script], {
    env: { ...process.env, OPC_UI_PREVIEW_PORT: String(port) },
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });
  const closed = once(child, "close");
  try {
    await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error("Preview startup timed out")), 10000);
      child.on("error", (error) => { clearTimeout(timeout); reject(error); });
      child.on("exit", (code) => { clearTimeout(timeout); reject(new Error(`Preview exited: ${code}`)); });
      child.stdout.on("data", (data) => {
        if (data.toString().includes("UI DEMO")) { clearTimeout(timeout); resolve(); }
      });
    });
    const origin = `http://127.0.0.1:${port}`;
    const health = await fetch(origin + "/health");
    assert.equal(health.status, 200);
    assert.deepEqual(await health.json(), {
      status: "ok", mode: "UI_FIXTURE", forwards_api_to_backend: false,
    });
    const catalog = await fetch(origin + "/api/contracts");
    assert.equal(catalog.headers.get("X-OPC-UI-Fixture"), "true");
    assert.equal((await catalog.json()).dataset_id, "UI-REVIEW");
    const start = await fetch(origin + "/api/cases/run", { method: "POST" });
    assert.equal(start.status, 202);
    assert.equal((await start.json()).workflow_run_id, "UI-REVIEW-RUN");
    for (const path of [
      "/api/approval-requests/UI-APPROVAL/decision",
      "/api/cases/UI-REVIEW-CASE/documents/evidence-supplements",
      "/api/workflows/UI-REVIEW-RUN/resume",
    ]) {
      const blocked = await fetch(origin + path, { method: "POST", body: "{}" });
      assert.equal(blocked.status, 409);
    }
    assert.equal((await fetch(origin + "/api/unknown")).status, 409);
    const errorMode = await fetch(origin + "/api/contracts", {
      headers: { Cookie: "opc_ui_demo_mode=error" },
    });
    assert.equal(errorMode.status, 503);
    assert.equal((await fetch(origin + "/api/contracts")).status, 200);
  } finally {
    child.kill();
    await closed;
  }
});

test("preview refuses the actual backend/frontend ports", async () => {
  for (const port of ["8000", "5173", "invalid"]) {
    const child = spawn(process.execPath, [script], {
      env: { ...process.env, OPC_UI_PREVIEW_PORT: port },
      stdio: "ignore", windowsHide: true,
    });
    const [code] = await once(child, "close");
    assert.notEqual(code, 0);
  }
});
