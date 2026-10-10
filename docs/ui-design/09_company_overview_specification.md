# Company Overview Specification

HEAD audit `707f58a`, 10/10/2026. **Company-level snapshot analysis đề xuất; chưa có trang/API này.** [Mapping](10_data_to_ui_mapping.md) và [API analysis](11_api_gap_analysis.md) là điều kiện triển khai.

## Context và layout

Trang `/company` sâu hơn Executive Home, cùng Mercury tokens. Header: company identity từ `02_OPC_PROFILE`, dataset/snapshot identity, source periods theo section, unit và limitations. Snapshot hash xác định phiên bản dữ liệu, không chứng minh business recency. Nếu nguồn không có `data_as_of`, ghi "Nguồn chưa cung cấp ngày chốt dữ liệu"; `generated_at` chỉ là lúc tạo read response.

Local sections: Tổng quan; Tài chính & dòng tiền; Hợp đồng & đơn hàng; Hóa đơn; Cảnh báo & giới hạn dữ liệu. Không thêm editing company profile, upload workbook, auth hoặc policy configuration.

| Section | Nội dung target | Giới hạn / drill-down |
|---|---|---|
| Tổng quan | Company profile, source population counts, data coverage, links các phần | `02_OPC_PROFILE` là field/value; validate keys/type/server trước expose. `target_gross_margin` là mục tiêu, không performance đã đạt |
| Tài chính & dòng tiền | Expected in/out; projected closing cash và minimum reserve theo tháng; source direct_cost/opex bảng riêng | Tất cả là projection. Không cộng direct_cost/opex vào expected_cash_out khi chưa biết công thức nguồn; không sum closing balance qua các tháng |
| Hợp đồng & đơn hàng | Count/value và status distribution; contract metadata table; order status/table | Contract source status tách current run business status. Drill-down qua exact `order.contract_id`; unlinked/ambiguous records giữ company scope |
| Hóa đơn | Amount/count theo Paid/Open/Not issued và unknown; table invoice/order/status/dates | Paid là nhãn nguồn, không cash receipt đã reconcile; Not issued không đưa thành issued receivable; không có partial payment model |
| Cảnh báo & giới hạn | Source alert severity/type/date/related_record; validation/coverage limitations; Risk assessments khi scope rõ | Alert dataset khác Risk run finding. Unknown linkage không thành contract-specific warning; không số hóa Risk Score hoặc combine severity thành company health score |

## Charts đề xuất có nguồn

1. **Line/combo** cash-in/cash-out dự kiến theo `09_CASHFLOW.month`. Có bảng thay thế và tooltip source/unit.
2. **Line** projected_closing_cash cùng cash_reserve_minimum; tooltip chỉ rõ projection. Reserve threshold lấy đúng monthly row, không tự dùng profile field để ghi đè.
3. **Bar** contract_value theo contract (hoặc source status), unique contract grain. Không ghép vào order_revenue/invoice_amount để tạo tổng doanh thu.
4. **Stacked bar** invoice amount theo source status; không tự tính overdue. **Donut** order count theo source status, kèm table/legend; status lạ vẫn có bucket/nhãn nguồn.

Đây là presentation/aggregation **cần API mới**, không khẳng định series đã được HTTP expose. Nếu nhỏ/ít category thì table hoặc bar ưu tiên readability hơn bắt buộc đủ mọi chart. Không thêm growth, forecast do AI tạo, valuation, actual company profit/cash balance, runway hoặc historical risk trend.

## Filters và nghĩa dữ liệu

- Default: một company/dataset snapshot được server cấu hình. Không thêm multi-tenant/company selector nếu chưa có backend scope.
- Month window chỉ áp dụng cashflow projection, không ngầm lọc source contract status hoặc pending workflow.
- Tables mặc định toàn snapshot. Filter status/search do read API kiểm soát. Nếu sau này có date filtering: contract start/end overlap khác order_date khác invoice issue_date; schema phải trả `filter_basis`, unknown-date count và phạm vi rows đã loại. Chưa duyệt date semantics thì chưa thêm universal period filter.
- Không đổi dates source thành "hiện tại" theo đồng hồ browser. Vào contract không chạy assessment mới; mở run qua index hoặc empty evaluation state.
- Cashflow không có company/contract keys trên từng row: scope là dataset-level OPC context, không join vào từng contract. Company ID phải resolve từ configured profile; không invent quan hệ cho multi-company workbook.

## Data quality và provenance

Mỗi metric/chart có scope/grain, source fields, source population/filter, unit, snapshot hash, coverage và reason khi unavailable. Source details cho aggregate là record-key/field references được server xác minh; không gửi arbitrary filesystem paths hoặc xem "Đã kiểm tra bằng chứng" là pháp lý verified.

Company snapshot mặc định dùng base configured dataset; user supplements/overlay của một case không viết ngược vào company totals. Nếu owner muốn approved supplements đổi company snapshot, cần policy/ingestion scope riêng, ngoài MVP.

Invalid numeric/date/key không impute zero. Duplicate IDs không được chọn row đầu hoặc sum tất cả; affected measure unavailable hoặc partial có exclusions theo policy đã duyệt. Valid zero vẫn hiện 0. Contract/orphan relationship warning không nhất thiết làm mọi độc lập company total unavailable; mỗi metric trả coverage riêng.

## Acceptance và review

- Tất cả sections thể hiện source/snapshot/kỳ/unit và phân biệt projection với actual.
- Mỗi entity chỉ đếm một lần ở grain chuẩn; dashboard và company dùng cùng read computation cho cùng population.
- Orphan/duplicate/null/date-invalid/unknown-status hiển thị đúng; không cộng lại OPC_GLOBAL facts của nhiều case.
- Chart selection/table/filter dùng keyboard được; 390/768/1440/1920px và zoom 200%; không tràn toàn trang.
- Owner review first-release measures, financial status labels, default projection window và exclusion semantics trước API implementation; charts có screenshot/table reconciliation trước release.
