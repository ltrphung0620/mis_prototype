# Giả định phản hồi Banking Provider và điểm mở rộng tương lai

## 1. Phạm vi của giả định

TeamPack không chứa phản hồi precheck thật từ VietinBank, không chứa đặc tả response chính thức
của `API-002` và không chứng minh ngân hàng đã đồng ý cấp bảo lãnh. TeamPack hiện chỉ cung cấp
metadata API, catalog product, handling rule và request example.

Để kiểm thử workflow đến Document Skill, prototype dùng một scenario deterministic do server quản
lý tại `config/banking/precheck_simulation_scenarios.json`. Scenario này là dữ liệu mô phỏng phục vụ
test, không phải dữ liệu do VietinBank gửi, và mọi result bắt buộc giữ:

```text
execution_mode = SIMULATED
authority      = SIMULATED_NON_BINDING
non_binding    = true
```

Không được hiển thị result này như bank approval, binding offer, guarantee issuance hoặc final
financing commitment.

## 2. Scenario `API-002` hiện tại

Scenario server-owned hiện trả một conditional response:

```text
scenario_id               = API-002-SIMULATED-CONDITIONAL-PRECHECK
api_id                    = API-002
provider                  = VietinBank
outcome                   = CONDITIONAL_PRECHECK
reason_code               = SIMULATED_CONDITIONAL_PRECHECK
eligibility_status        = ELIGIBLE
guarantee_decision        = CONDITIONAL
supported_amount_strategy = ECHO_REQUESTED_AMOUNT
currency                  = VND
authority                 = SIMULATED_NON_BINDING
```

Required-document codes:

- `SIGNED_CONTRACT`
- `COMPANY_PROFILE`
- `PERFORMANCE_BOND_REQUEST_FORM`
- `CASHFLOW_BUFFER_EVIDENCE`

Approval-condition codes:

- `CONTRACT_SIGNED`
- `CASHFLOW_BUFFER_CONFIRMED`

`ECHO_REQUESTED_AMOUNT` chỉ làm cho mock response lặp lại exact amount của request đã được
Governance cho phép, nhằm kiểm thử đường đi full-coverage. Giá trị đó không được diễn giải là hạn
mức VietinBank thật đã chấp nhận.

## 3. Khoảng trống dữ liệu không được tự lấp

| Thông tin | TeamPack hiện có | Cách hệ thống xử lý |
|---|---|---|
| Provider eligibility | Không có response thật | Chỉ dùng giá trị của mock scenario và gắn `SIMULATED_NON_BINDING` |
| Guarantee decision | Không có quyết định thật | Chỉ carry forward `CONDITIONAL` của scenario; `bank_approval_obtained = false` |
| Supported amount | Không có hạn mức thật | Mock dùng `ECHO_REQUESTED_AMOUNT`; không gọi đó là accepted amount thật |
| Required documents | Không có checklist VietinBank thật | Dùng exact codes của scenario, không suy ra bằng OpenAI hoặc mô tả tự nhiên |
| Approval conditions | Không có conditions có authority | Dùng exact codes của scenario, không phát minh conditions mới |

Các field sau không thay thế provider response:

- `10_CREDIT_PROFILE.requested_amount` là nhu cầu tín dụng tham khảo và chỉ dùng khi có relationship
  explicit.
- `11_BANK_PRODUCTS.minimum_amount` là điều kiện catalog, không phải hạn mức ngân hàng chấp nhận.
- `12_API_CATALOG.payload_example` là request example, không phải provider response.
- Founder approval cho `SUBMIT_BANKING_PRECHECK` chỉ cho phép chạy exact simulated proposal; nó
  không phải bank approval và không cho phép phát hành document.

## 4. Điều kiện Decision handoff sang Document

Decision chỉ tạo `DOCUMENT_PREPARATION_REQUEST` từ một normalized result đã validate khi result đó:

- có outcome `CONDITIONAL_PRECHECK`;
- có eligibility/guarantee fields, supported amount, currency, document codes và condition codes
  nhất quán;
- có exact result/review/evidence lineage;
- có `supported_amount == requested_amount` trong phase hiện tại; và
- vẫn giữ `non_binding = true`, `selection_performed = false` và
  `bank_approval_obtained = false`.

Partial coverage, ví dụ request 450 triệu nhưng provider chỉ hỗ trợ 420 triệu, được hoãn sang phase
mở rộng. Prototype không tự tính phần thiếu, không ghép nguồn vốn và không route partial coverage
vào Document Skill.

Decision bảo toàn mọi viable conditional result dưới dạng request độc lập. Master Workflow chỉ tự
chạy Document khi có **đúng một** request khả dụng. Trên conditional branch, không có request hoặc
nhiều hơn một request đều fail safe; trường hợp nhiều request yêu cầu Decision selection ở phase
sau. Workflow không tự chọn bank/product hoặc lấy phần tử đầu tiên.

```text
Founder authorizes SUBMIT_BANKING_PRECHECK
→ simulated API-002 conditional response
→ Evidence Validator
→ DECISION_POST_PRECHECK_REVIEW
→ DECISION_DOCUMENT_HANDOFF
→ exactly one DOCUMENT_PREPARATION_REQUEST
→ DOCUMENT_PREPARATION
```

## 5. Document preparation và Internal Decision boundary

Document Skill chuẩn bị một outbound banking dossier **trong nội bộ OPC**. Đây không phải hồ sơ
quyết định nội bộ và chưa phải dữ liệu đã gửi ra ngoài. Với scenario hiện tại:

- structured company profile có thể dùng sau data minimization/masking;
- performance-bond request form chỉ ở trạng thái `DRAFTED` và `DRAFT_NOT_SIGNED`;
- cashflow evidence chỉ có scope `OPC_GLOBAL`, phải giữ limitation và không được quy cho contract;
- TeamPack không có signed-contract document reference, nên `SIGNED_CONTRACT` là blocking gap.

Khi thiếu signed contract, Document tạo `MissingDataRequest`, package draft có
`WAITING_FOR_INPUT`, và Workflow pause tại `DOCUMENT_PREPARATION`. Authorized staff chỉ nộp metadata
tham chiếu bất biến gồm opaque `document_reference_id`, `content_sha256`, exact request/type và note;
API không nhận raw bytes, filesystem path hoặc URL. Sau khi exact request được resolve, Workflow
rebuild checklist/package từ artifact supplement mới, không sửa artifact cũ.

Khi package hoàn chỉnh, hệ thống tạo `DOCUMENT_RELEASE_PACKAGE`. Artifact này được lưu làm masked
input cho nhánh `CONDITIONAL_DOCUMENT_READY` của Internal Decision Package, với:

```text
release_authorized         = false
external_release_performed = false
```

Việc package sẵn sàng không tạo protected action, `ApprovalRequest`, hoặc Founder pause. Checkpoint
`SEND_DOCUMENT_TO_EXTERNAL_PARTNER` đã được đăng ký từ Risk vẫn dormant. Approval trước đó cho
`SUBMIT_BANKING_PRECHECK` không được tái sử dụng. Internal Decision Package chỉ tổng hợp exact
evidence; nó không chọn option hay request approval. Một phase Decision sau đó phải tạo exact
evidence-bound recommendation/proposal để Founder đồng ý với phương án; chỉ proposal đó mới được
kích hoạt checkpoint gửi tài liệu. Final recommendation/proposal, connector và việc gửi tài liệu
thật ra VietinBank đều chưa được implement.

## 6. Company-profile assumption

TeamPack/provider metadata không định nghĩa schema tài liệu company profile chính thức. Vì vậy
minimum required profile fields là assumption do server cấu hình/composition root sở hữu, không
phải yêu cầu được gán cho VietinBank và không được hard-code theo contract. Thiếu một required field
làm package fail closed; Document không fuzzy-match tên field hoặc lấy dữ liệu credit profile thay
thế.

Assumption này phải được thay bằng schema/provider contract có version khi tích hợp thật.

## 7. Data masking trước Internal Decision handoff

Document chỉ tạo release candidate từ payload đã qua policy server-owned:

```text
recipient + purpose + minimum required fields
→ data minimization
→ exact classification
→ deterministic masking
→ MaskingManifest
→ Evidence Validator
```

Các invariant chính:

- contextual tokenization dùng HMAC-SHA256 với namespace
  `provider | purpose | field | key_version`;
- secret key được runtime inject, tối thiểu 32 bytes (256 bit), không nằm trong TeamPack, config,
  artifact, exception hoặc log;
- token output tối thiểu 128 bit;
- unknown field, thiếu key, context/policy không hợp lệ hoặc unsupported payload đều fail closed;
- plain SHA-256, Base64 và LLM rewrite không phải masking controls;
- partial masking chỉ dùng cho display, không thay contextual token cho partner payload;
- tokenization là pseudonymization, không phải anonymization;
- Sheet `21_MASKING_EXAMPLES` chỉ là ví dụ minh họa, không phải executable policy và không quyết
  định thuật toán.

Chi tiết nằm trong [Data Masking Policy](DATA_MASKING_POLICY.md) và
[Data Masking Algorithms](DATA_MASKING_ALGORITHMS.md).

## 8. Điều kiện để thay mock bằng provider integration thật

Trước khi gọi VietinBank/sandbox thật cần bổ sung tối thiểu:

1. response schema và error contract chính thức, có version;
2. authentication, transport security, secret manager và provider identity validation;
3. binding giữa request, proposal, authorization permit, idempotency key và response;
4. semantics chính thức cho eligibility, guarantee decision, supported amount, required documents
   và conditions;
5. xử lý partial coverage và multi-option selection bằng Decision policy đã được duyệt;
6. document repository/virus scan/content validation cho file thật;
7. external connector chỉ nhận `sanitized_payload`, không serialize artifact/evidence closure;
8. retry, timeout, reconciliation và append-only audit cho actual submission/release.

Cho đến khi các điều kiện trên hoàn tất, mọi `API-002` result và document flow trong prototype phải
được hiểu là deterministic, simulated, non-binding và không có external side effect.
