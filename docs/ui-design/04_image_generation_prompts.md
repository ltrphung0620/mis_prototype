# Image-generation prompt: Founder Dashboard

> **Lưu trữ kế hoạch cũ, không dùng cho bản hiện hành.** User đã thay thế forest/emerald và layout cũ bằng Mercury × Linear, cho phép triển khai trực tiếp. Không sinh ảnh AI cho bản này; screenshot được chụp từ React chạy thật, xem [05_mercury_redesign_review.md](05_mercury_redesign_review.md).

Đầu ra mong muốn: **một ảnh desktop 16:9**, Founder Dashboard đang chờ duyệt Decision Card. Chỉ chuẩn bị prompt; không sinh ảnh hoặc code. MASTER PROMPT bên dưới có thể copy độc lập vào ChatGPT Image Generation, không cần đọc repo.

## 1. Shared design context

- Product: OPC MIS hỗ trợ Founder startup/SME đánh giá một hợp đồng, xem Finance/Operations/Risk, hồ sơ và Decision Card; con người quyết định qua Governance.
- Visual: forest/emerald, bề mặt neutral phẳng, typography tiếng Việt rõ, dữ liệu trước trang trí. Áp dụng chọn lọc Taste redesign/minimalist; không dùng marketing hero, motion mạnh hoặc glass.
- Palette: `#0B251D`, `#176448`, `#059669`, `#F2F5F3`, `#FFFFFF`, `#0F1A16`, `#475851`, `#DCE4DE`; amber/red có nghĩa nghiệp vụ.
- Typography/layout: Be Vietnam Pro-style, body 14–16px, title 26px, tabular numerals; spacing 4px rhythm, padding 24px, radius 8–12px; rail 200px, main assessment area và cột Decision Card.
- Workflow snapshot: final approval pending, `ACCEPT` proposal, `MEDIUM` confidence. Upstream applicable assessments complete; Banking/Document thuộc route minh họa đã xử lý nội bộ. Chưa phê duyệt cuối và chưa cho phép external release.
- Fixtures: CON-004, 7,0 tỷ VND, 18%, 16%, các summaries và statuses chỉ minh họa thiết kế. Không xác minh đây là kết quả thực tế của contract này. Badge “Dữ liệu minh họa” phải hiện trong ảnh.
- Constraints: exact-current-card review; precheck mô phỏng; phê duyệt quyết định khác release; prototype không gửi hồ sơ. Confidence định tính, không Risk Score hay chart lịch sử.

Nguồn design: [Taste redesign](https://github.com/Leonxlnx/taste-skill/blob/main/skills/redesign-skill/SKILL.md), [minimalist UI](https://github.com/Leonxlnx/taste-skill/blob/main/skills/minimalist-skill/SKILL.md). Cơ sở nghiệp vụ: [phân tích](01_project_ui_analysis.md); đặc tả visual: [design system](03_design_system.md).

## 2. Prompt riêng: Founder Dashboard chờ duyệt cuối

Chọn màn hình này vì thể hiện cùng lúc dữ liệu đầu vào, kết quả đánh giá, bằng chứng, proposal và bước Founder cần làm. Một ảnh đủ để duyệt visual direction trước khi mở rộng các dialogs. Prompt riêng và MASTER PROMPT là **cùng một prompt hoàn chỉnh** dưới đây; không lặp hai bản dễ lệch nội dung.

## 3. MASTER PROMPT

Copy toàn bộ block sau vào ChatGPT Image Generation:

```text
Create ONE high-fidelity desktop UI mockup image for “OPC MIS”, a decision-support application for startup and SME founders. Output a single 16:9 image, ideally 1920×1080, resembling a finished, realistic SaaS application screenshot. No code, device frame, browser chrome, collage, or additional screens.

The screen is a Founder Dashboard for ONE selected contract, paused while the Founder reviews the current Decision Card before final approval. All visible interface copy must be natural Vietnamese with accurate diacritics. Keep established technical names such as Finance, Operations, Risk and Decision Card where helpful.

DESIGN DIRECTION
Clean, premium, data-first enterprise SaaS. Apply Taste Skill principles selectively: intentional typography, clear hierarchy, disciplined spacing, restrained semantic color, flat surfaces and context-specific components. Prioritize legibility and decision-making over decorative novelty.

Use the same design system throughout:
Forest #0B251D for the navigation; deep green #176448 for primary actions; emerald #059669 for small accents; canvas #F2F5F3; white surfaces #FFFFFF; primary text #0F1A16; secondary text #475851; borders #DCE4DE. Amber indicates pending review or warnings; red is reserved for errors or rejection.
Use Be Vietnam Pro-style typography, tabular numerals, 14–16px body text, 26px page title, 24px panel padding, a 4px spacing rhythm and 8–12px corner radii. Avoid heavy shadows.

LAYOUT
Use a narrow 200px forest navigation rail, a compact header and a spacious main workspace. Navigation labels are “Tổng quan”, “Đánh giá”, “Hồ sơ & bằng chứng”, and “Nhật ký quy trình”. These are sections of the selected contract, not a multi-contract portal. Show a simple OPC wordmark.

Header:
“Bảng điều hành Founder”
Contract selector: “CON-004”
Status: “Chờ phê duyệt quyết định”
A clearly readable badge: “Dữ liệu minh họa”.
Do not invent an authenticated user profile, notification inbox, or settings module.

Below the header, show a compact KPI strip with three metrics:
“Giá trị hợp đồng”: “7,0 tỷ VND”
“Biên lợi nhuận ghi nhận trên hợp đồng”: “18%”
“Biên lợi nhuận đơn hàng liên kết”: “16%”
Under the third metric, include “Chỉ phản ánh đơn hàng liên kết”.
These are synthetic visual-design examples, not verified repository results.

Arrange the remaining workspace as a wider assessment area and a narrower right-hand Decision Card column.

MAIN ASSESSMENT AREA
A prominent but restrained attention banner:
“Cần Founder xem xét”
“Phiếu quyết định đã sẵn sàng. Quy trình đang tạm dừng để chờ phê duyệt.”

Show a compact workflow summary using meaningful stage labels:
“Tiếp nhận” → “Đánh giá ban đầu” → “Ngân hàng & hồ sơ” → “Quyết định”.
Mark preceding applicable stages complete and the current decision stage pending approval. These labels summarize the workflow; do not imply a fixed four-step backend or invent a completion percentage.

Below it, show three clearly differentiated assessment rows:
Finance — “Hoàn tất”
Operations — “Hoàn tất”
Risk — “Hoàn tất”
Each row has one short Vietnamese summary and a “Xem chi tiết” action. Keep execution completion separate from business risk. Do not interpret completion as safety.

Include a compact evidence table titled “Hồ sơ & bằng chứng”, with columns “Nguồn”, “Nội dung”, “Trạng thái”.
Show three illustrative rows:
“Finance Facts” | “Chỉ số tài chính của hợp đồng” | “Đã kiểm tra bằng chứng”
“Operations Facts” | “Lịch triển khai đơn hàng liên kết” | “Đã kiểm tra bằng chứng”
“Final Risk Assessment” | “Kết quả kiểm tra rủi ro cuối” | “Đã kiểm tra bằng chứng”
“Đã kiểm tra bằng chứng” refers to internal evidence validation, not legal verification.
Provide “Xem bằng chứng” as a secondary action.
Add a quiet workflow log preview with meaningful events, without invented timestamps.

DECISION CARD COLUMN
Title: “Phiếu quyết định”
Recommendation: “Chấp nhận hợp đồng”
Explain clearly that this is a proposal awaiting the Founder’s decision.
Qualitative confidence: “Độ tin cậy: Trung bình”.
Do not show a numerical confidence score or risk gauge.

Include a short illustrative executive summary:
“Đề xuất chấp nhận dựa trên hồ sơ đánh giá hiện hành. Founder cần xem lại các giới hạn bằng chứng trước khi quyết định.”

Include a small “Lưu ý khi quyết định” section:
“Precheck ngân hàng là mô phỏng, không ràng buộc.”
“Phê duyệt quyết định không đồng nghĩa cho phép gửi hồ sơ.”

Show “Xem Decision Card” and one primary CTA:
“Xem xét phê duyệt”
This opens review of the exact current card and approval request; do not depict one-click approval bypassing review.
Keep direct approve/reject controls inside the later approval dialog, outside this screenshot.

BUSINESS ACCURACY
The prototype does not send documents externally. Never display “Đã gửi ngân hàng”, a delivery receipt, real bank approval, or an external-send button.
Do not add chat, file upload, forecasting, scenario sliders, numeric Risk Scores, historical charts, product ranking, or invented growth metrics.
All amounts, summaries and outcomes in this image are illustrative and must remain visibly labeled as such.
Keep the screen internally consistent: final approval is pending, not completed.

AVOID
Purple AI glow, gradients, glassmorphism, oversized marketing headlines, decorative charts, repeated generic KPI cards, emoji, floating blobs, excessive rounded pills, tiny unreadable text, ornamental metadata and stock photography.

Deliver one coherent, polished Founder Dashboard screenshot with readable Vietnamese, convincing alignment, generous but efficient spacing, and a clear visual path from contract context to evidence to the Founder’s next action.
```

## 4. Checklist review ảnh

- Chỉ một ảnh 16:9, app screenshot đọc được tiếng Việt, cùng palette và typography.
- Contract, status và badge minh họa rõ; không hiểu nhầm số liệu như kết quả thực tế.
- KPI giữ phân biệt margin hợp đồng và margin đơn hàng liên kết; không có global cashflow gán vào contract.
- Hierarchy dẫn từ contract → pending action → assessment/evidence → Decision Card; không bị card spam hoặc text nhỏ.
- Card vẫn là proposal, confidence định tính; CTA mở review, không bypass dialog.
- Không có claim bank approval, legal verification, gửi hồ sơ, receipt hoặc final approval đã hoàn tất.

Dừng ở bước user tạo và review ảnh. Mockup không chứng minh UI runtime, API integration hay độ đúng của dữ liệu. Chưa có chức năng nào được triển khai từ tài liệu này.
