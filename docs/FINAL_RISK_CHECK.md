# Final Risk Check

## Mục đích

Final Risk Check là bước deterministic ngay sau khi Workflow đã tạo và validate một
`INTERNAL_DECISION_PACKAGE`. Bước này chuẩn hóa trạng thái rủi ro còn lại và các control phải
được giữ lại cho downstream Decision analysis/Card. Bản thân Final Risk không đưa ra quyết định
hợp đồng.

Luồng đã implement:

```text
INTERNAL_DECISION_PACKAGE_READY
  -> FINAL_RISK_CHECK
  -> Evidence Validator
  -> FINAL_RISK_ASSESSMENT
  -> FINAL_RISK_READY
```

`FINAL_RISK_READY` là boundary của Risk, không còn là terminal milestone của toàn workflow.
Workflow tiếp tục sang Decision composition: deterministic scenario packet, bounded OpenAI
analysis, deterministic guard, Evidence Validator, `DECISION_CARD` và final Founder approval cho
Card có recommendation approvable. Chi tiết ở
[Decision, Final Approval, and External-Release Readiness](DECISION_FINAL_APPROVAL_AND_RELEASE.md).

## Input contract

Final Risk nhận đúng một validated artifact `INTERNAL_DECISION_PACKAGE`. Artifact này đã snapshot
Evaluation Case, Finance, Operations, Initial Risk, Decision route và các Banking/Document/
Governance evidence phù hợp với assembly path.

Final Risk:

- không đọc TeamPack hoặc Excel trực tiếp;
- không fuzzy-match entity hoặc tạo quan hệ dữ liệu mới;
- không gọi OpenAI;
- không gọi Banking/Document/external adapter;
- không tính lại Finance, Operations hoặc Initial Risk.

Artifact draft phải giữ exact lineage tới ID, version và input hash của Internal Decision Package,
đồng thời giữ nguyên evidence references của package. Workflow chạy Evidence Validator trước khi
versioning và persistence.

## Xử lý deterministic

Final Risk v1 thực hiện các bước sau:

1. Carry forward từng Initial Risk finding thành `ResidualRiskFinding` với
   `status = OPEN_UNCHANGED`.
2. Giữ `residual_risk_level` bằng `initial_risk_level`. Không có mitigation rule nên bước này
   không được tự giảm hoặc đổi risk level.
3. Giữ nguyên evidence limitations. Initial assessment bị giới hạn bởi evidence thì
   `assessment_status = LIMITED_BY_EVIDENCE`; ngược lại là `COMPLETE`.
4. Xác định major exception chỉ từ explicit residual finding có severity `CRITICAL`:
   - có finding CRITICAL: `DETECTED` và tạo `major_exception_signal`;
   - không có finding CRITICAL nhưng evidence còn hạn chế: `NOT_EVALUABLE`;
   - không có finding CRITICAL và evidence đầy đủ: `NOT_DETECTED`.
5. Tạo `required_controls` từ explicit human-confirmation points, evidence limitations,
   registered Governance checkpoints, resolved rejection references, simulated Banking result và
   Document release boundary có trong package.
6. Không xem checkpoint đã đăng ký là approval gate đang active. Trong v1, một package READY không
   thể được tạo khi approval request còn pending; vì vậy `unresolved_approval_gates` rỗng.

`NOT_EVALUABLE` không có nghĩa là “không có rủi ro”; nó có nghĩa evidence hiện tại chưa đủ để kết
luận major exception là absent.

## Output artifact

`FINAL_RISK_ASSESSMENT` gồm các nhóm field chính:

- Identity và lineage: `assessment_id`, case/dataset/contract IDs, Internal Decision Package ID,
  artifact ID, version, input hash, assembly path và Initial Risk artifact ID.
- Trạng thái: `assessment_status`, `initial_assessment_status`, `initial_risk_level`,
  `residual_risk_level`.
- Risk detail: `residual_findings`, `limitations`, `evidence_ids`.
- Governance visibility: `unresolved_approval_gates`, exact gate-ID index, `required_controls` và
  exact control-ID index.
- Major exception: `major_exception_status` và optional `major_exception_signal`.
- Boundary flags: `recommendation_performed = false`, `approval_requested = false`,
  `external_action_performed = false`.

Các `FinalRiskControlCode` hiện có:

| Code | Ý nghĩa |
|---|---|
| `HUMAN_CONFIRMATION_REQUIRED` | Một điểm xác nhận của con người từ Initial Risk phải được giữ lại cho bước sử dụng phù hợp. |
| `EVIDENCE_LIMITATION_MUST_BE_PRESERVED` | Không được biến một unknown/evidence gap thành fact. |
| `GOVERNANCE_EVALUATION_BEFORE_PROTECTED_ACTION` | Nếu action tương ứng được đề xuất về sau, Governance phải evaluate checkpoint trước execution. |
| `GOVERNANCE_REJECTION_MUST_BE_HONORED` | Một rejection đã resolve vẫn ràng buộc đúng subject/action đó và không được bypass. |
| `SIMULATED_BANKING_RESULT_IS_NON_BINDING` | Simulated precheck không phải offer hoặc bank approval thật. |
| `DOCUMENT_RELEASE_REQUIRES_SEPARATE_AUTHORIZATION` | Internal Document candidate chưa được phép gửi ra ngoài; release cần proposal và authorization riêng. |

Required control là dữ liệu đầu vào cho bước sau; bản thân Final Risk không execute control, không
tạo `ApprovalRequest` và không pause để hỏi Founder.

## Pause và fail-safe

Final Risk không tạo `MissingDataRequest` muộn từ một package đã READY. Nếu thiếu đúng một source
package, source chưa validated, lineage không khớp, hoặc component trả sai contract, Workflow dừng
`FAILED_SAFE`. Đây là lỗi integrity/dependency, không phải lý do để Final Risk đoán dữ liệu hay tạo
một form Founder mới.

## API exposure

Không cần endpoint mutation riêng cho Final Risk. `POST /api/cases/run` tiếp tục tự động tới bước
này khi các pause trước đó đã được resolve. `GET /api/workflows/{workflow_run_id}` expose:

- `final_risk_assessment_id`;
- `final_risk_status`;
- `final_residual_risk_level`;
- `final_major_exception`;
- `final_unresolved_approval_gate_ids`;
- `final_required_control_codes`.

`final_required_control_codes` là danh mục code đã loại trùng để đọc nhanh. Artifact đầy đủ vẫn giữ
từng `RequiredControl` riêng biệt cùng source reference và evidence tương ứng.

`GET /api/cases/{evaluation_case_id}/artifacts` trả envelope đầy đủ của
`FINAL_RISK_ASSESSMENT`. API route trả trực tiếp typed `WorkflowRunSummary`; runtime chịu trách
nhiệm dựng summary, nên interface layer không duplicate hoặc diễn giải lại risk logic.

## CON-004 hiện tại

Sau khi signed-contract evidence được bổ sung và Internal Decision Package được tạo, Final Risk của
CON-004 tạo kết quả sau tại `FINAL_RISK_READY` trước khi Workflow chuyển sang Decision:

- residual risk vẫn là `HIGH`;
- status là `LIMITED_BY_EVIDENCE`;
- không có CRITICAL finding nhưng evidence còn hạn chế, nên major exception là `NOT_EVALUABLE`;
- RR-004/RR-005 đã đăng ký vẫn dormant, nên không có unresolved approval gate;
- controls giữ các human confirmations/limitations/checkpoints và hai boundary quan trọng:
  simulated Banking result là non-binding, Document package cần authorization riêng trước external
  release.

Kết quả này không phải recommendation accept/negotiate/reject và không gửi tài liệu cho ngân hàng.
