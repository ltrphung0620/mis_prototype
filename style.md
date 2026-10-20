# Frontend style guide — Contract Decision Workspace

> Tiếp quản sau Checkpoint 2: [handoff hiện hành 16](docs/ui-design/16_frontend_handoff_checkpoint2.md), gồm source map, preview/live boundaries, setup, Git inventory và backlog. [Handoff 06](docs/ui-design/06_frontend_handoff.md) giữ chi tiết connected UI baseline.

> Cập nhật 11/10/2026: **Executive Home + Drill-down có preview cô lập** trong `frontend/src/preview/`, bật bằng `?preview=1`. Xem [checkpoint 13](docs/ui-design/13_ui_first_preview_checkpoint.md). Navigation single-contract phía dưới mô tả connected UI baseline PR #3 khi không bật preview. Preview global shell có ba mục và hash routes; dữ liệu/biểu đồ hoàn toàn là fixtures có nhãn, không phải API mới hoặc historical data thật. Mercury tokens/conventions/governance guards được giữ.

Hướng dẫn cho người và agents tiếp tục UI. Đọc [AGENTS.md](AGENTS.md) trước; backlog và cách chạy nằm trong [frontend handoff](docs/ui-design/06_frontend_handoff.md). Design system chi tiết: [03_design_system.md](docs/ui-design/03_design_system.md).

## Hướng thiết kế hiện hành

**Mercury cho visual language, Linear cho tổ chức thông tin.** Giao diện là workspace của **một hợp đồng đang chọn**: trạng thái → đề xuất → kết quả đánh giá → bằng chứng → bước Founder cần làm. Không trở lại theme forest/emerald hoặc layout dashboard ba cột trước đây.

- Nền trắng/cool neutral, chữ charcoal, accent periwinkle/lavender; border và shadow nhẹ.
- Sidebar compact; nội dung rộng; section và bảng nhẹ thay vì nhiều card lồng nhau.
- Decision Card là đối tượng cần đọc và xem xét. CTA ở workspace mở review; approval/rejection ở dialog khớp đúng yêu cầu hiện hành.
- Sidebar và navigation mobile hiện dùng local views: Quyết định, Đánh giá, Bằng chứng, Quy trình, Dữ liệu đầu vào. Chưa có router, URL deep linking hoặc portal nhiều hợp đồng.
- Copy tiếng Việt tự nhiên, đủ dấu, dành cho người không có kiến thức chuyên môn. Dùng Tài chính, Vận hành, Rủi ro, Ngân hàng, Hồ sơ, Quy trình và Phiếu đề xuất quyết định. Không dùng emoji làm icon.

### Wording được duyệt ngày 20/10/2026

- Chỉ đổi nhãn hiển thị; giữ nguyên enum, trạng thái, action, payload, ID và phiên bản trong API/database.
- Dùng **Giá trị ghi nhận**, **Tổng quan công ty**, **Lần xử lý**, **Nguồn gốc dữ liệu**, **Trạng thái xử lý**. Kỳ snapshot là **Kỳ dữ liệu**; chỉ dùng **Kỳ ghi nhận** nếu đã xác minh đúng nghiệp vụ.
- Hóa đơn: `Paid` → **Đã thanh toán**, `Open` → **Đang mở**, `Not issued` → **Chưa phát hành**. Không suy diễn thanh toán thực tế, quá hạn hoặc doanh thu từ nhãn nguồn.
- Các trạng thái nguồn dùng chung `shared/sourceLabels.ts` trong bảng, bộ lọc và biểu đồ. Giá trị bộ lọc và URL vẫn là mã gốc. Tìm bằng chứng hỗ trợ tên tiếng Việt cùng với mã tra cứu.
- Gỡ giới thiệu “Bản xem trước giao diện” và diễn giải mock/fixtures/backend khỏi UI chính. Giữ nhãn ngắn **Dữ liệu mô phỏng** xuyên suốt, thêm thông báo **Kết quả mô phỏng** trong hộp thoại liên quan. Không gọi dữ liệu mô phỏng là dữ liệu thực hoặc thông báo đã lưu/phê duyệt/gửi thật.
- Các bộ chọn tình huống kiểm thử chỉ hiện khi thêm `&ui_test=1` bên cạnh `?preview=1`, trước dấu `#`. Đây là công cụ kiểm thử trình bày, không phải phân quyền hoặc cơ chế bảo vệ hành động.
- Đổi bộ lọc, kỳ dữ liệu, vùng sơ đồ hoặc mở/đóng yêu cầu không cuộn cả trang về đầu. Chuyển trang/tab/hợp đồng mới cuộn về đầu. Giữ kỳ dữ liệu giữa các tab công ty; tab đang chọn phải nằm trong vùng cuộn ngang của thanh tab mobile.

## Tokens và nhịp layout

Nguồn duy nhất cho màu/spacing/font là `frontend/src/styles/tokens.css`. Dùng `var(...)` trong CSS mới; không chép literal màu vào từng component.

| Vai trò | CSS token | Giá trị hiện tại |
|---|---|---|
| Canvas / surface | `--color-canvas` / `--color-surface` | `#FDFDFD` / `#FFFFFF` |
| Surface phụ / lavender | `--color-surface-muted` / `--color-lavender` | `#F7F8FA` / `#F0F1FC` |
| Accent / CTA | `--color-primary` / `--color-primary-strong` | `#536EF1` / `#4358C6` |
| Text chính / phụ | `--color-ink-950` / `--color-ink-600` | `#292B35` / `#656771` |
| Border nhẹ / control | `--color-line` / `--color-line-strong` | `#EDEEF1` / `#D5D7DF` |
| Success | `--color-green-700` / `--color-green-100` | `#237555` / `#E8F3EE` |
| Warning | `--color-amber-700` / `--color-amber-100` | `#8C641B` / `#FBF3E2` |
| Error | `--color-red-700` / `--color-red-100` | `#B23C50` / `#FBEEF0` |

- Font: `--font-sans` (Segoe UI + system fallback), `--font-mono` cho ID. Số liệu dùng `font-variant-numeric: tabular-nums`.
- Spacing: bước 4px, ưu tiên `--space-1` tới `--space-10`; section padding thường 24px.
- Radius: `--radius-sm/md/lg` = 6/10/12px. Không phủ pill lên mọi control.
- Sidebar desktop 224px, 190px dưới 1100px; header 76px; workspace max-width 1160px, padding desktop 40px. Dưới 760px dùng navigation ngang và content stack theo CSS hiện hành.
- `--color-emerald-*` và `--color-blue-*` là alias tương thích cho component cũ, hiện trỏ về periwinkle. Không dùng alias đó làm brand token trong code mới. Green chỉ dùng ngữ nghĩa, không làm theme.
- Không tự suy ra tên token như `--color-red-650`: kiểm tra token tồn tại trước khi dùng.

## Component và code conventions

### UI-first preview

Refinement Checkpoint 1: xem [visual review 14](docs/ui-design/14_visual_refinement_review.md). Giữ hierarchy đã duyệt: heading/metric desktop 28px, body/table 14px, controls/copy phụ 13px, metadata/chips/legends 12px; mobile table 13px. Dùng `--pv-text-body/control/meta`, không giảm metadata xuống 10–11px để nhồi nội dung. Tiền đầu vào vẫn VND: chart/tóm tắt hiển thị tỷ VND tối đa 2 chữ số thập phân, tooltip có VND đầy đủ; header bảng phải khớp đơn vị. Không tính lại nghiệp vụ. Contract row shortcut phải giữ native links, không chặn modified click hoặc text selection; wrapper phải chuyển tiếp accessible name cho icon links.

- `preview/PreviewEntry.tsx` lazy-load preview; `main.tsx` chỉ mount một root, không đặt lazy component boundary trong bootstrap để tránh entrypoint bị Fast Refresh chạy lại.
- `preview/data.ts` là read-model context, fixtures ở `preview/fixtures.ts`, presentation types ở `preview/models.ts`. Components đọc provider; không import production API clients/hooks, không tạo writes. API adapter tương lai là checkpoint riêng, cần approved schema/provenance/run binding.
- `preview/navigation.ts` giữ hash route/page/section/contract/period/request. Link dùng native anchors, `aria-current`; không ghi đè run/request bằng lựa chọn mặc định. Preview không thay connected navigation.
- CSS `pv-*` scoped dưới `.pv-app`, reuse Mercury tokens trong `tokens.css`. Không dùng fixture styles để thay business guards. Chart colors/CTA bổ sung là presentation tokens trong `preview.css`, xem bảng ở checkpoint 13; màu nhạt dùng surface, màu series có contrast ≥3:1 trên trắng; CTA trắng/primary ≥4.5:1.
- Recharts 3.10.1 là dependency đã được user cho phép cho preview; không thêm UI framework/router. Mỗi chart có tooltip/unit/source, table alternative và controls; không dựa vào màu để thao tác. Native bảng có caption và vùng cuộn focusable, giữ scrollbar trong container ở mobile.
- Decision/artifact dialogs reuse components hiện hành với optional `context` slot để đặt disclaimer/preview controls **bên trong focus trap**. Exact artifact/version/current/request/source/NOT_EVALUABLE guards không đổi. Context không thay approval logic.
- Mock submit chỉ hiện thông báo local, không resolve request như kết quả thật, không patch/resume/external release. Nhãn **Dữ liệu mô phỏng** phải hiện xuyên suốt; thông báo sau thao tác nói rõ chưa ghi nhận quyết định, chưa lưu hoặc chưa gửi thực tế.
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
8. UI fixture và screenshots synthetic luôn ghi **Dữ liệu mô phỏng**. `source: OPENAI` trong fixture không chứng minh đã gọi OpenAI. Preview dùng fixture trong entry riêng theo `?preview=1`; connected UI không sử dụng fixture làm dữ liệu thực.

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
