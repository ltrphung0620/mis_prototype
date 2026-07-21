# OPC MIS Data Masking Algorithms

## 1. Contextual HMAC tokenization

### Mục tiêu

Tạo pseudonymous identifier ổn định trong cùng context, nhưng không lộ raw ID và không
cho phép liên kết token giữa các provider/purpose khác nhau.

### Canonical input

Raw value chỉ được Unicode-normalize bằng NFC. Hệ thống không trim, lowercase,
fuzzy-normalize hoặc sửa identifier vì các thao tác đó có thể làm hai business identifier
khác nhau bị gộp nhầm.

Namespace gồm đúng bốn phần:

```text
provider + purpose + field_type + key_version
```

Namespace và raw value được encode thành JSON arrays với separators cố định để tránh
ambiguity do nối chuỗi.

### Công thức

```text
namespace_json = canonical_json([
  provider,
  purpose,
  field_type,
  key_version
])

message = canonical_json([namespace_json, NFC(raw_value)])

digest = HMAC-SHA256(secret_key, UTF8(message))
token_material = digest[0:16]       # 128 bits minimum
token = "TOK-" + FIELD + "-" + KEY_VERSION + "-" + Base32(token_material)
```

Ví dụ hình thức:

```text
CUS-005
→ TOK-CUSTOMER-ID-V1-<26 Base32 characters>
```

Token thực tế phụ thuộc secret key và không được ghi vào tài liệu như một giá trị cố định.

### Lý do chọn HMAC-SHA256

- Plain SHA-256 không phù hợp vì ID như `CUS-005` có không gian nhỏ và dễ dictionary
  attack.
- HMAC dùng secret làm cho attacker không thể precompute token nếu không có key.
- 128 bit truncated output vẫn cho collision probability đủ thấp ở quy mô hệ thống;
  implementation cho phép 16–32 bytes và cấm dưới 16 bytes.
- Provider/purpose namespace giảm cross-context linking.

### Key management

- Secret tối thiểu 32 bytes.
- Secret đến từ secret manager/runtime injection; không nằm trong TeamPack, JSON config,
  artifact, exception, repr hoặc log.
- `key_version` nằm trong token/manifest để rotation có kiểm soát.
- Rotation tạo token namespace mới; không âm thầm thay token cũ.
- Nếu cần reverse lookup, dùng token vault riêng. HMAC bản thân không reversible.

Tokenization là pseudonymization. Nó không chứng minh dữ liệu đã anonymous hoàn toàn.

## 2. VND value banding

Financial generalization dùng deterministic tiers trong server policy:

| Amount range | Band unit |
|---|---:|
| `< 1,000,000 VND` | 100,000 VND |
| `< 1,000,000,000 VND` | 100,000,000 VND |
| `>= 1,000,000,000 VND` | 1,000,000,000 VND |

Công thức:

```text
lower = floor(amount / unit) * unit
upper = lower + unit
output = "lower-upper VND"
```

Ví dụ:

```text
420,000,000  → 400M-500M VND
4,200,000,000 → 4B-5B VND
```

Input phải là whole, non-negative, finite VND amount. OpenAI không được chọn band hoặc
làm tròn. Nếu provider cần exact amount, field phải có explicit `ALLOW_EXACT` rule thay
vì đánh tráo band thành con số chính xác.

## 3. Partial masking

Thuật toán giữ số ký tự prefix/suffix do policy quy định:

```text
AB123456, prefix=2, suffix=2 → AB***56
```

Nếu input quá ngắn, output là `[MASKED]`. Partial masking chỉ phục vụ UI/log display; nó
không đủ chống re-identification và không được thay cho contextual token trong partner
payload.

## 4. Free-text redaction

Thứ tự deterministic:

1. exact dictionary scan từ identifier đã biết trong case;
2. regex cho credential marker, email, phone và account-like identifiers;
3. thay match bằng category marker;
4. chỉ lưu category/count, không lưu matched raw text.

Ví dụ:

```text
"Contract CON-004, access_token=abc"
→ "Contract [CONTRACT_ID_REDACTED], [SECRET_REDACTED]"
```

NER/LLM có thể được thêm như lớp hỗ trợ, nhưng không được là lớp bảo vệ duy nhất. Với file
format chưa hỗ trợ hoặc nested/binary payload chưa scan, policy fail closed.

## 5. Omit và vault reference

`OMIT` loại field khỏi outbound values. Manifest chỉ ghi action và digest của null output,
không hash raw secret.

`VAULT_REFERENCE` chỉ pass-through một reference đã có dạng `vault://...`. Nếu caller đưa
raw key/token, policy reject. Encryption-at-rest hoặc TLS không thay thế quy tắc này: sau
khi decrypt, raw secret vẫn là raw secret.

## 6. Exact pass-through

`ALLOW_EXACT` chỉ hợp lệ khi field, purpose và recipient nằm trong server policy. Restricted
identifier bị model validation cấm `ALLOW_EXACT`. Restricted-secret bị giới hạn ở `OMIT`
hoặc `VAULT_REFERENCE`.

Recipient authorization có hai tầng: recipient phải nằm trong global policy allowlist và đồng thời
nằm trong exact allowlist của field rule. Wildcard recipient bị schema từ chối. Việc caller đặt một
field trong `required_fields` chỉ chứng minh nhu cầu tối thiểu; nó không cấp quyền pass-through và
không bypass purpose/recipient rule. Ngược lại, một declared required field không hiện diện trong
payload làm operation fail closed trước khi chạy thuật toán.

Ví dụ có chủ đích là `requested_amount`: bank precheck/application cần đúng số tiền, nên
policy có thể cho exact amount trong đúng banking document purpose. Điều này không cho
phép tự động gửi và không thay Governance approval.

## 7. Các kỹ thuật không dùng sai mục đích

- Base64 là encoding, không phải masking.
- Encryption bảo vệ transport/storage, không thay data minimization hoặc tokenization.
- k-anonymity không phù hợp cho một hồ sơ hợp đồng đơn lẻ không có population dataset.
- Differential privacy không phù hợp khi provider cần case-specific document.
- Plain hash không phù hợp cho identifier có không gian nhỏ.
- LLM rewrite không phải security control deterministic.

## 8. Test invariants

Implementation phải chứng minh:

- cùng raw/context/key version tạo cùng token;
- đổi provider, purpose, field type hoặc key version tạo token khác;
- Unicode NFC variants tạo token giống nhau;
- token material tối thiểu 128 bits;
- raw restricted/secret không xuất hiện trong `MaskedPayload`, manifest, repr, exception
  hoặc log;
- unknown field, missing context và non-scalar/non-finite input fail closed;
- payload thiếu declared required field hoặc recipient ngoài global/field allowlist không thể được
  xử lý như một exact pass-through;
- policy không chứa secret key;
- same safe input/policy/context tạo stable manifest identity;
- manifest cam kết canonical policy SHA-256 và exact upstream source-evidence IDs;
- sửa masked output rồi tính lại digest/manifest/package IDs vẫn bị chặn khi Governance chạy lại
  thuật toán từ authoritative upstream evidence.
