# Bàn giao frontend — OPC MIS Contract Decision Workspace

Ngày rà soát: 08/10/2026 (cập nhật cùng ngày sau các task P1, bug Decision Card trên demo, P2 lịch sử workflow, đợt P1 detail coverage/form audit và đợt sửa lỗi UI từ browser review 09/10/2026, nhánh `feat/ui-polish`). Đây là bản UI đã triển khai để tiếp tục phát triển, chưa phải bản sản phẩm production hoàn chỉnh. Không đổi business logic/API/backend trong lần redesign này.

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
- Dialog chi tiết ([ArtifactDetailDialog.tsx](../../frontend/src/features/artifacts/ArtifactDetailDialog.tsx)) hiện loại artifact, `ID · vN · validation` và **Nguồn đầu vào** từ `input_artifact_ids`. Nhãn đủ 33 artifact types ở `shared/artifactLabels.ts`. Mọi type đều có renderer riêng, trừ `DECISION_CARD` (review riêng có guard).
- Khi playback timeline chưa bắt kịp projection, view Quyết định ghi rõ Decision Card **đã được tạo và đang chờ hiển thị** (`reveal_pending`), không còn báo "chưa sẵn sàng" như thể chưa có card. Gate playback giữ nguyên; reduced motion hiện ngay.
- Nhật ký quy trình ([WorkflowEvents.tsx](../../frontend/src/features/workspace/WorkflowEvents.tsx)) hiện nhãn tiếng Việt cho các `event_type` backend đang phát (`shared/eventLabels.ts`); mã/node chưa map hiện nguyên mã. Tải tăng dần bằng `after_sequence`, merge/dedupe theo `sequence`, reset khi đổi run, dừng poll sau một lần đọc bù khi projection terminal; lỗi giữ dữ liệu đã tải và retry từ cùng cursor.

Review và screenshots: [05_mercury_redesign_review.md](05_mercury_redesign_review.md). Quy tắc bắt buộc khi tiếp tục UI: [style.md](../../style.md). Các tài liệu 01/02/04 có phần kế hoạch lịch sử; **03, 05, 06 và style.md** mô tả bản hiện hành. Không dùng prompt forest cũ để redesign lần tiếp theo.

## Việc UI còn cần hoàn thành

Đây là backlog có thứ tự ưu tiên, không phải danh sách chức năng hoàn toàn chưa có. Không tự ý làm hết trong một PR lớn.

| Ưu tiên / việc | Evidence và file bắt đầu | Tiêu chí hoàn thành |
|---|---|---|
| ~~P1 — Đồng bộ các detail/form sâu với style mới~~ **Đã xong** | Inline styles đã bỏ ở `AssessmentViews.tsx`, `WorkflowArtifactViews.tsx`, `DocumentSupplementForm.tsx` (chỉ còn CSS custom property animation ở workflow). Precheck luôn ghi mô phỏng; form tài liệu không còn fallback hash/UUID cố định khi thiếu Web Crypto. `BankingAmountForm`/`PrecheckEvidenceForm` đã audit trên browser (desktop + 390px): không inline style; ô có `aria-invalid` có viền lỗi (`base.css`); nút submit trong dialog bổ sung dữ liệu không còn kéo full-width. Khung dialog dùng chung đã chuyển sang `--color-surface-muted`/`--color-line` (owner duyệt ảnh so sánh) | — |
| ~~P1 — Artifact detail coverage và lineage~~ **Đã xong** | Thêm `features/artifacts/DecisionTraceViews.tsx` + tests cho `APPROVAL_CHECKPOINTS`, `RISK_RULE_EVALUATION`, `DECISION_ROUTE_PLAN`, `DECISION_POST_BANKING_REVIEW`, `DOCUMENT_PREPARATION_REQUEST`, `AI_DECISION_ANALYSIS` (model lấy từ `src/opc_mis/domain`). 6 types này đứng cuối `ARTIFACT_PREFERENCE` nên lựa chọn milestone cũ không đổi; milestone "Lập Decision Card" giờ mở *Phân tích quyết định* (ghi rõ chưa phải quyết định Founder). Demo fixture có thêm rule evaluation, checkpoints, route plan và AI analysis đầy đủ hơn | Post-banking review và document preparation request chưa có trong fixture (fixture không có nhánh banking), chỉ verify bằng unit tests. `RiskPreScanView` vẫn chọn `APPROVAL_CHECKPOINTS` v1 theo heuristic vì backend không ghi upstream giữa pre-scan và checkpoint |
| P1 — Accessibility của dialogs/forms — **phần lớn đã xong** | `useDialogFocus` bám dialog modal trên cùng (kể cả khi dialog được thay thế), đặt `inert` cho nền, focus ban đầu vào dialog (không vào nút hành động), chặn Escape khi đang submit, trả focus về trigger hoặc `#workspace-content` bằng `preventScroll` (đóng dialog không còn cuộn header ra khỏi màn hình). Form số tiền/precheck gắn `aria-invalid` + `aria-describedby` với lỗi. Contrast các cặp token chữ/nền ≥ 4,5:1 | Chưa audit bằng screen reader thật (NVDA/VoiceOver) và zoom 200%; không công bố WCAG certification |
| P1 — Browser E2E của toàn workflow và edge cases — **tạm hoãn** | Owner quyết định **không thêm Playwright** (08/10/2026). Unit/regression tests đã có; screenshot fixture chỉ là một thời điểm final approval pending, live smoke chưa đi hết mọi branch | Cover banking/document waits, pause/resume, NOT_EVALUABLE, stale/replaced/resolved approval, duplicate submit, negotiation outcome và separate release gate bằng isolated fixtures/test backend; không dùng DB thật hoặc gọi external adapter |
| ~~P2 — Workflow history dễ đọc và tải hiệu quả hơn~~ **Đã xong** | Labels ở `shared/eventLabels.ts` (lấy từ các event mà orchestrators/runtime ghi); `api/client.ts#getWorkflowEvents`; polling theo `live` = projection chưa terminal, không suy trạng thái từ log | Còn lại: chưa hiển thị `metadata` của event; khi backend thêm event mới phải bổ sung label (mã lạ vẫn hiện nguyên) |
| P2 — Evidence table khi có nhiều artifacts | `features/workspace/ContractWorkspace.tsx`: chưa search/filter/paging | Filter/sort/search từ artifacts đã được API trả; preserve run scope/version. Empty filter state rõ; không biến thành document upload/search service mới |
| P2 — Navigation và component organization | Sidebar local views, không URL state; `App.tsx` vẫn chứa nhiều interaction wiring; brand link `/dashboard` cần kiểm tra cả Vite base và FastAPI | Kiểm tra reload/back/brand trên cả hai server; chỉ thêm URL/view state khi có scope. Tách shell/interaction presentation với tests giữ handlers/guards, không đổi API để phục vụ layout |
| P2 — Responsive/state polish — **một phần đã xong** | Đã kiểm tra 390/768/1440/1920px ở views chính. Đợt 09/10/2026: khôi phục CSS bị mất từ redesign Mercury cho tab Quy trình (overview, business status, stage list, milestone grid, hai lane song song có nhánh) và Dữ liệu đầu vào (panel readiness, linked counts, requirements, counters, empty state), `Notice` có mark, `LoadingBlock` hiện skeleton + nhãn thay vì span inline style vô hình. Đổi local view đưa trang về đầu (`shared/useScrollTopOnChange.ts`), focus giữ nguyên. Nút × nằm trong banner lỗi; mã hợp đồng ở tiêu đề không ngắt tại dấu gạch; tab strip mobile có bóng mép gợi ý cuộn; footer Decision Card dialog sticky ≤760px. Class còn lại không có selector (`workflow-panel`, `evidence-index`, `assessment-dialog`, `modal-card__body`, `assessment-fact-grid`, `status-badge--neutral`) là hook, layout do class cha đảm nhận. Chưa audit mọi dialog/form và chuỗi text dài | Kiểm tra zoom 200%, long IDs/text, loading/empty/error/warning/failed-safe/stale và pending/resolved; không tràn trang hoặc mất hành động |

Gợi ý task tiếp theo: P1 code-level đã xong; E2E tạm hoãn vì owner không thêm Playwright, accessibility còn lại cần kiểm thử thủ công bằng screen reader thật (NVDA/VoiceOver). Khi owner mở lại P2: **Evidence table** search/filter/sort. Mỗi task nhỏ nên có before/after và nêu rõ ảnh dùng dữ liệu thật hay fixture.

Ghi nhận từ browser review 09/10/2026, **cần owner quyết định trước khi làm** (không thuộc task sửa lỗi): empty state riêng cho từng tab; đổi tên mục "Hồ sơ & bằng chứng" (đang đếm Đánh giá: 5, Bằng chứng: 9); thống nhất ngôn ngữ Anh/Việt trong nhãn.

Đã giải quyết: demo fixture từng hiện "Decision Card của lượt chạy hiện tại chưa sẵn sàng" ~8 giây đầu. Không do fixture hay `normalize.ts` (card `available: true` được map đúng) mà do `App.tsx` ẩn card trong lúc playback timeline chạy từng mốc 1 giây, còn `DecisionDashboard` dùng chung câu "chưa sẵn sàng" cho cả hai trường hợp.

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

Frontend tại thời điểm bàn giao: **23 test files, 121 tests pass** (bản redesign ban đầu: 20 files, 77 tests); TypeScript/Vite build pass. Responsive, keyboard review và live smoke đã kiểm tra, không có screen-reader audit đầy đủ.

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
