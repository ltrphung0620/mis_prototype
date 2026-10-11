# Data-to-UI Mapping và scope contract

HEAD `707f58a`, audit 10/10/2026. **Các phép tổng hợp mới là đề xuất, không KPI đã triển khai.** Nguồn: `domain/team_pack.py`, `domain/dataset.py`, `api/routes.py`, `api/dashboard_schemas.py`, Finance builders/calculators và persistence ports. [API gaps](11_api_gap_analysis.md).

## Classification

- **A — Đã hỗ trợ**: API hiện hành trả chi tiết trong đúng scope đã biết; không mặc định đã có company/global API.
- **B — Cần aggregation/read API**: source/state tồn tại nhưng chưa có read contract đủ population/series để làm target UI. Server phải validate, aggregate và expose sau duyệt.
- **C — Chưa đủ dữ liệu/ngữ nghĩa**: không có source đáng tin hoặc chưa resolve semantics; không dựng KPI/state/series thay thế.

Các keys D*/C*/X* bên dưới chỉ là **ID hàng mapping**, không metric codes/enums mới trong production. Nếu một row mô tả khả năng A chi tiết nhưng B tổng hợp, target global component được phân loại B.

## Executive Home

| ID / UI | Scope / grain | Source và API hiện tại | Loại target | Aggregation / drill-down |
|---|---|---|---|---|
| D1 Approval detail / review | Request → exact run/case/subject version | `ApprovalRequest`; case approval GET + run dashboard `pending_interactions` | A khi biết case/run | Re-fetch exact binding; existing approval review; không batch approve |
| D2 Global pending approval queue/count | Configured dataset; request_id | D1 source đã persist, chưa list tất cả case/run | B | Distinct request_id, status PENDING + exact authority check; queue không lấy REGISTERED checkpoint làm request |
| D3 Blocking input / fail-safe detail | Run/node/request | Summary `pending_missing_data_ids`, nodes, failure_reason; typed projection interactions | A khi biết run | Workflow/form hiện hữu; không suy blocker từ warning_count |
| D4 Global blockers / contract-attention count | Distinct run hoặc contract, label đúng grain | D3 + current business status; chưa run index | B | Count pending blocking runs; contract count distinct contract_id, giữ toàn bộ run reasons ở drill-down |
| D5 NOT_EVALUABLE / negotiation follow-up | Run + exact Decision Card/request | Existing projection typed interactions | A known run; B global | Read-only NOT_EVALUABLE, negotiation đúng handler; không coi recommendation đã approved |
| D6 Source alerts / cảnh báo global | Snapshot + alert_id | `14_ALERTS`: severity/date/type/related_record/description | B | Source alert grouping; link chỉ khi related_record resolve unambiguous; không tạo activated Risk finding |
| D7 Số hợp đồng trong nguồn | Snapshot + contract_id | `/contracts` có ID catalog; không full quality/population contract metadata | B cho KPI chuẩn | Unique valid contract IDs, unknown/duplicate coverage rõ; mở company business hoặc contract list |
| D8 Tổng giá trị hợp đồng ghi nguồn | Snapshot + contract_id | `04_CONTRACTS.contract_value`; CASE_SPECIFIC fact cho từng evaluated contract | B | Sum once theo contract grain, VND theo verified server unit; không revenue/profit hoặc sum artifacts qua runs |
| D9 Giá trị hóa đơn Open | Snapshot + invoice_id | `07_INVOICES.invoice_amount/status`; case `OPEN_INVOICE_TOTAL` đã có | B | Global sum source status Open, valid unique invoices; link company invoices status Open, không claim reconciled receivable |
| D10 Cash-in/cash-out projection chart | Snapshot + month | `09_CASHFLOW.expected_cash_in/out/month`; case facts chỉ derived summary OPC_GLOBAL | B | Một series company snapshot, gap khi invalid/missing; link finance cùng month window |
| D11 SLA/urgency score, portfolio risk score | Global | Không có approved source/policy cho các chỉ số này | C | Không hiển thị; có source severity thì giữ mức định tính |

## Company Overview

| ID / UI | Scope / grain | Source fields / existing behavior | Loại | Contract và giới hạn |
|---|---|---|---|---|
| C1 Company identity/profile | Snapshot + profile field | `02_OPC_PROFILE.field/value`: company_id/name, business_model, regions, core_services, constraints | B | Typed key allowlist; không expose secret/arbitrary unknown field; thiếu key không invent ID/name |
| C2 Target margin / reserve context | Profile policy vs monthly projection | Profile target_gross_margin/cash_reserve_minimum; cashflow monthly reserve | B | Ghi "mục tiêu/nguỡng nguồn"; không reported achieved margin hoặc override monthly threshold |
| C3 Contract count/value/status chart/table | Snapshot + contract_id | `04_CONTRACTS` ID/customer/start/end/status/value/gross_margin | B | Count/value theo source status; unknown bucket; join customer metadata exact customer_id với quality check |
| C4 Order status/revenue/cost table/chart | Snapshot + order_id | `06_ORDERS.order_revenue/estimated_cost/status/dates/contract_id/service_id` | B | Revenue là trường nguồn của đơn hàng, estimated_cost là ước tính; không accounting actual revenue/cost |
| C5 Invoice status amount/count | Snapshot + invoice_id | `07_INVOICES` status/amount/order_id/issue_date/due_date/paid_date; `receivables.py` phân Paid/Open/Not issued | B | Status taxonomy nguồn; unknown giữ riêng; paid label khác bank receipt; no partial-payment allocation |
| C6 Monthly cash projection | Snapshot + month | `09_CASHFLOW` expected_in/out, projected_closing_cash, reserve | B | Direct source series; no fill/interpolation; không sum closing stocks theo month |
| C7 Direct cost/opex source table | Snapshot + month | `09_CASHFLOW.direct_cost/opex` | B | Expose separate source fields; additive relationship với expected_cash_out chưa xác minh |
| C8 Worst reserve gap / negative net month count | OPC_GLOBAL snapshot + valid month | Existing `calculate_cashflow`, Finance facts WORST_RESERVE_GAP, WORST_RESERVE_GAP_MONTH, NEGATIVE_NET_CASHFLOW_MONTH_COUNT | B global (A case artifact) | Reuse semantics: max(max(reserve-closing,0)), count expected_in-expected_out<0 on complete valid rows; không cộng lại qua case artifacts. Tie month không tự đổi semantics |
| C9 Alerts severity/type table | Snapshot + alert_id | `14_ALERTS.alert_date/type/severity/related_record/description/recommended_action` | B | Raw source alerts, qualitative severity; không tái dùng `risk_score` thành company/contract Risk Score |
| C10 Data coverage/limitations | Snapshot/entity/field | Dataset duplicate_ids, validation_issues, missing_sheets/headers; relationship validation | B | Coverage measure metadata/read warnings, không biến validation issue thành financial severity hoặc business state |
| C11 Current residual risk của run đã chọn | Run + exact FINAL_RISK_ASSESSMENT version | Existing artifact API + projection references | A | Chỉ selected run; không aggregate thành company risk index |
| X1 Actual company cash/bank balance | Company/account + as-of | Bank rows có direction/amount, không opening balance/reconciled ledger | C | Không suy balance từ sums transaction; cash projection không thay actual |
| X2 Actual recognized revenue/profit, runway, YoY growth | Company + comparable fiscal periods | Không có accounting ledger, burn definition hoặc comparable actual periods | C | Không dùng contract value/order revenue/projection thay kế toán thực |
| X3 Overdue receivables / overdue approvals | Invoice/request + approved as-of policy | Invoice due_date tồn tại; không đủ approved global overdue rules; approval không có SLA trong request model | C ở release này | Có thể thiết kế sau khi owner duyệt assessment date, statuses, nulls và policy; không tính bằng browser today |
| X4 Staffing capacity / real delivery performance | Company/resource/event | Không có staffing/resource ledger; order status/due_date không đủ actual delivery event series | C | Không suy năng lực từ completion/task count hoặc delivery_note |

## Inventory thực đọc, không phải KPI sản phẩm

Đã mở workbook **read-only**, theo named sheets/headers. Current fixture source có 5 contract rows, 10 order rows, 7 invoice rows, 6 cashflow rows (2026-06 tới 2026-11), 5 alert rows; đây chỉ là inventory nguồn, chưa metric API/validation result. Source SHA-256: `47CB68B278852223D6E79A15F6C3BD10468CD134E5341B94E8015C611F93ADD3`.

Source statuses đã thấy: contracts Active/Negotiation/Pending expansion; orders At risk/Delivered/In progress/Pending approval/Planned; invoices Not issued/Open/Paid. Chỉ dùng để thiết kế label/unknown handling; không hard-code dataset outcomes/counts/IDs vào production. Registry là schema, không chứng minh mọi record/header/value hợp lệ. Snapshot hash qua ingestion có thể khác source hash khi overlay; không đồng nhất hai loại hash.

## Scope và chống double-count

| Scope | Identity/population đề xuất | Quy tắc |
|---|---|---|
| Company | Configured dataset + base snapshot_hash + resolved company context | Không merge snapshots hoặc case-specific overlays; OPC_GLOBAL là dataset-level fact không có contract key |
| Contract | Snapshot + contract_id | Source row một lần. Không cộng contract_value với order_revenue/invoice_amount; không sum nhiều versions/runs của cùng contract |
| Order | Snapshot + order_id | Relation qua explicit contract_id; duplicated/orphan/ambiguous key cần coverage policy, không resolve bằng customer/name |
| Invoice | Snapshot + invoice_id | Relation invoice.order_id → order.contract_id, exact unique links. Global sum độc lập có thể chứa unlinked invoices nhưng contract drill-down phải ghi linkage limitations |
| Run/case | workflow_run_id / evaluation_case_id, dataset_snapshot_hash | Không dùng case_id như contract_id. Financial source totals độc lập số runs; business states không thay source statuses |
| Artifact | artifact_id + version + validation + run reference | Chỉ selected current-run identity; không trộn latest case artifacts ở các run/version khác |
| Approval | request_id + run/case + exact subject/action/hash | Distinct request_id; checkpoint count khác pending request count; không loại pending chỉ vì run không được chọn làm representative |
| Cashflow | Snapshot + month | Read mỗi tháng một lần. Numeric flow có thể sum qua period khi công thức/unit được duyệt; closing/reserve stocks không sum, không lặp theo contract |

Company read totals lấy source entities độc lập, không join một bảng fact rộng contracts×orders×invoices rồi sum. Numeric invalid/null không bằng zero; duplicate keys không silently dedupe bằng first row. Proposed default: affected measure unavailable, kèm excluded/unknown coverage; partial totals chỉ nếu owner duyệt và luôn có nhãn.

Existing Finance `VERIFIED` nghĩa deterministic/evidence validation, không biến projection thành thực tế. Existing calculators có assumptions về complete inputs (receivables dùng numeric fallback sau requirements validation; cashflow bỏ incomplete month); global read implementation phải validate trước và expose coverage, không copy fallback thành cách impute dữ liệu toàn công ty.

## Metadata contract cho mọi read metric/chart (đề xuất)

`value/points`, `unit`, `scope`, `grain`, `dataset_id`, `source_hash`, `snapshot_hash`, `source_fields`, record-key references hoặc drill-down token, `period/filter_basis`, `coverage`, `limitations`, `generated_at`, `data_as_of` nullable với reason. Availability/coverage là read-model metadata, không thêm domain workflow status. Monetary sheets không có currency column; VND phải lấy từ verified server/domain convention và ghi rõ assumption, không inference theo từng row. Không aggregate nhiều currency nếu backend tương lai bổ sung mà chưa conversion policy.
