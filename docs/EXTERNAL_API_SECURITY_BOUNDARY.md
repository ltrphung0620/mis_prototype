# Ranh giới bảo mật khi gọi API ngoại vi

## 1. Mục đích

Tài liệu này mô tả các ranh giới bảo mật đã có cơ sở rõ trong hệ thống OPC MIS khi một luồng nghiệp
vụ cần gọi adapter ngoại vi. Phạm vi hiện tại tập trung vào luồng Banking precheck và các nguyên tắc
chung có thể tái sử dụng cho adapter thật trong tương lai.

Hệ thống hiện sử dụng Banking precheck adapter mô phỏng, không gửi dữ liệu đến ngân hàng thật. Vì
vậy, tài liệu này xác nhận các kiểm soát ở lớp ứng dụng, workflow và governance; không tuyên bố rằng
các kiểm soát hạ tầng của một kết nối ngân hàng thật đã được triển khai.

## 2. Nguyên tắc ranh giới tổng thể

Luồng được kiểm soát theo thứ tự:

```text
Business Component
→ Workflow Orchestrator
→ Evidence Validation
→ Governance Gate
→ Human Approval
→ Authorized Action Permit
→ External Adapter
→ Response Validation
→ Artifact Persistence
```

Ranh giới này bảo đảm một business component không thể tự ý gửi dữ liệu ra ngoài, tự cấp quyền cho
mình hoặc bỏ qua bước kiểm tra bằng chứng.

## 3. Các điểm đã có cơ sở rõ

### 3.1 Business component không sở hữu external side effect

Business component chỉ được tạo artifact draft, signal hoặc action command. Component không được:

- gọi protected external adapter trực tiếp;
- tự phê duyệt hành động;
- thay đổi trạng thái workflow;
- persist artifact hoặc kết quả gửi ra ngoài.

Workflow Orchestrator là thành phần sở hữu thứ tự thực thi và là nơi duy nhất điều phối lời gọi đến
protected adapter sau khi governance cho phép.

### 3.2 External call được biểu diễn thành protected action

Một yêu cầu gửi Banking precheck được biểu diễn bằng protected action có kiểu xác định:

```text
SUBMIT_BANKING_PRECHECK
```

Action command phải tham chiếu đến proposal artifact đã được persist. Việc tạo proposal không đồng
nghĩa với việc đã gửi dữ liệu. Proposal vẫn là đối tượng không có side effect và phải chờ governance
đánh giá.

### 3.3 Human approval là điều kiện bắt buộc

Governance chỉ cho phép tiếp tục khi approval request:

- tồn tại trong repository;
- có trạng thái `APPROVED`;
- có quyết định `APPROVE` rõ ràng của con người;
- thuộc đúng workflow run và evaluation case;
- bảo vệ đúng action `SUBMIT_BANKING_PRECHECK`;
- tham chiếu đúng proposal artifact cần thực thi.

Nếu một trong các điều kiện trên không thỏa mãn, hệ thống không cấp permit và adapter không được gọi.

### 3.4 Approval được ràng buộc với đúng phiên bản dữ liệu

Approval không phải là quyền chung cho mọi lần gửi. Nó được ràng buộc với:

```text
subject_artifact_id
subject_artifact_version
subject_input_hash
```

Trước khi cấp permit, hệ thống đối chiếu artifact hiện tại với artifact đã được phê duyệt. Permit bị
từ chối nếu:

- artifact ID không khớp;
- version đã thay đổi;
- business input hash đã thay đổi;
- artifact không còn là phiên bản mới nhất;
- có nhiều phiên bản mới nhất gây mơ hồ;
- artifact chưa có validation status hợp lệ.

Cơ chế này ngăn việc sử dụng một approval cũ để gửi payload đã bị thay đổi sau phê duyệt.

### 3.5 Permit chỉ cấp quyền cho một hành động cụ thể

Sau khi xác minh approval, Governance phát hành `AuthorizedActionPermit`. Permit chứa danh tính của:

- workflow run;
- evaluation case;
- approval request;
- protected action;
- subject artifact, version và input hash;
- người phê duyệt và thời điểm phê duyệt.

Permit được tạo từ các đầu vào xác định và không tự thực hiện external side effect. Adapter phải
kiểm tra permit trước khi xử lý request.

### 3.6 Request được resolve từ nguồn dữ liệu tường minh

Payload Banking precheck được tạo từ các binding đã khai báo rõ:

```text
contract_id     → EvaluationCase
amount          → BankingInputSupplement
company_profile → 02_OPC_PROFILE
```

Hệ thống không suy diễn quan hệ từ mô tả hoặc tên gần giống. Resolver kiểm tra source artifact,
source record ID, loại dữ liệu, case, dataset và contract trước khi tạo request.

Giá trị nhạy cảm trong `company_profile` chỉ được resolve trong bộ nhớ tại thời điểm chuẩn bị gọi
adapter. Proposal và artifact kết quả không lưu lại request body hoặc giá trị `company_profile`.

### 3.7 Request có kiểm tra toàn vẹn và idempotency

Request có canonical request hash được tính từ toàn bộ business payload theo thứ tự ổn định.
Idempotency key tiếp tục ràng buộc:

- permit ID;
- proposal artifact ID;
- proposal item ID;
- canonical request hash.

Adapter tính lại các giá trị này trước khi xử lý. Request bị từ chối nếu request hash hoặc
idempotency key không khớp, qua đó phát hiện payload bị thay đổi hoặc request không thuộc permit đã
cấp.

### 3.8 Adapter áp dụng fail-closed authorization

Adapter kiểm tra tối thiểu các điều kiện sau trước khi thực thi:

- protected action đúng loại;
- evaluation case trong permit khớp request;
- subject artifact trong permit khớp proposal artifact của request;
- request hash và idempotency key hợp lệ.

Khi authorization hoặc integrity check thất bại, adapter phát sinh lỗi và không trả về một kết quả
giả như thể external call đã thành công.

### 3.9 Lỗi hạ tầng được xử lý theo hướng failed-safe

Workflow Orchestrator bắt các lỗi authorization, request resolution, schema validation và lỗi adapter.
Các lỗi này được chuyển thành kết quả `FAILED_SAFE` thay vì:

- tiếp tục workflow như thành công;
- tự tạo provider response;
- tuyên bố đã được ngân hàng phê duyệt;
- persist một artifact kết quả không hợp lệ.

### 3.10 Response phải qua validation trước khi persist

Kết quả adapter được chuyển thành typed result set. Trước khi persist, hệ thống:

- kiểm tra contract của component result;
- chạy Evidence Validator;
- từ chối persistence khi validation report có trạng thái `BLOCKED`;
- chỉ persist artifact đã được xác định là hợp lệ hoặc hợp lệ kèm cảnh báo.

Result component không được phát approval signal hoặc protected action mới, nhờ đó response ngoại
vi không thể tự mở rộng quyền hoặc kích hoạt một side effect tiếp theo.

### 3.11 Dữ liệu nhạy cảm không đi vào artifact kết quả

Các giá trị `company_profile` được đánh dấu không hiển thị trong `repr`. Adapter mô phỏng không giữ
request state và không log các giá trị này. Artifact kết quả chỉ lưu các identifier, hash, outcome,
reason code và metadata cần thiết; không lưu:

- `company_profile`;
- `request_body`;
- `request_payload`.

Đây là biện pháp data minimization và log redaction tại ranh giới adapter. Nó không thay thế một
thuật toán Data Masking hoàn chỉnh.

### 3.12 Kết quả mô phỏng không được mang thẩm quyền ngân hàng

Banking precheck hiện chạy với adapter mô phỏng và kết quả bắt buộc thể hiện:

```text
execution_mode          = SIMULATED
authority               = SIMULATED_NON_BINDING
external_bank_submission = false
bank_approval_obtained   = false
```

Hệ thống cũng không cho phép result set tuyên bố đã chọn phương án, xếp hạng phương án hoặc chuẩn bị
tài liệu. Ranh giới này ngăn kết quả mô phỏng bị hiểu nhầm thành quyết định của ngân hàng.

### 3.13 Secret được lấy từ cấu hình phía server

OpenAI API key được đọc từ biến môi trường và truyền trực tiếp vào SDK client. Public API không nhận
API key hoặc đường dẫn dataset tùy ý từ client. Mã khởi tạo client không log secret.

OpenAI chỉ được bật khi đồng thời có cấu hình `OPENAI_ENABLED` và `OPENAI_API_KEY`; nếu không, hệ
thống sử dụng deterministic fallback cho các phần diễn đạt hỗ trợ.

## 4. Trạng thái bảo đảm hiện tại

Các bảo đảm có thể khẳng định ở phiên bản hiện tại:

- protected external action không được gọi trực tiếp từ business component;
- Banking precheck phải qua human approval;
- approval bị khóa vào đúng artifact, version và business input hash;
- adapter chỉ nhận request có permit và integrity identity hợp lệ;
- request nhạy cảm được tạo trong bộ nhớ và không persist vào result artifact;
- lỗi adapter làm workflow failed-safe;
- response phải được validate trước persistence;
- kết quả mô phỏng không được tuyên bố là bank approval hoặc external bank submission.

## 5. Giới hạn của phạm vi hiện tại

Tài liệu này không khẳng định các nội dung sau đã được triển khai:

- kết nối đến API ngân hàng thật;
- TLS/mTLS, OAuth, certificate pinning hoặc key rotation cho ngân hàng;
- network egress allowlist hoặc firewall policy;
- rate limiting và circuit breaker tập trung;
- Data Masking theo classification policy trước mọi outbound call;
- authentication/RBAC hoàn chỉnh cho người phê duyệt;
- audit logger bảo mật hợp nhất cho toàn bộ external call;
- data-loss-prevention gateway chung cho payload gửi OpenAI hoặc đối tác.

Các nội dung này cần được bổ sung và kiểm thử trước khi thay adapter mô phỏng bằng một external
adapter có side effect thật.

## 6. Decision-to-Document external-submission boundary

The implemented Document-release path has a stricter terminal boundary than the simulated Banking
precheck path. It never issues an `AuthorizedActionPermit` to a Document connector because no such
connector exists.

```text
approved exact ACCEPT Decision Card with Document package
  -> validated EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL
  -> separate Governance request for SEND_DOCUMENT_TO_EXTERNAL_PARTNER
  -> exact proposal authorization
  -> READY_FOR_EXTERNAL_SUBMISSION
     adapter_invoked = false
     external_submission_performed = false
     submission_receipt_created = false
```

The final-decision approval and the external-release approval are different requests and protect
different subjects. The first binds the exact `DECISION_CARD`; the second binds the exact
`EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL`. Each request also records the current checkpoint-registry
artifact ID/version/input hash and the exact triggered checkpoint IDs. Superseding either the
subject or policy scope invalidates authorization.

`READY_FOR_EXTERNAL_SUBMISSION` is not a provider acknowledgment, delivery status, or receipt. A
future real connector must start after this boundary and add its own permit, secure reference
resolution, outbound minimization, transport controls, response/receipt validation, idempotency,
retry, and reconciliation. See
[Decision, Final Approval, and External-Release Readiness](DECISION_FINAL_APPROVAL_AND_RELEASE.md).
