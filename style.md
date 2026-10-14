# Frontend style guide — Contract Decision Workspace

> Tiếp quản sau Checkpoint 2: [handoff hiện hành 16](docs/ui-design/16_frontend_handoff_checkpoint2.md), gồm source map, preview/live boundaries, setup, Git inventory và backlog. [Handoff 06](docs/ui-design/06_frontend_handoff.md) giữ chi tiết connected UI baseline.

> Cập nhật 11/10/2026: **Executive Home + Drill-down có preview cô lập** trong `frontend/src/preview/`, bật bằng `?preview=1`. Xem [checkpoint 13](docs/ui-design/13_ui_first_preview_checkpoint.md). Navigation single-contract phía dưới mô tả connected UI baseline PR #3 khi không bật preview. Preview global shell có ba mục và hash routes; dữ liệu/biểu đồ hoàn toàn là fixtures có nhãn, không phải API mới hoặc historical data thật. Tokens/conventions/governance guards dùng chung.

> Cập nhật 13/10/2026: owner chuyển visual language từ Mercury sang **Dify** cho cả connected UI và preview. Nghiên cứu, mapping token và các điều chỉnh contrast: [18_dify_design_language.md](docs/ui-design/18_dify_design_language.md). Cấu trúc thông tin, navigation và mọi guard bên dưới không đổi.

Hướng dẫn cho người và agents tiếp tục UI. Đọc [AGENTS.md](AGENTS.md) trước; backlog và cách chạy nằm trong [frontend handoff](docs/ui-design/06_frontend_handoff.md). Design system chi tiết: [18_dify_design_language.md](docs/ui-design/18_dify_design_language.md) (hiện hành); [03_design_system.md](docs/ui-design/03_design_system.md) là bản Mercury lịch sử.

## Hướng thiết kế hiện hành

**Dify cho visual language, Linear cho tổ chức thông tin.** Giao diện là workspace của **một hợp đồng đang chọn**: trạng thái → đề xuất → kết quả đánh giá → bằng chứng → bước Founder cần làm. Không trở lại theme forest/emerald, Mercury periwinkle hoặc layout dashboard ba cột trước đây.

- Canvas xám `#F2F4F7` cho cả trang và sidebar (không kẻ giữa); nội dung nằm trong panel trắng bo 12px, `shadow-xs`; accent xanh điện `#0033FF`; divider alpha mảnh.
- Sidebar kiểu Dify main nav: workspace card trắng, item 32px bo 10px, item chọn là nền "blue glass" (`--nav-active-surface`). Một lớp panel; panel lồng bên trong dùng `--color-surface-muted` và không thêm shadow.
- Nhãn section, eyebrow, header bảng và nhãn metric dùng uppercase 12px medium màu tertiary; filter/phase dùng segmented control; tabs gạch chân accent.
- Decision Card là đối tượng cần đọc và xem xét. CTA ở workspace mở review; approval/rejection ở dialog khớp đúng yêu cầu hiện hành.
- Sidebar và navigation mobile hiện dùng local views: Quyết định, Đánh giá, Bằng chứng, Quy trình, Dữ liệu đầu vào. Chưa có router, URL deep linking hoặc portal nhiều hợp đồng.
- Copy tiếng Việt đủ dấu; giữ tên Finance, Operations, Risk, Decision Card khi hữu ích. Không dùng emoji làm icon.

## Tokens và nhịp layout

Nguồn duy nhất cho màu/spacing/font là `frontend/src/styles/tokens.css`. Dùng `var(...)` trong CSS mới; không chép literal màu vào từng component.

| Vai trò | CSS token | Giá trị hiện tại |
|---|---|---|
| Canvas / surface | `--color-canvas` / `--color-surface` | `#F2F4F7` / `#FFFFFF` |
| Surface phụ / accent nhạt | `--color-surface-muted` / `--color-accent-soft` (= `--color-lavender`) | `#F9FAFB` / `#EEF4FF` |
| Accent / CTA hover | `--color-primary` / `--color-primary-strong` | `#0033FF` / `#002CDE` |
| Text chính / phụ / nav / tertiary | `--color-ink-950` / `--color-ink-800` / `--color-ink-600` / `--color-ink-450` | `#101828` / `#354052` / `#495464` / `#676F83` |
| Divider / control border | `--color-line` / `--color-line-strong` | `rgb(16 24 40 / .08)` / `rgb(16 24 40 / .14)` |
| Input nền / hover state | `--color-input-bg` / `--color-state-hover` | `rgb(200 206 218 / .25)` / `rgb(200 206 218 / .2)` |
| Success | `--color-green-700` / `--color-green-100` | `#067647` / `#ECFDF3` |
| Warning | `--color-amber-700` / `--color-amber-100` | `#B54708` / `#FFFAEB` |
| Error | `--color-red-700` / `--color-red-100` | `#B42318` / `#FEF3F2` |

- Font: `--font-sans` (system stack như Dify: -apple-system, Segoe UI, Roboto…), `--font-mono` cho ID. Số liệu dùng `font-variant-numeric: tabular-nums`.
- Spacing: bước 4px, ưu tiên `--space-1` tới `--space-10`; section padding thường 24px.
- Radius: `--radius-sm/md/lg/xl` = 6/8/12/16px (badge / button–input / panel / dialog–workflow block). Không phủ pill lên mọi control.
- Shadow: `--shadow-xs` cho panel/button, `--shadow-lg` cho popover/tooltip, `--shadow-xl` cho dialog; `--shadow-primary-button` chỉ cho CTA primary.
- Control cao 32px, chữ 13px medium; input nền xám, focus nền trắng + viền `--color-input-border-active`, luôn giữ outline focus 2px accent.
- Sidebar desktop 240px, 200px dưới 1100–1200px; header 56px; workspace max-width 1160px, padding desktop 32px. Dưới 760px dùng navigation ngang và content stack theo CSS hiện hành.
- `--color-emerald-*`, `--color-blue-*` và `--color-lavender` là alias tương thích cho component cũ, trỏ về accent. Code mới dùng `--color-primary`/`--color-accent-soft`. Green chỉ dùng ngữ nghĩa, không làm theme.
- Chữ trạng thái dùng bậc 700 (contrast ≥4,5:1), chấm status/legend có thể dùng bậc 500 khi đi kèm nhãn chữ.
- **Dark mode**: giá trị dark chỉ nằm trong `:root[data-theme="dark"]` ở `tokens.css`; không viết selector dark trong component. `--color-primary` chỉ làm nền (nút, brand mark); chữ/icon/viền/focus dùng `--color-accent`. Không viết literal `rgb(...)`/hex trong component CSS: thêm token kèm giá trị dark và kiểm tra contrast ở cả hai theme. Theme do `ThemeSwitcher` chọn, lưu `localStorage` của trình duyệt, không phải setting backend. Chi tiết: [18](docs/ui-design/18_dify_design_language.md#dark-mode).
- Không tự suy ra tên token như `--color-red-650`: kiểm tra token tồn tại trước khi dùng.

## Component và code conventions

### UI-first preview

Refinement Checkpoint 1: xem [visual review 14](docs/ui-design/14_visual_refinement_review.md). Hierarchy (cập nhật theo Dify 13/10/2026): page heading desktop 24px (mobile 20px), metric 26px, body/table 14px, controls/copy phụ 13px, metadata/chips/legends 12px; mobile table 13px. Dùng `--pv-text-body/control/meta`, không giảm metadata xuống 10–11px để nhồi nội dung. Tiền đầu vào vẫn VND: chart/tóm tắt hiển thị tỷ VND tối đa 2 chữ số thập phân, tooltip có VND đầy đủ; header bảng phải khớp đơn vị. Không tính lại nghiệp vụ. Contract row shortcut phải giữ native links, không chặn modified click hoặc text selection; wrapper phải chuyển tiếp accessible name cho icon links.

- `preview/PreviewEntry.tsx` lazy-load preview; `main.tsx` chỉ mount một root, không đặt lazy component boundary trong bootstrap để tránh entrypoint bị Fast Refresh chạy lại.
- `preview/data.ts` là read-model context, fixtures ở `preview/fixtures.ts`, presentation types ở `preview/models.ts`. Components đọc provider; không import production API clients/hooks, không tạo writes. API adapter tương lai là checkpoint riêng, cần approved schema/provenance/run binding.
- `preview/navigation.ts` giữ hash route/page/section/contract/period/request. Link dùng native anchors, `aria-current`; không ghi đè run/request bằng lựa chọn mặc định. Preview không thay connected navigation.
- CSS `pv-*` scoped dưới `.pv-app`, reuse tokens trong `tokens.css`. Không dùng fixture styles để thay business guards. Chart colors/CTA bổ sung là presentation tokens trong `preview.css`, xem bảng ở checkpoint 13; màu nhạt dùng surface, màu series có contrast ≥3:1 trên trắng; CTA trắng/primary ≥4.5:1.
- Recharts 3.10.1 là dependency đã được user cho phép cho preview; không thêm UI framework/router. Mỗi chart có tooltip/unit/source, table alternative và controls; không dựa vào màu để thao tác. Native bảng có caption và vùng cuộn focusable, giữ scrollbar trong container ở mobile.
- Decision/artifact dialogs reuse components hiện hành với optional `context` slot để đặt disclaimer/preview controls **bên trong focus trap**. Exact artifact/version/current/request/source/NOT_EVALUABLE guards không đổi. Context không thay approval logic.
- Mock submit chỉ hiện thông báo local, không resolve request như kết quả thật, không patch/resume/external release. Preview badge phải hiện xuyên suốt; mock labels không được bỏ khi chưa kết nối và xác minh API thật.
- Workflow tab có viewer chỉ đọc của Checkpoint 2 trong `frontend/src/preview/workflow/`: React Flow, typed topology/fixtures, phase navigation, inspector và mobile list. Xem [review 15](docs/ui-design/15_workflow_viewer_checkpoint.md). Không nối preview với API client, không dùng event order để dựng edges, không thêm editor/run-node/approval actions. Hai gate presentation dùng `APPROVAL_GATE` phải giữ nhãn instance, không trình bày như persisted node ID mới.
- Workflow scenarios là snapshot minh họa riêng, ID chứa contract + scenario. Không ghi đè contract status, Decision Card hay approval request của workspace. `not-applicable` là applicability, không phải `WorkflowNodeStatus`; unknown không đồng nghĩa bị skip. Output chưa hoàn tất không được hiển thị như artifact đã validation. Giữ exact ID/version/action binding khi tích hợp sau duyệt.

| Nơi | Trách nhiệm |
|---|---|
| `frontend/src/app/App.tsx` | Shell, chọn view, mở interaction phù hợp; tránh thêm nghiệp vụ vào đây |
| `frontend/src/app/dashboardIntegration.ts` | Ánh xạ API/artifact sang presentation và identity guards |
| `frontend/src/api/` | DTO, normalization, HTTP client, lifecycle của workflow |
| `frontend/src/features/workspace/` | Metrics, assessment rows, evidence table, limits, event log |
| `frontend/src/features/artifacts/` | Typed detail renderers; mở đúng artifact và giữ lineage |
| `frontend/src/features/decision/` | Recommendation summary và Decision Card review |
| `frontend/src/features/governance/`, `missing-data/`, `negotiation/` | Interaction đã có, giữ payload/handlers |
| `frontend/src/shared/` | Labels, formatting, status, notice, focus hook |
| `frontend/src/styles/` | Tokens → base semantics → workspace/component styles |

- React function components + TypeScript; colocate test cạnh feature. Không thêm UI library/router/framework nếu chưa có yêu cầu.
- Tách component theo trách nhiệm và pattern thực sự dùng lại. Dùng class có tên rõ; thay inline styles cũ từng phần, không refactor nghiệp vụ để đạt visual consistency.
- Reuse `section-heading`, `table-scroll`, `evidence-table`, `primary-action`, `Notice`, `StatusBadge` khi phù hợp. Bảng dùng `table/th/td`, metrics dùng `dl`, thao tác dùng native `button`.
- Dữ liệu async có loading, empty, error và retry/cập nhật lại hợp lý; không render placeholder như kết quả thật. Hủy request khi đổi run/unmount.
- Focus-visible luôn rõ; icon-only action có accessible name; dialog có tên, trap/restore focus và Escape. Không lấy hover làm cách duy nhất để biết thông tin hoặc thực hiện hành động.
- Bảng rộng cuộn trong container; tránh tràn ngang toàn trang. Kiểm tra 390/768/1440/1920px và reduced motion. Responsive không được làm mất identity hoặc nút review.

## Những ranh giới không được thay đổi để làm UI đẹp hơn

1. Dashboard projection là nguồn trạng thái. Playback chỉ trình bày; không suy diễn trạng thái từ animation, phần trăm hay thời gian chờ.
2. Giữ workflow run, artifact ID/version, validation và upstream lineage. Không chọn artifact mới nhất của toàn case khi request chỉ định một version khác.
3. Recommendation khác approved decision; execution COMPLETED khác rủi ro thấp. Không dùng green chỉ vì task đã chạy xong.
4. Approval phải khớp request/action/subject/version và chưa resolved; giữ stale, NOT_EVALUABLE, source verification và duplicate-submit guards. Không thêm one-click approval trên dashboard.
5. Final decision approval khác external-release approval. Precheck là `SIMULATED_NON_BINDING`; prototype không gửi tài liệu hay tạo receipt. Không thêm nút chuyển tiền/gửi ngân hàng.
6. Browser chỉ format số theo unit/scope hiện có, không tính lại margin/risk/finance; phân biệt null với zero. Không thêm Risk Score, confidence phần trăm, historical charts hoặc KPI không có nguồn.
7. Không thêm auth/profile/notifications/settings như thể backend đã hỗ trợ. Không hard-code CON-004 hoặc kết quả demo vào `frontend/src/`.
8. UI fixture và screenshots synthetic luôn ghi **Dữ liệu minh họa**. `source: OPENAI` trong fixture không chứng minh đã gọi OpenAI. Fixture chỉ nằm trong development tooling, không import vào production bundle.

## Kiểm tra trước khi bàn giao

```powershell
cd frontend
npm.cmd test -- --run
npm.cmd run build
cd ..
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\python.exe -m pytest -q
```

Build Vite hiện ghi vào `src/opc_mis/api/static/react/`: commit bundle cùng source khi UI thay đổi, không sửa bundle bằng tay. Kiểm tra Git chỉ có file dự định; không commit `.env`, API key, DB runtime, node_modules hay browser traces/logs.

Với thay đổi interaction/data binding, thêm regression test cho hành vi quan trọng: current artifact/version, stale/resolved request, duplicate submit, NOT_EVALUABLE, pause/resume, negotiation và release boundary. Với chỉnh spacing nhỏ, visual/browser verification là đủ; không viết test mirror CSS. Báo riêng test failures đã tồn tại, không bỏ qua chúng hoặc đổi backend trong task UI để làm test xanh.
