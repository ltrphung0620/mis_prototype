# Kế hoạch UI/UX Founder Dashboard

> Kế hoạch cũ bên dưới được thay thế về layout, navigation và theme bởi yêu cầu Mercury × Linear ngày 08/10/2026. Bản đã triển khai là **Contract Decision Workspace**, xem [05_mercury_redesign_review.md](05_mercury_redesign_review.md) và [03_design_system.md](03_design_system.md). Không còn ràng buộc ba cột hoặc Decision Card cố định bên phải.

Trạng thái: kế hoạch đã duyệt để tạo tài liệu và prompt; frontend chỉ triển khai sau duyệt mockup. Cơ sở: [phân tích project](01_project_ui_analysis.md), [design system](03_design_system.md).

## 1. Information architecture

Một route chính `/dashboard`, tập trung một hợp đồng và một run hiện hành. Navigation bốn mục: **Tổng quan**, **Đánh giá**, **Hồ sơ & bằng chứng**, **Nhật ký quy trình**. Đây là chuyển section/panel trong cùng case, không phải trang portfolio nhiều hợp đồng.

| Giao diện | Nội dung và hành động | Cách mở |
|---|---|---|
| Founder Dashboard | Contract selector, KPI, business status, workflow summary, pending interaction, Decision summary | Route chính |
| Chi tiết đánh giá | Facts, observations, findings, limitations; Finance/Operations/Initial Risk/Final Risk/Banking theo artifact | Panel/dialog từ “Xem chi tiết” |
| Decision Card | Recommendation, confidence, summary, điều kiện, calculations và evidence references hiện hành | “Xem Decision Card” |
| Phê duyệt | Exact subject/version, scope, consequences, approve/reject và trạng thái đã xử lý | “Xem xét phê duyệt” từ pending interaction |
| Bổ sung dữ liệu | Amount, precheck evidence hoặc Document metadata theo interaction type | Banner việc cần làm; một form đúng request |
| Hồ sơ/bằng chứng | Run artifacts, version, validation và lineage; Document manifest nếu route có | Navigation hoặc “Xem bằng chứng” |
| Ghi nhận đàm phán | Xác nhận đã gửi điều kiện bên ngoài, phản hồi từng điều kiện, xác nhận kết quả | Chỉ khi projection yêu cầu |

Tổng: **7 giao diện chức năng**, gồm **1 dashboard + 6 giao diện phụ**; **1 màn hình được chọn tạo mockup**. Dialog đóng sẽ trả focus về trigger và giữ ngữ cảnh contract/run.

Vai trò Founder không tạo RBAC mới. Future portal cho nhân sự, danh sách/lịch sử case toàn hệ thống, user management và policy configuration cần backend/auth riêng, không có trong mockup này.

## 2. Bố cục và user flows

Desktop: rail 200px → header contract/status → KPI strip → vùng assessment 2/3 và Decision Card 1/3. Banner pending interaction gần đầu vùng nội dung. Sidebar không thêm chat, inbox, settings hoặc dashboard doanh thu toàn công ty.

Workflow summary có bốn nhóm nhãn ở ảnh mẫu: Tiếp nhận, Đánh giá ban đầu, Ngân hàng & hồ sơ, Quyết định. Đây là nhóm presentation, không thay thế canonical stages/tasks. UI thật phải phản ánh applicability từ projection; nhánh direct không đánh dấu Banking/Document “đã hoàn tất” khi không áp dụng. Đàm phán và external-release xuất hiện khi đúng route.

| Flow | Trải nghiệm cần giữ |
|---|---|
| Khởi tạo | Chọn contract từ server → start với `run_request_id` → theo dõi run; không ghi TeamPack |
| Thiếu dữ liệu | Banner chỉ rõ blocker → form đúng type/request → server nhận supplement → poll cùng run; warning không chặn vẫn nhìn thấy |
| Precheck | Review exact proposal → governance decision → simulation nếu authorized → kết quả ghi “mô phỏng, không ràng buộc” |
| Duyệt cuối | Xem assessments/evidence → xem Card → review approval dialog → approve/reject → poll PostDecision outcome |
| Không đủ cơ sở | `NOT_EVALUABLE` → xem Card/limitations; không tạo nút phê duyệt cuối |
| Đàm phán | Founder xác nhận gửi điều kiện ngoài hệ thống → ghi đủ response mỗi condition → review outcome → confirmation gate nếu yêu cầu |
| External release | Review proposal riêng → governance decision → readiness; không hiển thị gửi thành công hoặc receipt |

Mockup dùng route minh họa có Banking/Document đã xử lý nội bộ và đang ở `FINAL_DECISION_APPROVAL`, recommendation `ACCEPT`, confidence `MEDIUM`. Chỉ final approval đang pending; không hiển thị các gate khác như việc đang chờ cùng lúc.

## 3. Component architecture và API strategy

Giữ React/TypeScript/Vite, CSS tokens, API client/normalizers và `useWorkflowDashboard`. Tái tổ chức các feature hiện có thay vì viết lại domain trong browser. Các nhóm presentation đề xuất: DashboardShell/SectionNavigation, ContractHeader/KpiStrip, WorkflowSummary, PendingActionBanner, AssessmentSummary, EvidencePanel, DecisionSummary. Approval/MissingData/Negotiation/Decision dialogs tiếp tục dùng contracts hiện có.

- `GET /api/workflows/{run}/dashboard` là nguồn workflow status, business status, applicability, progress và pending interactions. Giữ fallback hiện có cho projection endpoint 404; không dùng fallback để tự chế protected interaction.
- Case artifacts endpoint cung cấp payload và lineage. Lọc theo `run_artifacts`, đúng artifact ID/version và exact subject của request. Case-wide artifact cũ không được thay cho subject hiện hành.
- Giữ polling interval hiện tại; cancel request khi đổi ngữ cảnh, không để response run cũ ghi đè run mới. Refresh sau mutation. Không giả animation là backend progress.
- Start retries dùng cùng `run_request_id` cho cùng ý định; form/approval disabled khi submitting. Sau lỗi hoặc stale subject, refresh server state trước khi retry hành động.
- UI định dạng VND và tỷ lệ theo unit của server; `null` = chưa có dữ liệu, không phải 0. KPI ưu tiên scope case; global context nằm phần riêng với nhãn rõ ràng.
- Projection metric không có lineage: mở artifact nguồn để xem evidence. Không dựng evidence IDs từ nhãn metric.
- Approval chỉ submit decision vào request hiện có; không gọi generic protected-action endpoint để thay flow automatic. Không expose arbitrary paths, bytes hoặc secrets.
- Chỉ thêm presentation types để ánh xạ fields hiện có. Không đổi public APIs, backend/domain schema hoặc database trong kế hoạch frontend này.

## 4. Thứ tự triển khai sau duyệt mockup

| Phase | Nội dung | Điều kiện hoàn thành |
|---|---|---|
| 1 | Tokens, typography, shell/navigation, contract header | Bám visual được duyệt; selector/start còn hoạt động |
| 2 | KPI, workflow summary, assessments, Decision summary, evidence/log panels | Chỉ dùng data/run hiện hành; applicability và scopes đúng |
| 3 | Card/approval/supplement/negotiation dialogs | Exact binding, validation, submitting và pause/resume giữ nguyên |
| 4 | Responsive, keyboard/focus, empty/error/stale states | Desktop/tablet/mobile đọc được, hành động không bị che |
| 5 | Regression tests và integration smoke | Frontend tests/build, Ruff và pytest pass; không sửa TeamPack |

Không cần thư viện UI, router hay chart mới. Khi triển khai, dùng dependency versions đã lock của repo, không tự upgrade các khai báo `latest`. Font đề xuất cần kiểm tra Vietnamese glyphs và cách phân phối asset lúc triển khai; fallback Segoe UI phải hoạt động trước khi font tải.

Rủi ro chính: doc cũ khác source; dữ liệu không đủ bị render thành “an toàn”; artifact cũ bị dùng để duyệt; labels ngụ ý gửi thật; layout quá nhiều cards. Xử lý bằng ma trận nguồn, strict scope/run binding, labels nghiệp vụ và progressive disclosure.

## 5. Kiểm thử và acceptance

Trong task hiện tại: kiểm tra bốn Markdown, relative links, self-contained MASTER PROMPT, nhãn minh họa và diff chỉ thuộc `docs/ui-design/`. Chạy Ruff và pytest theo AGENTS; không cần build frontend vì chưa thay frontend và build ghi bundle vào source static.

Khi triển khai frontend, dùng Vitest/Testing Library và backend tests hiện có để kiểm tra:

- Start → running → assessment results; cùng request retry không tạo ý định mới; response stale không đổi run hiện hành.
- Warning không blocker; missing input mở đúng form; supplement resumes cùng run; lỗi validation giữ input để sửa.
- Card/approval bind exact artifact/version; stale, expired, resolved hoặc missing subject không cho quyết định; ngăn double submit.
- `NOT_EVALUABLE` chỉ review; completed không đồng nghĩa accepted; direct route hiển thị Banking không áp dụng.
- Đàm phán chỉ hiện đúng interaction và đúng condition set; confirmation khác approval Card.
- Simulated precheck và readiness không thành bank approval/send receipt; final approval không kích hoạt nút gửi ngoài.
- Tab/Shift+Tab, Escape, focus return, visible focus, responsive 320/768/1280/1920px; loading/empty/error không gây layout jump lớn.

Lệnh giai đoạn frontend: `npm.cmd test`, `npm.cmd run build` trong frontend; `ruff check .`, `pytest -q` tại root. Kết quả static/mockup review không thay thế runtime verification.

Điểm dừng: giao bốn tài liệu và một prompt; user tạo ảnh bằng ChatGPT, duyệt visual direction rồi mới triển khai frontend.

### Kết quả kiểm tra tài liệu ngày 08/10/2026

- PASS: đủ đúng bốn Markdown; UTF-8 không có replacement character; code fences cân bằng; tất cả relative links trỏ đến file tồn tại.
- PASS: MASTER PROMPT có một ảnh 16:9, badge minh họa, fixture đã duyệt, palette, CTA review và trạng thái final approval pending.
- PASS: `git diff --check`; Git chỉ ghi nhận thư mục mới `docs/ui-design/`, không thay source ứng dụng.
- Không chạy được `ruff check .`: shell không tìm thấy executable `ruff`.
- `pytest -q` thất bại ở bước tải `tests/conftest.py`: `ModuleNotFoundError: No module named 'openpyxl'` trong môi trường pytest hiện có. Chưa có kết quả test ứng dụng.
- Không cài dependencies, build frontend, chạy demo workflow hoặc sinh ảnh trong task này. Các kiểm tra tài liệu đạt không thay thế Ruff/pytest hay runtime validation.
