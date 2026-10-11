# UI-first preview — Checkpoint 1

11/10/2026 · baseline HEAD `707f58a` sau PR #3 · **đã triển khai frontend preview, chờ owner review bằng browser**. Không commit/push. Backend/API/database/TeamPack/business logic không thay đổi; bundle trong `src/opc_mis/api/static/react/` được sinh bởi Vite, không sửa tay.

## Mở và trải nghiệm

Server Vite local đang được giữ hoạt động:

- [Dashboard](http://127.0.0.1:5173/dashboard-assets/?preview=1#/dashboard)
- [Company Overview](http://127.0.0.1:5173/dashboard-assets/?preview=1#/company)
- [Contracts](http://127.0.0.1:5173/dashboard-assets/?preview=1#/contracts)
- [CON-004](http://127.0.0.1:5173/dashboard-assets/?preview=1#/contracts/CON-004)

Preview không cần backend. Khi mở URL không có `preview=1`, connected workspace cũ vẫn gọi API thật theo cấu hình đã có; đây là hai chế độ riêng. Không có API mới trong checkpoint này.

Thử navigation bên trái, tabs Company, lọc/search Contracts, chọn CON-004, mở assessment/evidence/Decision Review. Biểu đồ cho phép đổi kỳ, bật/tắt series, xem tooltip bằng chuột hoặc phím mũi tên, chuyển bảng số liệu; chart hợp đồng drill-down sang workspace, legend order lọc bảng. KPI Open invoices mở Company/Hóa đơn đúng filter. Thử dropdown **Trạng thái preview** cho loading/empty/error/retry; trong review chọn pending/stale/resolved. CON-001 minh họa NOT_EVALUABLE; CON-002 thử form bổ sung; CON-003 không có run; CON-005 minh họa failed-safe.

Nút phê duyệt/từ chối trong review và submit form **chỉ hiện thông báo local**, không gửi request, không resolve approval backend, không patch dữ liệu, không resume workflow. Giữ đúng recommendation ≠ approved decision; precheck mô phỏng không ràng buộc; external release là gate riêng và preview không gửi hồ sơ.

Chạy lại trên máy khác, từ `frontend/`:

```powershell
npm ci
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Mở URLs phía trên; log hiện ở terminal, dừng bằng Ctrl+C. Server hidden được khởi chạy trong lần review này lưu stdout/stderr và PID ở `C:/Users/Paul/.codex/visualizations/2026/10/08/01a11a07-e0d5-7402-9591-082b8890b399/ui-first-preview/`. PID lúc bàn giao là `16464`; trước khi dừng phải kiểm tra process còn là Vite của workspace, không dừng một process khác đã tái sử dụng PID.

## Bố cục và components

| Khu vực | Pattern đã triển khai | Vì sao |
|---|---|---|
| Shell | Sidebar 3 mục, breadcrumb topbar, badge minh họa, navigation mobile, hash/deep links | Tách cấp công ty khỏi workspace từng hợp đồng, giữ back/forward/reload |
| Dashboard | Action list trước, attention contracts bên cạnh; KPI strip không lồng cards; một chart projection bên dưới | Founder nhìn việc tiếp theo trước khi đọc phân tích |
| Company | 5 tabs: Tổng quan, Tài chính, Hợp đồng & đơn hàng, Hóa đơn, Cảnh báo & giới hạn | Drill-down theo đối tượng; snapshot context xuyên suốt, không nhồi mọi phân tích vào Home |
| Charts | Line in/out, closing/reserve, horizontal bars contract/invoice, donut orders | Đồ thị đủ cho visual review, có table/legend/tooltip/filter và scope/unit/source |
| Contracts | Lightweight list, search/status filter, contract picker, 5 tabs | Source status tách workflow state; no-run khác completed; không tự start run |
| Decision | Full-width proposal summary, current identity, qualitative confidence, review modal | Đề xuất dễ đọc, không fixed-right card hoặc one-click approval |
| Assessments/evidence | Compact rows, reusable typed detail renderers, searched artifact table và upstream lineage | Không bỏ version/identity/validation để đổi visual |
| History / async | Mock events không timestamp giả, loading/empty/error/retry; stale/resolved review | Có trạng thái để thử tương tác, ghi rõ nguồn minh họa |

Không có authentication, notifications, transfers, settings hoặc chức năng ngân hàng Mercury. Workflow canvas chưa làm, tab hiện đúng checkpoint tiếp theo.

## Design tokens

Reuse [tokens.css](../../frontend/src/styles/tokens.css), scoped additions ở [preview.css](../../frontend/src/preview/preview.css).

| Token / nhóm | Giá trị |
|---|---|
| Surface / canvas / muted | `#FFFFFF` / `#FDFDFD` / `#F7F8FA` |
| Lavender surface / current accent | `#F0F1FC` / `#536EF1` |
| Primary text / secondary / metadata | `#292B35` / `#656771` / `#6C707A` |
| Light line / control line | `#EDEEF1` / `#D5D7DF` |
| Preview CTA / hover | `--pv-action-primary: #4C63DD` / `#4358C6` |
| Chart series | `#6266D9`, `#858CBB`, `#7C8599`, `#AD805B`, `#758E96` |
| Sidebar / header / content | 224px desktop, 190px ≤1200; 76px header, 64px mobile; max content 1280px |
| Typography / radius / spacing | Segoe UI/system; title 25–28px, body 13–14px, secondary 11–12px; tabular numeric; 6/10/12px radii; 4px rhythm |

Preview CTA tăng contrast chữ trắng lên 5.08:1; metadata 4.96:1 trên trắng; chart series 3.25–4.75:1 trên trắng. Các controls có label/keyboard/table alternative; đây không phải chứng nhận WCAG. Chưa chạy screen reader thật hoặc browser zoom 200%; đã kiểm tra CSS viewport tương đương 720px, không mô tả nó là kiểm thử browser zoom thật.

So với Mercury references: giữ white/cool-neutral shell, lavender accents, charcoal hierarchy, minimal borders, flat panels và lightweight tables. Số mục navigation ít hơn vì nghiệp vụ OPC; không copy banking search/transfer/user avatar. Snapshot và governance copy làm màn hình dài hơn. Review giữ dialog có focus trap/sticky footer của OPC, chưa đổi thành floating panel giống ảnh reference 3. Font là Segoe UI hiện có, không giả dùng proprietary Mercury font. Charts dùng đường tuyến tính để giữ ý nghĩa dữ liệu theo kỳ, không thêm decorative smoothing/gradient.

## Dữ liệu minh họa và integration boundary

| Preview data | Nguồn hiện tại / giới hạn | API cần sau duyệt |
|---|---|---|
| Company/profile/KPIs/cash series/distributions | Typed fixtures, không đọc workbook; KPI arrays đã được compose trong fixture, UI chỉ format/filter. Cùng company snapshot; không tính tổng OPC_GLOBAL qua contract/run | Snapshot/overview/records read layer trong [11](11_api_gap_analysis.md), mapping D7–D10/C1–C10 trong [10](10_data_to_ui_mapping.md) |
| Actions/attention/status/run refs | Fixture request/run IDs, không queue/projection thật hoặc freshness verification | Executive overview/actions + contract/run read index |
| Contract list | 5 fixture contracts; source fields và workflow status riêng | Contract overview metadata; `/api/contracts` hiện chỉ catalog IDs |
| Assessment/card/artifacts | Fixtures theo presentation interfaces có sẵn; kể cả OpenAI/VALID là nhãn fixture. Không có model hoặc Evidence Validator thật | Reuse exact selected-run projections + artifact envelopes; không lấy latest case artifact ngầm |
| Review / supplement | Local UI feedback, các guard hiện hành reuse; không business mutation | Khi tích hợp mới dùng existing guarded handlers và revalidation, không thêm API approvals khác |
| History | Các event names minh họa, không audit timestamps thật | Existing incremental events API với đúng run/cursor |
| Workflow | Chưa có canvas/topology fixture ở checkpoint 1 | Checkpoint 2 preview trước; canonical graph read adapter/API sau duyệt |

`preview/data.ts` expose read-model context; `models.ts` là presentation types, không public schemas. Default provider là `fixtures.ts`, lazy-loaded chỉ trong preview. Đây là seam cho API adapter tương lai; không chỉ bỏ badge để biến fixture thành production. Không tự triển khai các endpoints còn thiếu. Backend gates tại tài liệu 10/11 vẫn còn nguyên.

## Validation và screenshots

Frontend: **134 tests / 24 files**, gồm 121 tests hiện hữu và 13 preview tests; `npm run build` đạt. Preview tests bao gồm no-fetch invariant, action filter, invoice/contract search, URL state, chart table/missing period, exact/stale/resolved request, duplicate local submit, NOT_EVALUABLE, lineage, input validation và async states.

Browser automation với Playwright CLI, không thêm `@playwright/test` vào repository: navigation/back/forward/reload; chart keyboard tooltip/legend/table/period/drill-down/order filter; exact review/Tab focus trap/Escape; stale/resolved/NOT_EVALUABLE; form invalid/local success; mobile navigation; reduced motion. Các lượt audit cuối ghi nhận **0 runtime errors và 0 `/api/` requests**. Screens 390/1440/1920 đều không tràn document; kiểm tra thêm 768px và 720px CSS viewport. Bảng vẫn có vùng cuộn ngang focusable, không làm mất source/identity/action.

Screenshots thực tế từ Vite, toàn bộ dữ liệu minh họa:

| Page | Desktop | Mobile |
|---|---|---|
| Dashboard | [1440](../../output/playwright/ui-first-dashboard-1440.png) · [1920](../../output/playwright/ui-first-dashboard-1920.png) | [390](../../output/playwright/ui-first-dashboard-390.png) |
| Company | [1440](../../output/playwright/ui-first-company-1440.png) · [1920](../../output/playwright/ui-first-company-1920.png) | [390](../../output/playwright/ui-first-company-390.png) |
| Contracts | [1440](../../output/playwright/ui-first-contracts-1440.png) · [1920](../../output/playwright/ui-first-contracts-1920.png) | [390](../../output/playwright/ui-first-contracts-390.png) |
| Decision workspace | [1440](../../output/playwright/ui-first-decision-1440.png) · [1920](../../output/playwright/ui-first-decision-1920.png) | [390](../../output/playwright/ui-first-decision-390.png) |
| Decision Review | [1440](../../output/playwright/ui-first-review-1440.png) | [390](../../output/playwright/ui-first-review-390.png) |

Browser scripts/results nằm trong `output/playwright/ui-first-*`. Sau đối chiếu 3 Mercury ảnh, đã sửa entrypoint Fast Refresh gây duplicate root, mobile table SR-label gây document overflow, label artifact khi filter Risk và tăng contrast CTA/metadata/series. Không dùng screenshot để thay browser demo.

Repository checks đã chạy: Ruff **2 I001** ở `domain/case_workflow_models.py`, `governance/evidence_validator.py`; pytest **481 passed / 4 failed / 1 warning**, cùng baseline sau PR #3:

- `test_exact_decision_card_requires_founder_then_routes_to_negotiation`
- `test_con004_card_carries_one_precomputed_margin_negotiation_strategy`
- `test_openai_adapter_retries_ungrounded_numeric_free_prose`
- `test_external_proposal_rejects_non_accept_route`

Không auto-fix backend để làm UI tests xanh. Vitest bị EPERM rename cache và pytest bị treo khi chạy trong Windows sandbox lần đầu; đã chạy lại ngoài sandbox để lấy kết quả thật. Dependency production audit `npm audit --omit=dev --json`: 0 vulnerabilities; install output còn 6 advisories thuộc dev tree, không chạy audit fix/force hoặc nâng cấp toolchain ngoài scope.

## Điểm review trước checkpoint 2

Founder đã duyệt IA/bố cục của ba trang Checkpoint 1. Vòng polish tiếp theo và screenshots mới nằm ở [14_visual_refinement_review.md](14_visual_refinement_review.md); giữ ảnh bên trên làm baseline before. Chờ review cuối, chưa triển khai Workflow Viewer.

Review ba trang ở browser: hierarchy/action-first, mật độ thông tin, chart labels/filters, Company section boundaries, Contracts detail và Decision Review desktop/mobile. Sau feedback mới tinh chỉnh visual hoặc mở Dify canvas; không đi trước bằng backend integration. Roadmap mới nằm ở [12](12_revised_implementation_roadmap.md).
