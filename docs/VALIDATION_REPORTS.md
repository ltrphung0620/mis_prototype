# Validation Reports, Fields và Enums

Tài liệu này mô tả contract validation và toàn bộ enum đang có trong OPC MIS Planner.
Nội dung bám theo code hiện tại, không mô tả các trạng thái chưa được định nghĩa trong source.

## 1. Validation Report dùng để làm gì?

Business component chỉ tạo `ArtifactDraft`. Nó không được tự tuyên bố artifact hợp lệ và không
được tự persist artifact.

Luồng xử lý là:

```text
Planner
→ ArtifactDraft
→ EvidenceValidator
→ ValidationReport
→ BLOCKED: không persist artifact bị block, workflow FAILED_SAFE
→ VALID/VALID_WITH_WARNINGS: tạo ArtifactEnvelope và persist
```

Implementation:

- Model: [`src/opc_mis/domain/validation_reports.py`](../src/opc_mis/domain/validation_reports.py)
- Validator: [`src/opc_mis/governance/evidence_validator.py`](../src/opc_mis/governance/evidence_validator.py)
- Orchestrator: [`src/opc_mis/workflow/orchestrator.py`](../src/opc_mis/workflow/orchestrator.py)

`ValidationReport` đánh giá tính hợp lệ kỹ thuật và evidence lineage của một artifact. Nó không
đánh giá contract có lời hay không, delivery có rủi ro hay không, hoặc có cần approval hay không.

## 2. Các field của ValidationReport

```python
class ValidationReport(BaseModel):
    status: ValidationStatus
    checks: tuple[str, ...] = ()
    blocking_errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
```

| Field | Kiểu | Ý nghĩa |
|---|---|---|
| `status` | `ValidationStatus` | Kết luận tổng thể của Evidence Validator đối với một artifact. |
| `checks` | `tuple[str, ...]` | Danh sách check đã chạy thành công. |
| `blocking_errors` | `tuple[str, ...]` | Lỗi làm artifact không được persist. Nếu có ít nhất một lỗi, status là `BLOCKED`. |
| `warnings` | `tuple[str, ...]` | Cảnh báo validation không ngăn artifact được persist. |

Model là `frozen=True`, nghĩa là sau khi tạo thì không được mutate trực tiếp.

## 3. Các validation check hiện có

### 3.1 `SCHEMA_JSON_SAFE`

Check này xác nhận toàn bộ payload có thể serialize thành strict JSON:

- không có `NaN`;
- không có infinity;
- không có pandas object lọt vào response;
- không có object Python không được JSON hỗ trợ.

Validator sử dụng `allow_nan=False`. Nếu serialize thất bại, lỗi được thêm vào
`blocking_errors`.

### 3.2 `LINEAGE_IDS_UNIQUE`

Check này xác nhận mỗi `evidence_id` chỉ xuất hiện một lần trong
`ArtifactDraft.evidence_refs`.

Nếu hai evidence entry có cùng ID, artifact bị block vì lineage không còn rõ ràng.

Lưu ý: cùng evidence có thể được tham chiếu trong nhiều vị trí của payload, ví dụ warning và
`EvaluationCase`. Điều đó không phải lỗi. Check chỉ yêu cầu catalog `evidence_refs` của artifact
không chứa hai entry trùng ID.

### 3.3 `LINEAGE_DERIVED_SOURCES_EXIST`

Mỗi evidence có `source_type = DERIVED` phải khai báo `source_evidence_ids`. Tất cả source ID đó
phải tồn tại trong `ArtifactDraft.evidence_refs`.

Ví dụ:

```text
Contract value evidence
+ Order revenue evidence
→ Derived unmapped contract value evidence
```

Nếu derived evidence trỏ đến một source ID không tồn tại, artifact bị block.

## 4. Cách EvidenceValidator quyết định status

```text
blocking_errors không rỗng
→ BLOCKED

không có blocking error, warnings không rỗng
→ VALID_WITH_WARNINGS

không có blocking error và không có warning
→ VALID
```

Trong implementation hiện tại, validator chưa tạo validation warning, nên kết quả thực tế thường
là `VALID` hoặc `BLOCKED`. `VALID_WITH_WARNINGS` đã được định nghĩa để dùng khi bổ sung các check
không blocking trong tương lai.

## 5. Ví dụ ValidationReport hợp lệ

```json
{
  "status": "VALID",
  "checks": [
    "SCHEMA_JSON_SAFE",
    "LINEAGE_IDS_UNIQUE",
    "LINEAGE_DERIVED_SOURCES_EXIST"
  ],
  "blocking_errors": [],
  "warnings": []
}
```

Planner thường tạo hai artifact là `EVALUATION_CASE` và `PLANNER_RESULT`, vì vậy response thường
có hai validation report.

## 6. Ví dụ ValidationReport bị block

```json
{
  "status": "BLOCKED",
  "checks": [
    "SCHEMA_JSON_SAFE",
    "LINEAGE_IDS_UNIQUE"
  ],
  "blocking_errors": [
    "Derived evidence EVD-EXAMPLE has unknown sources: EVD-MISSING"
  ],
  "warnings": []
}
```

Khi đó Orchestrator:

- không persist artifact draft bị block;
- đặt workflow thành `FAILED_SAFE`;
- giữ node hiện tại;
- copy lỗi vào `PlannerExecutionResult.validation_errors`.

Lưu ý về implementation hiện tại: Orchestrator validate và persist từng draft theo thứ tự.
Vì vậy, nếu một draft trước đó đã `VALID` thì draft đó có thể đã được persist
trước khi draft tiếp theo bị block. Response failed-safe sẽ trả `generated_artifacts = []`, nhưng
việc persist cả batch theo transaction atomic chưa được implementation bảo đảm.

## 7. Các field validation liên quan trong response

### 7.1 `PlannerExecutionResult.validation_reports`

Danh sách report do Evidence Validator trả về. Mỗi artifact draft tương ứng với một report.

### 7.2 `PlannerExecutionResult.validation_errors`

Danh sách lỗi validation hoặc lỗi kỹ thuật ở cấp workflow. Mảng rỗng nghĩa là không có lỗi làm
workflow `FAILED_SAFE`.

### 7.3 `ArtifactEnvelope.validation_status`

Kết luận validation được lưu cùng artifact. Field này dùng enum `ValidationStatus`.

### 7.4 `ArtifactEnvelope.validation_notes`

Các warning/note do Evidence Validator ghi nhận. Nó không chứa business warning của Planner.
Business warning nằm trong:

- `PlannerResult.warnings`;
- `DataReadiness.non_blocking_warnings`;
- `EvaluationCase.warnings`.

### 7.5 `DataReadiness.validation_notes`

Đây là note về chất lượng và tính đầy đủ của dataset mà Planner quan sát được, ví dụ duplicate
ID hoặc alert được giữ cho Initial Risk Scan. Nó không phải kết luận của Evidence Validator.

### 7.6 `PlannerResult.evaluation_case`

Có. Trong JSON response, `evaluation_case` nằm ở đường dẫn:

```text
planner_result.evaluation_case
```

Đây là case chuẩn hóa mà Planner tạo sau khi tìm được contract, customer và các quan hệ
explicit. Model được định nghĩa trong
[`src/opc_mis/domain/planner_models.py`](../src/opc_mis/domain/planner_models.py).

| Field | Ý nghĩa |
|---|---|
| `evaluation_case_id` | ID deterministic của case, được tạo từ dataset ID, snapshot hash, contract ID và evaluation scope. Cùng input/snapshot sẽ cho cùng ID. |
| `dataset_id` | Dataset/TeamPack snapshot mà case đã đọc. |
| `contract_id` | Contract đang được đánh giá. |
| `customer_id` | Customer được contract tham chiếu explicit qua `customer_id`. |
| `related_order_ids` | Các order tham chiếu explicit đến contract. Mảng rỗng nghĩa là không tìm thấy quan hệ explicit. |
| `related_invoice_ids` | Các invoice đi qua những order đã liên kết explicit; Planner không match invoice theo tên/mô tả. |
| `related_service_ids` | Các service có quan hệ explicit với contract/order. |
| `related_credit_case_ids` | Các credit profile/case có quan hệ explicit; không suy luận chỉ vì tên customer giống nhau. |
| `evaluation_scope` | Phạm vi initial assessment được yêu cầu: `FINANCE`, `OPERATIONS`, `RISK`. |
| `cashflow_scope` | Phạm vi cashflow quan sát được: `OPC_GLOBAL`, `CASE_SPECIFIC` hoặc `NOT_AVAILABLE`. Planner không tính cashflow. |
| `warnings` | Business/evidence gaps không blocking gắn riêng với case. |
| `evidence_refs` | Catalog evidence chứng minh các entity và quan hệ đã chọn. |

`evaluation_case` là nullable. Nó sẽ là `null` nếu Planner không thể tạo case an toàn, ví dụ contract
không tồn tại, contract ID bị trùng, hoặc contract không resolve được customer hợp lệ. Khi đó
chi tiết blocking gap nằm trong `missing_data_requests`.

Khi case được tạo thành công, bạn có thể thấy nội dung tương tự ở hai chỗ:

1. `planner_result.evaluation_case`: business output trực tiếp của Planner.
2. `generated_artifacts[*].payload` với `artifact_type = "EVALUATION_CASE"`: bản artifact đã
   qua Evidence Validator và được persist.

Hai vị trí không phải hai case khác nhau; artifact envelope là bản persisted, có thêm artifact ID,
version, input hash và validation status.

## 8. Phân biệt các loại status

Một response có thể đồng thời chứa:

```json
{
  "status": "COMPLETED",
  "component_status": "COMPLETED_WITH_WARNINGS",
  "planner_result": {
    "data_readiness": {
      "status": "READY_WITH_WARNINGS"
    }
  },
  "generated_artifacts": [
    {
      "validation_status": "VALID"
    }
  ]
}
```

Các field này không mâu thuẫn:

| Field | Câu hỏi nó trả lời |
|---|---|
| `WorkflowStatus` | Workflow đang ở trạng thái nào? |
| `ComponentStatus` | Business component hoàn thành theo cách nào? |
| `ReadinessStatus` | Dữ liệu đã đủ cho initial assessment chưa? |
| `ValidationStatus` | Artifact có đúng schema và evidence lineage không? |
| `ArtifactStatus` | Artifact đang ở trạng thái persistence nào? |

## 9. Toàn bộ enum hiện có

Các enum được định nghĩa tại
[`src/opc_mis/domain/enums.py`](../src/opc_mis/domain/enums.py).

### 9.1 SourceType

Xác định nguồn gốc của một `EvidenceRef`.

| Giá trị | Ý nghĩa |
|---|---|
| `TEAM_PACK` | Evidence đọc trực tiếp từ cell hoặc header của TeamPack. |
| `USER_INPUT` | Evidence đến từ `DataPatch` do người dùng cung cấp, chỉ áp dụng trên in-memory overlay. |
| `DERIVED` | Evidence được dẫn xuất deterministic từ các evidence khác. |

`DERIVED` phải có `source_evidence_ids`. `TEAM_PACK` và `USER_INPUT` thường không cần source ID.

### 9.2 EvaluationScope

Xác định phạm vi initial assessment mà người dùng yêu cầu.

| Giá trị | Ý nghĩa |
|---|---|
| `FINANCE` | Yêu cầu chuẩn bị input cho Finance Assessment. |
| `OPERATIONS` | Yêu cầu chuẩn bị input cho Operations Assessment. |
| `RISK` | Yêu cầu chuẩn bị input cho Initial Risk Scan. |

Scope ảnh hưởng đến blocking requirement. Ví dụ thiếu `contract_value` chỉ là finance blocker khi
request có scope `FINANCE`.

### 9.3 ReadinessStatus

Kết luận của Planner về việc dữ liệu có đủ để chạy initial assessment hay không.

| Giá trị | Ý nghĩa |
|---|---|
| `READY` | Đủ dữ liệu và không có business warning. |
| `READY_WITH_WARNINGS` | Đủ dữ liệu để tiếp tục nhưng có evidence gap không blocking. |
| `BLOCKED` | Thiếu hoặc sai dữ liệu nền; initial tasks không được chạy. |

### 9.4 CashflowScope

Mô tả quan hệ giữa cashflow data và evaluation case.

| Giá trị | Ý nghĩa |
|---|---|
| `OPC_GLOBAL` | Cashflow chỉ có phạm vi toàn OPC, không có explicit contract relationship. |
| `CASE_SPECIFIC` | Cashflow có structured `contract_id` và có record khớp case. |
| `NOT_AVAILABLE` | Dataset không có cashflow record. |

`OPC_GLOBAL` không được hiểu là cashflow của riêng contract.

### 9.5 MissingSeverity

Mức độ nghiêm trọng của `MissingDataRequest`.

| Giá trị | Ý nghĩa |
|---|---|
| `BLOCKING` | Thiếu dữ liệu làm workflow phải dừng ở Planner Intake. |

Hiện tại Planner chỉ tạo missing-data request cho lỗi blocking. Evidence gap không blocking được
biểu diễn bằng `PlannerWarning`, không phải `MissingDataRequest`.

### 9.6 MissingRequestStatus

Lifecycle của yêu cầu bổ sung dữ liệu.

| Giá trị | Ý nghĩa |
|---|---|
| `OPEN` | Request mới được tạo và chưa được xử lý. |
| `RESOLVED` | Dữ liệu đã được bổ sung/xác nhận và request đã được giải quyết. |

Planner tạo request ở trạng thái `OPEN`. `RESOLVED` sẽ được dùng bởi resume/data-patch flow.

### 9.7 ComponentStatus

Status chung mà một business component được phép trả về.

| Giá trị | Ý nghĩa |
|---|---|
| `COMPLETED` | Component hoàn thành và không có business warning. |
| `COMPLETED_WITH_WARNINGS` | Component hoàn thành, output dùng được nhưng có warning không blocking. |
| `WAITING_FOR_INPUT` | Component phát hiện blocking missing data; Orchestrator phải pause workflow. |
| `FAILED_SAFE` | Component không thể tạo output an toàn do input contract/schema/runtime failure. |

Business component không trả `WAITING_FOR_APPROVAL`. Trạng thái approval thuộc Orchestrator và
Approval Gate Coordinator.

### 9.8 WorkflowStatus

Trạng thái persisted của toàn workflow, do Orchestrator sở hữu.

| Giá trị | Ý nghĩa |
|---|---|
| `COMPLETED` | Node/workflow slice hiện tại hoàn thành và có thể chuyển tiếp. |
| `WAITING_FOR_INPUT` | Workflow pause để chờ bổ sung dữ liệu. |
| `WAITING_FOR_APPROVAL` | Workflow pause tại governance gate để chờ approval. Planner không tạo trạng thái này. |
| `BLOCKED` | Workflow không được phép tiếp tục, ví dụ protected action bị từ chối. |
| `FAILED_SAFE` | Workflow dừng an toàn vì lỗi kỹ thuật hoặc validation blocking. |

Trong Planner slice hiện tại thường gặp `COMPLETED`, `WAITING_FOR_INPUT` và `FAILED_SAFE`.
`WAITING_FOR_APPROVAL` và `BLOCKED` dành cho các governance node sau này.

### 9.9 RunTaskType

Ba task duy nhất Planner được phép đưa vào initial run plan.

| Giá trị | Ý nghĩa |
|---|---|
| `FINANCE_ASSESSMENT` | Chạy Finance Agent sau Planner. |
| `OPERATIONS_ASSESSMENT` | Chạy Operations Skill sau Planner. |
| `INITIAL_RISK_SCAN` | Chạy Risk Agent ở initial mode sau Planner. |

Banking, Document, Final Risk và Decision không thuộc `RunTaskType` của Planner.

### 9.10 ArtifactType

Artifact mà Planner có thể tạo.

| Giá trị | Ý nghĩa |
|---|---|
| `PLANNER_RESULT` | Toàn bộ kết quả Planner: readiness, case, run plan, missing requests, warnings và evidence. |
| `EVALUATION_CASE` | Standardized case dùng làm input cho downstream assessments. |

Nếu contract không tồn tại, Planner chỉ tạo `PLANNER_RESULT`; `EVALUATION_CASE` sẽ không tồn tại.

### 9.11 ArtifactStatus

Trạng thái persistence của artifact.

| Giá trị | Ý nghĩa |
|---|---|
| `CREATED` | Artifact envelope đã được tạo và persist sau validation. |

Hiện tại enum mới có `CREATED`. Các trạng thái như `STALE` hoặc `SUPERSEDED` chưa được implement,
không nên tự sử dụng trước khi bổ sung domain rule và test.

### 9.12 ValidationStatus

Kết luận của governance validation đối với artifact.

| Giá trị | Ý nghĩa |
|---|---|
| `PENDING` | Artifact đang chờ validation. Đã định nghĩa cho lifecycle mở rộng nhưng chưa xuất hiện trong normal Planner flow. |
| `VALID` | Artifact pass toàn bộ check và không có validation warning. |
| `VALID_WITH_WARNINGS` | Artifact pass các check blocking nhưng có validation warning. |
| `BLOCKED` | Artifact có lỗi schema hoặc lineage; không được persist. |

Không đồng nhất `ValidationStatus.BLOCKED` với `ReadinessStatus.BLOCKED`:

- validation blocked: artifact không đáng tin về schema/lineage;
- readiness blocked: artifact có thể hợp lệ nhưng nội dung báo rằng dữ liệu business chưa đủ.

## 10. Các field chính của ArtifactDraft

| Field | Ý nghĩa |
|---|---|
| `artifact_type` | Loại artifact Planner muốn tạo. |
| `evaluation_case_id` | Case mà artifact thuộc về. |
| `producer` | Component tạo draft, hiện là `PLANNER_SKILL`. |
| `payload` | Business payload cần validate. |
| `evidence_refs` | Evidence catalog dùng để chứng minh payload và derived warnings. |

`ArtifactDraft` chưa có artifact ID, version, input hash, validation status hoặc timestamp. Các
field đó do Orchestrator thêm sau validation.

## 11. Các field chính của ArtifactEnvelope

| Field | Ý nghĩa |
|---|---|
| `artifact_id` | ID deterministic của artifact version/input. |
| `artifact_type` | `PLANNER_RESULT` hoặc `EVALUATION_CASE`. |
| `evaluation_case_id` | Case sở hữu artifact. |
| `producer` | Business component tạo draft. |
| `version` | Version số nguyên, bắt đầu từ 1. |
| `status` | Persistence status, hiện là `CREATED`. |
| `payload` | Payload đã pass validation. |
| `evidence_refs` | Evidence catalog đã pass lineage validation. |
| `input_artifact_ids` | Upstream artifacts/dataset snapshot được dùng làm input. |
| `input_hash` | Fingerprint dùng cho idempotency, versioning và invalidation. |
| `validation_status` | Kết luận của Evidence Validator. |
| `validation_notes` | Validation warning/note, không phải Planner business warning. |
| `created_at` | Thời điểm Orchestrator tạo/persist envelope. |

## 12. Quy tắc đọc nhanh response

### Case bình thường có warning

```text
WorkflowStatus.COMPLETED
ComponentStatus.COMPLETED_WITH_WARNINGS
ReadinessStatus.READY_WITH_WARNINGS
ValidationStatus.VALID
ArtifactStatus.CREATED
```

Ý nghĩa: workflow đã hoàn thành, dữ liệu có hạn chế nhưng đủ dùng, artifact có schema và lineage
hợp lệ và đã được persist.

### Case thiếu dữ liệu nền

```text
WorkflowStatus.WAITING_FOR_INPUT
ComponentStatus.WAITING_FOR_INPUT
ReadinessStatus.BLOCKED
ValidationStatus.VALID
ArtifactStatus.CREATED
```

Ý nghĩa: artifact hợp lệ và mô tả chính xác việc dữ liệu đang thiếu; workflow pause để chờ input.

### Artifact hỏng lineage

```text
WorkflowStatus.FAILED_SAFE
ComponentStatus.FAILED_SAFE
ValidationStatus.BLOCKED
generated_artifacts = []
```

Ý nghĩa: output không đủ tin cậy để persist hoặc chuyển downstream.
