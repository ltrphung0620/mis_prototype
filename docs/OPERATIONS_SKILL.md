# Operations Skill

Operations Skill là business component xác minh dữ liệu lịch giao hàng của các order đã được
Planner liên kết rõ ràng với một contract. Component tạo facts và observations trung lập để Risk
Agent dùng ở bước sau; bản thân Operations không đánh giá mức độ rủi ro và không phê duyệt.

## Workflow

```text
EvaluationCase + PlannerResult
  → kiểm tra đúng dataset, case, scope OPERATIONS và Planner readiness
  → resolve contract, orders, services bằng exact ID
  → validate contract/order dates và source order status
  → chuẩn hóa Excel serial/ISO dates
  → tính planned schedule facts
  → giữ nguyên source status và delivery_note
  → tạo observations + evidence limitations
  → Evidence Validator
  → persist OPERATIONS_FACTS
  → Evidence Validator
  → persist OPERATIONS_ASSESSMENT
```

Component không đọc sheet bằng vị trí số, không fuzzy-match tên/mô tả, không đọc `13_RISK_RULES`
hoặc `14_ALERTS`, và không ghi vào TeamPack.

## Input

- Một `EvaluationCase` artifact hợp lệ.
- Một `PlannerResult` artifact hợp lệ và không bị blocked.
- Dataset trùng với dataset của case.
- Scope của case phải chứa `OPERATIONS`.
- `as_of_date` tùy chọn do caller cung cấp rõ ràng.

Nếu không có `as_of_date`, hệ thống không dùng ngày hiện tại của server. Hai facts
`OPEN_PAST_DUE_ORDER_COUNT` và `MAX_OPEN_PAST_DUE_DAYS` có value `null`, quality
`NOT_AVAILABLE`, đồng thời assessment có limitation `AS_OF_DATE_NOT_PROVIDED`.

## Blocking data

Operations trả `WAITING_FOR_INPUT`, tạo `MissingDataRequest`, và không tạo artifact khi dữ liệu
thật sự cần cho phép tính deterministic bị lỗi:

- contract `start_date` hoặc `end_date` không hợp lệ;
- contract `end_date` trước `start_date`;
- order `order_date` hoặc `due_date` không hợp lệ;
- order `due_date` trước `order_date`;
- source order `status` rỗng.

Capacity, contractor, SLA, location, phase dependency, actual delivery date và penalty basis không
phải blocker. Các khoảng trống đó là evidence limitations vì workbook hiện không có quan hệ/field
cấu trúc đủ rõ.

## Artifacts và fields chính

`OPERATIONS_FACTS` chứa:

- `facts`: contract window, schedule span, order counts, gap/overlap, exact status counts,
  past-due facts và OPC penalty-rate reference;
- `order_schedules`: lịch planned theo từng order và source status nguyên bản;
- `source_notes`: delivery note nguyên bản, không semantic parsing;
- `observations`: điều kiện dữ liệu trung lập;
- `limitations`: phần bằng chứng chưa đủ để kết luận.

`OPERATIONS_ASSESSMENT` chứa:

- `assessment_status`: `COMPLETE` hoặc `LIMITED_BY_EVIDENCE`;
- `facts_input_hash`: hash canonical của `OPERATIONS_FACTS` để kiểm tra identity/idempotency;
- `fact_ids`: toàn bộ facts được assessment tham chiếu;
- `observations`, `limitations`;
- `summary`: câu deterministic và mỗi câu phải trỏ về fact IDs.

Mỗi fact có `evidence_id` của chính fact và `source_evidence_ids`. Evidence nguồn ghi rõ sheet,
row, record, field và display value. Derived evidence phải trỏ tới toàn bộ source evidence.

## Boundary với Risk và các component sau

Operations chỉ ghi nhận những câu như “source status là `At risk`”, “source status là
`Pending approval`”, “có khoảng trống lịch” hoặc “order quá due date theo ngày caller cung cấp”.
Đây không phải risk result hay approval result.

Operations không tạo:

- risk level, score, severity hoặc triggered rule;
- approval signal/request;
- capacity score hoặc feasibility conclusion;
- penalty amount;
- banking option, document package hoặc Decision Card;
- protected action hoặc external call.

## Swagger

Chạy server:

```powershell
.\.venv\Scripts\python.exe -m uvicorn opc_mis.app:app --host 127.0.0.1 --port 8000
```

Trong `http://127.0.0.1:8000/docs`:

1. Gọi `POST /api/planner/evaluate` với scope chứa `OPERATIONS`.
2. Copy `evaluation_case_id` từ response.
3. Gọi `POST /api/cases/{evaluation_case_id}/operations-assessment`.

Body có thể là:

```json
{
  "as_of_date": "2026-07-16"
}
```

Hoặc `{ "as_of_date": null }` nếu không muốn tính past-due tại một thời điểm cụ thể.

## CLI

```powershell
.\.venv\Scripts\python.exe -m opc_mis.cli.run_operations `
  --workbook data/input/MISTalent2026_OPC_AgenticAI_TeamPack_v3.xlsx `
  --contract CON-004 `
  --as-of-date 2026-07-16
```

CLI chạy Planner trước, sau đó chạy Operations và in strict JSON (`allow_nan=False`).
