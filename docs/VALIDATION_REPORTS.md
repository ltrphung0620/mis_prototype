# Validation Reports, Fields và Enums

Tài liệu này mô tả contract validation và các enum chính đang dùng trong OPC MIS modular monolith,
bao gồm Planner, Initial Assessment, Banking readiness và Decision post-Banking review.
Nội dung bám theo code hiện tại, không mô tả các trạng thái chưa được định nghĩa trong source.

## 1. Validation Report dùng để làm gì?

Business component chỉ tạo `ArtifactDraft`. Nó không được tự tuyên bố artifact hợp lệ và không
được tự persist artifact.

Luồng xử lý là:

```text
Business component
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

## 9. Các enum chính được dùng trong tài liệu này

Các enum được định nghĩa tại
[`src/opc_mis/domain/enums.py`](../src/opc_mis/domain/enums.py).

### 9.1 SourceType

Xác định nguồn gốc của một `EvidenceRef`.

| Giá trị | Ý nghĩa |
|---|---|
| `TEAM_PACK` | Evidence đọc trực tiếp từ cell hoặc header của TeamPack. |
| `USER_INPUT` | Evidence do người dùng cung cấp, gồm immutable `BANKING_INPUT_SUPPLEMENT`; không ghi ngược vào TeamPack. |
| `DERIVED` | Evidence được dẫn xuất deterministic từ các evidence khác. |
| `POLICY_CONFIG` | Evidence từ server-owned typed policy, ví dụ Banking catalog/field-source mapping. |

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
| `BLOCKING` | Thiếu dữ liệu làm workflow phải dừng ở node sở hữu requirement, ví dụ Planner Intake hoặc Decision post-Banking review. |

Planner tạo missing-data request cho base-data blockers. Decision post-Banking review tạo request
blocking cho amount explicit còn thiếu. Evidence gap không blocking vẫn là warning/limitation, không
phải `MissingDataRequest`.

### 9.6 MissingRequestStatus

Lifecycle của yêu cầu bổ sung dữ liệu.

| Giá trị | Ý nghĩa |
|---|---|
| `OPEN` | Request mới được tạo và chưa được xử lý. |
| `RESOLVED` | Dữ liệu đã được bổ sung/xác nhận và request đã được giải quyết. |

Planner hoặc Decision tạo request ở trạng thái `OPEN`. Banking input-supplement flow dùng
`RESOLVED` sau khi server đã validate đúng case, workflow, pending request và evidence.

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
| `PENDING` | Workflow đã được tạo nhưng chưa bắt đầu node tiếp theo. |
| `RUNNING` | Orchestrator đang thực thi một node. |
| `COMPLETED` | Node/workflow slice hiện tại hoàn thành và có thể chuyển tiếp. |
| `WAITING_FOR_DEPENDENCIES` | Workflow đang chờ artifact/dependency upstream, không phải chờ user input. |
| `WAITING_FOR_INPUT` | Workflow pause để chờ bổ sung dữ liệu. |
| `WAITING_FOR_APPROVAL` | Workflow pause tại governance gate để chờ approval. Planner không tạo trạng thái này. |
| `BLOCKED` | Workflow không được phép tiếp tục, ví dụ protected action bị từ chối. |
| `FAILED_SAFE` | Workflow dừng an toàn vì lỗi kỹ thuật hoặc validation blocking. |

Master Workflow hiện dùng `WAITING_FOR_INPUT` tại Planner hoặc `DECISION_POST_BANKING_REVIEW`.
Approval Control Plane dùng `WAITING_FOR_APPROVAL` và `BLOCKED` khi một protected action thực sự
được đề xuất; checkpoint registration và Banking readiness không tự tạo các trạng thái này.

### 9.9 RunTaskType

Ba task duy nhất Planner được phép đưa vào initial run plan.

| Giá trị | Ý nghĩa |
|---|---|
| `FINANCE_ASSESSMENT` | Chạy Finance Agent sau Planner. |
| `OPERATIONS_ASSESSMENT` | Chạy Operations Skill sau Planner. |
| `INITIAL_RISK_SCAN` | Logical Planner task; Workflow triển khai thành `INITIAL_RISK_PRE_SCAN` và `INITIAL_RISK_FINALIZATION`. |

Banking, Document, Final Risk và Decision không thuộc `RunTaskType` của Planner.

### 9.10 ArtifactType

Các artifact chính của slice hiện tại. Mỗi business component chỉ tạo draft thuộc boundary của nó.

| Giá trị | Ý nghĩa |
|---|---|
| `PLANNER_RESULT` | Toàn bộ kết quả Planner: readiness, case, run plan, missing requests, warnings và evidence. |
| `EVALUATION_CASE` | Standardized case dùng làm input cho downstream assessments. |
| `BANKING_DISCOVERY_REQUEST` | Request nội bộ bất biến từ Decision; `requested_amount` luôn null. |
| `BANKING_OPTION_MATRIX` | Matrix facts/criteria deterministic; version mới được tạo khi supplement đổi input. |
| `BANKING_DISCOVERY_RESULT` | Compact status và pointer tới matrix cùng version/input. |
| `BANKING_OPTION_ADVICE` | Diễn giải `NOT_INVOKED` hoặc `ADVISORY_ONLY`; không có authority route. |
| `BANKING_INPUT_SUPPLEMENT` | Positive-integer VND amount do người dùng xác nhận, có `USER_INPUT` lineage. |
| `BANKING_PRECHECK_READINESS` | Required-field và option-readiness assessment; không chạy precheck. |
| `DECISION_POST_BANKING_REVIEW` | Typed Decision outcome sau Banking readiness; không chọn product/action. |

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
| `producer` | Business component tạo draft, ví dụ Planner, Banking hoặc Decision. |
| `payload` | Business payload cần validate. |
| `evidence_refs` | Evidence catalog dùng để chứng minh payload và derived warnings. |

`ArtifactDraft` chưa có artifact ID, version, input hash, validation status hoặc timestamp. Các
field đó do Orchestrator thêm sau validation.

## 11. Các field chính của ArtifactEnvelope

| Field | Ý nghĩa |
|---|---|
| `artifact_id` | ID deterministic của artifact version/input. |
| `artifact_type` | Một giá trị `ArtifactType` đúng với producer và schema payload. |
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

## 13. Banking discovery, readiness và post-review enums

Các enum dưới đây mô tả business output của Banking; chúng không thay thế
`ValidationStatus` của Evidence Validator.

### 13.1 BankingDiscoveryStatus

| Giá trị | Ý nghĩa |
|---|---|
| `OPTIONS_READY` | Có candidate và không có data gap cho precheck. |
| `OPTIONS_READY_WITH_GAPS` | Có candidate nội bộ nhưng còn gap chặn một precheck sau này. |
| `NO_CONFIGURED_OPTIONS` | Policy không map need hiện tại tới product nào. |
| `WAITING_FOR_REQUEST` | Chưa có `BANKING_DISCOVERY_REQUEST`; workflow phải pause. |
| `NOT_APPLICABLE` | Decision route là direct, không được tạo Banking artifact. |
| `FAILED_SAFE` | Context, catalog, mapping hoặc validation không nhất quán. |

### 13.2 BankingCriterionStatus

| Giá trị | Ý nghĩa |
|---|---|
| `PASS` | Criterion có thể kiểm tra và đã thỏa theo dữ liệu explicit. |
| `FAIL` | Criterion có thể kiểm tra và không thỏa; Decision không tự tính lại criterion này. |
| `NOT_EVALUABLE` | Thiếu dữ liệu hoặc đơn vị để so sánh an toàn. |
| `NOT_APPLICABLE` | Criterion không áp dụng cho candidate này. |

`MINIMUM_AMOUNT` ở matrix version 1 là `NOT_EVALUABLE` vì request bất biến chưa có amount. Sau
supplement, matrix version 2 dùng amount có `USER_INPUT` evidence và ghi `PASS` hoặc `FAIL`. Các
monetary field không có cột currency riêng được chuẩn hóa theo quy ước hệ thống là `VND`.

### 13.3 BankingDataGapCode

| Giá trị | Ý nghĩa |
|---|---|
| `REQUESTED_AMOUNT_UNAVAILABLE` | Chưa có số tiền yêu cầu. |
| `REQUESTED_AMOUNT_CURRENCY_UNAVAILABLE` | Legacy compatibility code; output mới không emit vì currency mặc định là VND. |
| `CREDIT_PROFILE_RELATIONSHIP_UNCONFIRMED` | EvaluationCase không có credit-case ID liên kết explicit. |

`REQUESTED_AMOUNT_UNAVAILABLE` là precheck blocker cho tới khi có supplement. Thiếu explicit credit
profile có thể vẫn được ghi như discovery limitation nhưng không block readiness: `company_profile`
được map riêng, explicit tới `02_OPC_PROFILE`, không phải `10_CREDIT_PROFILE`.

### 13.4 BankingPrecheckStatus

| Giá trị | Ý nghĩa |
|---|---|
| `MOCK_AVAILABLE_NOT_EXECUTED` | Có metadata API mock, endpoint chưa được gọi. |
| `NOT_CONFIGURED` | Không có API ID được map cho product. |

### 13.5 BankingAdviceStatus và BankingAdviceSource

| Field/value | Ý nghĩa |
|---|---|
| `status = NOT_INVOKED` | Dưới hai candidate nên không gọi advisor. |
| `status = ADVISORY_ONLY` | Chỉ là diễn giải; không phải recommendation hay selection. |
| `source = OPENAI` | Structured output đã qua deterministic guard. |
| `source = DETERMINISTIC_FALLBACK` | OpenAI tắt hoặc expected failure; không tạo ranking giả. |
| `source = NOT_INVOKED` | Không có bài toán so sánh nhiều candidate. |

`SOURCE_GUIDANCE_ONLY` trên handling rule nghĩa là text từ TeamPack được hiển thị để tham khảo; nó
không phải approval policy và không tạo `ApprovalRequest`.

### 13.6 BankingPrecheckFieldSource

Nguồn server policy cho từng required field; không được suy diễn từ tên gần giống.

| Giá trị | Ý nghĩa |
|---|---|
| `EVALUATION_CASE` | `contract_id` lấy từ case đã validate. |
| `BANKING_INPUT_SUPPLEMENT` | `amount` lấy từ supplement bất biến do người dùng cung cấp. |
| `OPC_PROFILE` | `company_profile` dùng exact records từ `02_OPC_PROFILE`. |

### 13.7 BankingPrecheckFieldStatus

| Giá trị | Ý nghĩa |
|---|---|
| `RESOLVED` | Explicit source tồn tại và có source record/artifact cùng evidence. |
| `MISSING_INPUT` | Field được map tới user input nhưng supplement chưa có. |
| `SOURCE_UNAVAILABLE` | Mapping hợp lệ nhưng source artifact/record không tồn tại. |
| `UNMAPPED` | API field không có explicit server-policy source; không được tự đoán. |

### 13.8 BankingPrecheckReadinessStatus

| Giá trị | Ý nghĩa |
|---|---|
| `READY` | Required fields và deterministic option requirements đều đáp ứng. |
| `PARTIALLY_READY` | Một phần evidence đã có nhưng option chưa ready. |
| `INPUT_REQUIRED` | Thiếu mapped user input, hiện là amount. |
| `NOT_CONFIGURED` | Option không có mapped mock precheck API. |
| `UNSUPPORTED_MAPPING` | API metadata và explicit field-source mapping không khớp an toàn. |
| `OPTION_REQUIREMENTS_NOT_MET` | Một deterministic product requirement, ví dụ minimum amount, bị fail. |

Mọi readiness artifact và option entry đều có `precheck_executed: false`. `READY` không phải bank
approval và không phải permission để gọi API.

### 13.9 DecisionPostBankingOutcome

| Giá trị | Ý nghĩa |
|---|---|
| `BANKING_PRECHECK_READY` | Có ít nhất một option ready cho protected action ở phase sau. |
| `BANKING_INPUT_REQUIRED` | Decision tạo durable `MissingDataRequest` và Workflow pause. |
| `NO_PRECHECK_PATH` | Không có configured precheck path. |
| `UNSUPPORTED_PRECHECK_MAPPING` | Mapping không thể được sử dụng an toàn. |
| `NO_VIABLE_OPTION` | Không có candidate đáp ứng deterministic requirements. |

Outcome chỉ phân loại route. Nó không chọn option, tạo approval/action, chuẩn bị document hoặc tạo
Decision Card.

### 13.10 BankingInputSupplement fields

| Field | Ý nghĩa |
|---|---|
| `requested_amount` | Strict positive integer; string, boolean, fraction, zero và số âm bị từ chối. |
| `requested_amount_currency` | Chỉ `VND`; mặc định VND ở API. |
| `provider` | Principal do server gán; prototype hiện ghi `AUTHORIZED_STAFF`. API không nhận `provided_by` từ client. |
| `note` / API `evidence_note` | Diễn giải evidence, không dùng để suy luận amount khác. |
| `resolved_request_ids` | Exact durable missing request được supplement giải quyết. |
| `evidence_ids` | `USER_INPUT` lineage của amount và provenance. |

`BANKING_DISCOVERY_REQUEST` và matrix version 1 không bị sửa. Supplement tạo matrix/result/advice,
readiness và Decision review version mới. `ArtifactStatus` vẫn là `CREATED`; version cũ không cần
đổi sang trạng thái `STALE` hoặc `SUPERSEDED` để giữ audit history.

## 14. Banking pause và auto-resume đọc nhanh

Trước supplement:

```text
WorkflowStatus.WAITING_FOR_INPUT
current_stage = DECISION_POST_BANKING_REVIEW
DecisionPostBankingOutcome.BANKING_INPUT_REQUIRED
MissingRequestStatus.OPEN
BANKING_PRECHECK_READINESS.precheck_executed = false
```

Sau supplement hợp lệ:

```text
MissingRequestStatus.RESOLVED
SourceType.USER_INPUT
BankingCriterionStatus.PASS hoặc FAIL
DecisionPostBankingOutcome.BANKING_PRECHECK_READY nếu có option READY
ArtifactType.BANKING_PRECHECK_SUBMISSION_PROPOSAL
ProtectedAction.SUBMIT_BANKING_PRECHECK
WorkflowStatus.WAITING_FOR_APPROVAL nếu policy yêu cầu human; nếu không có trigger thì tạo `AUTHORIZED_WITHOUT_HUMAN`
current_stage = WAITING_FOR_APPROVAL
ArtifactType.BANKING_PRECHECK_RESULT_SET
BankingPrecheckExecutionMode.SIMULATED
BankingPrecheckResultAuthority.SIMULATED_NON_BINDING
ArtifactType.DECISION_POST_PRECHECK_REVIEW
current_stage = DECISION_POST_PRECHECK_REVIEW_COMPLETED
```

Sau human hoặc machine authorization hợp lệ, `BANKING_PRECHECK_SUBMISSION_AUTHORIZED` chỉ là transition nội bộ. Workflow
phát hành permit cho đúng proposal envelope, chạy adapter `SIMULATED`, validate rồi persist
`BANKING_PRECHECK_RESULT_SET`. `BANKING_PRECHECK_RESULTS_READY` là milestone; Decision sau đó
persist `DECISION_POST_PRECHECK_REVIEW`. Conditional full-coverage result có thể đi tiếp tới
Decision-to-Document handoff; outcome khác dừng tại `DECISION_POST_PRECHECK_REVIEW_COMPLETED` hoặc
pause khi có explicit evidence gap. Đây không phải external/real-bank API call hoặc bank response.
Slice này vẫn không selection/ranking, không Decision Card và không dùng OpenAI để tạo hoặc diễn
giải precheck outcome. Document preparation là component riêng và release phải qua checkpoint riêng.

## 15. Banking precheck submission proposal và approval

`BANKING_PRECHECK_SUBMISSION_PROPOSAL` là artifact bất biến, chỉ chứa manifest tham chiếu:

| Field | Ý nghĩa |
|---|---|
| `proposal_id` | Stable ID từ business inputs và upstream artifacts. |
| `proposal_mode` | Luôn `BATCH_ALL_READY_OPTIONS`; không chọn hoặc xếp hạng option. |
| `proposed_action` | Luôn `SUBMIT_BANKING_PRECHECK`. |
| `governance_source_facts` | Exact policy facts/evidence từ API catalog và mapped handling rules; business component không quyết định approval. |
| `candidate_option_ids` | Toàn bộ option có readiness `READY`. |
| `non_ready_option_ids` | Các option còn lại, không được đưa vào batch. |
| `catalog_terms` | Exact fee/rate, processing fee, collateral ratio và minimum amount từ catalog. |
| `field_bindings` | Nguồn tham chiếu cho required API fields; không chứa request body. |
| `source_artifact_ids` / `evidence_ids` | Lineage bắt buộc để Governance và validator kiểm tra. |
| `precheck_executed` / `submission_executed` | Luôn `false` trong proposal; execution state nằm ở result artifact riêng. |

Sau khi proposal được persist, Governance tạo proposal-scoped policy cho:

```text
ApprovalTriggerEvent.BANKING_PRECHECK_SUBMISSION_REQUESTED
ProtectedAction.SUBMIT_BANKING_PRECHECK
Subject: exact proposal artifact ID/version/input hash
Policy sources: 12_API_CATALOG + explicit 22_API_HANDLING_RULES mapping
Additional condition: exact RR-005 amount rule when applicable
```

`ApprovalGate` hợp nhất API policy và amount checkpoint cho cùng exact action. TeamPack hiện tại ghi
`API-002` cần human approval trước submission, nên Founder vẫn phải approve khi amount không kích
hoạt `RR-005`. Nếu loaded policy hợp lệ ghi rõ không cần human và không có checkpoint khác trigger,
Governance persist `AUTHORIZED_WITHOUT_HUMAN`. Thiếu, mơ hồ hoặc sai policy thì fail closed.

## 16. Phase B1 simulated precheck result

Sau authorization, Workflow tạo `AuthorizedActionPermit` tạm thời, ràng buộc đúng workflow, case,
authorization/policy record và proposal artifact ID/version/input hash. Request cho adapter chỉ được resolve từ
explicit bindings đã validate. `company_profile` tồn tại trong request in-memory nhưng không phải
field của persisted result payload.

`BANKING_PRECHECK_RESULT_SET` có các nhóm field chính:

| Field | Ý nghĩa |
|---|---|
| `result_set_id` | Stable ID của toàn bộ batch kết quả. |
| `proposal_artifact_id` / `proposal_id` | Proposal envelope đã được Governance authorize. |
| `approval_request_id` / `permit_id` | Lineage của human/machine authorization và permit thực thi. |
| `execution_mode` | Luôn `SIMULATED` trong Phase B1. |
| `authority` | Luôn `SIMULATED_NON_BINDING`. |
| `adapter_id` / `adapter_config_hash` | Identity của adapter và typed server configuration. |
| `candidate_option_ids` | Giữ đúng toàn bộ thứ tự option trong authorized proposal; không selection. |
| `results` | Một normalized result cho từng proposal item. |
| `source_artifact_ids` / `evidence_ids` | Exact proposal lineage, approval và scenario evidence. |
| `adapter_invoked` | `true` vì simulated adapter đã chạy. |
| `external_bank_submission` | Luôn `false`; không truyền dữ liệu tới real bank. |
| `bank_approval_obtained` | Luôn `false`. |
| `selection_performed` / `ranking_performed` | Luôn `false`. |
| `documents_prepared` | Luôn `false`. |

Mỗi normalized result có `request_hash`, `idempotency_key`, deterministic `provider_reference`,
`scenario_hash`, `response_hash`, `outcome`, `reason_codes`, `non_binding = true` và evidence IDs.
Khi scenario cung cấp provider posture, result còn có `eligibility_status`,
`guarantee_decision`, `supported_amount`, `currency`, `required_documents` và
`approval_conditions`. Những field này phải nhất quán với typed scenario; không được suy luận từ
catalog text hoặc OpenAI.
Các `BankingPrecheckOutcome` hợp lệ gồm:

| Enum | Ý nghĩa |
|---|---|
| `CONDITIONAL_PRECHECK` | Kết quả mô phỏng có điều kiện; không phải approval. |
| `MISSING_EVIDENCE` | Scenario báo thiếu evidence cho bước khảo sát tiếp theo. |
| `NOT_ELIGIBLE` | Kết quả mô phỏng không đáp ứng scenario; không phải final Decision. |
| `NO_RECOMMENDATION` | Không có provider recommendation; vẫn là generic outcome hợp lệ cho scenario khác. |
| `SERVICE_UNAVAILABLE` | Không có explicit API/provider scenario hoặc simulation không khả dụng. |

Scenario `API-002` hiện trả `CONDITIONAL_PRECHECK`, reason
`SIMULATED_CONDITIONAL_PRECHECK`, eligibility `ELIGIBLE`, guarantee `CONDITIONAL`, currency `VND`
và supported-amount strategy `ECHO_REQUESTED_AMOUNT`. Required documents là `SIGNED_CONTRACT`,
`COMPANY_PROFILE`, `PERFORMANCE_BOND_REQUEST_FORM`, `CASHFLOW_BUFFER_EVIDENCE`; conditions là
`CONTRACT_SIGNED`, `CASHFLOW_BUFFER_CONFIRMED`. Đây là server-owned mock, không có trong TeamPack,
không phải VietinBank response/approval/offer thật. Evidence Validator chặn mọi result artifact
vượt boundary này trước persistence.

## 17. Decision Post-Precheck Review

`DECISION_POST_PRECHECK_REVIEW` đọc đúng result set và authorized proposal được result đó tham chiếu.
Mỗi item giữ nguyên `normalized_result_id`, `proposal_item_id`, `option_id`, `bank_product_id`, API,
provider và evidence lineage. Các disposition hợp lệ:

| Enum | Nguồn | Ý nghĩa |
|---|---|---|
| `CONDITIONAL_REVIEW` | `CONDITIONAL_PRECHECK` | Kết quả có điều kiện được carry forward; chưa phải selection hoặc approval. |
| `FOLLOW_UP_EVIDENCE_REQUIRED` | `MISSING_EVIDENCE` | Tạo request cho từng field explicit và pause. |
| `NOT_ELIGIBLE` | `NOT_ELIGIBLE` | Giữ kết quả non-binding; chưa phải final Decision. |
| `NO_PROVIDER_RECOMMENDATION` | `NO_RECOMMENDATION` | Giữ candidate nhưng chưa có provider recommendation. |
| `PRECHECK_UNAVAILABLE` | `SERVICE_UNAVAILABLE` | Provider/simulation không khả dụng; không phải thiếu Founder data. |

Aggregate `DecisionPostPrecheckOutcome` gồm:

- `FOLLOW_UP_EVIDENCE_REQUIRED`
- `CONDITIONAL_OPTIONS_AVAILABLE`
- `ALL_OPTIONS_NOT_ELIGIBLE`
- `NO_PROVIDER_RECOMMENDATION`
- `PRECHECK_SERVICE_UNAVAILABLE`
- `MIXED_NON_ACTIONABLE_RESULTS`

Chỉ `MISSING_EVIDENCE` với `required_follow_up_fields` nonblank mới tạo `MissingDataRequest`.
`MISSING_EVIDENCE` không nêu field sẽ fail safe thay vì invent requirement. Review luôn giữ
`non_binding = true`, `bank_approval_obtained = false`, `selection_performed = false`,
`ranking_performed = false` và `documents_prepared = false`.

## 18. Governance authorization và post-precheck evidence

`ApprovalRequestStatus` gồm:

| Enum | Ý nghĩa |
|---|---|
| `PENDING` | Đang chờ Founder quyết định cho exact protected action. |
| `AUTHORIZED_WITHOUT_HUMAN` | Loaded policy xác nhận không cần human và không có checkpoint khác trigger; vẫn persist policy lineage. |
| `APPROVED` | Founder đã `APPROVE`; bắt buộc có `decision_record`. |
| `REJECTED` | Founder đã `REJECT`; bắt buộc có `decision_record`. Với Banking precheck, Workflow đóng route tại `BANKING_PRECHECK_DECLINED`. |
| `EXPIRED` | Subject/policy không còn current; authorization cũ không được dùng. |

Mọi Banking precheck authorization đều giữ `policy_artifact_id`,
`policy_artifact_version`, `policy_input_hash` và `policy_coverage_ids`. Human approval không thay thế
policy lineage; machine authorization không được chứa human `decision_record`.

Khi post-precheck outcome là `MISSING_EVIDENCE`, endpoint staff tạo
`BANKING_PRECHECK_EVIDENCE_SUPPLEMENT` với các field chính:

| Field | Ý nghĩa |
|---|---|
| `missing_request_id` | Exact request đang mở được giải quyết. |
| `evidence_reference_id` | Reference tới evidence; không phải nội dung API request tự suy luận. |
| `provided_by` | Do server gán `AUTHORIZED_STAFF`, không nhận từ client. |
| `input_handoff_resolved` | `true` khi exact request được resolve. |
| `fresh_governed_precheck_required` | Luôn `true`; evidence mới không tái diễn giải result cũ. |
| `source_precheck_result_unchanged` | Luôn `true`. |
| `bank_approval_obtained` | Luôn `false`. |
| `protected_action_authorized` | Luôn `false`; nộp evidence không phải approval. |

Sau khi hết request mở, Workflow dùng stage `BANKING_PRECHECK_RETRY_REQUIRED` và status
`WAITING_FOR_DEPENDENCIES`. Fresh provider retry chưa được implement; hệ thống không giả lập rằng
evidence reference đã tự động trở thành request hợp lệ cho ngân hàng.

## 19. Provider posture enums

### 19.1 ProviderEligibilityStatus

| Enum | Ý nghĩa |
|---|---|
| `ELIGIBLE` | Scenario/provider cho biết hồ sơ đủ điều kiện ở mức precheck; không phải final approval. |
| `CONDITIONAL` | Eligibility còn phụ thuộc conditions/evidence được nêu explicit. |
| `NOT_ELIGIBLE` | Không đủ điều kiện theo response hiện tại; không thay Final Decision của OPC. |
| `NOT_EVALUABLE` | Response không có đủ thông tin để kết luận. |

### 19.2 ProviderGuaranteeDecision

| Enum | Ý nghĩa |
|---|---|
| `WILLING` | Provider posture sẵn sàng xem xét; vẫn phải đọc authority/non-binding flags. |
| `CONDITIONAL` | Chỉ có thể tiếp tục nếu exact conditions được đáp ứng. |
| `DECLINED` | Provider posture từ chối trong response đó. |
| `NO_DECISION` | Không có provider decision. |

### 19.3 BankingPrecheckSupportedAmountStrategy

| Enum | Ý nghĩa |
|---|---|
| `NONE` | Scenario không tạo supported amount. |
| `ECHO_REQUESTED_AMOUNT` | Mock lặp lại exact authorized requested amount để test full coverage; không phải accepted amount thật. |

Mọi current result vẫn có `BankingPrecheckResultAuthority.SIMULATED_NON_BINDING` và
`bank_approval_obtained = false`. Partial coverage (`supported_amount < requested_amount`) không
được route vào Document trong phase này.

## 20. Document artifacts và enums

### 20.1 Artifact chain

| `ArtifactType` | Ý nghĩa |
|---|---|
| `DOCUMENT_PREPARATION_REQUEST` | Decision handoff cho một viable conditional result; không phải selection. |
| `DOCUMENT_CHECKLIST` | Một item/evidence status cho mỗi provider document code. |
| `DOCUMENT_PACKAGE_DRAFT` | Internal sanitized draft, có thể còn blocking requests. |
| `DOCUMENT_EVIDENCE_SUPPLEMENT` | Immutable opaque document reference và content hash giải quyết exact request. |
| `DOCUMENT_RELEASE_PACKAGE` | Complete masked candidate consumed by the conditional Internal Decision Package path; chưa authorize/chưa gửi. |

Master Workflow tự tiếp tục chỉ khi có đúng một `DOCUMENT_PREPARATION_REQUEST`. Nhiều request không
được chọn theo array order; route fail safe cho tới khi Decision selection được implement.

### 20.2 DocumentRequirementCode

| Enum | Ý nghĩa trong current scenario |
|---|---|
| `SIGNED_CONTRACT` | Cần reference đến hợp đồng đã ký; TeamPack structured row không đủ. |
| `COMPANY_PROFILE` | Dùng exact `02_OPC_PROFILE`, sau đó phải minimize/mask. |
| `PERFORMANCE_BOND_REQUEST_FORM` | OPC tạo internal unsigned draft. |
| `CASHFLOW_BUFFER_EVIDENCE` | Chỉ có thể dùng với scope limitation; OPC-global evidence không được quy cho contract. |

### 20.3 DocumentRequirementStatus

| Enum | Ý nghĩa |
|---|---|
| `AVAILABLE` | Exact evidence/reference có sẵn. |
| `DRAFTED` | Internal draft đã tạo nhưng chưa có authority/signature cuối. |
| `MISSING` | Thiếu evidence bắt buộc; luôn có `missing_request_id`. |
| `AVAILABLE_WITH_LIMITATIONS` | Có evidence nhưng phải giữ limitation về scope/authority. |
| `NOT_APPLICABLE` | Requirement không áp dụng. |

### 20.4 DocumentPackageReadiness

| Enum | Ý nghĩa |
|---|---|
| `WAITING_FOR_INPUT` | Có ít nhất một blocking `MissingDataRequest`; chưa tạo release candidate. |
| `READY_FOR_INTERNAL_DECISION` | Không còn blocking gap; package sẵn sàng làm input cho Decision, không kích hoạt Founder approval. |
| `READY_FOR_RELEASE_REVIEW` | Giá trị legacy chỉ được giữ để đọc artifact cũ; run mới không emit giá trị này. |

### 20.5 Các field quan trọng

`DOCUMENT_PREPARATION_REQUEST`:

| Field | Ý nghĩa |
|---|---|
| `requested_amount` / `supported_amount` / `currency` | Full-coverage VND mock facts; current validator yêu cầu hai amount bằng nhau. |
| `required_document_codes` / `approval_condition_codes` | Exact controlled codes từ normalized scenario response. |
| `provider_result_authority` / `non_binding` | Luôn giữ non-binding boundary. |
| `selection_performed` / `bank_approval_obtained` | Luôn `false`. |
| `source_artifact_ids` / `evidence_ids` | Exact result/review lineage. |

`DOCUMENT_PACKAGE_DRAFT` và `DOCUMENT_RELEASE_PACKAGE`:

| Field | Ý nghĩa |
|---|---|
| `sanitized_payload` | Chỉ các output values sau minimization/masking. |
| `classification_decisions` | Exact field-to-policy decisions. |
| `masking_manifest` | Per-field action/algorithm/output digest, exact source evidence IDs và canonical policy SHA-256; không chứa raw input. |
| `missing_data_requests` | Chỉ có trên draft khi readiness là `WAITING_FOR_INPUT`. |
| `release_authorized` | `false` trong business artifact; authorization là Governance state riêng. |
| `external_release_performed` | Luôn `false` trong current phase. |

`DOCUMENT_EVIDENCE_SUPPLEMENT` nhận `document_reference_id` theo namespace
`DOCREF-<UUIDv4>` và `content_sha256` đúng 64 hex characters. API không nhận arbitrary reference
text, path, URL, raw file bytes hoặc client-controlled `provided_by`. Reference/hash vẫn là metadata
do caller khai báo và chưa được repository xác minh trong prototype. `evidence_note` chỉ nhận enum
`REQUESTED_DOCUMENT_REFERENCE_SUPPLIED`, không nhận free text. Current intake route:

```http
POST /api/cases/{evaluation_case_id}/documents/evidence-supplements
```

Current minimum profile fields `company_id` và `company_name` là server assumption do prototype
composition root sở hữu. Đây không phải official VietinBank schema hoặc relationship suy ra từ tên.

## 21. Data classification và masking enums

### 21.1 DataClassification

| Enum | Default trust-boundary meaning |
|---|---|
| `PUBLIC` | Có thể exact pass-through khi context allowlist cho phép. |
| `INTERNAL` | Minimize; identifier thường phải token hóa. |
| `CONFIDENTIAL` | Generalize/omit, trừ exact purpose exception trong server policy. |
| `RESTRICTED` | Không được `ALLOW_EXACT`; dùng contextual token khi cần. |
| `RESTRICTED_SECRET` | Chỉ `OMIT` hoặc pre-existing vault reference. |
| `CONTEXT_DEPENDENT` | Free text phải deterministic redact hoặc fail closed. |

### 21.2 MaskingAction và algorithm tương ứng

| Action | Algorithm | Ý nghĩa |
|---|---|---|
| `ALLOW_EXACT` | `EXACT_PASS_THROUGH` | Giữ exact value chỉ trong allowlisted recipient/purpose. |
| `OMIT` | `DATA_MINIMIZATION_OMIT` | Loại khỏi outbound payload. |
| `TOKENIZE` | `HMAC_SHA256_CONTEXTUAL_TOKEN` | Pseudonym ổn định trong exact context. |
| `PARTIAL_MASK` | `PARTIAL_MASK_DISPLAY` | Chỉ cho display; không đủ cho partner identifier. |
| `GENERALIZE` | `VND_VALUE_BANDING` | Chuyển amount sang configured deterministic band. |
| `REDACT` | `FREE_TEXT_IDENTIFIER_REDACTION` | Xóa exact identifiers/patterns khỏi text. |
| `VAULT_REFERENCE` | `VAULT_REFERENCE_ONLY` | Chỉ chấp nhận `vault://` reference, không raw credential. |

`MaskingReasonCode` gồm:

- `POLICY_ACTION`: action trực tiếp từ exact rule;
- `NOT_REQUIRED_FOR_PURPOSE`: field bị omit do data minimization; và
- `CONTEXT_NOT_ALLOWED`: recipient/purpose không nằm trong allowlist.

Contextual HMAC namespace gồm `provider | purpose | field_type | key_version`. Secret runtime key
phải tối thiểu 32 bytes; output token tối thiểu 16 bytes (128 bit). Secret/key digest không nằm
trong artifact, log hoặc node identity; node identity chỉ dùng canonical policy hash và key
version. Thiếu key hoặc unknown field làm Document fail closed nhưng không làm các upstream
assessment giả vờ thành công.

Tokenization là pseudonymization, không phải anonymization. Plain SHA-256, Base64 và LLM rewrite
không phải masking controls. Sheet `21_MASKING_EXAMPLES` chỉ là ví dụ và không bao giờ được dùng
làm executable policy/algorithm selector.

## 22. Document release Governance state

`DOCUMENT_RELEASE_PACKAGE_READY` là internal Document milestone. Workflow persist package rồi có
thể tiếp tục sang `INTERNAL_DECISION_PACKAGE_ASSEMBLY`, nhưng không tạo `ActionCommand`,
`ApprovalRequest`, `WAITING_FOR_APPROVAL`, hoặc external-send authority. Summary tại boundary này
phải giữ:

```text
document_release_authorized         = false
document_external_release_performed = false
```

Checkpoint `SEND_DOCUMENT_TO_EXTERNAL_PARTNER` đã được Initial Risk đăng ký vẫn ở trạng thái dormant;
registration không tự pause workflow. Approval `SUBMIT_BANKING_PRECHECK` không được tái sử dụng.
Internal Decision Package chỉ tổng hợp evidence và cũng không phải approval subject. Một phase
Decision sau đó phải tạo exact evidence-bound recommendation/proposal để Founder xem phương án.
Chỉ proposal tương lai đó mới được kích hoạt checkpoint gửi tài liệu. Final Decision
recommendation/proposal, connector authorization và external delivery chưa được implement.

## 23. Internal Decision Package enums

`ArtifactType.INTERNAL_DECISION_PACKAGE` là evidence dossier deterministic đã validate. Nó dùng
`InternalDecisionPackageReadiness.READY`; không có trạng thái partial-ready.

`InternalDecisionAssemblyPath` gồm:

- `DIRECT_ROUTE`;
- `BANKING_NO_VIABLE_OPTION`;
- `BANKING_NO_PRECHECK_PATH`;
- `BANKING_PRECHECK_DECLINED`;
- `BANKING_NON_ACTIONABLE`; và
- `CONDITIONAL_DOCUMENT_READY`.

Mỗi path bắt buộc phải khớp với exact route/review/Governance/Document artifacts tương ứng. Package
ready luôn giữ `recommendation_performed`, `selection_performed`, `approval_requested` và
`external_action_performed` bằng `false`. Xem
[Internal Decision Package](INTERNAL_DECISION_PACKAGE.md) để biết source và validation rules.
