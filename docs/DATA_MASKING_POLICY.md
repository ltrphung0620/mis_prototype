# OPC MIS Data Masking Policy

## 1. Mục đích và ranh giới

Policy này bảo vệ dữ liệu tại trust boundary, đặc biệt khi Document Skill chuẩn bị
payload dự kiến gửi ngân hàng hoặc đối tác. Thứ tự bắt buộc là:

```text
Purpose + recipient
→ data minimization
→ exact field classification
→ deterministic masking
→ MaskingManifest
→ validation
→ outbound package draft
```

Policy không gửi dữ liệu, không cấp approval và không thay thế Governance. Document
Skill chỉ nhận `MaskedPayload`; external adapter sau này chỉ được serialize
`MaskedPayload.values`, không được serialize toàn bộ artifact envelope hay evidence closure.

## 2. Nguồn policy

- `20_DATA_CLASS` cung cấp bối cảnh phân loại ở mức TeamPack, nhưng prototype không tạo giả
  `source_evidence_ids` cho executable field rules khi chưa có exact row-to-rule binding.
- `21_MASKING_EXAMPLES` chỉ chứa ví dụ minh họa input/output. Sheet này được ingestion
  theo đúng tên và headers nhưng **không phải mã nguồn thuật toán**.
- `22_API_HANDLING_RULES` cung cấp yêu cầu xử lý ở trust boundary.
- `config/data_protection/masking_policy.json` là policy thực thi do server quản lý,
  có version và không chứa secret key.

Mỗi `MaskingManifest` mang SHA-256 của canonical policy document. Governance so sánh commitment
này với policy đang nạp; thay nội dung policy mà không đổi version vẫn làm validation thất bại.

Thay một ví dụ ở Sheet 21 không được phép tự động thay thuật toán. Mọi thay đổi thuật
toán hoặc field allowlist phải qua review và tăng policy/algorithm version.

## 3. Threat model

Policy giảm các rủi ro sau:

- raw identifier bị gửi sang provider không cần thiết;
- secret/API credential đi vào prompt, artifact outbound hoặc log;
- plain hash của ID có không gian nhỏ bị dictionary attack;
- cùng một token được dùng ở nhiều provider/purpose và tạo khả năng cross-context linking;
- free text chứa identifier ẩn ngoài các field có cấu trúc;
- field chưa phân loại vô tình được truyền qua do default permissive;
- LLM tự chọn field, thuật toán, amount band hoặc tạo bank requirement.

Policy không tuyên bố chống được người có quyền truy cập key/token vault, correlation từ
thông tin công khai, hoặc tái nhận diện từ một tập dữ liệu ngoài hệ thống. Tokenization ở
đây là pseudonymization, không phải anonymization tuyệt đối.

## 4. Data minimization

Caller bắt buộc khai báo:

```text
recipient
purpose
required_fields
```

`required_fields` không chỉ là nhãn phục vụ manifest. Mọi field đã khai báo bắt buộc phải hiện
diện trong input payload; thiếu bất kỳ field nào làm toàn bộ masking operation fail closed. Caller
không được khai báo một field là required rồi dựa vào giá trị mặc định, LLM hoặc adapter để bổ sung
sau.

Recipient được kiểm tra theo hai lớp chính xác:

1. recipient phải có trong global `MaskingPolicyDocument.allowed_recipients`;
2. từng field rule phải chứa đúng recipient đó trong `allowed_recipients` của field.

Wildcard `*` bị cấm ở cả global recipient allowlist và field-level recipient allowlist. Recipient
không có trong global allowlist làm toàn bộ operation fail closed; recipient không được field rule
cho phép khiến riêng field đó bị `OMIT` với reason `CONTEXT_NOT_ALLOWED`. Wildcard vẫn có thể xuất
hiện trong purpose allowlist đối với rule cố ý áp dụng cho mọi purpose đã được review.

Field có trong payload nhưng không thuộc `required_fields` bị `OMIT` và vẫn có một
manifest item giải thích `NOT_REQUIRED_FOR_PURPOSE`. Field không nằm trong allowlist của
recipient/purpose cũng bị `OMIT`. Field không có exact classification rule làm toàn bộ
operation fail closed; hệ thống không fuzzy-match hoặc suy luận theo tên gần giống.

Input hiện là flat mapping các JSON scalar. File binary, nested object và arbitrary path
phải được xử lý bởi một intake/document repository riêng trước khi đi vào policy. Điều
này tránh một dict/file chưa scan bị coi như một scalar an toàn.

## 5. Classification

| Classification | Default handling tại external boundary |
|---|---|
| `PUBLIC` | `ALLOW_EXACT` khi đúng purpose |
| `INTERNAL` | minimize; token/surrogate cho identifier |
| `CONFIDENTIAL` | `GENERALIZE` hoặc `OMIT`; exact chỉ khi server policy nói rõ provider cần |
| `RESTRICTED` | contextual deterministic `TOKENIZE`; không `ALLOW_EXACT` |
| `RESTRICTED_SECRET` | `OMIT` hoặc pre-existing `vault://` reference cho secure connector |
| `CONTEXT_DEPENDENT` | deterministic `REDACT`, fail closed nếu input không phải text đã hỗ trợ |

Ví dụ ngoại lệ có chủ đích: `requested_amount` được gửi exact cho purpose
`PERFORMANCE_BOND_DOCUMENT_RELEASE`, vì ngân hàng cần amount chính xác để xử lý yêu cầu.
Ngoại lệ này nằm trong server policy, không phải quyết định của OpenAI.

## 6. Actions được hỗ trợ

- `ALLOW_EXACT`: chỉ cho field, purpose và exact recipient đã qua cả global và field allowlist;
  `required_fields` không thể override allowlist.
- `OMIT`: loại field khỏi outbound values.
- `TOKENIZE`: HMAC-SHA256 contextual token, tối thiểu 128 bit output.
- `PARTIAL_MASK`: chỉ dùng cho UI/display; không thay tokenization cho partner ID.
- `GENERALIZE`: đưa financial value vào band cấu hình sẵn.
- `REDACT`: loại exact identifiers và structured patterns khỏi free text.
- `VAULT_REFERENCE`: chỉ chấp nhận giá trị đã có prefix `vault://`; raw credential bị chặn.

Founder approval không thể override `RESTRICTED_SECRET` suppression hoặc biến raw
credential thành outbound field.

## 7. Manifest và audit

Mỗi input field tạo một `MaskingManifestItem` gồm:

- classification decision ID;
- recipient và purpose;
- action, reason code, algorithm ID/version và key version;
- field có được include hay không;
- digest của **output đã xử lý**, không phải raw input;
- policy reference và policy evidence IDs;
- exact upstream `source_evidence_ids` của raw business field;
- `raw_value_persisted=false`.

Manifest không có raw input. `MaskedPayload` đồng thời trả:

```text
values
classification_decisions
manifest
```

`manifest_id` phụ thuộc deterministic vào policy version, canonical policy SHA, context và safe
output decisions. Evidence Validator không chỉ kiểm tra digest/ID tự tham chiếu: nó lấy lại exact
raw field value từ các `source_evidence_ids` trong evidence closure rồi chạy lại trusted masking
service. Vì vậy sửa output rồi tính lại digest, manifest ID và package ID vẫn bị chặn nếu không khớp
upstream business evidence.

## 8. Evidence boundary cần lưu ý

Evidence Validator hiện yêu cầu derived evidence nhúng closure của source evidence trong
internal artifact envelope. Vì vậy raw TeamPack display value có thể vẫn tồn tại trong artifact
nội bộ. Prototype hiện chưa có authentication/RBAC cho artifact inspection API, nên API đó chỉ
được dùng trong môi trường phát triển tin cậy và không được expose ra production. Raw value không
được đưa vào `MaskedPayload` hoặc outbound serialization.

Nếu kiến trúc sau này yêu cầu “không raw restricted value trong bất kỳ artifact envelope
nào”, cần bổ sung evidence vault/reference-only evidence và cập nhật Evidence Validator.
Không được xóa lineage hoặc tạo evidence giả để đạt yêu cầu này.

Secret là trường hợp nghiêm ngặt hơn: component không được chọn secret làm evidence,
payload, prompt hoặc log ngay từ đầu.

## 9. Failure behavior

Operation bị chặn khi:

- thiếu purpose, recipient hoặc required-fields declaration;
- payload thiếu một field đã khai báo trong `required_fields`;
- thiếu exact source-evidence mapping cho bất kỳ masking input field nào;
- recipient không có trong global exact-recipient allowlist;
- field chưa có classification/masking rule;
- input không phải finite JSON scalar;
- TOKENIZE nhận null/non-text;
- GENERALIZE nhận số âm, fraction hoặc non-finite;
- VAULT_REFERENCE nhận raw credential;
- cấu hình có duplicate/missing rule hoặc dùng thuật toán sai với action;
- restricted field được cấu hình `ALLOW_EXACT`;
- restricted-secret field không dùng `OMIT`/`VAULT_REFERENCE`.

Exception chỉ nêu field/rule; không echo raw value.

## 10. Vận hành và mở rộng

Khi thêm field/provider/purpose:

1. Xác định business purpose và minimum required fields.
2. Thêm exact classification rule và policy rationale.
3. Chọn action/algorithm server-side.
4. Review re-identification risk và recipient allowlist.
   Recipient mới phải được thêm rõ ràng vào cả global allowlist và từng field rule cần thiết; không
   dùng wildcard để mở quyền hàng loạt.
5. Tăng policy/algorithm version khi semantics đổi.
6. Thêm test chứng minh raw restricted/secret không xuất hiện trong JSON và log.
7. Thêm tamper test chứng minh sửa output và toàn bộ self-referential digest/ID vẫn bị Governance
   chặn khi không khớp upstream evidence.
8. Không dùng Sheet 21 hoặc LLM output làm executable policy.
