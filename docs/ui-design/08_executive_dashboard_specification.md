# Executive Dashboard Specification

Baseline HEAD `707f58a`; target IA đã chốt, **spec chưa triển khai**, cập nhật 10/10/2026. [Sitemap](07_executive_information_architecture.md) · [Mapping](10_data_to_ui_mapping.md) · [API gaps](11_api_gap_analysis.md).

## Mục đích và bố cục action-first

Founder mở hệ thống để biết **việc cần xem xét**, hợp đồng liên quan và context công ty đủ để quyết định bước tiếp theo. Dashboard không chứa toàn bộ Finance/Risk/artifact analysis và không phê duyệt trực tiếp.

Thứ tự desktop từ trên xuống:

1. **Context header**: Dashboard; nguồn snapshot, khoảng tháng dự kiến nếu có và thời điểm đọc workflow. Action refresh chỉ GET. Không ghi "realtime" hoặc thời điểm refresh thành ngày cập nhật dữ liệu.
2. **Cần Founder xử lý**: section rộng, phân nhóm yêu cầu phê duyệt, dữ liệu đang chặn workflow, failed-safe và tương tác đàm phán/review hiện có. Mỗi row: việc cần làm, contract/run, stage, thời điểm tạo nếu server có, CTA mở đúng review/form. Các group counts là presentation aggregation đề xuất, không phải business states mới.
3. **Hợp đồng cần chú ý / Cảnh báo nguồn**: rows ngắn, lý do có nguồn, scope, link. Không tự chấm điểm để rank hoặc suy warning thành blocker. Cảnh báo TeamPack và finding do Risk sinh được phân biệt.
4. **Context kinh doanh**: tối đa ba giá trị mặc định đề xuất: số hợp đồng trong snapshot, tổng giá trị hợp đồng ghi nguồn và giá trị hóa đơn trạng thái Open. Mỗi giá trị có source/scope/unit, missing coverage và drill-down; không gọi tổng hợp đồng là doanh thu đã ghi nhận.
5. **Dòng tiền dự kiến**: một compact line chart cash-in/cash-out theo tháng, legend và table alternative; link "Xem tình hình công ty" giữ tháng đang chọn. Nếu thiếu tháng/giá trị thì thể hiện gap, không nội suy/zero-fill.

Header → action queue luôn đứng trước KPI/chart. Dùng section/dividers, table/rows và metric strip nhẹ; không lặp generic KPI cards, biểu đồ Risk Score, hero hoặc nested card grids. Mobile stack cùng thứ tự, action labels đọc được và không mất source badge.

## Action queue contract đề xuất

| Nhóm UI | Nguồn hiện hành | Drill-down và guard |
|---|---|---|
| Chờ phê duyệt | Projection `pending_interactions` APPROVAL + case `ApprovalRequest.status` | Exact request/run/subject ID/version/input hash/action; re-fetch trước review, giữ duplicate-submit và resolved/stale guards |
| Cần bổ sung dữ liệu | Typed input interactions, pending missing IDs, readiness | Mở form hiện hữu đúng request; UNSUPPORTED_INPUT chỉ thông báo, không tự tạo form nghiệp vụ |
| Quy trình dừng an toàn | Projection FAILED_SAFE + summary failure reason | Workflow/node inspection; không auto-resume vì thấy error |
| Cần xem xét / đàm phán | NOT_EVALUABLE_REVIEW, NEGOTIATION_TERMS_SENT_CONFIRMATION, NEGOTIATION_OUTCOME_INPUT hiện có | NOT_EVALUABLE chỉ đọc; negotiation chỉ handlers có sẵn, không gửi email/CRM |
| Cảnh báo | Source alert hoặc validated Risk finding | Xem source/detail; severity khác execution status, không tạo approval từ warning |

**Global queue chưa có API.** Known-run views đã hoạt động nhưng không chứng minh một Executive queue đầy đủ. Không duyệt mọi hợp đồng bằng POST để tạo dashboard, không quét `/cases` theo IDs đoán, không dùng localStorage làm catalog run toàn hệ thống.

Đề xuất order presentation: pending approvals → blocking inputs → failed-safe → review/negotiation; mỗi nhóm theo `created_at` tăng dần khi field có nguồn, tie-break bằng ID. Cần owner duyệt thứ tự. Không invent SLA, deadline, "quá hạn approval" hoặc urgency score. Ngày hết hạn chỉ dùng nếu backend có đúng field/policy.

Counts và rows phải chung population/consistency token; pagination không làm total bằng số items tải trong trang. Approval đếm distinct `request_id`; hợp đồng cần chú ý đếm distinct contract, luôn có lý do và link tới từng run. Chưa xác định current action identity → hiện lý do chưa xác minh, không enable submit; không đổi domain status request.

## Phạm vi thời gian và freshness

- Executive operational actions là pending ở thời điểm đọc DB, không lọc theo tháng cashflow.
- Company KPIs mặc định toàn snapshot; cashflow có month window riêng. Header dùng hai nhãn thời gian độc lập để tránh hiểu financial period = run evaluation period.
- Contract source `status` khác workflow business outcome. Không thay `Active` bằng `ACCEPTED` hoặc gắn recommendation chưa duyệt như quyết định Founder.
- Khi nhiều runs/cùng contract: queue kiểm tra mọi pending exact request trong scope được duyệt, không lấy một latest run để bỏ pending cũ. Lựa chọn "run đại diện" cho overview không quyết định authority của approval.

## Loading, empty, partial và error

Action queue lỗi → "Chưa tải được việc cần xử lý", retry GET; không hiện "Không có việc" hoặc 0. Empty chỉ khi server xác nhận full scope. Partial coverage/pagination ghi rõ; metrics lỗi độc lập không che action queue đang dùng được. Stale data có timestamp và refresh affordance; submit luôn revalidate current detail.

Unavailable KPI = "Chưa đủ dữ liệu" với reason/source, khác zero. Không đủ API ở release frontend-only → toàn trang demo ghi **Dữ liệu minh họa** hoặc unavailable module; không trộn mock count với real action controls mà thiếu phân biệt.

## Acceptance và review

- Default page đúng Executive Home; action đầu màn hình, mọi row mở đúng contract/run/request; không POST khi đọc/mở page.
- Không action nào bypass existing Governance review. Precheck mô phỏng; final decision và external-release approval riêng; không external send.
- KPI/chart link giữ snapshot/filter; số/data table nhất quán, VND/unit do read API xác nhận.
- Test same contract nhiều runs, two requests/action types, resolved/stale request, error vs empty, partial pagination, month filter không hide pending actions, responsive/keyboard.
- Owner review queue order, ba KPI mặc định, mockup desktop/mobile và API population trước code. Phases trong [roadmap](12_revised_implementation_roadmap.md).
