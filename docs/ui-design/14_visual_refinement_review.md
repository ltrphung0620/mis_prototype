# Checkpoint 1 — Visual Refinement & UX Polish

Ngày kiểm tra: 11/10/2026. IA và bố cục Checkpoint 1 đã được Founder duyệt; vòng này chỉ tinh chỉnh presentation. **Chờ review cuối trước Checkpoint 2.** Không triển khai Workflow Viewer, API, backend hoặc dữ liệu nghiệp vụ mới; không commit/push.

## Thay đổi để review

- **Typography:** giữ heading 28px và metrics 28px trên desktop. Action heading 14px/600, nội dung 13px; table body 14px, labels 12px/500, ID 13px/600 mono. Metadata/badges/legends tối thiểu 12px trong preview CSS. Mobile table body 13px, page heading 25px.
- **Dashboard:** ưu tiên action đề xuất quyết định bằng heading đậm và CTA periwinkle; secondary actions giữ nền trắng. Bỏ disclaimer lặp trong action section. Giữ cấu trúc action-first, không thêm KPI cards. Mobile chia icon/nội dung thành hai cột, đặt CTA dưới nội dung để tránh bó hẹp câu vào giữa icon và button.
- **Spacing:** nhịp 4px, section padding 24px desktop/18px mobile; action row padding 16px. Main desktop bắt đầu tại 32px, desktop rộng 40px. Các chart Company có title, controls và unit/legend cùng hàng ngang giữa hai panel; footer nguồn nằm ở đáy panel.
- **Company:** axes 13px, legend 12px, tooltip 13px; một tooltip pattern cho line/bar/donut. Tick và giá trị rút gọn dùng dấu phẩy, tối đa 2 chữ số thập phân; tooltip tiền có cả tỷ VND và số VND đầy đủ. Bảng tiền dùng VND đầy đủ, contract list có header `tỷ VND`. Dot màu series giúp đường liên tục và dễ đọc. Kỳ, nguồn minh họa, phạm vi công ty và giới hạn thời điểm chốt được gom vào context strip; không coi snapshot là realtime.
- **Contracts:** trạng thái nguồn có nhãn Việt và nguyên giá trị nguồn bên dưới; workflow có cột và chip riêng. Bộ lọc hiển thị `Workflow: Tất cả`. Toàn bộ dòng có pointer shortcut mở đúng hợp đồng; native links vẫn dành cho keyboard/open-in-new-tab. Modified click và thao tác chọn text không bị shortcut chiếm. Hover/focus-within tint lavender rất nhẹ.
- **Controls/microcopy:** labels trạng thái tải/trống/lỗi, navigation và metadata được Việt hóa. Controls 36px, mobile action CTA 40px; tab focus ring giữ rõ. Fix wrapper Link chuyển tiếp `aria-label` cho chevron mở hợp đồng. Sidebar/header/footer giữ nhãn minh họa và backend-disconnection; bỏ một số dòng source trùng ở Company và contract list. Source codes, artifact IDs, versions và governance copy vẫn được giữ.

Fixture records, amounts, dates, distributions, qualitative confidence và workflow/request binding giữ nguyên. Chỉ dịch hai cụm trong nội dung cảnh báo khi render; không sửa `fixtures.ts`. Chart scale/unit formatting không tính lại Finance hoặc aggregate company facts.

## Tokens và computed styles

Token presentation trong `frontend/src/preview/preview.css`; palette nền tiếp tục lấy từ `frontend/src/styles/tokens.css`. Không thay shared styles của connected workspace.

| Vai trò | Token / giá trị |
|---|---|
| Body | `--pv-text-body: 14px` |
| Control / copy phụ | `--pv-text-control: 13px` |
| Metadata / chip / legend | `--pv-text-meta: 12px` |
| CTA | `--pv-action-primary: #4C63DD`; hover `--color-primary-strong: #4358C6` |
| Primary series | `--pv-chart-primary: #6266D9` |
| Secondary series | `--pv-chart-secondary: #858CBB` |
| Main / secondary text | `#292B35` / `#656771` |
| Surfaces / lavender | `#FFFFFF`, `#F7F8FA`, `#F0F1FC` |
| Border / control border | `#EDEEF1` / `#D5D7DF` |
| Font | Segoe UI / system; Consolas cho contract ID; tabular numerals cho tiền |

Đo computed styles trong Chromium tại 1440px, contrast foreground với ancestor background opaque. Đây là kiểm tra các mẫu chữ thực tế, không phải chứng nhận accessibility toàn sản phẩm.

| Mẫu | Before | After | Contrast after |
|---|---|---|---|
| Heading trang | 28px/600 | 28px/600 | 14,08:1 |
| Primary metric | 28px/500 | 28px/500 | 14,08:1 |
| Action heading | 13px/500 | 14px/600 | 10,62:1 |
| Action description | 12px | 13px | 5,63:1 |
| KPI label | 12px | 13px | 5,63:1 |
| Badge minh họa | 11px/400 | 12px/500 | 5,27:1 |
| Source metadata | 11px | 12px | 4,96:1 |
| Table label | 11px/400 | 12px/500 | 5,40:1 |
| Table body | 13px | 14px | 8,27:1 |
| Contract ID | 12px/500 | 13px/600 mono | 6,93:1 |
| Primary CTA | 12px | 13px | 5,08:1 |
| Chart axis | 12px trong source trước | 13px computed | 5,63:1 |

Evidence: [before measurements](../../output/playwright/ui-polish-before.json), [after measurements](../../output/playwright/ui-polish-after.json). Baseline đo trước không chờ chart render nên không ghi computed chart axis; không trình bày 12px đó như một kết quả browser đã đo.

## So sánh với Checkpoint 1 và Mercury

Các ảnh `ui-first-*` được giữ nguyên làm baseline. Screenshots mới là ảnh thực từ Vite, không phải ảnh sinh. Đã đối chiếu trực quan với ba Mercury references được cung cấp: typography charcoal/periwinkle, nav compact, control refinement, bảng nhẹ và flat surfaces. Không sao chép chức năng banking, avatar hoặc notifications vào OPC.

| Trang | Before 1440 | After 1440 | After 1920 | After 390 |
|---|---|---|---|---|
| Dashboard | [before](../../output/playwright/ui-first-dashboard-1440.png) | [after](../../output/playwright/ui-polish-dashboard-1440.png) | [1920](../../output/playwright/ui-polish-dashboard-1920.png) | [390](../../output/playwright/ui-polish-dashboard-390.png) |
| Company | [before](../../output/playwright/ui-first-company-1440.png) | [after](../../output/playwright/ui-polish-company-1440.png) | [1920](../../output/playwright/ui-polish-company-1920.png) | [390](../../output/playwright/ui-polish-company-390.png) |
| Contracts | [before](../../output/playwright/ui-first-contracts-1440.png) | [after](../../output/playwright/ui-polish-contracts-1440.png) | [1920](../../output/playwright/ui-polish-contracts-1920.png) | [390](../../output/playwright/ui-polish-contracts-390.png) |

Baseline 1920/390 của từng trang nằm trong [checkpoint 13](13_ui_first_preview_checkpoint.md). Bộ ảnh bổ sung có `ui-polish-decision-{1440,1920,390}.png`, review dialog 1440/390 và tooltip 1440/1920/390.

Ở 1440px, action area Dashboard giảm từ 450,5px xuống 406,5px; page height giảm 1489px xuống 1445px. Company cần thêm khoảng một hàng controls để hai chart thẳng hàng; ưu tiên readability và alignment, không giảm mọi khoảng trắng. Mobile dài hơn baseline do chữ lớn hơn và CTA tách dòng; bảng vẫn cuộn trong container, không làm cả trang tràn ngang.

## Validation

| Kiểm tra | Kết quả |
|---|---|
| `npm test` | **136 passed / 24 files**; gồm 2 regression tests mới cho row shortcut, modified click, native links và không tự mở approval |
| `npm run build` | **Pass**, TypeScript + Vite; static assets được build bằng lệnh, không sửa bằng tay |
| Browser screenshots | 3 trang × 3 viewport, thêm workspace × 3; không document overflow, runtime error hoặc `/api/` request |
| Navigation/review | 28 assertions: back/forward/reload, period/table, focus trap/Escape, exact card, stale/resolved/NOT_EVALUABLE guards, Risk upstream lineage, mobile navigation, loading/empty/error/retry |
| Charts/responsive | 10 checks: keyboard tooltip, series toggle, donut filter, bar drill-down, local input validation, 768px, 720px CSS viewport, reduced motion, không gọi backend |
| UX refinement | 33 checks: action filters, full VND tooltip, tooltip trong viewport, empty chart, row hover/keyboard focus/click, contract search/workflow filter tại 1440/1920/390; Company chart metadata cùng tọa độ Y tại hai desktop widths |
| `ruff check .` | **2 I001 baseline** ở `domain/case_workflow_models.py`, `governance/evidence_validator.py` |
| `pytest -q` | **481 passed / 4 failed / 1 warning**, 105,47s; cùng 4 failure đã ghi ở checkpoint 13 |

Browser scripts và JSON results: `output/playwright/ui-polish-{browser-check,measure,interactions,chart-check,ux-check}.js` cùng các file results. Các checks 720px mô phỏng CSS viewport tương đương zoom, không tuyên bố đã kiểm tra browser zoom hoặc screen reader thật.

## Giới hạn và browser review

- Vẫn dùng system font Segoe UI, không có font độc quyền Mercury. Chart typography/layout của Recharts được tinh chỉnh nhưng không tái tạo chart engine Mercury. Không đánh giá pixel-perfect khi chỉ có ảnh tham chiếu với tỷ lệ khác nhau.
- Company và Dashboard vẫn là UI fixtures, không có company/global API; snapshot không có thời điểm chốt thật. Raw source status được giữ để tránh biến dữ liệu nguồn thành kết luận xác thực.
- Mobile tables giữ horizontal scroll để không mất trạng thái, provenance hoặc tiền. Tabs Company cũng cuộn ngang; không thu chữ lại để nhồi vừa màn hình.
- Repository checks vẫn có 2 lint và 4 test failures baseline. Không sửa backend trong task refinement.
- Workflow tab vẫn là placeholder; chưa có canvas/viewer. Connected Contract Decision Workspace và approval guards không được thay thế bằng preview behavior.

Mở [Dashboard preview](http://127.0.0.1:5173/dashboard-assets/?preview=1#/dashboard), chuyển sidebar sang Company/Contracts; chọn CON-004 để review đúng card minh họa. Server Vite local được giữ hoạt động, log/PID tại thư mục visualization `ui-first-preview`. Không cần backend cho preview này. Dừng ở đây để Founder duyệt trước Workflow Viewer.
