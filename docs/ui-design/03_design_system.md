# Design system hiện hành — Mercury × OPC MIS

Cập nhật 08/10/2026. Đã triển khai trong `frontend/src/styles/`. Tài liệu này thay thế design system forest/emerald trước đó. Các màu là lựa chọn của OPC MIS dựa trên ba ảnh tham chiếu, không phải token chính thức của Mercury.

## Visual language

Mercury quyết định hình thức: nền trắng/cool neutral, chữ charcoal, accent periwinkle, bề mặt phẳng, border nhẹ, control nhỏ gọn và bảng dữ liệu thoáng. Linear định hướng cấu trúc workspace theo một object, điều hướng theo ngữ cảnh và mở chi tiết khi cần. Không có gradient, glassmorphism, marketing hero hay biểu đồ trang trí.

## Tokens

| Vai trò | Token CSS | Giá trị |
|---|---|---|
| Canvas | `--color-canvas` | `#FDFDFD` |
| Surface | `--color-surface` | `#FFFFFF` |
| Surface phụ | `--color-surface-muted` | `#F7F8FA` |
| Lavender nhẹ | `--color-lavender` | `#F0F1FC` |
| Accent/icon | `--color-primary` | `#536EF1` |
| CTA/text/focus | `--color-primary-strong` | `#4358C6` |
| Charcoal chính | `--color-ink-950` | `#292B35` |
| Charcoal phụ | `--color-ink-800` | `#41434D` |
| Nội dung phụ | `--color-ink-600` | `#656771` |
| Metadata | `--color-ink-450` | `#6C707A` |
| Border nhẹ | `--color-line` | `#EDEEF1` |
| Border control | `--color-line-strong` | `#D5D7DF` |
| Success text/surface | `--color-green-700/100` | `#237555` / `#E8F3EE` |
| Warning text/surface | `--color-amber-700/100` | `#8C641B` / `#FBF3E2` |
| Error text/surface | `--color-red-700/100` | `#B23C50` / `#FBEEF0` |

Green chỉ dùng làm màu trạng thái. Các alias `--color-emerald-*` cũ trỏ sang periwinkle để component hiện hữu tiếp tục dùng CSS tokens; không giữ brand green. Accent `#536EF1` dùng cho chi tiết, còn chữ trắng trên CTA dùng `#4358C6` (contrast với white khoảng 6,09:1).

## Typography và spacing

- Font: Segoe UI, fallback Apple/system sans; hỗ trợ tiếng Việt, không tải font từ dịch vụ ngoài. Font exact của Mercury chưa xác minh.
- Body 14px/1.5; summary 14px/1.6; page title 29px desktop, 26px mobile; recommendation 27px desktop, 24px mobile.
- Section heading 16px; nav 14px; supporting copy 12–13px; metadata 10–11px. Metadata nhỏ dành cho ID/nguồn, không thay thế thông tin ra quyết định chính.
- Số liệu dùng tabular numerals; ID chi tiết dùng Consolas. Định dạng `RATIO` thành phần trăm bằng đơn vị, không đoán dựa vào độ lớn; `null` khác `0`.
- Spacing scale 4/8/12/16/20/24/32/40px. Radius 6/10/12px. Control cao tối thiểu 36px desktop; text actions tối thiểu 44px trên mobile.
- Shadow chính `0 1px 2px rgba(25,29,50,.025)`; shadow overlay `0 16px 48px rgba(29,32,55,.12)`.

## Layout

Sidebar trắng cố định 224px desktop (190px dưới 1100px), header 76px, workspace tối đa 1160px có padding 40px. Desktop dùng một cột nội dung, không ghim Decision Card bên phải.

Thứ tự: hợp đồng/trạng thái → yêu cầu đang chờ → dải chỉ số không đóng card → đề xuất quyết định → cơ sở Finance/Operations/Risk → ranh giới mô phỏng/phát hành. Bằng chứng và lịch sử có phần riêng trong cùng workspace; không thêm route backend.

Dưới 760px: sidebar thu thành brand, điều hướng thành thanh ngang cuộn; header nhỏ; metrics wrap hai cột; decision properties và actions xếp dọc. Bảng được cuộn trong container, không làm toàn trang tràn ngang.

## Component patterns

| Component | Cách trình bày |
|---|---|
| Workspace navigation | Line icons, active background cool gray, accent nhẹ |
| ContractMetrics | `dl` trên bề mặt trang; chỉ metric `CASE_SPECIFIC` từ projection |
| Decision workspace | Một panel lớn, recommendation rõ là đề xuất, confidence định tính |
| DecisionLimits | Native `details/summary`; giới hạn luôn truy cập được |
| AssessmentIndex | Dòng nhẹ, task status và kết luận tách nhau; mở exact artifact ID |
| EvidenceIndex | Bảng phẳng, ID/version/validation nội bộ; không coi validation là xác minh pháp lý |
| WorkflowEvents | Read-only endpoint hiện có; không suy diễn transition từ event |
| Review/approval | Detail panel trên overlay; identity/version, summary và limitations trước CTA |
| Input/supplement/negotiation | Giữ form và schema hiện có, dùng control và bề mặt chung |

## UI states và accessibility

- Loading/empty/error tiếp tục theo hook hiện có; poll projection là nguồn trạng thái. Playback chỉ tiết chế trình bày.
- Missing data mở đúng form được backend hỗ trợ; warnings không tự biến thành blocking.
- `FAILED_SAFE`/blocked hiện notice. Stale/version mismatch khóa approval. `NOT_EVALUABLE` chỉ đọc, không mở approve/reject.
- Business status quyết định tone badge đầu trang. Task execution completion không đồng nghĩa rủi ro thấp hoặc hợp đồng được chấp nhận.
- Approval pending/resolved và submit guard giữ handler/API cũ; final approval và external release là hai gate riêng.
- Skip link, semantic landmarks/headings, labels, visible keyboard focus, focus trap/restore trong dialog; Escape đóng; body scroll lock; reduced motion.
- Kiểm tra keyboard và responsive đã chạy. Chưa thực hiện audit screen-reader đầy đủ hoặc chứng nhận toàn bộ WCAG.

Kết quả chạy và screenshots: [05_mercury_redesign_review.md](05_mercury_redesign_review.md).
