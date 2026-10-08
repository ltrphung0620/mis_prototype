import { createServer, request as httpRequest } from "node:http";
import { connect } from "node:net";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

// Development-only fixture preview. Never forwards API requests to a real backend.
const previewPort = Number(process.env.OPC_UI_PREVIEW_PORT ?? "5174");
if (!Number.isInteger(previewPort) || previewPort < 1024 || previewPort > 65535 || previewPort === 5173 || previewPort === 8000) {
  throw new Error("OPC_UI_PREVIEW_PORT must be an available port in 1024..65535, excluding 5173/8000");
}
const previewOrigin = "http://127.0.0.1:" + previewPort;
const fixturePath = fileURLToPath(new URL("../output/playwright/mercury-review.js", import.meta.url));
const source = await readFile(fixturePath, "utf8");
const { default: installFixture } = await import("data:text/javascript;base64," + Buffer.from("export default " + source).toString("base64"));
let fixtureHandler;
const ready = new Error("FIXTURE_ROUTE_READY");
try {
  await installFixture({
    unrouteAll: async () => {},
    route: async (_predicate, handler) => { fixtureHandler = handler; },
    emulateMedia: async () => {},
    goto: async () => { throw ready; },
  });
} catch (error) {
  if (error !== ready) throw error;
}
if (!fixtureHandler) throw new Error("Existing fixture did not provide its route handler");

const labelScript = `<script type="module">
const label = () => {
  const badges = document.querySelector(".system-badges");
  if (badges && !document.getElementById("local-ui-demo-label")) {
    const badge = document.createElement("span");
    badge.id = "local-ui-demo-label";
    badge.textContent = "Dữ liệu minh họa · kiểm thử UI";
    badge.title = "Fixture UI: không phải kết quả backend thật; phê duyệt bị chặn.";
    badge.style.cssText = "padding:4px 8px;color:#595d9e;background:#f0f1fc;border-radius:4px;font-size:11px";
    badges.prepend(badge);
  }
};
let started = false;
const mode = new URL(location.href).searchParams.get("demo_api");
const observe = () => {
  label();
  if (started || mode === "error") return;
  const start = [...document.querySelectorAll("button")].find(button => button.textContent.includes("Bắt đầu đánh giá"));
  if (start && !start.disabled) { started = true; start.click(); }
};
new MutationObserver(observe).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["disabled"] });
observe();
</script>`;

function json(response, status, body) {
  response.writeHead(status, { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store", "X-OPC-UI-Fixture": "true" });
  response.end(JSON.stringify(body));
}

const server = createServer(async (incoming, outgoing) => {
  const url = new URL(incoming.url, previewOrigin);
  if (url.pathname === "/") { outgoing.writeHead(302, { Location: "/dashboard-assets/" }); outgoing.end(); return; }
  if (url.pathname === "/health") { json(outgoing, 200, { status: "ok", mode: "UI_FIXTURE", forwards_api_to_backend: false }); return; }
  if (url.pathname.startsWith("/api/")) {
    console.log(new Date().toISOString(), incoming.method, url.pathname, "[UI fixture]");
    // Never forward an API request or protected mutation to FastAPI.
    if (incoming.method !== "GET" && !(incoming.method === "POST" && url.pathname === "/api/cases/run")) {
      incoming.resume();
      json(outgoing, 409, { detail: "Bản demo UI chỉ đọc. Phê duyệt và các thao tác bảo vệ đã bị chặn; không gửi dữ liệu tới backend thật." });
      return;
    }
    incoming.resume();
    const mode = /opc_ui_demo_mode=(error|slow)/.exec(incoming.headers.cookie ?? "")?.[1];
    if (mode === "error") { json(outgoing, 503, { detail: "Lỗi API có chủ đích để kiểm thử UI demo. Mở URL demo bình thường để khôi phục." }); return; }
    await new Promise(resolve => setTimeout(resolve, mode === "slow" ? 1500 : 100));
    try {
      await fixtureHandler({
        request: () => ({ url: () => url.href }),
        fulfill: async ({ status = 200, json: body }) => json(outgoing, status, body),
      });
    } catch (error) { json(outgoing, 500, { detail: "UI fixture adapter failed" }); console.error(error.message); }
    return;
  }
  const upstream = httpRequest({
    hostname: "127.0.0.1", port: 5173, path: incoming.url, method: incoming.method,
    headers: { ...incoming.headers, host: "127.0.0.1:5173", "accept-encoding": "identity" },
  }, response => {
    if (String(response.headers["content-type"]).includes("text/html")) {
      const chunks = [];
      response.on("data", chunk => chunks.push(chunk));
      response.on("end", () => {
        const html = Buffer.concat(chunks).toString("utf8").replace("</body>", labelScript + "</body>");
        const headers = { ...response.headers };
        delete headers["content-length"]; delete headers.etag;
        const mode = ["slow", "error"].includes(url.searchParams.get("demo_api")) ? url.searchParams.get("demo_api") : "normal";
        headers["set-cookie"] = "opc_ui_demo_mode=" + mode + "; Path=/; SameSite=Lax";
        headers["cache-control"] = "no-store";
        outgoing.writeHead(response.statusCode ?? 200, headers); outgoing.end(html);
      });
    } else { outgoing.writeHead(response.statusCode ?? 200, response.headers); response.pipe(outgoing); }
  });
  upstream.on("error", () => json(outgoing, 502, { detail: "Vite dev server is unavailable" }));
  incoming.pipe(upstream);
});
server.on("upgrade", (incoming, client, head) => {
  if (new URL(incoming.url, previewOrigin).pathname.startsWith("/api/")) {
    client.destroy(); return;
  }
  const upstream = connect(5173, "127.0.0.1", () => {
    let headers = incoming.method + " " + incoming.url + " HTTP/" + incoming.httpVersion + "\r\n";
    for (let index = 0; index < incoming.rawHeaders.length; index += 2) headers += incoming.rawHeaders[index] + ": " + incoming.rawHeaders[index + 1] + "\r\n";
    upstream.write(headers + "\r\n");
    if (head.length) upstream.write(head);
    client.pipe(upstream); upstream.pipe(client);
  });
  upstream.on("error", () => client.destroy());
  client.on("error", () => upstream.destroy());
  client.on("close", () => upstream.destroy());
});
server.listen(previewPort, "127.0.0.1", () => {
  console.log("UI DEMO " + previewOrigin + "/dashboard-assets/");
  console.log("Existing fixture:", fixturePath);
  console.log("No API forwarding, no database, protected mutations return 409.");
});
