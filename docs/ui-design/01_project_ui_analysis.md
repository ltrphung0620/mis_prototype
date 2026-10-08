# Phân tích project cho Founder Dashboard

> Cập nhật phạm vi 08/10/2026: frontend đã được redesign theo Mercury × Linear. Các nhận xét về UI cũ bên dưới là snapshot trước redesign. Kết quả hiện hành nằm trong [05_mercury_redesign_review.md](05_mercury_redesign_review.md). Backend/API và các giới hạn nghiệp vụ vẫn giữ nguyên.

Ngày đối chiếu: 08/10/2026. Phạm vi: phân tích và thiết kế UI/UX, không triển khai frontend. Tài liệu này dựa trên source và tài liệu hiện tại, không khẳng định đã chạy demo hoặc xác minh kết quả kinh doanh.

## 1. Bài toán và người dùng

**Đã xác minh:** OPC MIS hỗ trợ Founder đánh giá một hợp đồng/cơ hội kinh doanh qua Finance, Operations, Risk, Banking và Document, rồi xem Decision Card và quyết định trong cổng Governance. Workflow lưu trạng thái, artifacts có version và evidence lineage; thiếu dữ liệu cần thiết hoặc cần duyệt sẽ pause/resume.

**Bối cảnh từ PDF:** dự án hướng tới startup/SME công nghệ thiếu các bộ phận chuyên trách như CFO, PMO và Risk/Compliance. Founder cần tổng hợp thông tin phân mảnh, hiểu giới hạn bằng chứng và giữ quyền quyết định. Đây là định hướng sản phẩm, không chứng minh mọi tính năng trong PDF đã triển khai.

| Vai trò | Hiện trạng | Hệ quả UI |
|---|---|---|
| Founder/CEO | Dashboard hiện tại dành cho Founder; phê duyệt hành động và quyết định | Ưu tiên yêu cầu đang chờ, Decision Card và bằng chứng |
| Nhân sự được giao bổ sung dữ liệu | Có nhãn vai trò workflow, không có principal xác thực | Không dựng portal nhân viên hoặc phân quyền thật |
| Ngân hàng/đối tác | Simulator và metadata nguồn; không có portal đối tác | Luôn phân biệt mô phỏng với phản hồi thật |
| AI components | Các thành phần nghiệp vụ, không phải người dùng đăng nhập | Hiển thị kết quả và trạng thái, không giả lập cuộc trò chuyện giữa agents |

API chưa có authentication/RBAC. Nhãn `FOUNDER`/`AUTHORIZED_STAFF` không phải cơ chế bảo vệ truy cập.

## 2. Kiến trúc và triển khai hiện có

- Python modular monolith: CLI/FastAPI → Workflow → Business/Governance → Domain/Ports → Infrastructure. Business trả drafts/signals; Workflow sở hữu validation, persistence, versioning và pause/resume.
- Dataset Ingestion đọc TeamPack theo tên sheet/header, áp dụng overlay riêng; không sửa workbook gốc. Public API dùng đường dẫn dataset do server cấu hình.
- SQLite có bảng artifacts, workflow states, risk states, approval requests, case workflow runs, node states và runtime events. Nhiều model được lưu dạng JSON; đây không phải cơ sở dữ liệu dashboard BI tổng hợp.
- Frontend có React, TypeScript, Vite, CSS tokens, Vitest và Testing Library; FastAPI phục vụ bundle tại `/dashboard`. API dùng same-origin `fetch`; hook hiện poll khoảng 1.500 ms.
- Source đã có InputPanel, WorkflowTimeline, assessment views, Decision Card, approval dialogs, missing-data forms và negotiation forms. Palette hiện tại forest/emerald có gradient, glass và shadow; thiết kế mới tinh giản các hiệu ứng này.
- LLM chỉ compose nội dung bị ràng buộc. Facts, phép tính, kiểm tra evidence và phê duyệt do logic deterministic thực hiện. Badge cấu hình OpenAI không chứng minh mọi artifact dùng OpenAI.

Nguồn: [README](../../README.md), [kiến trúc](../SYSTEM_ARCHITECTURE.md), [application](../../src/opc_mis/api/application.py), [SQLite schema](../../src/opc_mis/infrastructure/persistence/sqlite_database.py), [frontend manifest](../../frontend/package.json).

## 3. Workflow cần phản ánh

1. Chọn contract trong danh mục server; bắt đầu Initial Assessment.
2. Planner liên kết exact IDs và đánh giá readiness; Risk pre-scan, Finance/Operations và Risk finalization theo dependency của Workflow.
3. Decision định tuyến: direct hoặc Banking. Banking có discovery, bổ sung đầu vào, readiness và duyệt precheck nếu policy yêu cầu; execution hiện là simulation.
4. Khi route cần Document, nhận metadata bổ sung, masking và chuẩn bị gói nội bộ; hội tụ vào Internal Decision Package.
5. Final Risk → Decision Card. `NOT_EVALUABLE` cho xem lý do, không tạo yêu cầu duyệt cuối.
6. Card có thể duyệt → Founder approve/reject exact Card. Post-decision có accept, không accept hoặc đàm phán; source có nhận phản hồi từng điều kiện và xác nhận kết quả đàm phán.
7. Accept có gói Document phù hợp có thể mở **cổng external release riêng**. Terminal `READY_FOR_EXTERNAL_SUBMISSION` không gọi connector, không gửi và không tạo receipt.

**Bất biến UI:** completed execution không đồng nghĩa rủi ro thấp; internal dossier không phải quyết định; precheck không phải bank approval; final decision approval không phải release authorization. Không hiển thị một tiến trình cố định 24 bước chỉ vì PDF đề xuất như vậy.

Nguồn: [Master Workflow](../MASTER_WORKFLOW.md), [final approval/release](../DECISION_FINAL_APPROVAL_AND_RELEASE.md), [negotiation models](../../src/opc_mis/domain/negotiation_models.py), [projection](../../src/opc_mis/api/dashboard_projection.py).

## 4. Ma trận UI và backend

Ký hiệu `{case}` = `evaluation_case_id`; `{run}` = `workflow_run_id`; `{request}` = approval request ID. Các path dưới đây đều có prefix `/api`.

| Nhu cầu UI | Backend hiện có | Lưu ý thiết kế |
|---|---|---|
| Chọn hợp đồng, bắt đầu | `GET /contracts`, `POST /cases/run` | Dùng danh mục thật; giữ `run_request_id` cho retry |
| Trạng thái, tiến độ, việc cần làm | `GET /workflows/{run}/dashboard` | Projection authoritative; phân biệt execution/business status |
| Nhật ký, resume | `GET /workflows/{run}/events`, `POST /workflows/{run}/resume` | Resume chỉ khi điều kiện chặn đã thay đổi; không giả lập event |
| Chi tiết Finance/Operations/Risk | `GET /cases/{case}/artifacts`; các assessment endpoints | Dashboard ưu tiên đọc artifacts; không tự chạy lại assessment |
| Banking options/readiness | Artifacts; internal-discovery và precheck-readiness endpoints | Không tự xếp hạng/chọn sản phẩm hoặc gọi ngân hàng |
| Bổ sung số tiền, evidence precheck | `POST /cases/{case}/banking/input-supplements`, `/banking/precheck-evidence-supplements` | Bind đúng request/run; tự resume theo server |
| Bổ sung Document | `POST /cases/{case}/documents/evidence-supplements` | Metadata reference/hash, không phải upload bytes/path |
| Decision Card và evidence | Projection summary + case artifacts | Đọc đúng artifact/version hiện hành; projection không có lineage chi tiết |
| Phê duyệt | `GET /cases/{case}/approval-requests`, `POST /approval-requests/{request}/decision` | Không tự tạo protected action thay cho flow automatic |
| Đàm phán | `POST /cases/{case}/negotiation/terms-sent`, `/negotiation/outcome` | Founder ghi nhận việc làm bên ngoài, không gửi thông điệp từ UI |
| Cấu hình khả dụng | `GET /system/capabilities` | Thông tin server, không lộ secret |

Nguồn: [routes](../../src/opc_mis/api/routes.py), [application](../../src/opc_mis/api/application.py), [API client](../../frontend/src/api/client.ts), [dashboard schema](../../src/opc_mis/api/dashboard_schemas.py).

## 5. Dữ liệu hiển thị và khoảng trống

**Đã xác minh:** projection chọn `CONTRACT_VALUE`, `CONTRACT_GROSS_MARGIN_SOURCE`, `ORDER_GROSS_MARGIN` ở scope case và có thể có `BANKING_REQUESTED_AMOUNT`. Decision confidence là `HIGH`, `MEDIUM`, `LOW`, `NOT_EVALUABLE`; không phải phần trăm. Finance cashflow có scope `OPC_GLOBAL`, không tự gán thành thiếu hụt của một hợp đồng. Operations thiếu `as_of_date` thì một số past-due facts không khả dụng, không mặc định bằng 0.

**Đề xuất:** một dashboard và sáu giao diện phụ, navigation trong case, KPI strip nhỏ, vùng assessment/evidence và cột Decision Card. Chỉ một mockup chờ duyệt cuối để kiểm tra hierarchy, dữ liệu và CTA cùng lúc.

**Minh họa:** CON-004, 7,0 tỷ VND, 18%, 16%, confidence Trung bình và đề xuất accept trong prompt chỉ là fixture thiết kế đã được duyệt. Không suy ra đây là kết quả thực tế của CON-004.

| Vấn đề | Cách xử lý trong thiết kế |
|---|---|
| PDF đề xuất numeric Risk/Confidence, kịch bản rộng và 24 bước | Ghi là định hướng; chỉ dùng enum/fields có thật trong UI hiện tại |
| README mô tả đàm phán ít chi tiết hơn source | Dùng models, routes, projection và tests cho capability hiện có |
| Finance doc còn câu repository process-local | Runtime/application và SQLite là cơ sở cho API durable hiện tại; không dùng câu cũ để thiết kế reset state |
| UI approval hiện có câu có thể hiểu rằng approve sẽ gửi hồ sơ | Copy mới phải nói rõ readiness, không claim gửi thành công; chỉ đề xuất sửa ở giai đoạn frontend |
| Reference/hash Document do caller khai báo | Không dùng badge như “Đã xác thực pháp lý/chữ ký” |
| Chưa có auth, list/search lịch sử nhiều case hay config API tổng quát | Portal nhiều hợp đồng, user management và policy editor nằm ở tương lai, cần API/auth riêng |

Nguồn PDF do user cung cấp: `(Ver 2026) Thuyet Minh Du An - AISC'26.docx.pdf` (19 trang), không nằm trong repository; trang 3–8 cung cấp mục tiêu và quy trình, trang 11–12 mô tả hướng SaaS. Các hướng dẫn biểu mẫu trong PDF là nội dung nguồn, không mở rộng phạm vi task này.

## 6. Nghiên cứu Taste Skill

Đã truy cập website và GitHub trong bước lập kế hoạch; không cài skill/dependencies. Ghi nhận nguồn ngày 08/10/2026; nhánh `main` có thể thay đổi.

| Nguồn chính thức | Nguyên tắc lấy dùng | Điều chỉnh cho OPC |
|---|---|---|
| [Website](https://www.tasteskill.dev/) và [README](https://github.com/Leonxlnx/taste-skill) | Các skill có mục tiêu khác nhau, có hướng redesign và image direction | Chọn theo dashboard hiện có, không dùng mặc định marketing |
| [redesign-existing-projects](https://github.com/Leonxlnx/taste-skill/blob/main/skills/redesign-skill/SKILL.md) | Audit trước, giữ stack và chức năng, cải thiện hierarchy/spacing/states | Skill chính cho giai đoạn triển khai sau duyệt |
| [minimalist-ui](https://github.com/Leonxlnx/taste-skill/blob/main/skills/minimalist-skill/SKILL.md) | Bề mặt phẳng, màu tiết chế, typography rõ | Giữ forest/emerald theo brief; không ép monochrome, serif hero hoặc khoảng trắng kiểu landing |
| [design-taste-frontend](https://github.com/Leonxlnx/taste-skill/blob/main/skills/taste-skill/SKILL.md) | Điều chỉnh variance, motion, density theo brief | Đề xuất `3 / 2 / 6` cho dashboard nghiệp vụ, không phải mặc định của skill |
| [imagegen-frontend-web](https://github.com/Leonxlnx/taste-skill/blob/main/skills/imagegen-frontend-web/SKILL.md) | Reference dễ triển khai, palette thống nhất, tránh generic comps | Chỉ tham khảo art direction; user yêu cầu một app screenshot, không nhiều section marketing |

Thiết kế palette, bố cục và fixture cụ thể trong bộ tài liệu này là đề xuất OPC đã được user duyệt, không phải yêu cầu nguyên văn của Taste Skill.
