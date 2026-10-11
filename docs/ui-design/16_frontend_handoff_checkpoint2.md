# OPC MIS — Frontend/UI-First Handoff (sau Checkpoint 2)

> **Git handoff đã chuẩn bị local, 11/10/2026:** branch `codex/frontend-checkpoint2-handoff` giữ CP1 `0329574`; CP2 source ở `5d96f21`, evidence ở `7f97f56`, tài liệu trong commit docs tiếp theo của branch. Xem `git log -4 --oneline` để lấy SHA cuối. Chưa push/merge/tạo PR; branch chưa có remote upstream. Source/dependencies/bundle, fixture, 8 screenshots và reports được đóng gói; chỉ `workflow-interactions.js`/`workflow-review.js` cố ý giữ untracked local, không cần để chạy preview. 435 tracked temporary artifacts cũ không được cleanup trong UI handoff, cần sensitive-data review/PR riêng trước chia sẻ toàn repo.
>
> Các Git inventories/kết quả audit bên dưới là snapshot **trước commit**, không trạng thái working tree cuối. [Audit 17](17_git_handoff_readiness_audit.md) ghi nhóm commit, PR draft và cách nhận source sau khi owner cho phép publish. UI review CP2 và backend integration approval vẫn là các bước riêng.

> **Ngày audit trực tiếp:** 11/10/2026
>
> **Đối tượng nhận:** Thành viên tiếp quản phát triển OPC MIS
>
> **Source đã đối chiếu:** branch `main`, HEAD `03295747b7dafbe96f8eb9f6675683fe4bdc08c3` **cộng working tree chưa commit của Checkpoint 2**; routes, schemas, projection, orchestration, preview/connected frontend và tài liệu 13–15.
> **Trạng thái bàn giao:** Checkpoint 1/polish đã được Founder duyệt và commit ở `0329574`. Checkpoint 2 đã triển khai preview, **chờ Founder review**, chưa commit. Local tracking cho thấy `main` ahead `origin/main` 1 commit; chưa fetch/xác minh GitHub trong audit này. `git pull` không lấy được các files chưa commit.

> **Cập nhật Git readiness sau lần audit tài liệu:** đã fetch origin và chạy lại tests/build; phân loại files, ignore/security gaps, kế hoạch commits/PR và checklist nhận source ở [audit 17](17_git_handoff_readiness_audit.md). Git inventory/kết quả trong 16 giữ snapshot lần audit trước; dùng 17 cho quyết định đóng gói hiện tại.

## 0. Đọc nhanh — 5 điều quan trọng nhất

1. **UI-first preview đã triển khai hai checkpoint:** (1) Dashboard, Company Overview, Contracts; (2) read-only Workflow Viewer kiểu Dify. CP1 đã duyệt; CP2 còn chờ review. Các màn preview dùng **fixtures / dữ liệu minh họa**, không phải số liệu thực được tổng hợp từ backend.
2. **Frontend là React + TypeScript + Vite; backend thật là FastAPI/Python + SQLite.** Backend có workflow, assessment, Governance, artifacts và approvals cho từng case/run; **API company/executive tổng hợp và canonical workflow graph chưa được triển khai**. Ba trang global và canvas mới chỉ có ở preview, chưa tích hợp vào connected App.
3. **Không đánh đồng trạng thái nghiệp vụ:** assessment `completed` không có nghĩa rủi ro thấp; Decision Card là đề xuất, chưa phải Founder approval; bank precheck là mô phỏng; final approval **khác** external release; trạng thái sẵn sàng gửi **không phải** đã gửi.
4. **Kiểm tra chạy lại trong audit:** frontend 155/155 tests (25 files), TypeScript đạt; backend 481 passed/4 failed/1 warning, Ruff 2 lỗi `I001`. Vite build đạt và 46 browser checks đạt là kết quả **lần Checkpoint 2**, không chạy lại build/browser trong audit tài liệu. Xem mục 6 để biết phạm vi và failures.
5. **Ưu tiên tiếp quản:** có đủ working tree CP2 → nghiệm thu preview → mapping existing read APIs cho một exact run → review topology/data contracts trước live integration. Audit handoff không phải approval CP2 hoặc quyền sửa backend/push.

## 1. Bài toán sản phẩm và phạm vi

**OPC MIS** hỗ trợ Founder doanh nghiệp startup/SME xem tình hình công ty và đánh giá hợp đồng thông qua Finance, Operations, Risk, Banking/Document (khi áp dụng), Decision Card và các cổng Governance. Phần AI composition không thay thế deterministic rules, evidence validation hoặc quyết định của người có thẩm quyền.

**IA đã chốt:** *Executive Home + Drill-down*:

```text
OPC MIS
├── Dashboard /dashboard                  — Executive Home; action-first
├── Tình hình công ty /company            — company snapshot + phân tích
└── Hợp đồng /contracts                   — danh sách hợp đồng
    └── /contracts/:contractId             — Contract Decision Workspace
        ├── Tổng quan
        ├── Đánh giá
        ├── Workflow
        ├── Bằng chứng
        └── Lịch sử
```

Routing đã xác minh tại `frontend/src/main.tsx` và `frontend/src/preview/navigation.ts`: `?preview=1` **trước** `#` chọn preview entry; các paths trên là **hash routes**, không server routes mới. Company có `section=overview|finance|business|invoices|alerts`, `period`, `status`; contract có `view=overview|assessments|workflow|evidence|history`, optional `request`, `scenario`, `phase`. Workflow phase là `assessment|banking|decision|followup|all`. Reload/back/forward giữ hash route; state local của dialogs/filter không lưu URL sẽ reset. Connected App khi không có `preview=1` vẫn dùng local workspace views. FastAPI chỉ phục vụ bundle ở `/dashboard`, assets ở `/dashboard-assets`; chưa có global route fallback mới.

**Định hướng thiết kế:** Mercury-inspired (nền trắng/cool-neutral, màu periwinkle/lavender, chữ charcoal, border rất nhẹ, ít shadow); Linear tham khảo typography, hierarchy, navigation; Dify tham khảo workflow graph/canvas interaction. Không khôi phục theme forest/emerald cũ.

## 2. Hiện trạng đã bàn giao

| Phạm vi | Đã có trong UI-first preview | Chưa được chứng minh bằng preview |
|---|---|---|
| Dashboard | Action queue, hợp đồng cần chú ý, 3 KPI, cash-in/out chart, drill-down | Global live pending queue/aggregation API; dữ liệu công ty thực |
| Company Overview | 5 tabs, cashflow và các charts, filter/tooltip, source/coverage notes | Company read APIs/aggregation thực; reconciliation với workbook |
| Contracts | 5 contract fixtures, list/search/workflow filter/selector, row click và native link, source status riêng workflow status, assessments/evidence search/detail/review | Full persisted contract/run index cho dữ liệu thật; historical-run policy |
| Workflow Viewer | **27 nodes/checkpoints, 32 connections** trong fixture; zoom/pan/fit, selection/highlighting, inspector, keyboard, mobile list | Canonical topology + runtime states/artifacts/approval binding từ backend |
| Visual polish | Theme Mercury đồng nhất, responsive, navigation/CTA/labels | Screen-reader audit đầy đủ, mọi edge case nghiệp vụ thực |

**9 workflow scenarios có sẵn trong preview:** chờ duyệt Card; đánh giá song song; chờ duyệt precheck; Document chờ dữ liệu; intake thiếu dữ liệu; failed-safe; NOT_EVALUABLE hoàn tất; đàm phán; gate chia sẻ hồ sơ.

**Ranh giới demo đã xác minh:** Preview không import/call business API để thực thi; requests, artifacts, validation, evidence, events, blockers và charts là fixtures có nhãn. Review mock chỉ hiện notice local, không resolve request hoặc resume; nhãn `OPENAI` không chứng minh model đã chạy. `data.ts` là read-model context seam, chưa là API adapter. Inspector evidence là placeholder cấp artifact, chưa record-level `EvidenceRef` hay payload đầy đủ. Output refs chỉ xuất hiện ở completed nodes; gates không sinh business artifacts. `not-applicable` là applicability presentation với execution status null, không domain status mới.

**Topology đã đối chiếu:** `topology.ts` ghi `sourceNode` và method orchestration. `execute` trong `case_workflow_orchestrator.py` chạy Finance/Operations bằng `asyncio.gather`; Risk chờ cả hai facts; route direct hoặc Banking; precheck có gate trước execution; Document conditional converge package → Final Risk → Card → exact approval → post-decision/negotiation/release khi áp dụng. `PRECHECK_GATE`/`EXTERNAL_GATE` chỉ là presentation instances của `APPROVAL_GATE`, không persisted node IDs mới. 27 nodes/32 connections là control-flow UI đã audit, **không server graph response**, không full artifact DAG/mọi helper ingestion/evidence/retry/reject path. Absence trong summary không đủ để kết luận NOT_APPLICABLE; không suy edges từ events. Mapping chi tiết ở [review 15](15_workflow_viewer_checkpoint.md).

9 scenarios có run riêng `UI-WF-{contractId}-{SCENARIO}`, không ghi đè Card/request/status của header contract. Scenario mặc định chọn theo fixture status; CON-003 chưa có run thì empty, không mượn dữ liệu contract khác. `completed` là Card NOT_EVALUABLE, không Founder approval. `release` còn pending gate, chưa gửi hồ sơ.

## 3. Cách chạy / review tại máy phát triển

> Lệnh được đối chiếu với `README.md`, `pyproject.toml`, `frontend/package.json` và `vite.config.ts`. URLs chỉ hoạt động trên máy chạy server; remote cần forwarded port. Không phụ thuộc PID/log path riêng máy người bàn giao hoặc coi server còn chạy sau clone.

### 3.1. UI-first preview (không gọi backend)

Yêu cầu Node.js phù hợp Vite lockfile (`^20.19.0 || >=22.12.0`) và npm. Runtime dùng Recharts `^3.10.1`, React Flow `^12.12.0`; `@types/node` là dev dependency. Giữ lockfile, không upgrade chỉ để chạy. Preview không cần FastAPI/workbook/DB/API key. Từ repository root, PowerShell:

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Mở trong browser:

- Executive Home: `http://127.0.0.1:5173/dashboard-assets/?preview=1#/dashboard`
- Company: `http://127.0.0.1:5173/dashboard-assets/?preview=1#/company`
- Contracts: `http://127.0.0.1:5173/dashboard-assets/?preview=1#/contracts`
- Workflow pending Card: `http://127.0.0.1:5173/dashboard-assets/?preview=1#/contracts/CON-004?view=workflow&scenario=approval&phase=decision`
- Toàn graph: đổi `phase=all`; các scenario IDs: `approval`, `assessment`, `banking`, `document`, `input`, `failed`, `completed`, `negotiation`, `release`.

Thử navigation/Company sections, chart period/legend/tooltip/table, Contracts search/filter/selector/drill-down, evidence details và Decision Review pending/stale/resolved. Workflow: click hoặc Enter/Space để inspect, Escape đóng/trả focus; kéo canvas pan, +/−/pinch zoom, Fit; mũi tên/F khi focus canvas. Mobile ≤760px dùng list; desktop cũng có list. Topbar dropdown mô phỏng loading/empty/error/retry. Không add/delete/connect/run-node/editor/approval actions trong viewer.

Vite proxy `/api` và `/health` sang port 8000 nhưng preview không gọi business endpoints. Dev module `/dashboard-assets/src/api/client.ts` là source asset, không business API call. Log ngay terminal; Ctrl+C dừng Vite. Nếu port bận, xác định server hoặc chọn port khác và đổi URL; `--strictPort` tránh tự đổi port. **Không dùng preview để kiểm chứng backend.**

### 3.2. Backend/live UI (khi cần kiểm thử riêng)

Python 3.12; dependencies ở [pyproject.toml](../../pyproject.toml). Workbook mặc định có trong checkout này: `data/input/MISTalent2026_OPC_AgenticAI_TeamPack_v3.xlsx`; người nhận kiểm tra sau clone. Từ repo root ở terminal riêng:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
$env:OPENAI_ENABLED = "false"
$env:OPC_MIS_DATABASE_PATH = ":memory:"
.\.venv\Scripts\python.exe -m uvicorn opc_mis.app:app --reload --host 127.0.0.1 --port 8000
```

- Connected Vite frontend: `http://127.0.0.1:5173/dashboard-assets/` — **không `preview=1`**, các nút submit có thể ghi DB demo.
- Backend Swagger: `http://127.0.0.1:8000/docs`; health: `/health`.
- FastAPI-served bundle hiện hữu: `http://127.0.0.1:8000/dashboard` sau khi build.
- Preview trong FastAPI-served bundle: `http://127.0.0.1:8000/dashboard?preview=1#/dashboard`.
- **Không nhầm** single-contract live API hiện có với Executive Home/Company/Workflow Graph live integrations chưa làm.
- App có thể đọc `.env`; hai env vars phía trên override OpenAI/DB trong terminal demo. DB in-memory reset khi reload/restart; không đụng `.env`, TeamPack nguồn, DB thật hay credentials. Dataset khác cấu hình server qua `OPC_MIS_TEAM_PACK_PATH`, không browser path. Masking cần secret server hợp lệ; không bypass guard.
- OpenAI tắt có thể ra NOT_EVALUABLE; live CON-004 không đảm bảo vào final approval, có thể chờ Banking/Document. Không approve các gate để ép screenshot. Log ở terminal backend; Ctrl+C dừng.
- `npm.cmd run build` trong `frontend/` chạy `tsc -b && vite build`, sinh assets vào **`src/opc_mis/api/static/react/`**, không `frontend/dist/`; không sửa generated assets tay. Audit docs không build lại để giữ bundle nguyên vẹn.

### 3.3. Screenshots/review artifacts đã kiểm tra tồn tại

`ui-first-*` trong 13 là **before**; `ui-polish-*` là CP1 reference sau refinement đã duyệt. Tất cả ảnh dưới đây dùng dữ liệu minh họa, không backend evidence; không tự cập nhật theo source.

| Trang/view | Viewport 1440px | Viewport 1920px | Viewport 390px |
|---|---|---|---|
| Dashboard | [Ảnh](../../output/playwright/ui-polish-dashboard-1440.png) | [Ảnh](../../output/playwright/ui-polish-dashboard-1920.png) | [Ảnh](../../output/playwright/ui-polish-dashboard-390.png) |
| Company | [Ảnh](../../output/playwright/ui-polish-company-1440.png) | [Ảnh](../../output/playwright/ui-polish-company-1920.png) | [Ảnh](../../output/playwright/ui-polish-company-390.png) |
| Contracts | [Ảnh](../../output/playwright/ui-polish-contracts-1440.png) | [Ảnh](../../output/playwright/ui-polish-contracts-1920.png) | [Ảnh](../../output/playwright/ui-polish-contracts-390.png) |
| Workflow assessment | [Assessment](../../output/playwright/workflow-assessment-1440.png) | [Canvas](../../output/playwright/workflow-canvas-1920.png) | [List](../../output/playwright/workflow-mobile-390.png) |
| Workflow Card/inspector | [Decision](../../output/playwright/workflow-decision-1440.png), [Inspector](../../output/playwright/workflow-inspector-1440.png) | [Banking](../../output/playwright/workflow-banking-1920.png), [Full graph](../../output/playwright/workflow-overview-1920.png) | [Inspector](../../output/playwright/workflow-mobile-inspector-390.png) |

Tên ảnh thể hiện **viewport dùng lúc review**, không kích thước PNG cố định: phần lớn ảnh full-page có chiều rộng 1425/1905/375px do scrollbar 15px; chiều cao theo nội dung. Contracts desktop là 1440×1080 và 1920×1080. Đã đọc PNG headers của 17 ảnh liên kết; không đổi tên/resize ảnh để khớp viewport.

Full graph là overview thu nhỏ cần zoom/chọn vùng để đọc labels, không mọi labels dễ đọc cùng lúc ở fit. Các JSON đã đọc/đếm trong audit: [34 checks](../../output/playwright/workflow-interaction-results.json), [12 final checks](../../output/playwright/workflow-final-check-results.json), [typography](../../output/playwright/workflow-typography-results.json). Không chụp/chạy lại browser trong audit tài liệu.

## 4. Nguồn tài liệu nên đọc theo thứ tự

1. `README.md`, `style.md`, `frontend/package.json` — setup, quy ước repository và dependencies.
2. `docs/ui-design/15_workflow_viewer_checkpoint.md` — checkpoint mới nhất; xác nhận scenarios/graph/interaction và giới hạn.
3. `docs/ui-design/14_visual_refinement_review.md` — visual polish; screenshot trước/sau.
4. `docs/ui-design/13_ui_first_preview_checkpoint.md` — preview shell/Dashboard/Company/Contracts.
5. `docs/ui-design/06_frontend_handoff.md` — baseline PR #3, live API, testing, demo tooling và regressions.
6. `docs/ui-design/07_executive_information_architecture.md` → `12_revised_implementation_roadmap.md` — IA, Dashboard, Company, data mapping, API gaps và roadmap được **lập trước khi UI-first preview triển khai**.
7. `docs/ui-design/03_design_system.md` — design system có lịch sử chỉnh sửa; ưu tiên `style.md` và CSS tokens thực tế. Font hiện hành là Segoe UI/system sans, không Be Vietnam Pro đề xuất cũ. Canvas `#FDFDFD`, surface `#FFFFFF`, muted surface `#F7F8FA`, lavender `#F0F1FC`, primary `#536EF1`, strong `#4358C6`, charcoal `#292B35`, border `#EDEEF1`; spacing 4px.
8. Backend: `src/opc_mis/api/`, `src/opc_mis/workflow/`, `src/opc_mis/domain/`, `src/opc_mis/infrastructure/` cùng tests — nguồn sự thật cho API, topology, workflow semantics.

**Quy tắc:** code tại HEAD hiện hành quyết định chức năng đã có; tài liệu `07–12` là spec/roadmap đề xuất, không tự động chứng minh API mới đã triển khai. Đọc `13–15` để nhận biết thay đổi sau đó.

### 4.1. Source map đã đối chiếu

| Nhu cầu | File bắt đầu |
|---|---|
| Entry/shell/routes | [main.tsx](../../frontend/src/main.tsx), [PreviewEntry.tsx](../../frontend/src/preview/PreviewEntry.tsx), [PreviewApp.tsx](../../frontend/src/preview/PreviewApp.tsx), [navigation.ts](../../frontend/src/preview/navigation.ts) |
| Preview data boundary | [models.ts](../../frontend/src/preview/models.ts), [data.ts](../../frontend/src/preview/data.ts), [fixtures.ts](../../frontend/src/preview/fixtures.ts) |
| Global pages/charts/controls | [Dashboard.tsx](../../frontend/src/preview/Dashboard.tsx), [Company.tsx](../../frontend/src/preview/Company.tsx), [Charts.tsx](../../frontend/src/preview/Charts.tsx), [components.tsx](../../frontend/src/preview/components.tsx) |
| Contract wiring/tests | [Contracts.tsx](../../frontend/src/preview/Contracts.tsx), [PreviewApp.test.tsx](../../frontend/src/preview/PreviewApp.test.tsx) |
| Workflow UI/topology/data/tests | [WorkflowViewer.tsx](../../frontend/src/preview/workflow/WorkflowViewer.tsx), [topology.ts](../../frontend/src/preview/workflow/topology.ts), [workflow fixtures](../../frontend/src/preview/workflow/fixtures.ts), [WorkflowViewer.test.tsx](../../frontend/src/preview/workflow/WorkflowViewer.test.tsx) |
| Styles | [tokens.css](../../frontend/src/styles/tokens.css), [preview.css](../../frontend/src/preview/preview.css), [workflow.css](../../frontend/src/preview/workflow/workflow.css) |
| Connected UI/API mapping | [App.tsx](../../frontend/src/app/App.tsx), [dashboardIntegration.ts](../../frontend/src/app/dashboardIntegration.ts), [client.ts](../../frontend/src/api/client.ts), [normalize.ts](../../frontend/src/api/normalize.ts) |
| Review/approval/focus guards | [DecisionCardModal.tsx](../../frontend/src/features/decision/DecisionCardModal.tsx), [ApprovalDialog.tsx](../../frontend/src/features/governance/ApprovalDialog.tsx), [useDialogFocus.ts](../../frontend/src/shared/useDialogFocus.ts) |
| Artifact detail/connected history | [ArtifactDetailDialog.tsx](../../frontend/src/features/artifacts/ArtifactDetailDialog.tsx), [WorkflowEvents.tsx](../../frontend/src/features/workspace/WorkflowEvents.tsx), [ContractWorkspace.tsx](../../frontend/src/features/workspace/ContractWorkspace.tsx) |
| Backend entry/config/routes | [app.py](../../src/opc_mis/app.py), [config.py](../../src/opc_mis/config.py), [application.py](../../src/opc_mis/api/application.py), [routes.py](../../src/opc_mis/api/routes.py) |
| Schemas/projection | [schemas.py](../../src/opc_mis/api/schemas.py), [dashboard_schemas.py](../../src/opc_mis/api/dashboard_schemas.py), [dashboard_projection.py](../../src/opc_mis/api/dashboard_projection.py), [case_workflow_models.py](../../src/opc_mis/domain/case_workflow_models.py) |
| Workflow authority/query port | [case_workflow_orchestrator.py](../../src/opc_mis/workflow/case_workflow_orchestrator.py), [workflow.py](../../src/opc_mis/domain/workflow.py), [enums.py](../../src/opc_mis/domain/enums.py), [case_workflow_repository.py](../../src/opc_mis/ports/case_workflow_repository.py) |

Business components trả artifact drafts/signals; Orchestrator validate/version/persist và sở hữu pause/resume. Giữ layer rules trong [AGENTS.md](../../AGENTS.md). Identifier tests đọc enums Python như text, không import Python runtime vào browser.

### 4.2. Existing read APIs — chưa phải global integration

| API hiện có trong `routes.py` | Dữ liệu có thể dùng / giới hạn |
|---|---|
| `GET /api/contracts` | Catalog IDs, dataset/snapshot identity; chưa rich contract metadata/run index |
| `GET /api/workflows/{workflow_run_id}` | Nodes/status/current stage, artifact refs, branch outcomes, pending/resume/failure; chưa full graph edges/topology version/applicability contract |
| `GET /api/workflows/{workflow_run_id}/dashboard` | Canonical Founder projection, typed interactions/current references; chỉ một run |
| `GET /api/workflows/{workflow_run_id}/events?after_sequence=N` | Ordered incremental events; không dùng làm graph/state authority |
| `GET /api/cases/{evaluation_case_id}/artifacts` | Envelope/version/evidence/input lineage; case-wide nên lọc exact run refs, không latest-by-type xuyên runs |
| `GET /api/cases/{evaluation_case_id}/approval-requests` | Exact pending/resolved subject/action; không global queue discovery |
| `GET /api/cases/{evaluation_case_id}/approval-checkpoints` | Gate registry; REGISTERED checkpoint không pending human request |

Start/evaluate, resume, business assessments, supplements, negotiation và approval decision là existing mutations, không gọi để load viewer/global pages. `CaseWorkflowRepository.list_recoverable` phục vụ recovery, không full WAITING/terminal run index. Các endpoints ở H2–H4 bên dưới **chưa triển khai**.

### 4.3. Git inventory — working tree cần bàn giao

Remote origin: `https://github.com/ltrphung0620/mis_prototype`. Branch `main`, HEAD `0329574`; local `origin/main` là `707f58a` (merge PR #3). `git rev-list --left-right --count origin/main...HEAD` trả **0 / 1**; index rỗng. Không fetch/network remote trong audit, nên ahead là so sánh local tracking, không xác nhận tuyệt đối GitHub hiện tại. Commit CP1 là `feat(ui): add executive preview and polish checkpoint 1`.

Trước cập nhật tài liệu: **37 paths dirty: 11 tracked changes + 26 untracked files**. Đây là manifest quan sát, không danh sách file được tạo trong audit này:

```text
M  docs/ui-design/06_frontend_handoff.md
M  docs/ui-design/12_revised_implementation_roadmap.md
M  frontend/package-lock.json
M  frontend/package.json
M  frontend/src/preview/Contracts.tsx
M  frontend/src/preview/models.ts
M  frontend/src/preview/navigation.ts
D  src/opc_mis/api/static/react/assets/PreviewApp-VcK1YR3u.js
D  src/opc_mis/api/static/react/assets/index-BzKmjIYQ.js
M  src/opc_mis/api/static/react/index.html
M  style.md
?? docs/ui-design/15_workflow_viewer_checkpoint.md
?? docs/ui-design/16_frontend_handoff_checkpoint2.md
?? frontend/src/preview/workflow/WorkflowViewer.test.tsx
?? frontend/src/preview/workflow/WorkflowViewer.tsx
?? frontend/src/preview/workflow/fixtures.ts
?? frontend/src/preview/workflow/topology.ts
?? frontend/src/preview/workflow/workflow.css
?? output/playwright/workflow-assessment-1440.png
?? output/playwright/workflow-banking-1920.png
?? output/playwright/workflow-canvas-1920.png
?? output/playwright/workflow-decision-1440.png
?? output/playwright/workflow-final-check-results.json
?? output/playwright/workflow-final-checks.js
?? output/playwright/workflow-inspector-1440.png
?? output/playwright/workflow-interaction-results.json
?? output/playwright/workflow-interactions.js
?? output/playwright/workflow-mobile-390.png
?? output/playwright/workflow-mobile-inspector-390.png
?? output/playwright/workflow-overview-1920.png
?? output/playwright/workflow-review.js
?? output/playwright/workflow-typography-results.json
?? src/opc_mis/api/static/react/assets/PreviewApp-CAM7oVTL.js
?? src/opc_mis/api/static/react/assets/WorkflowViewer-C0ys1lzU.js
?? src/opc_mis/api/static/react/assets/WorkflowViewer-DOzebP57.css
?? src/opc_mis/api/static/react/assets/index-DompW74u.js
?? src/opc_mis/api/static/react/assets/navigation-BPoIaTCC.js
```

Bundle replacements là generated output CP2, không Python backend changes. Không có Python source/tests/workbook changes trong manifest. Audit này chỉ sửa 16 và thêm liên kết 16 ở 06/15/style, không app/deps/fixtures/screenshots/bundle hoặc staging index. Nếu muốn người nhận lấy CP2 qua GitHub, owner cần cho phép commit/push sau review; chưa thực hiện. Recheck status/tracking khi chuyển giao, không coi manifest là bất biến.

## 5. Backlog còn lại và thứ tự đề xuất

### H0 — Bàn giao, Git và nghiệm thu trạng thái hiện tại (ưu tiên cao nhất)

- [x] Audit Git/source/links/tests hiện tại; branch/SHA/dirty files ở mục 4.3.
- [ ] Đảm bảo người nhận có **đầy đủ working tree CP2**, không mặc định `git pull` nhận được uncommitted files. Thống nhất cách chuyển giao; không commit/push trong task audit này.
- [ ] Chạy preview tất cả 4 phần và 9 scenarios; xem desktop/mobile, Node Inspector, approvals chỉ là mock.
- [ ] Người nhận chạy frontend tests/build trên máy mình; so sánh screenshots đã có, ghi discrepancies.
- [ ] Founder nghiệm thu CP2; audit handoff không thay approval này.

**Đầu ra:** nguồn có thể tái tạo, handoff thực sự mở được UI trên máy người nhận.

### H1 — Data contracts / owner decisions (gate trước live integration)

- [ ] Chốt phạm vi API đọc cộng thêm (không đổi mutation API hiện hữu); review query ports/index/migration riêng.
- [ ] Chốt company base snapshot, source periods, record quality, unit/currency và missing/duplicate policy.
- [ ] Chốt run mặc định, historical-snapshot pending visibility/authority, exact deep-link semantics; không tự xem pending cũ là actionable.
- [ ] Chốt KPI/chart release đầu, action queue order và formal browser E2E policy. Dependencies preview đã chọn và được cho phép: Recharts/React Flow; không hỏi duyệt lại quyền library này.
- [ ] Có owner phê duyệt rõ ràng trước khi sửa backend cho metrics, graph hoặc action queue.

**Đề xuất sẵn từ spec (chưa phải phê duyệt cuối):** 3 KPI snapshot (số hợp đồng, tổng giá trị hợp đồng nguồn, hóa đơn Open), cashflow dự kiến; queue approvals → blocking inputs → failed-safe → review/negotiation; historical pending group riêng/read-only nếu authority chưa xác minh.

### H2 — Canonical Workflow Graph + Viewer live integration

- [ ] Trước tiên mapping existing summary/projection/events/artifacts/requests cho **một exact run**. Review topology authority: versioned audited frontend adapter hay additive backend graph; không coi graph endpoint là lựa chọn đã duyệt.
- [ ] Nếu chọn backend graph sau duyệt: versioned node/edge/topology từ **executable orchestration**, route applicability và node state mapping; không dựng edge từ thứ tự events.
- [ ] Review read contract dự kiến `GET /api/workflows/{run}/graph`; dữ liệu node/edge đầy đủ cho direct/banking/document/negotiation/release branches.
- [ ] Nối viewer React với graph/run data thật; giữ lựa chọn fixture ở preview mode **độc lập**.
- [ ] Inspector bind exact run/artifact version, evidence và event sequence; không hiển thị proposal như approval đã được chấp thuận.
- [ ] Kiểm thử no mutation từ viewer, mobile list, keyboard, pause/wait/fail-safe/terminal, applicability không rõ.

**Acceptance:** graph đúng topology thật; viewer đọc được từng node mà không phát sinh POST hoặc bypass Governance.

### H3 — Company read/aggregation APIs + Company Overview live

Theo `11_api_gap_analysis.md`, các endpoints **đề xuất**, chưa xem là đã triển khai:

- `GET /api/company/snapshot`
- `GET /api/company/overview`
- `GET /api/company/records/{entity}`

- [ ] Xây read models ở server cho source identity, coverage, periods, provenance và quality.
- [ ] Tổng hợp company/contract/order/invoice theo **đúng grain độc lập**, tránh join nhân bản dữ liệu.
- [ ] Cashflow `09_CASHFLOW` chỉ là **dự kiến**; dòng tiền theo tháng có missing gaps; không gọi projected closing cash là số dư ngân hàng thực hoặc sum các balances theo tháng.
- [ ] Tách `OPC_GLOBAL` khỏi từng contract run; không cộng lặp qua nhiều cases/artifacts/versions.
- [ ] Nối charts/tables/filters và drill-down với API; giữ fallback unavailable/partial/error, không impute null thành 0.
- [ ] Dùng test fixtures số liệu nhỏ để reconciliation giữa chart, table và response API.

**Acceptance:** chỉ số có scope, grain, unit, nguồn, snapshot, coverage; Dashboard và Company hiển thị cùng giá trị khi cùng population/filter.

### H4 — Global run index, Executive actions, Contracts live

Endpoints read **đề xuất**:

- `GET /api/executive/overview`
- `GET /api/executive/actions`
- `GET /api/contracts/overview`
- `GET /api/contracts/{contract_id}/runs`

- [ ] Index đủ tất cả run statuses (bao gồm WAITING/terminal), không chỉ `list_recoverable`.
- [ ] Queue đếm distinct approval requests, phân biệt checkpoint registry với pending approval thực tế.
- [ ] Exact contract/run/request/artifact identity qua deep links; kiểm tra stale/expired/resolved trước mutation.
- [ ] Không tự `POST` planner/run để chuẩn bị dữ liệu cho trang Dashboard.
- [ ] Historical pending vẫn được phát hiện nhưng không cho approve tự động nếu authority chưa rõ.
- [ ] Giữ source contract status riêng workflow/decision business status.

**Acceptance:** action queue đưa Founder đến đúng review/form; không one-click approve, không nhầm across contracts/runs/snapshots; các tổng hợp server trả đủ total/coverage/pagination.

### H5 — Hardening, bug backlog, regression & release

- [ ] **Điều tra** 4 backend pytest fails, 2 Ruff `I001` theo baseline; không đổi asserts chỉ để xanh test.
- [ ] Browser E2E các flow thật: missing input, banking/document waits, NOT_EVALUABLE, stale approval, duplicate submit, negotiation, separate external release.
- [ ] Accessibility: NVDA/VoiceOver, zoom 200%, keyboard navigation, modal focus và mobile scrolling.
- [ ] UI polish **connected mode**: evidence table chưa search/filter/paging; preview đã có evidence search. Connected event log chưa metadata; inspector preview có synthetic event codes. Chuẩn hóa nhãn/empty/error/partial sau data integration, không liệt kê phần preview đã có như chưa triển khai.
- [ ] Security/product boundary: HEAD từng **chưa có authentication/RBAC**; phải thiết kế riêng trước khi coi dashboard/global read APIs là multi-user production-ready.
- [ ] Performance/data density/bundle audit khi cần. Viewer đã lazy-load từ Contracts; không liệt kê lazy canvas như tính năng chưa có.
- [ ] Chạy test/build/lint, ghi issues còn mở, review docs, xin phép owner trước commit/push/merge.

**Acceptance:** tất cả regression quan trọng được báo cáo trung thực; không claim production-ready chỉ vì preview đẹp/tests frontend xanh.

## 6. Kết quả kiểm tra và baseline failures

| Kiểm tra | Kết quả | Thời điểm/phạm vi |
|---|---|---|
| `npm.cmd test` | **155 passed, 25 files**, 13.54s | Chạy lại audit 11/10 trên HEAD + dirty CP2, gồm 19 tests viewer mới; không phải tests chỉ ở commit HEAD |
| `npm.cmd exec tsc -- --build` | **Pass** | Chạy lại audit, không sinh Vite assets |
| `npm.cmd run build` | **Pass theo review 15** | Lần CP2; không build lại audit docs để tránh thay generated bundles |
| Browser checks | **46/46 passed** (34 + 12), request/error arrays rỗng | JSON ở mục 3.3 đã đọc/đếm lại; không chạy/chụp browser lại audit này |
| `.\.venv\Scripts\ruff.exe check .` | **2 I001**, exit 1 | Chạy lại audit; hai files bên dưới, không auto-fix |
| `.\.venv\Scripts\python.exe -m pytest -q` | **481 passed, 4 failed, 1 warning**, 87.26s | Chạy lại audit; cùng bốn failure names baseline; không sửa source/tests |
| npm audit | Production 0 vulnerabilities, 6 dev advisories | Historical CP2 report, không network audit lại/force-fix |

Vitest sandbox ban đầu lỗi cache rename `EPERM` trước khi thực thi tests; chạy lại ngoài sandbox đạt 155. Pytest sandbox không xuất output và đã dừng trước lần chạy local. Đây là môi trường chạy, không thêm chúng vào application failures.

Lệnh kiểm tra lại từ repo root:

```powershell
cd frontend
npm.cmd test
npm.cmd run build
cd ..
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\python.exe -m pytest -q
```

Browser scripts dùng Playwright CLI ngoài repo; **không có Playwright framework dependency/npm E2E script**. Không dùng npm-cache path/session riêng máy làm yêu cầu setup. Người nhận có thể review thủ công bằng checklist mục 3; formal E2E setup là scope riêng. Narrow 720px viewport trong report không phải browser zoom 200% thật. Chưa audit screen reader hoặc claim WCAG certification.

Đã tái hiện bốn pytest failures được ghi ở 06/15:

1. `tests/integration/test_decision_final_workflow.py::test_exact_decision_card_requires_founder_then_routes_to_negotiation` — expected `COMPLETED`, actual `WAITING_FOR_INPUT`.
2. `tests/integration/test_decision_final_workflow.py::test_con004_card_carries_one_precomputed_margin_negotiation_strategy` — expected `NEGOTIATION_IN_PROGRESS`, actual `NEGOTIATION_TERMS_SENT`.
3. `tests/unit/test_decision_openai_composer.py::test_openai_adapter_retries_ungrounded_numeric_free_prose` — numeric-summary assertion khác output.
4. `tests/unit/test_post_decision_release.py::test_external_proposal_rejects_non_accept_route` — regex message không khớp.

Ruff `I001` ở `src/opc_mis/domain/case_workflow_models.py`, `src/opc_mis/governance/evidence_validator.py`.

**Không suy luận đây là lỗi do Checkpoint 2.** Tạo ticket riêng, xác định semantics expected/actual rồi mới quyết định sửa source hoặc test.

## 7. Những bất biến nghiệp vụ không được phá

- Dữ liệu nguồn/TeamPack là snapshot; thời điểm `response_generated_at` **không** phải ngày cập nhật nghiệp vụ.
- `NOT_EVALUABLE` được xem lý do/giới hạn, **không** đưa vào final approval.
- `Finance/Operations/Risk: completed` là execution completion, **không** tương đương safe/accepted.
- Final Decision Card là **proposal**; founder approval bind vào exact artifact/version/hash + pending request và chỉ qua Governance review.
- Banking precheck là **simulation, non-binding**, không phải ngân hàng chấp thuận.
- Document metadata/hash không mặc định là file verified hoặc legal signature.
- Final decision approval **không** cấp quyền external release; `READY_FOR_EXTERNAL_SUBMISSION` **không** chứng minh đã gửi hồ sơ/nhận receipt.
- Mock preview không được gọi live protected actions, tự tạo case, khởi chạy/resume workflows hay chỉnh DB nguồn.
- Dữ liệu tài chính không gộp nhầm `contract_value`, `order_revenue`, `invoice_amount` thành cùng một tổng; phân biệt flow với stock, actual với projected, source status với workflow status.

## 8. Owner decisions còn cần xác nhận

- **Review/chuyển giao:** Founder nghiệm thu CP2 và chọn cách chuyển working tree cho thành viên, hoặc cho phép commit/push sau review. Audit không tự cấp quyền này.
- **Read integration (R1):** Scope endpoints/query ports/index/migration nào được duyệt? Live topology dùng versioned audited adapter hay canonical graph API?
- **Company truth (R2):** BASE snapshot vs case overlays/historical snapshot; không trộn company totals với run facts.
- **Runs/authority (R3):** Default representative run, visibility/authority của pending trên snapshot cũ và exact deep links; không âm thầm hide hoặc coi historical pending actionable.
- **Metrics/actions (R4–R6):** Period/filter/coverage/partial totals, metric/chart release scope, action queue order/grouping. IA Executive Home đã chốt, không hỏi duyệt lại IA.
- **Testing/release (phần còn lại R7):** Formal browser E2E tooling, screen reader/200% zoom thật; internal prototype hay multi-user deployment. Auth/RBAC cần scope riêng nếu multi-user. Quyền preview/library đã cấp không đồng nghĩa cho phép backend work.

## 9. Tiêu chí hoàn tất việc bàn giao

- [ ] Người nhận **clone/pull hoặc nhận patch** và chạy lại preview đủ 4 khu vực.
- [ ] Người nhận xem 9 workflow scenarios, chọn node và mở inspector được.
- [ ] Người nhận đọc source/tài liệu, biết rõ mock so với real API và các business guard.
- [ ] Người nhận có danh sách task có dependency và acceptance (H1–H5).
- [ ] Người nhận nắm 4 pytest fails/2 Ruff errors chưa giải quyết.
- [ ] Các quyết định về owner approval, branch/PR và phạm vi implementation tiếp theo được thống nhất.

---

### Gợi ý task đầu tiên cho người tiếp quản

> **H0 — nghiệm thu/tái tạo CP2 trên máy người nhận.** Có đủ source CP2/lockfile/bundle, chạy preview không backend, review ba global pages + 9 scenarios, inspector/keyboard/mobile/no API, chạy tests/build và ghi discrepancies. Đầu ra: checklist pass/fail kèm branch/SHA/dirty-file scope; không thêm backend/API/mutations. Sau Founder duyệt CP2, H1 là mapping existing GET APIs cho **một exact run** và đề xuất read-only live slice; review topology authority trước graph endpoint hoặc adapter mới.

*Tài liệu 16 tổng hợp audit working tree hiện hành. 13/14 là records lịch sử CP1 trước/sau polish; 15 là record CP2, không tự cập nhật tests/build/screenshots/servers theo thời gian. Giữ số liệu lịch sử của mỗi checkpoint; source và schemas quyết định chức năng có thật. Audit chỉ cập nhật handoff/liên kết, không app code, commit hoặc push.*
