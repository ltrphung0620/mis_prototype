# Design language hiện hành — Dify × OPC MIS

Cập nhật 13/10/2026. Owner yêu cầu chuyển UI sang phong cách Dify. Tài liệu này thay thế phần visual
language Mercury trong [03](03_design_system.md); cấu trúc thông tin (workspace một hợp đồng, preview
global shell, workflow viewer) và mọi governance guard trong [style.md](../../style.md) giữ nguyên.

## Nguồn nghiên cứu

- Mã nguồn `langgenius/dify` nhánh `main` (10/2026): `packages/dify-ui/src/themes/light.css`
  (semantic tokens, sinh tự động), `packages/dify-ui/src/styles/styles.css` (palette, shadow),
  `packages/dify-ui/src/styles/utilities.css` (thang chữ `system-*`, `title-*`),
  `web/app/components/main-nav/*` (main nav mới), `web/app/styles/glass-surface.css`
  (nav item đang chọn), `web/app/components/workflow/nodes/_base/node.tsx` (workflow block).
- Ảnh giao diện trong docs.dify.ai: Monitoring dashboard, Workflow logs/Log detail, model parameter popover.

Chỉ học visual language; không sao chép logo, icon set, emoji app icon hay tên sản phẩm Dify.

## Đặc trưng Dify đã rút ra

| Khía cạnh | Dify | Áp dụng ở OPC MIS |
|---|---|---|
| Canvas | `background-body` `#F2F4F7` cho cả trang và main nav, không có đường kẻ giữa nav và nội dung | `--color-canvas`; sidebar cùng màu nền, bỏ `border-right` |
| Panel/card | Nền trắng, viền trắng/hairline, `shadow-xs`, bo `rounded-xl` 12px; block workflow bo 16px | `.pv-section`, `.panel`, `.decision-workspace`, metric cards, `--radius-lg/xl` |
| Main nav | Rộng ~248px; logo + workspace card trắng; item 32px, bo 10px, chữ 14px medium `#495464`; item chọn là "blue glass" (gradient xanh 8–12%, chữ accent semibold, bóng nhẹ) | Sidebar 240px, `.sidebar-context`/`.pv-company-switch` là workspace card, `--nav-active-surface/-shadow` |
| Accent | `#0033FF` (button primary, link, tab, focus), hover `#002CDE`, nền nhạt `#EEF4FF` | `--color-primary`, `--color-primary-strong`, `--color-accent-soft` |
| Chữ | Primary `#101828`, secondary `#354052`, tertiary `#676F83`, placeholder `#98A2B2` | `--color-ink-950/800/450`, `--color-placeholder`; `--color-ink-600` = `#495464` (main-nav text) |
| Divider | Alpha `rgb(16 24 40 / .04 / .08 / .14)` | `--color-line-subtle`, `--color-line`, `--color-line-strong` |
| Typography | System font stack; 12/13/14px với line-height 16/16/20; tiêu đề 16–18px semibold; nhãn section/table `system-xs-medium-uppercase` | Body 14, control 13, meta 12; h1 24px (mobile 20px); eyebrow, `th`, metric `dt`, legend dùng uppercase 12px medium tertiary |
| Button | Primary xanh đặc + `shadow-primary-button`; secondary trắng, viền 14% alpha, `shadow-xs`; cao 32px, bo 8px, 13px medium | `base.css` `button`, `.primary-action`, `.pv-button(--primary)` |
| Input | Nền xám `rgb(200 206 218 / .25)`, không viền; khi focus nền trắng + viền `#D0D5DC` | `base.css` input/select/textarea, `.pv-search` |
| Badge | Bo 6px, viền hairline, nền mềm alpha, 12px medium; status indicator là chấm màu có halo | `.status-badge` hiện `.status-badge__dot`; `.pv-badge` |
| Segmented control | Track `rgb(200 206 218 / .2)`, item chọn nền trắng + `shadow-xs` | `.pv-filter-tabs`, workflow phase nav, Canvas/Danh sách |
| Tabs | Gạch chân 2px màu accent | `.pv-tabs`, `.workspace-tab` |
| Bảng | Header là dải `#F2F4F7`, chữ uppercase 12px tertiary; hàng phân cách hairline | `.evidence-table th`, `.pv-app th` |
| Drawer/dialog | Panel trắng nổi, bo 16px, `shadow-xl`, overlay `rgb(16 24 40 / .4)` | `.modal-card`, các dialog phải màn hình |
| Workflow | Canvas `#F2F4F7` chấm `rgb(133 133 173 / .15)` gap 14 size 2; block `#FCFCFD` bo 16px; icon tile đặc màu theo loại node, glyph trắng; edge `#D0D5DC`, active `#085AFC`; handle là thanh 2×8px xanh; panel node nổi bên phải | `workflow.css`, `WorkflowViewer.tsx` (`wf-node-icon--<type>`, Background, edge colors) |

## Điều chỉnh có chủ đích so với Dify

- **Contrast**: Dify dùng `#079455`/`#DC6803`/`#D92D20` cho chữ trạng thái. OPC MIS dùng bậc 700 của
  util colors (`#067647`, `#B54708`, `#B42318`) để chữ nhỏ trên nền mềm đạt ≥4,5:1 (5,40 / 5,20 / 6,05).
  `--color-ink-450` trên canvas đạt 4,56:1. Chấm status dùng bậc 500 vì chỉ là trang trí cạnh nhãn chữ.
- **Icon tile workflow**: Finance `#085AFC`, Operations `#6172F3`, Risk `#088AB2`, Gate `#DC6803`; glyph trắng
  đều ≥3:1 (5,41 / 4,03 / 3,97 / 3,49). Màu tile là **loại node**, không phải trạng thái; trạng thái vẫn là
  nhãn chữ + ký hiệu.
- **Chart**: `--pv-chart-*` lấy từ Dify util colors với hue khác nhau rõ (blue, teal, violet, orange, gray),
  tất cả ≥3:1 trên trắng.
- Giữ focus outline 2px accent cho mọi control (Dify chỉ đổi viền input); không ẩn focus để giống Dify.
- Không dùng emoji làm icon (Dify dùng emoji cho app icon). Không thêm glass blur thật,
  marketing gradient hay animation mới.
- Không thêm tính năng Dify (Explore, Studio, Knowledge, Tools, search ⌘K, account menu) như thể backend đã hỗ trợ.

## Tokens chính

Nguồn duy nhất: `frontend/src/styles/tokens.css`. Tên token cũ được giữ để component hiện hữu tự đổi theo;
`--color-lavender` nay là nền accent nhạt, `--color-emerald-*`/`--color-blue-*` vẫn là alias của accent.

| Vai trò | Token | Giá trị |
|---|---|---|
| Canvas / surface / surface phụ | `--color-canvas` / `--color-surface` / `--color-surface-muted` | `#F2F4F7` / `#FFFFFF` / `#F9FAFB` |
| Accent / hover / nền nhạt | `--color-primary` / `--color-primary-strong` / `--color-accent-soft` | `#0033FF` / `#002CDE` / `#EEF4FF` |
| Chữ | `--color-ink-950/800/600/450` | `#101828` / `#354052` / `#495464` / `#676F83` |
| Divider | `--color-line-subtle/line/line-strong` | `rgb(16 24 40 / .04 / .08 / .14)` |
| Input / hover state | `--color-input-bg` / `--color-state-hover` | `rgb(200 206 218 / .25)` / `rgb(200 206 218 / .2)` |
| Success / warning / error (text–surface) | `--color-green-*`, `--color-amber-*`, `--color-red-*` | `#067647–#ECFDF3`, `#B54708–#FFFAEB`, `#B42318–#FEF3F2` |
| Radius | `--radius-sm/md/lg/xl` | 6 / 8 / 12 / 16px |
| Shadow | `--shadow-xs/sm/md/lg/xl`, `--shadow-primary-button` | Thang shadow của Dify |

## Dark mode

Giá trị lấy từ `packages/dify-ui/src/themes/dark.css` và đặt trong khối `:root[data-theme="dark"]`
của `tokens.css`; component không có selector dark riêng.

- **Chọn theme**: `ThemeSwitcher` (`shared/components/`) ở cuối sidebar của cả hai shell, ba lựa chọn
  Theo hệ thống / Sáng / Tối (segmented control như Dify). Mặc định theo hệ thống và theo dõi khi OS đổi.
  Lựa chọn tay lưu `localStorage["opc-mis-theme"]` của từng trình duyệt; không gửi backend, không phải
  account setting. Mobile connected: switcher nằm ở top bar cạnh logo; preview: trong drawer navigation.
- **Không nháy**: script nhỏ trong `frontend/index.html` đặt `<html data-theme>` trước lần vẽ đầu;
  `shared/theme.ts` dùng cùng key. Nếu storage bị chặn, vẫn theo hệ thống.
- **Accent tách hai vai trò**: `--color-primary` là nền nút/brand mark (dark `#085AFC`, chữ trắng 5,41:1);
  `--color-accent` dùng cho chữ, icon, viền, focus ring, chấm/thanh tiến độ (dark `#6694FF`, 5,47:1 trên
  `#222225`). Ở light hai token cùng `#0033FF`. Code mới không dùng `--color-primary` làm màu chữ.
- **Màu chính (dark)**: canvas `#1D1D20`, panel `#222225`, section `#27272B`, dải header bảng `#1C1C1F`;
  chữ `#FBFBFC / #D9D9DE / #B4B8C2 / #8E93A0` (≥4,84:1 trên mọi nền trên); divider `rgb(200 206 218 / .14)`.
- **Trạng thái (dark)**: chữ success `#47CD89`, warning `#FDB022`, error `#F97066` trên nền mềm alpha 14%
  (6,36 / 6,79 / 4,92:1). Chart dùng bậc sáng (`--color-chart-1..6`, ≥5,4:1 trên panel).
- **Token mới dùng chung**: `--color-card-border`, `--color-button-*`, `--color-segmented-*`,
  `--color-overlay`, `--color-fill-subtle`, `--color-*-border`, `--color-accent-border*`,
  `--color-primary-border*`, `--color-primary-disabled*`, `--color-selection`, `--color-highlight`,
  `--color-nav-active-text`. Không viết literal `rgb(...)` trong component CSS; thêm token có giá trị dark.
- Workflow canvas dùng token `--color-workflow-*` (dark: canvas `#1D1D20`, block `#27272B`, edge `#676F83`,
  edge active `#3072FF`). Icon tile node giữ màu đặc, glyph trắng ở cả hai theme.
- Tooling dev `tools/ui-demo-preview.mjs` chèn nhãn fixture bằng inline style sáng; chỉ là công cụ demo,
  không thuộc bundle.

## Kiểm tra đã chạy (13/10/2026)

- `npm test` (26 files, 159 tests, gồm `ThemeSwitcher.test.tsx`) và `npm run build` pass.
- Ảnh Chrome headless 1440/768/390px: connected UI (fixture `tools/ui-demo-preview.mjs`: Quyết định, Đánh giá,
  Bằng chứng, Quy trình, Dữ liệu đầu vào, Decision Card drawer) và preview (Dashboard, Company, Contracts,
  chi tiết CON-004, Workflow canvas + inspector, mobile list). Không có cuộn ngang toàn trang.
- Dark mode: chụp qua CDP với `prefers-color-scheme: dark` (Dashboard, Company/charts, Workflow + inspector,
  Decision Card drawer, connected Quyết định, mobile top bar và drawer); bấm "Tối" khi hệ thống sáng đổi
  đúng theme và lưu storage. Light mode chụp lại không đổi.
- Chưa kiểm tra bằng screen reader, zoom 200% và mọi dialog/form hiếm gặp.
