# Bàn giao frontend — OPC MIS Contract Decision Workspace

Ngày rà soát: 08/10/2026 (cập nhật cùng ngày sau 2 task P1 trên nhánh `feat/ui-polish`). Đây là bản UI đã triển khai để tiếp tục phát triển, chưa phải bản sản phẩm production hoàn chỉnh. Không đổi business logic/API/backend trong lần redesign này.

## Backend đã có chưa?

**Có.** Backend FastAPI/Python nằm trong `src/opc_mis/`, không phải mock server của frontend. Có SQLite persistence cho workflow, approval và artifact; đọc TeamPack theo cấu hình server, không nhận đường dẫn workbook từ browser.

| Khối | Đã có | Giới hạn cần giữ |
|---|---|---|
| Dataset / Planner | Ingestion, contract catalog, intake, missing-data và evidence lineage | Không sửa workbook; không đoán quan hệ/vật liệu thiếu |
| Finance / Operations / Risk | Deterministic facts, assessments, initial/final Risk, validated artifacts | Không tính lại nghiệp vụ ở browser; completion không có nghĩa an toàn |
| Workflow / Governance | Persisted state machine, projection, events, pause/resume, exact approvals | Founder là workflow role; chưa có authentication/RBAC |
| Banking | Discovery, readiness, approval gate, precheck simulation | Không phải phản hồi/phê duyệt ngân hàng thật; không transfer/product ranking |
| Document | Metadata supplement, masking, checklist và internal packages | Không upload raw bytes; metadata không xác minh file/signature/pháp lý |
| Decision / Negotiation | Bounded AI composition, deterministic guards, Decision Card, final approval, negotiation input/outcome | OpenAI tắt/unavailable có thể ra NOT_EVALUABLE; không bỏ source/identity guards |
| External release | Proposal và gate riêng; dừng ở READY_FOR_EXTERNAL_SUBMISSION | Không có external connector, delivery hoặc receipt |

API đầy đủ và setup cấu hình nằm ở [README](../../README.md). Xem `/docs` khi backend chạy. Backend đang có một số tests/lint fail được ghi bên dưới; không mô tả hệ thống là đã hoàn tất production.

## Frontend hiện đã làm gì?

- React/TypeScript/Vite thật, dùng API thật qua `/api`; không thay framework/dependency declarations.
- Workspace một hợp đồng; 5 local views: Quyết định, Đánh giá, Bằng chứng, Quy trình, Dữ liệu đầu vào. Sidebar desktop + navigation mobile, contract selector và current business status.
- Decision summary và limitations; metrics theo scope/unit từ projection; assessment rows; evidence table có ID/version/validation; workflow timeline và event log.
- Decision Card review; approval, banking/document supplements, negotiation và external-release review giữ handlers/contracts hiện hữu.
- New Mercury-inspired tokens, typography, flat surfaces, responsive; focus hook, skip link, reduced motion; test coverage cho binding/interaction guards.
- FastAPI `/dashboard` dùng bundle đã build. Development Vite proxy sang backend ở port 8000.
- Detail views (Finance/Operations/Risk, Banking, Document, precheck) và form bổ sung hồ sơ dùng class/tokens, không còn inline styles. Badge mức rủi ro/precheck theo ngữ nghĩa, không dùng success.
- Dialog chi tiết ([ArtifactDetailDialog.tsx](../../frontend/src/features/artifacts/ArtifactDetailDialog.tsx)) hiện loại artifact, `ID · vN · validation` và **Nguồn đầu vào** từ `input_artifact_ids`. Nhãn đủ 33 artifact types ở `shared/artifactLabels.ts`.

Review và screenshots: [05_mercury_redesign_review.md](05_mercury_redesign_review.md). Quy tắc bắt buộc khi tiếp tục UI: [style.md](../../style.md). Các tài liệu 01/02/04 có phần kế hoạch lịch sử; **03, 05, 06 và style.md** mô tả bản hiện hành. Không dùng prompt forest cũ để redesign lần tiếp theo.

## Việc UI còn cần hoàn thành

Đây là backlog có thứ tự ưu tiên, không phải danh sách chức năng hoàn toàn chưa có. Không tự ý làm hết trong một PR lớn.

| Ưu tiên / việc | Evidence và file bắt đầu | Tiêu chí hoàn thành |
|---|---|---|
| ~~P1 — Đồng bộ các detail/form sâu với style mới~~ **Đã xong** | Inline styles đã bỏ ở `AssessmentViews.tsx`, `WorkflowArtifactViews.tsx`, `DocumentSupplementForm.tsx` (chỉ còn CSS custom property animation ở workflow). Precheck luôn ghi mô phỏng; form tài liệu không còn fallback hash/UUID cố định khi thiếu Web Crypto | Còn lại: `BankingAmountForm`, `PrecheckEvidenceForm` chưa audit riêng về style |
| P1 — Artifact detail coverage và lineage — **phần lớn đã xong** | Đã thêm renderer + tests cho `BANKING_PRECHECK_SUBMISSION_PROPOSAL`, `EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL`, `POST_DECISION_UPDATE`, `NEGOTIATION_OUTCOME`, `BANKING_INPUT_SUPPLEMENT`, `BANKING_PRECHECK_EVIDENCE_SUPPLEMENT`, `DOCUMENT_EVIDENCE_SUPPLEMENT`; dialog hiện ID/version/upstream | Còn 6 types disable detail: `APPROVAL_CHECKPOINTS`, `RISK_RULE_EVALUATION`, `DECISION_ROUTE_PLAN`, `DECISION_POST_BANKING_REVIEW`, `DOCUMENT_PREPARATION_REQUEST`, `AI_DECISION_ANALYSIS` (Decision Card có panel riêng). `RiskPreScanView` chọn `APPROVAL_CHECKPOINTS` v1 theo heuristic vì backend không ghi upstream giữa pre-scan và checkpoint. Demo fixture chưa có các types mới, mới verify bằng unit tests |
| P1 — Accessibility của tất cả dialogs/forms | `shared/useDialogFocus.ts` dùng dialog đầu tiên và chưa inert background; đã test trap/Escape/restore cơ bản | Audit screen reader, active dialog scope, hidden/disabled focus targets, form error associations, contrast mọi trạng thái. Keyboard hoàn chỉnh trên desktop/mobile; không công bố WCAG certification khi chưa audit |
| P1 — Browser E2E của toàn workflow và edge cases | Unit/regression tests đã có; screenshot fixture chỉ là một thời điểm final approval pending, live smoke chưa đi hết mọi branch | Cover banking/document waits, pause/resume, NOT_EVALUABLE, stale/replaced/resolved approval, duplicate submit, negotiation outcome và separate release gate bằng isolated fixtures/test backend; không dùng DB thật hoặc gọi external adapter |
| P2 — Workflow history dễ đọc và tải hiệu quả hơn | `features/workspace/WorkflowEvents.tsx` hiện show raw `event_type`, poll toàn list 1,5s; backend có `after_sequence` | Map event labels, xử lý unknown codes trung thực; incremental fetch/merge/dedupe theo sequence, dừng timer đúng lifecycle, test đổi run/error/recovery; không lấy log làm source state |
| P2 — Evidence table khi có nhiều artifacts | `features/workspace/ContractWorkspace.tsx`: chưa search/filter/paging | Filter/sort/search từ artifacts đã được API trả; preserve run scope/version. Empty filter state rõ; không biến thành document upload/search service mới |
| P2 — Navigation và component organization | Sidebar local views, không URL state; `App.tsx` vẫn chứa nhiều interaction wiring; brand link `/dashboard` cần kiểm tra cả Vite base và FastAPI | Kiểm tra reload/back/brand trên cả hai server; chỉ thêm URL/view state khi có scope. Tách shell/interaction presentation với tests giữ handlers/guards, không đổi API để phục vụ layout |
| P2 — Responsive/state polish | Đã kiểm tra 390/768/1440/1920px ở views chính; chưa audit mọi dialog/form và chuỗi text dài | Kiểm tra zoom 200%, long IDs/text, loading/empty/error/warning/failed-safe/stale và pending/resolved; không tràn trang hoặc mất hành động |

Gợi ý task tiếp theo: **P1 — accessibility của dialogs/forms** (`useDialogFocus` chỉ lấy dialog đầu tiên, background chưa inert), hoặc bổ sung các artifact types mới vào demo fixture để xem renderer trên UI. Mỗi task nhỏ nên có before/after và nêu rõ ảnh dùng dữ liệu thật hay fixture.

Các mở rộng cần backend/product scope riêng: multi-contract overview/search được persist, quản lý người dùng/RBAC, policy settings, historical analytics, document repository verification, live banking/external connector. Không tạo UI trông như đã hoạt động cho các phần này.

## Chạy ứng dụng sau khi clone/pull

Yêu cầu Python 3.12, Node.js/npm và TeamPack ở đường dẫn mặc định trong repository. Dùng lockfile `npm ci`; không cập nhật dependencies chỉ để chạy.

Terminal backend, từ repo root (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
# Environment chỉ cho process hiện tại; không sửa .env/database đang có.
$env:OPENAI_ENABLED = "false"
$env:OPC_MIS_DATABASE_PATH = ":memory:"
.\.venv\Scripts\python.exe -m uvicorn opc_mis.app:app --reload --host 127.0.0.1 --port 8000
```

App có thể đọc `.env` hiện hữu; environment phía trên override hai cấu hình cho phiên demo. Không cần OpenAI key để kiểm thử catalog/assessments/NOT_EVALUABLE. Memory DB mất khi reload/restart. Khi cần persisted local run, dùng một DB demo riêng trong `data/runtime/` và đặt environment trước startup; không tái sử dụng DB thật. Masking cần secret server theo README; không bypass guard khi thiếu key.

Terminal frontend:

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev -- --host 127.0.0.1 --strictPort
```

- Frontend API thật: `http://127.0.0.1:5173/dashboard-assets/`.
- Backend/Swagger: `http://127.0.0.1:8000/docs`; health: `/health`.
- FastAPI-served UI: `npm.cmd run build` trong `frontend`, rồi mở `http://127.0.0.1:8000/dashboard`.
- Xem log ngay trong các terminal. Dừng từng server bằng Ctrl+C. Đây là local URLs trên máy chạy servers; remote/container cần port forwarding riêng.

Chọn hợp đồng rồi bắt đầu đánh giá. Các nút submit trên **API thật** ghi nhận workflow/approval vào DB đang cấu hình. Với CON-004, không cam kết tự động vào final approval: có thể chờ banking input/precheck/document. Không approve các bước chỉ để xem screenshot. Không tạo backend ACCEPT giả hoặc bỏ qua NOT_EVALUABLE để ép màn final review.

### Demo final Decision Card chỉ để kiểm thử UI

Existing fixture: `output/playwright/mercury-review.js`. Tất cả số tiền, lời đề xuất và outcomes trong fixture là synthetic; `source: OPENAI` cũng là mock. Không phải kết quả backend hoặc lần gọi model thật.

Để người tiếp nhận trải nghiệm fixture bằng Chrome thường, sau khi Vite chạy, từ repo root mở một terminal nữa:

```powershell
node tools/ui-demo-preview.mjs
```

Mở `http://127.0.0.1:5174/dashboard-assets/`. Tool chỉ proxy frontend assets/HMR sang Vite và dùng fixture cho API, **không forward bất kỳ API nào sang FastAPI**, không DB và không cần backend. Demo auto-start CON-004; đóng panel để xem workspace rồi mở lại review. Badge **Dữ liệu minh họa · kiểm thử UI** luôn hiển thị. Approval/reject/supplement/negotiation mutations trả 409 có chủ đích; contract catalog chỉ có CON-004.

- Loading: thêm `?demo_api=slow` vào URL (delay 1,5s).
- Error: thêm `?demo_api=error` (503 có chủ đích).
- Mở URL thường để reset mode; cookie mode dùng chung trong browser profile. Dùng profile/tab testing riêng nếu đồng thời thử nhiều modes.
- Dừng preview bằng Ctrl+C, giữ Vite/backend nếu vẫn muốn kiểm thử thật. Port khác: `$env:OPC_UI_PREVIEW_PORT = "5175"` trước lệnh; Vite upstream vẫn 5173.
- `tools/ui-demo-preview.mjs` là development tooling; không bundle/import vào `frontend/src/`, không deploy như backend.

Các browser scripts `mercury-review.js`, `workspace-validation.js`, `live-smoke.js` có thể chạy qua Playwright CLI `run-code --filename` trong session đã mở đúng server. Live smoke khởi tạo một workflow thường, không approve; dùng DB riêng. Screenshots đã commit là evidence của lần review, không tự cập nhật khi đổi source.

## Checks và lỗi cần người phụ trách backend review

Frontend tại thời điểm bàn giao: **21 test files, 93 tests pass** (bản redesign ban đầu: 20 files, 77 tests); TypeScript/Vite build pass. Responsive, keyboard review và live smoke đã kiểm tra, không có screen-reader audit đầy đủ.

Backend: **481 passed, 4 failed / 485 tests**; Ruff **2 I001**. Python source/tests không thay đổi trong redesign; các failures đã quan sát trước lần bàn giao này. Không xem chúng là kiểm tra xanh hay tự sửa business semantics trong task UI.

| Test / check | Hiện tượng cần review |
|---|---|
| `tests/integration/test_decision_final_workflow.py::test_exact_decision_card_requires_founder_then_routes_to_negotiation` | Test kỳ vọng COMPLETED, workflow đang WAITING_FOR_INPUT |
| Cùng file: `test_con004_card_carries_one_precomputed_margin_negotiation_strategy` | Test kỳ vọng NEGOTIATION_IN_PROGRESS, nhận NEGOTIATION_TERMS_SENT sau final approval |
| `tests/unit/test_decision_openai_composer.py::test_openai_adapter_retries_ungrounded_numeric_free_prose` | Assertion chữ số trong executive summary không khớp output |
| `tests/unit/test_post_decision_release.py::test_external_proposal_rejects_non_accept_route` | Regex kỳ vọng không khớp message backend hiện hành |
| Ruff: `src/opc_mis/domain/case_workflow_models.py`, `src/opc_mis/governance/evidence_validator.py` | Import ordering I001 |

Chạy lại commands trong [style.md](../../style.md) trước mỗi bàn giao. Preview tooling có kiểm tra riêng: `node --test tools/ui-demo-preview.test.mjs` (API fixture, protected mutations, error/recovery, port guards; không cần FastAPI/Vite). Nếu lỗi mới xuất hiện, so sánh với baseline này; không che failure bằng cách skip test hoặc đổi assertion không có căn cứ.

## Scope Git của bản bàn giao

Commit gồm frontend source/tests, bundle FastAPI, design docs/style và screenshot/fixture tooling để tái hiện UI. Không có `.env`, DB runtime, API keys, node_modules, host-specific launcher/logs hoặc sửa workbook. Backend implementation đã có từ trước; commit UI không được mô tả là backend mới.

Tiếp tục bằng task UI nhỏ; không đổi lớn theme/layout hoặc API/backend trước khi owner review.
