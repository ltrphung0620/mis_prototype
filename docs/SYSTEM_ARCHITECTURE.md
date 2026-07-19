# OPC MIS Agentic AI — Kiến trúc hệ thống

## 1. Mục đích tài liệu

Tài liệu này mô tả kiến trúc mục tiêu của OPC MIS Agentic AI theo thiết kế Modular Monolith đã
chốt, đồng thời ghi rõ phần nào đã được triển khai trong prototype hiện tại.

Nguyên tắc quan trọng:

- Business component tạo facts, artifacts, signals và commands; không tự điều khiển workflow.
- Workflow Orchestrator sở hữu thứ tự thực thi, dependency, persistence, pause/resume và
  invalidation.
- Governance kiểm soát evidence, approval và protected action.
- OpenAI chỉ diễn đạt dữ liệu đã được xác minh; không sở hữu phép tính hoặc quyết định nghiệp vụ.
- TeamPack gốc luôn là nguồn read-only, không bị ghi ngược.

## 2. Architecture pattern

Hệ thống sử dụng:

```text
Modular Monolith
+ Persisted State Machine
+ Approval Control Plane
+ Artifact / Evidence Store
```

Không dùng microservice trong giai đoạn MVP.

```text
CLI / FastAPI
       │
       ▼
Workflow Orchestrator
  ├── node execution
  ├── dependency
  ├── persistence
  ├── pause / resume
  └── invalidation
       │
       ├──────────────────────────┐
       ▼                          ▼
Business Components       Governance Components
  ├── Planner Skill         ├── Approval Policy Registry
  ├── Finance Agent         ├── Approval Gate Coordinator
  ├── Operations Skill      ├── Evidence Validator
  ├── Risk Agent            └── Audit Logger
  ├── Decision Agent
  ├── Banking Skill
  └── Document Skill
       │                          │
       └──────────────┬───────────┘
                      ▼
             Domain Models / Ports
                      │
                      ▼
          Infrastructure Adapters
      Excel · SQLite · OpenAI · Simulated Precheck · Files
```

Hướng dependency trong source code:

```text
Interface
  → Workflow / Application
  → Business và Governance
  → Domain và Ports
  → Infrastructure implementations
```

Business không import concrete infrastructure. Domain không import framework hoặc SDK bên ngoài.

## 3. Các layer

### 3.1 Interface Layer

Bao gồm CLI và FastAPI.

Trách nhiệm:

- Nhận request và trả response.
- Chuyển đổi input/output giữa giao diện và domain.
- Cung cấp Swagger cho việc test API.

Không được:

- Chứa business rule.
- Tính toán tài chính.
- Tự resolve workflow state.
- Gọi protected external action trực tiếp.

### 3.2 Application / Workflow Layer

Thành phần trung tâm là `Workflow Orchestrator`.

Trách nhiệm:

- Chọn node cần chạy.
- Kiểm tra dependency và input artifact.
- Chạy các node có thể song song.
- Gọi Evidence Validator trước khi persist.
- Persist artifact và workflow state sau từng node.
- Pause khi thiếu dữ liệu hoặc cần approval.
- Resume từ đúng node.
- Invalidate artifact downstream khi input thay đổi.
- Điều phối protected action qua governance gate.

Orchestrator không thực hiện business calculation.

### 3.3 Business Component Layer

Gồm ba agent và bốn skill:

| Loại | Component |
|---|---|
| Skill | Planner |
| Agent | Finance |
| Skill | Operations |
| Agent | Risk |
| Agent | Decision |
| Skill | Banking Integration |
| Skill | Document |

Mỗi component:

- Có input schema và output schema riêng.
- Chỉ đọc explicit upstream artifacts và domain ports được cấp.
- Trả về artifact drafts, missing-data requests, signals hoặc commands.
- Không persist artifact.
- Không thay đổi workflow state.
- Không tự approve.
- Không ghi vào artifact của component khác.

### 3.4 Governance Layer

Governance là cross-cutting layer được Orchestrator gọi tại các checkpoint quan trọng:

- Approval policy evaluation.
- Approval gate execution.
- Evidence validation.
- Audit event recording.

### 3.5 Domain Layer

Chứa:

- Pydantic models.
- Enums.
- Value objects.
- Pure deterministic logic.
- Infrastructure-neutral contracts.

Domain không import pandas, openpyxl, FastAPI, SQLite hoặc OpenAI SDK.

### 3.6 Ports Layer

Chứa Protocol cho:

- Dataset access.
- Artifact persistence.
- Workflow state persistence.
- Approval persistence.
- Event persistence.
- LLM composition.
- Banking adapter.

### 3.7 Infrastructure Layer

Chứa implementation cụ thể:

- Excel ingestion.
- SQLite repositories.
- OpenAI Responses adapter.
- Deterministic fallback.
- Mock banking adapter.
- File storage, clock và ID generation.

## 4. Contract chung cho Business Component

```python
class BusinessComponent(Protocol):
    component_id: str

    async def execute(
        self,
        context: ExecutionContext,
    ) -> ComponentResult:
        ...
```

`ExecutionContext` chứa tối thiểu:

```text
evaluation_case_id
dataset_id
workflow_run_id
input_artifact_ids
requested_scope
component_input
current_node
```

`ComponentResult` chứa:

```text
status
artifacts
missing_data_requests
approval_signals
action_commands
warnings
runtime_events
```

Business component chỉ được trả các status:

- `COMPLETED`
- `COMPLETED_WITH_WARNINGS`
- `WAITING_FOR_INPUT`
- `FAILED_SAFE`

`WAITING_FOR_APPROVAL` chỉ do Approval Gate Coordinator và Workflow Orchestrator tạo.

Trạng thái implementation hiện tại: `WAITING_FOR_DEPENDENCIES` chỉ tồn tại trong
`WorkflowStatus` và `WorkflowNodeStatus`. Risk business component chạy với mode tường minh
`PRE_SCAN` hoặc `FINALIZE` và chỉ trả các `ComponentStatus` hợp lệ ở trên. Master Workflow sở hữu
node chờ dependency, kiểm tra `FINANCE_FACTS` và `OPERATIONS_FACTS`, rồi mới gọi Risk finalization.

## 5. Protected action và Approval Control Plane

Business component không được trực tiếp thực hiện hành động nhạy cảm.

Ví dụ Banking Skill muốn gửi hồ sơ precheck sẽ chỉ tạo:

```json
{
  "action_type": "SUBMIT_BANKING_PRECHECK",
  "evaluation_case_id": "CASE-ID",
  "payload_artifact_id": "BANKING-PRECHECK-PROPOSAL-ARTIFACT-ID",
  "requested_by": "CASE_WORKFLOW_ORCHESTRATOR"
}
```

Luồng xử lý:

```text
ActionCommand
  → Evidence Validator
  → Proposal-scoped Approval Policy Registry
  → Approval Gate Coordinator
  → AUTHORIZED / WAITING_FOR_INPUT / WAITING_FOR_APPROVAL / APPROVED / REJECTED / EXPIRED
  → Adapter chỉ khi exact action có valid human hoặc machine authorization
```

Do đó, gọi Banking Skill sai thời điểm vẫn không thể vượt governance gate.

## 6. Business components

### 6.1 Planner Skill

Workflow:

```text
TeamPack snapshot
  → validate intake
  → locate contract
  → locate customer
  → locate explicitly related orders
  → locate invoices through orders
  → locate only explicit service/reference relationships
  → assess readiness
  → EvaluationCase
  → Initial RunPlan
```

Output:

- `PlannerResult`
- `EvaluationCase`
- `MissingDataRequest` cho blocking base-data gaps
- Warnings cho non-blocking evidence gaps

Planner không làm:

- Margin hoặc cashflow calculation.
- Risk evaluation hoặc risk-rule activation.
- Approval signal.
- Banking selection.
- Document preparation.
- OpenAI narrative.
- Decision Card.

### 6.2 Finance Agent

Finance đọc `EvaluationCase`, `PlannerResult` và các explicit records đã được Planner chọn.

Deterministic calculations gồm:

- Contract value và source gross margin.
- Related-order revenue và estimated cost.
- Order gross profit và gross margin.
- Order coverage và uncovered contract value.
- Invoice totals theo source status.
- Outstanding issued receivable.
- Invoice coverage.
- OPC-global cashflow và reserve gap khi TeamPack không có contract key.

Output:

- `FinanceFacts`
- `FinanceObservation[]`
- `FinanceEvidenceLimitation[]`
- `FinanceAssessment`
- Bounded `FinanceNarrative`

Finance không làm:

- Đọc hoặc kích hoạt `13_RISK_RULES`.
- Gán risk level, risk score hoặc severity.
- Tạo triggered risk-rule IDs.
- Tạo ApprovalSignal hoặc ApprovalRequest.
- Tự xác định working-capital request.
- Tạo banking trigger hoặc chọn sản phẩm ngân hàng.
- Thực hiện external action.

Các điều kiện như margin thấp, reserve shortfall hoặc performance-bond requirement chỉ được ghi
nhận dưới dạng neutral observation. Risk Agent sẽ đọc chúng ở bước sau.

OpenAI chỉ nhận facts/observations/limitations đã xác minh và diễn đạt lại. Nếu OpenAI lỗi,
Finance dùng deterministic fallback; facts không thay đổi.

### 6.3 Operations Skill

Operations đọc `EvaluationCase`, `PlannerResult`, contract, orders và services được Planner chọn
bằng explicit IDs. Phần deterministic hiện đã implement gồm chuẩn hóa ngày, contract/order window,
planned duration, schedule span, interval gap/overlap, exact source-status counts và past-due theo
`as_of_date` do caller cung cấp.

Output:

- `OperationsFacts`
- `OrderScheduleFact[]`
- `OperationsObservation[]`
- `OperationsEvidenceLimitation[]`
- `OperationsAssessment`

Operations giữ nguyên delivery note dưới dạng source evidence, không semantic parsing. Thiếu actual
delivery date, capacity, contractor, phase dependency, location, SLA hoặc penalty basis là
non-blocking limitation. Operations không tự sinh capacity score, feasibility conclusion, penalty
amount, risk level, triggered rule hoặc approval result.

### 6.4 Risk Agent

Risk Agent có hai mode.

Initial Risk Scan:

- Đọc TeamPack risk rules.
- Đọc Planner, Finance và Operations artifacts.
- Kích hoạt typed risk rules.
- Tạo risk level, cảnh báo và điểm cần con người xác nhận.
- Phát `ApprovalSignal` khi điều kiện phù hợp.

Risk Agent chỉ phát signal; nó không tạo `ApprovalRequest`.

Final Risk Check:

- Đọc final evidence.
- Đọc approval status.
- Kiểm tra unresolved evidence và gates.
- Xác định residual risk và major exceptions.

Output mục tiêu:

- `InitialRiskAssessment`
- `ApprovalSignal[]`
- `FinalRiskAssessment`
- `MajorExceptionSignal`
- `UnresolvedApprovalGates`
- `RequiredControls`

### 6.5 Decision Agent

Decision Agent có bốn phase:

1. Route Planning.
2. Internal Decision Package.
3. Deterministic Decision Policy.
4. Decision Card composition.

Phase 1 và Phase 2 đã được implement. Phase 2 chỉ hội tụ các artifact đã validate thành một evidence
dossier deterministic theo đúng route đã đi qua. Nó không tạo recommendation, không chọn Banking
option, không request approval và không thực hiện external action. Phase 3 và Phase 4 vẫn chưa
implement.

Recommendation chỉ do deterministic policy tạo:

- `ACCEPT`
- `NEGOTIATE_CONDITIONS_TO_ACCEPT`
- `DO_NOT_ACCEPT`

OpenAI không được thay đổi recommendation.

Banking Integration Skill và Document Skill là hai capability chuyên môn dưới sự điều phối nghiệp
vụ của Decision Agent. Decision quyết định khi nào cần capability, tạo typed request và đọc artifact
trả về để lập route tiếp theo. Workflow Orchestrator vẫn là thành phần duy nhất chọn/chạy node,
persist artifact và quản lý pause/resume; Governance vẫn là thành phần duy nhất kích hoạt approval
gate. Decision không gọi trực tiếp external adapter.

### 6.6 Banking Integration Skill

Phase A — Internal discovery, chưa cần approval:

- Explicit Credit Profile Reference Reader.
- Bank Product Matcher.
- Deterministic Criterion Evaluator.
- Required Field Readiness Checker.
- Option Matrix Builder.
- Optional Advisory Explanation Composer.

Implementation Phase A hiện tại dùng các artifact tách trách nhiệm:

- `BANKING_OPTION_MATRIX` cho facts/criteria deterministic;
- `BANKING_DISCOVERY_RESULT` cho trạng thái và pointer gọn; và
- `BANKING_OPTION_ADVICE` cho diễn giải `NOT_INVOKED` hoặc `ADVISORY_ONLY`.

Precheck-readiness slice hiện tại bổ sung:

- `BANKING_PRECHECK_READINESS`, luôn được tạo từ matrix đã validate và luôn giữ
  `precheck_executed: false`;
- `DECISION_POST_BANKING_REVIEW`, dùng readiness deterministic để phân loại route;
- durable `MissingDataRequest` khi amount explicit chưa có; và
- `BANKING_INPUT_SUPPLEMENT` bất biến với `USER_INPUT` evidence để auto-resume đúng Master run.

Request ban đầu và matrix version 1 giữ `requested_amount: null`. Sau supplement VND hợp lệ,
Workflow tạo matrix/result/advice version 2 thay vì sửa artifact cũ. Mapping field là server-owned:
`contract_id -> EVALUATION_CASE`, `amount -> BANKING_INPUT_SUPPLEMENT`, và
`company_profile -> 02_OPC_PROFILE`. Credit profile không được dùng thay company profile và không
là blocker của precheck readiness nếu không có explicit relationship.

TeamPack API catalog chỉ là mock metadata. Discovery/readiness không chạy endpoint và không tự
liên kết credit profile bằng mô tả tự nhiên. Sau readiness, proposal artifact chỉ giữ reference
manifest; Governance tạo proposal-scoped policy rồi mới quyết định có cần `ApprovalRequest` hay có
thể persist `AUTHORIZED_WITHOUT_HUMAN`.

Quy ước monetary của OPC là `VND`. Khi sheet không có cột currency riêng, ingestion/domain phải
chuẩn hóa currency thành VND thay vì tạo missing-currency gap.

Governed submission proposal và Phase B1 simulated precheck — đã implement:

- Protected action: `SUBMIT_BANKING_PRECHECK`.
- Banking Skill tạo reference-only `BANKING_PRECHECK_SUBMISSION_PROPOSAL` cho tất cả READY options.
- Orchestrator persist proposal rồi mới tạo `ActionCommand` tham chiếu artifact envelope.
- Governance tạo policy theo exact API facts từ sheets 12/22 và merge amount checkpoint phù hợp.
  Policy yêu cầu human thì pause tại `WAITING_FOR_APPROVAL`; explicit no-human policy và không có
  trigger khác thì persist `AUTHORIZED_WITHOUT_HUMAN`.
- Valid authorization tạo permit tạm thời, ràng buộc đúng workflow/case/policy record và proposal
  artifact ID/version/input hash.
- Sau authorization, Orchestrator resolve request từ explicit proposal bindings, gọi adapter
  `SIMULATED`, validate rồi persist `BANKING_PRECHECK_RESULT_SET`.
- `BANKING_PRECHECK_RESULTS_READY` là milestone; Decision sau đó persist
  `DECISION_POST_PRECHECK_REVIEW`. Conditional full-coverage result có thể đi tiếp vào
  `DECISION_DOCUMENT_HANDOFF`; outcome khác dừng tại `DECISION_POST_PRECHECK_REVIEW_COMPLETED` hoặc
  pause nếu có evidence gap explicit.
- Phase B1 và post-precheck review không dùng OpenAI và không selection/ranking. Decision tạo một
  Document request cho mỗi viable result; Workflow chỉ tự chạy khi có đúng một request.
- Founder reject `SUBMIT_BANKING_PRECHECK` đóng riêng Banking route tại
  `BANKING_PRECHECK_DECLINED`; adapter không chạy và case không bị block toàn cục.

Các response được phép:

- `CONDITIONAL_PRECHECK`
- `MISSING_EVIDENCE`
- `NOT_ELIGIBLE`
- `NO_RECOMMENDATION`
- `SERVICE_UNAVAILABLE`

Mọi result hiện tại có authority `SIMULATED_NON_BINDING`. Không được tuyên bố loan/bank approval,
provider recommendation hoặc guarantee issuance.

### 6.7 Document Skill

Document Skill đã implement phần chuẩn bị outbound banking dossier bên trong OPC. Nó nhận đúng một
`DOCUMENT_PREPARATION_REQUEST` đã validate và tạo:

- `DOCUMENT_CHECKLIST`: exact status/evidence của từng provider document code;
- `DOCUMENT_PACKAGE_DRAFT`: minimized, policy-masked internal draft;
- blocking `MissingDataRequest` khi tài liệu bắt buộc chưa có;
- `DOCUMENT_EVIDENCE_SUPPLEMENT`: immutable opaque reference + content SHA-256 để resume; và
- `DOCUMENT_RELEASE_PACKAGE`: masked candidate làm input cho nhánh
  `CONDITIONAL_DOCUMENT_READY` của Internal Decision Package khi không còn blocking gap; chưa phải
  approval subject.

Scenario `API-002` hiện yêu cầu `SIGNED_CONTRACT`, `COMPANY_PROFILE`,
`PERFORMANCE_BOND_REQUEST_FORM` và `CASHFLOW_BUFFER_EVIDENCE`. TeamPack không có signed-contract
file reference nên Workflow pause tại `DOCUMENT_PREPARATION`. Structured company profile phải qua
masking; request form chỉ là unsigned draft; OPC-global cashflow giữ limitation và không được quy
cho contract.

Data protection thực thi theo server policy: minimize trước, classify exact field, sau đó
`ALLOW_EXACT`/`OMIT`/contextual HMAC-SHA256 tokenization/VND banding/redaction/vault reference.
HMAC namespace gồm provider, purpose, field và key version; runtime key tối thiểu 32 bytes, token
tối thiểu 128 bit. Thiếu key/unknown field fail closed. Tokenization là pseudonymization, không phải
anonymization. Sheet `21_MASKING_EXAMPLES` chỉ minh họa, không phải executable policy.

Current composition root yêu cầu exact `company_id` và `company_name` như minimum profile fields.
Đây là server assumption cho prototype, không phải requirement chính thức của VietinBank. Partial
coverage và multi-option selection được hoãn; Workflow không tự chọn request.

Document Skill không tự gửi payload. Khi release package ready, Workflow persist package làm input
cho phase Decision tiếp theo; nó không tạo protected action hoặc Founder approval. Checkpoint
`SEND_DOCUMENT_TO_EXTERNAL_PARTNER` vẫn registered nhưng dormant và tách biệt hoàn toàn với
approval `SUBMIT_BANKING_PRECHECK`. Một Decision recommendation/proposal có evidence đầy đủ trong
tương lai mới được kích hoạt checkpoint này; phase đó và external connector chưa được implement.

## 7. Governance components

### 7.1 Approval Policy Registry

Registry hiện hỗ trợ ba protected actions:

- `SEND_DOCUMENT_TO_EXTERNAL_PARTNER`;
- `COMMIT_LARGE_FINANCIAL_DECISION`; và
- `SUBMIT_BANKING_PRECHECK`.

Initial Risk đăng ký các typed future checkpoints từ `13_RISK_RULES`, gồm
`document_sent_to_partner` và `requested_amount`. Riêng Banking precheck, policy chỉ được tạo sau
khi exact proposal đã persist. Registry đọc:

- `12_API_CATALOG.extension_rule` của từng API trong proposal;
- các field `rule_id`, `applies_to` và `requires_human_approval` từ record
  `22_API_HANDLING_RULES` được map tường minh; và
- unique Risk `requested_amount` checkpoint, hiện là `RR-005`, đồng thời giữ nguyên rule ID,
  operator, threshold và evidence.

Mỗi API có một `ApprovalPolicyCoverage`. Registry chuyển amount rule thành checkpoint scoped cho
`SUBMIT_BANKING_PRECHECK` và hợp nhất các checkpoint trong cùng proposal-scoped
`APPROVAL_CHECKPOINTS` artifact. Không có file
`config/governance/approval_policies.yml` trong implementation hiện tại, không dùng `eval()`, và
không suy luận policy từ tên API hay mô tả tự nhiên.

Chưa persist `ApprovalRequirement` như entity độc lập. Các protected action tương lai trong phần 9
chỉ là target contract và phải có explicit policy source trước khi implement.

### 7.2 Approval Gate Coordinator

Runtime gate result:

- `AUTHORIZED`
- `WAITING_FOR_INPUT`
- `WAITING_FOR_APPROVAL`
- `APPROVED`
- `REJECTED`
- `EXPIRED`

Approval phải gắn với:

```text
subject_artifact_id
subject_artifact_version
subject_input_hash
policy_artifact_id
policy_artifact_version
policy_input_hash
policy_coverage_ids
```

Nếu subject artifact thay đổi, approval cũ chuyển thành `EXPIRED` và phải approve lại.

Request bind với exact subject và policy artifact identity. Trước khi phát permit, Governance đọc
lại current artifacts, coverage và chạy lại gate. Subject/policy superseded làm request chuyển
`EXPIRED`, không được thực thi. Explicit no-human policy vẫn tạo durable
`AUTHORIZED_WITHOUT_HUMAN`; machine record không có human decision.

Nếu protected-action request có `workflow_run_id`, pause và resume cập nhật chính
`CaseWorkflowRun` cùng node `APPROVAL_GATE`. Founder reject Banking precheck đóng route tại
`BANKING_PRECHECK_DECLINED`; các action khác áp dụng rejection branch riêng theo policy.

### 7.3 Evidence Validator

Evidence Validator chạy tại năm checkpoint:

1. Trước khi persist artifact.
2. Trước khi tạo ApprovalRequest.
3. Trước protected action.
4. Sau OpenAI Structured Output.
5. Trước Decision Card finalization.

Validation categories mục tiêu:

- `SCHEMA`
- `LINEAGE`
- `NUMERIC_FACT`
- `DATA_CLASSIFICATION`
- `MASKING`
- `APPROVAL_SUBJECT`
- `LLM_FACT_REFERENCE`

Trạng thái implementation hiện tại:

- Đã validate strict JSON, schema, evidence lineage và boundary trước khi persist artifact của
  Planner, Finance, Operations, Risk và Approval Checkpoint.
- ApprovalRequest và protected action hiện chỉ kiểm tra subject/checkpoint artifact đã có validation
  status hợp lệ; chưa chạy một validation checkpoint độc lập và chưa persist ValidationReport riêng.
- OpenAI Finance output được validate khi Finance artifact đi qua persistence pipeline, nhưng chưa
  có audit checkpoint riêng cho Structured Output.
- Data classification, masking và Decision Card finalization chưa được implement đầy đủ.

### 7.4 Audit Logger

Audit Logger khác developer log.

- Developer log phục vụ debug, stack trace và performance.
- Audit Logger là append-only business event stream.

Event types mục tiêu gồm:

```text
WORKFLOW_STARTED
NODE_STARTED
DATA_READ
FACT_DERIVED
RULE_TRIGGERED
ARTIFACT_CREATED
APPROVAL_SIGNAL_DETECTED
APPROVAL_REQUIREMENT_REGISTERED
APPROVAL_REQUESTED
WORKFLOW_PAUSED
APPROVAL_RESOLVED
PROTECTED_ACTION_ALLOWED
PROTECTED_ACTION_BLOCKED
OPENAI_CALL_STARTED
OPENAI_CALL_COMPLETED
FALLBACK_USED
EVIDENCE_VALIDATED
DECISION_READY
WORKFLOW_COMPLETED
NODE_FAILED_SAFE
```

Audit Logger phải redact API key, access token, restricted identifiers và unmasked payload.

Trạng thái implementation hiện tại: SQLite `runtime_events` là append-only theo từng Master
Workflow run và có sequence tăng dần, nhưng chưa phải Audit Logger đầy đủ. Component events, LLM
calls, evidence-validation events, approval events và protected-action events chưa được hợp nhất vào
một business audit stream duy nhất.

## 8. Workflow Orchestrator

MVP dùng custom persisted state machine, không dùng CrewAI, AutoGen hoặc LangGraph làm
orchestrator chính.

Lý do:

- Thứ tự nghiệp vụ rõ ràng.
- Approval gate phải deterministic.
- Pause/resume phải chắc chắn.
- Mỗi node phải giải thích và test độc lập được.
- LLM không được tự thay đổi route.

Node execution algorithm:

```text
Load workflow state
  → resolve dependencies
  → check input hashes
  → reuse output nếu vẫn valid
  → audit NODE_STARTED
  → execute business component
  → Evidence Validator
  → persist artifacts
  → register approval signals
  → process action commands
  → persist workflow state
  → select next node
```

Idempotency:

- Mỗi artifact có `input_artifact_ids`, `input_hash` và `version`.
- Cùng input hash thì tái sử dụng artifact hiện hành.
- Input thay đổi thì artifact cũ thành `STALE`, downstream bị invalidate và chạy lại từ node phù
  hợp.

Trạng thái implementation hiện tại:

- Artifact orchestrator đã tái sử dụng envelope khi cùng `input_hash` và tăng version khi business
  input thay đổi.
- Master Workflow đã có deterministic `workflow_run_id` và node state, nhưng việc thấy node đã
  completed hiện đủ để skip node; chưa đối chiếu lại upstream artifact hash.
- Chưa có lifecycle `STALE`, generic transitive downstream invalidation hoặc arbitrary
  DataPatch-driven rerun. Approval subject/policy revalidation và `EXPIRED` đã implement.

Workflow pause states:

- `WAITING_FOR_INPUT`
- `WAITING_FOR_APPROVAL`
- `BLOCKED`
- `FAILED_SAFE`

Terminal success state: `COMPLETED`.

## 9. Workflow graph mục tiêu

```text
DATASET_INGESTION
  → PLANNER_INTAKE
      ├── thiếu base data → WAITING_FOR_INPUT
      └── đủ dữ liệu
            ↓
INITIAL_ASSESSMENT
  → INITIAL_RISK_PRE_SCAN
  → FINANCE_ASSESSMENT + OPERATIONS_ASSESSMENT (chạy song song)
  → INITIAL_RISK_FINALIZATION (chờ đủ hai fact artifacts)
            ↓
REGISTER_APPROVAL_REQUIREMENTS
  → DECISION_ROUTE
      ├── không cần Banking/Document
      │     → INTERNAL_DECISION_PACKAGE
      └── cần Banking
            → BANKING_DISCOVERY_REQUEST
            → BANKING_INTERNAL_DISCOVERY
            → BANKING_OPTION_MATRIX
            → BANKING_PRECHECK_READINESS
            → DECISION_POST_BANKING_REVIEW
                ├── thiếu amount explicit
                │     → persist MissingDataRequest
                │     → WAITING_FOR_INPUT
                │     → BANKING_INPUT_SUPPLEMENT
                │     → auto-resume và tạo matrix/readiness version mới
                ├── không có precheck path/viable option → typed non-ready outcome
                │     → INTERNAL_DECISION_PACKAGE_ASSEMBLY
                └── có option ready → BANKING_PRECHECK_READY
                      → BANKING_PRECHECK_SUBMISSION_PROPOSAL
                      → proposal-scoped APPROVAL_CHECKPOINTS từ sheets 12/22 + amount rule
                      → CHECK SUBMIT_BANKING_PRECHECK GATE
                          ├── explicit no-human + không có trigger khác
                          │     → AUTHORIZED_WITHOUT_HUMAN
                          ├── human required → WAITING_FOR_APPROVAL
                          │     ├── approve → BANKING_PRECHECK_SUBMISSION_AUTHORIZED
                          │     └── reject → BANKING_PRECHECK_DECLINED
                          │           → INTERNAL_DECISION_PACKAGE_ASSEMBLY
                          └── missing/invalid policy hoặc input → fail closed
                      → authorized branch only: BANKING_PRECHECK_EXECUTION (SIMULATED)
                      → BANKING_PRECHECK_RESULT_SET
                      → BANKING_PRECHECK_RESULTS_READY
                      → DECISION_POST_PRECHECK_REVIEW
                          ├── conditional full coverage → DECISION_DOCUMENT_HANDOFF
                          │     → exactly one request → DOCUMENT_PREPARATION
                          │     → missing signed contract → WAITING_FOR_INPUT
                          │     → DOCUMENT_EVIDENCE_SUPPLEMENT → rebuild package
                          │     → DOCUMENT_RELEASE_PACKAGE_READY
                          │     → INTERNAL_DECISION_PACKAGE_ASSEMBLY
                          │       (no Founder approval; no actual external send)
                          ├── other typed outcome → DECISION_POST_PRECHECK_REVIEW_COMPLETED
                          │     → INTERNAL_DECISION_PACKAGE_ASSEMBLY
                          └── MISSING_EVIDENCE → WAITING_FOR_INPUT
                                → BANKING_PRECHECK_EVIDENCE_SUPPLEMENT
                                → BANKING_PRECHECK_RETRY_REQUIRED / WAITING_FOR_DEPENDENCIES
                      → eligible nonblocked branch → INTERNAL_DECISION_PACKAGE_READY
  → FINAL_RISK_CHECK
      └── major exception → CHECK MAJOR_EXCEPTION GATE
  → DECISION_POLICY
  → OPENAI_DECISION_COMPOSER
  → EVIDENCE_VALIDATOR
  → DECISION_READY
  → CHECK FINAL_DECISION GATE
  → POST_DECISION_UPDATE
```

Approval matrix:

| Protected action | Approval type | Nguồn requirement |
|---|---|---|
| `SUBMIT_BANKING_PRECHECK` | `BANKING_PRECHECK_API_POLICY` plus applicable amount approval | Proposal-scoped TeamPack sheets 12/22 + applicable Risk amount rule |
| `SEND_DOCUMENT_TO_EXTERNAL_PARTNER` | `HUMAN_APPROVAL` | Future exact Decision recommendation/proposal bound to a validated Document release package + registered document-release checkpoint |
| `COMMIT_LARGE_FINANCIAL_DECISION` | `HUMAN_APPROVAL` | Applicable evidence-backed financial checkpoint |

Implementation hiện tại chạy Decision Phase 1 Initial Route, tạo
`BANKING_DISCOVERY_REQUEST` khi route yêu cầu Banking, chạy Banking internal discovery/readiness và
Decision post-Banking review. Khi amount chưa có, Master Workflow pause tại
`DECISION_POST_BANKING_REVIEW`; supplement hợp lệ tự resume, tạo governed submission proposal và
đánh giá proposal-scoped policy. Current `API-002` yêu cầu Founder nên pause tại
`WAITING_FOR_APPROVAL`; policy no-human hợp lệ có thể tạo machine authorization khi không có trigger
khác. Valid authorization chạy precheck mô phỏng deterministic; Founder reject đóng Banking route
tại `BANKING_PRECHECK_DECLINED`. Current `API-002` mock conditional result có thể tiếp tục qua
Decision-to-Document handoff, input pause, masking, package draft và internal Decision handoff.
External/real-bank precheck, actual bank response, option selection/ranking, partial coverage,
actual document send và các Decision phase sau vẫn là kiến trúc mục tiêu.

## 10. Domain artifacts mục tiêu

```text
PlannerResult
EvaluationCase
FinanceFacts
FinanceAssessment
OperationsAssessment
InitialRiskAssessment
ApprovalSignal
ApprovalRequirement
ApprovalRequest
ApprovalDecision
RouteDecision
BankingRoutePackage
BankingInputSupplement
BankingPrecheckReadiness
DecisionPostBankingReview
DocumentReleasePackage
InternalDecisionPackage
FinalRiskAssessment
DecisionCard
PostDecisionUpdate
MissingDataRequest
DataPatch
EvidenceRef
ValidationReport
RuntimeEvent
ActionCommand
ArtifactEnvelope
```

`ArtifactEnvelope` chứa:

```text
artifact_id
artifact_type
evaluation_case_id
producer
version
status
payload
evidence_refs
input_artifact_ids
input_hash
validation_status
validation_notes
created_at
```

## 11. Persistence plan

Prototype mục tiêu dùng SQLite với các nhóm table:

```text
datasets
evaluation_cases
workflow_runs
workflow_node_states
artifacts
artifact_dependencies
missing_data_requests
data_patches
approval_signals
approval_requirements
approval_requests
approval_decisions
runtime_events
llm_calls
validation_reports
```

Schema SQLite hiện đang có:

```text
artifacts
workflow_states
risk_run_states
approval_requests
case_workflow_runs
workflow_node_states
runtime_events
```

Trong đó `workflow_states` còn phục vụ execution state của Planner endpoint/CLI cũ.
`case_workflow_runs` + `workflow_node_states` là nguồn trạng thái cho Durable Master Workflow và
Approval Control Plane đã attach vào Master run. Standalone Governance test không tạo thêm workflow
state. Các bảng `datasets`, `evaluation_cases`,
`artifact_dependencies`, `missing_data_requests`, `data_patches`, `approval_signals`,
`approval_requirements`, `approval_decisions`, `llm_calls` và `validation_reports` vẫn thuộc
persistence plan, chưa tồn tại dưới dạng table độc lập.

TeamPack handling:

```text
Original Excel, read-only
  → SHA-256
  → workbook validation
  → DatasetSnapshot
  → primary-key indexes
  → dataset metadata
```

User bổ sung dữ liệu bằng overlay:

```text
Original TeamPack + DataPatch = ResolvedCaseContext
```

Không ghi ngược vào Excel.

## 12. Công nghệ

| Nhu cầu | Công nghệ |
|---|---|
| Runtime | Python 3.12 |
| Domain/schema | Pydantic v2 |
| Excel | pandas + openpyxl |
| API | FastAPI + Uvicorn |
| Persistence mục tiêu | SQLite + SQLAlchemy/SQLModel |
| HTTP adapter | HTTPX |
| LLM | Official OpenAI Python SDK + Responses API |
| Fallback | Deterministic templates |
| Tests | pytest |
| Lint/format | Ruff |
| Secrets | `.env`, không commit |

Không cần trong MVP:

- Redis.
- Celery.
- Kafka.
- Temporal.
- LangGraph.
- CrewAI.
- AutoGen.

## 13. API contract mục tiêu

Dataset:

```text
POST /api/datasets
GET  /api/datasets/{dataset_id}
GET  /api/datasets/{dataset_id}/contracts
```

Case:

```text
POST /api/cases
POST /api/cases/{case_id}/run
POST /api/cases/{case_id}/resume
GET  /api/cases/{case_id}
POST /api/cases/{case_id}/reset
```

Approval và missing data:

```text
GET  /api/cases/{case_id}/approvals
POST /api/cases/{case_id}/approvals/{approval_id}/resolve
GET  /api/cases/{case_id}/missing-data
POST /api/cases/{case_id}/missing-data/{request_id}/resolve
```

Prototype hiện tại dùng route chuyên biệt, typed và tự resume cho amount Banking:

```text
POST /api/cases/{evaluation_case_id}/banking/input-supplements
POST /api/cases/{evaluation_case_id}/banking/precheck-evidence-supplements
```

Client chỉ gửi `workflow_run_id`, exact `missing_request_id`, positive-integer VND amount,
và `evidence_note`; với post-precheck evidence thì gửi thêm exact `evidence_reference_id`. Server tự
resolve case/dataset/contract/Banking request và gán principal `AUTHORIZED_STAFF`; client không được
truyền `provided_by` hoặc các authoritative identity khác.

Events và artifacts:

```text
GET /api/cases/{case_id}/events?after_sequence={sequence}
GET /api/cases/{case_id}/artifacts
GET /api/artifacts/{artifact_id}
GET /api/evidence/{evidence_id}
```

UI giai đoạn đầu có thể polling event, chưa cần WebSocket.

## 14. Test plan bắt buộc

Business:

- Planner tạo case có lineage.
- Finance chỉ tính verified metrics.
- Operations không tự sinh capacity.
- Risk phát ApprovalSignal nhưng không tạo ApprovalRequest.
- Decision recommendation là deterministic.
- Banking discovery không gọi external adapter.
- Document masking restricted fields.

Governance:

- Approval signal được chuyển thành requirement.
- Requirement chưa pause workflow cho tới khi protected action được chạm tới.
- Pending approval pause workflow.
- Rejected approval block action.
- Approved gate allow action.
- Artifact thay đổi làm approval hết hiệu lực.
- Evidence Validator từ chối unknown fact/evidence.

Orchestrator:

- Initial tasks chạy song song.
- State được persist sau từng node.
- Resume từ blocked node.
- Patch chỉ invalidate downstream cần thiết.
- Cùng input hash là idempotent.
- Node lỗi chuyển `FAILED_SAFE`.

OpenAI:

- Timeout, authentication failure, refusal hoặc invalid schema đều dùng fallback.
- Fallback không thay đổi deterministic facts.
- Runtime ghi `FALLBACK_USED`.
- LLM output không được đưa số hoặc fact references chưa xác minh vào artifact.

## 15. Repository structure mục tiêu

```text
config/
  banking/
  data_protection/
  prompts/
data/
  input/
  runtime/
src/opc_mis/
  api/
  business/
    agents/
      finance/
      risk/
      decision/
    skills/
      planner/
      operations/
      banking/
      document/
  domain/
  governance/
  infrastructure/
    banking/
    config/
    excel/
    security/
    persistence/
    openai/
  ports/
  workflow/
  cli/
tests/
  unit/
  integration/
  golden/
```

## 16. Trạng thái prototype hiện tại

| Hạng mục | Trạng thái |
|---|---|
| Read-only TeamPack ingestion | Đã implement |
| Dataset hashing, normalization và indexes | Đã implement |
| Planner Skill | Đã implement |
| EvaluationCase và PlannerResult | Đã implement |
| Finance deterministic calculations | Đã implement |
| FinanceFacts và FinanceAssessment | Đã implement |
| OpenAI Finance Composer | Đã implement, có fallback |
| Finance evidence limitations | Đã implement |
| Evidence validation trước persistence | Đã implement cho Planner/Finance/Operations/Risk/checkpoint/Decision/Banking, Document và Internal Decision Package artifacts |
| Artifact versioning và idempotency | Đã implement reuse/versioning và narrow supplement-driven Banking invalidation; generic STALE chưa implement |
| Swagger Planner/Finance/Operations/Risk/Decision/Governance/Workflow | Đã implement |
| API contract mục tiêu theo case/dataset | Chưa implement; hiện dùng prototype routes |
| Persistent SQLite repositories | Đã implement partial cho artifacts, Master/legacy component state, Risk, approvals và events |
| Unified Master + Approval state machine | Đã implement; cùng CaseWorkflowRun và APPROVAL_GATE node |
| Durable Master Workflow | Nhánh Banking/Document đã implement amount pause, governed simulated precheck, conditional handoff, signed-contract pause/resume, masking, release candidate và Internal Decision Package convergence; real-bank execution/actual send chưa có |
| Parallel Initial Assessment | Finance và Operations chạy song song; Risk pre-scan/finalize tự động |
| Operations Skill | Đã implement |
| Risk Agent | Đã implement Initial Risk Scan; Final Risk Check chưa implement |
| Approval Policy Registry / Gate | Đã implement proposal-scoped Banking precheck và separate Document external-release action; full action matrix cho các protected action tương lai chưa có |
| Approval expiration khi subject artifact đổi | Đã implement tại gate/decision revalidation |
| Downstream invalidation / DataPatch resume | Đã có narrow Banking supplement invalidation; generic transitive STALE/DataPatch chưa implement |
| Decision Agent | Đã implement Initial Route, Banking handoff/readiness/post-precheck review, conditional Decision-to-Document handoff và deterministic Internal Decision Package assembly; Decision Policy/Card chưa có |
| Banking Integration Skill | Đã implement internal discovery, readiness, submission proposal, deterministic simulated precheck result và evidence-supplement handoff; real-bank precheck/retry chưa có |
| Document Skill | Đã implement internal checklist/package, blocking signed-contract intake, deterministic masking và release candidate; actual send chưa có |
| Append-only Audit Logger | Chưa implement |

Prototype hiện tại hoàn thành vertical slice:

```text
Dataset Ingestion
  → Planner Intake
  → Initial Risk pre-scan / Approval Checkpoint registration
  → Finance Assessment + Operations Assessment
  → Initial Risk finalization
  → INITIAL_ASSESSMENT_COMPLETED
  → Decision Initial Route
  → DECISION_ROUTE_PLANNED
      ├── direct route: INTERNAL_DECISION_PACKAGE_ASSEMBLY
      └── Banking discovery handoff (khi route yêu cầu)
  → BANKING_DISCOVERY_REQUESTED
  → Banking Phase A internal discovery
  → BANKING_INTERNAL_OPTIONS_READY
  → BANKING_PRECHECK_READINESS
  → DECISION_POST_BANKING_REVIEW
      → thiếu amount: WAITING_FOR_INPUT
      → supplement VND: auto-resume
      → có option ready: BANKING_PRECHECK_READY
          → BANKING_PRECHECK_SUBMISSION_PROPOSAL
          → proposal-scoped APPROVAL_CHECKPOINTS
          → human required: WAITING_FOR_APPROVAL
              → approve: BANKING_PRECHECK_SUBMISSION_AUTHORIZED
              → reject: BANKING_PRECHECK_DECLINED
                  → INTERNAL_DECISION_PACKAGE_ASSEMBLY
          → explicit no-human/no other trigger: AUTHORIZED_WITHOUT_HUMAN
          → authorized branch: BANKING_PRECHECK_EXECUTION (SIMULATED)
          → BANKING_PRECHECK_RESULT_SET
          → BANKING_PRECHECK_RESULTS_READY
          → DECISION_POST_PRECHECK_REVIEW
              → conditional full coverage: DECISION_DOCUMENT_HANDOFF
                  → exactly one DOCUMENT_PREPARATION_REQUEST
                  → DOCUMENT_CHECKLIST + DOCUMENT_PACKAGE_DRAFT
                  → thiếu SIGNED_CONTRACT: WAITING_FOR_INPUT
                  → DOCUMENT_EVIDENCE_SUPPLEMENT: auto-resume
                  → DOCUMENT_RELEASE_PACKAGE_READY
                  → INTERNAL_DECISION_PACKAGE_ASSEMBLY
                    (no ApprovalRequest; external_release_performed = false)
              → other typed outcome: DECISION_POST_PRECHECK_REVIEW_COMPLETED
                  → INTERNAL_DECISION_PACKAGE_ASSEMBLY
              → MISSING_EVIDENCE: WAITING_FOR_INPUT
                  → BANKING_PRECHECK_EVIDENCE_SUPPLEMENT
                  → BANKING_PRECHECK_RETRY_REQUIRED
      → không có option ready: typed non-ready outcome
          → INTERNAL_DECISION_PACKAGE_ASSEMBLY
  → INTERNAL_DECISION_PACKAGE_READY
```

Việc tiếp tục build phải giữ nguyên responsibility boundaries trong tài liệu này.

## 17. Approval checkpoint implementation update (2026-07-16)

The prototype now implements the first case-scoped Approval Control Plane slice:

- Initial Risk Scan emits typed, evidence-bound checkpoint candidates for explicit event rules.
- Governance validates and persists `APPROVAL_CHECKPOINTS`; registration is non-blocking.
- `ApprovalGate` evaluates only exact typed protected-action payload fields.
- A triggered checkpoint creates an `ApprovalRequest` and the Orchestrator persists
  `WAITING_FOR_APPROVAL`.
- Human approval authorizes the exact protected action. A Banking-precheck rejection closes only
  that route at `BANKING_PRECHECK_DECLINED`; rejection behavior for other protected actions remains
  policy-specific and can block the action.
- Every human or machine authorization binds the subject artifact and policy artifact ID, version,
  and input hash.
- Initial Risk does not persist a hard-coded Banking-precheck checkpoint. After the exact proposal
  exists, Governance creates a proposal-scoped policy from `12_API_CATALOG` and explicitly mapped
  `22_API_HANDLING_RULES`, then merges an applicable amount rule such as `RR-005`.
- Explicit no-human policy produces a durable `AUTHORIZED_WITHOUT_HUMAN` record. Missing, invalid,
  or ambiguous policy fails closed.
- RR-001 remains OPC-global and is not attached to a contract checkpoint without an explicit
  transaction-to-case relationship.

This slice now executes internal Document preparation through `DOCUMENT_RELEASE_PACKAGE_READY` and
then deterministic `INTERNAL_DECISION_PACKAGE` assembly. It does not execute the future Decision
recommendation/proposal, Document release gate, real external Banking precheck, or protected
external adapter. The authorized Phase B1 path invokes only the server-configured deterministic
simulation; its output is `SIMULATED_NON_BINDING`. Readiness of either package creates no document
authorization and never sends. Authentication/RBAC and the full
append-only Audit Logger remain future work. A protected-action request that supplies
the Master `workflow_run_id` now persists pause/resume/block on the same `CaseWorkflowRun` and
`APPROVAL_GATE` node. Approval subject revalidation expires a pending request after supersession.
The older `WorkflowRunState` remains only for the manual Planner execution path and is not used as
the source of truth for Master Workflow approvals.

## 18. Durable Master Workflow update (2026-07-16)

The automatic Initial Assessment workflow is now implemented through SQLite-backed run, node,
artifact, Risk, approval, and event repositories. One `POST /api/cases/run` request performs Planner
Intake, registers the Risk pre-scan checkpoints, runs Finance and Operations concurrently, resumes
Risk finalization deterministically, runs Decision Initial Route, conditionally creates an internal
`BANKING_DISCOVERY_REQUEST`, runs Banking discovery/readiness, and runs Decision post-Banking
review. A Banking route with missing amount pauses at `DECISION_POST_BANKING_REVIEW`. The validated
`BANKING_INPUT_SUPPLEMENT` resolves the durable request and auto-resumes the same run; a ready route
persists a submission proposal and proposal-scoped Governance policy. The current TeamPack
`API-002` policy requires Founder approval; an explicit no-human policy could instead create a
machine authorization when no amount checkpoint triggers. Authorization resumes deterministic
simulated precheck execution. The workflow
validates and persists `BANKING_PRECHECK_RESULT_SET`, records the
`BANKING_PRECHECK_RESULTS_READY` milestone, then runs deterministic
`DECISION_POST_PRECHECK_REVIEW`. A full-coverage conditional result then runs
`DECISION_DOCUMENT_HANDOFF`. Workflow auto-runs Document only for exactly one preparation request,
pauses for an exact signed-contract reference, resumes to rebuild the masked package, and persists
the resulting `DOCUMENT_RELEASE_PACKAGE` as input for deterministic Internal Decision Package
assembly; it does not create a Founder gate. Other non-actionable typed provider outcomes reach
`DECISION_POST_PRECHECK_REVIEW_COMPLETED` and then converge on the same assembly phase unless an
explicit follow-up evidence field pauses them.
Authorized staff can persist a typed evidence reference without altering the old result; Workflow
then stops at `BANKING_PRECHECK_RETRY_REQUIRED` until a future fresh governed retry exists. Direct
routes, no-viable/no-precheck paths, rejected precheck proposals, non-actionable precheck results,
and ready conditional Document paths converge on `INTERNAL_DECISION_PACKAGE_READY`.

The in-process runner recovers matching `PENDING` and interrupted `RUNNING` records on startup.
Runtime dependency waits are persisted on Master Workflow nodes. The current path exposes genuine
missing-input, approval, and fail-safe pauses. The workflow automatically attaches the validated
proposal to `SUBMIT_BANKING_PRECHECK`; Governance evaluates the proposal-specific TeamPack policy
and pauses only when human approval is required. It does not itself execute the action. After a
valid human or machine authorization, the worker issues an ephemeral exact-subject permit and
invokes only `SimulatedBankingPrecheckAdapter`. The worker executes Decision routing,
internal handoff, Banking readiness, supplement-driven versioning, pre-execution post-Banking
review, Phase B1 simulated result persistence, and post-precheck classification; it still executes
no real bank adapter, selection/ranking, partial-coverage logic, external document send, or final
Decision policy/Card. Its Document branch performs only internal preparation; Internal Decision
Package assembly then records the exact validated evidence without adding a recommendation.

The Master Workflow now creates the Banking submission `ActionCommand` only after its proposal
artifact is validated and persisted. The Governance API remains the human decision interface for
the unified `WAITING_FOR_APPROVAL` lifecycle. Approval resumes the exact proposal; rejection closes
the Banking route without executing the adapter or blocking the whole case.

Phase B1 scenarios are server-owned at
`config/banking/precheck_simulation_scenarios.json` and participate in result identity through a
canonical configuration hash. The current `API-002`/`VietinBank` scenario returns
`CONDITIONAL_PRECHECK` with `SIMULATED_CONDITIONAL_PRECHECK`, controlled document/condition codes,
and authority `SIMULATED_NON_BINDING`; an unknown API/provider returns `SERVICE_UNAVAILABLE`.
Request/response hashes and permit-bound idempotency prevent an identical authorized execution from
creating a second logical result. Decision preserves the exact `option_id`/`bank_product_id` and
does not claim selection. No OpenAI component participates in request construction, adapter
execution, outcome normalization, result persistence, post-precheck classification, masking, or
release authorization.

## 19. Architecture audit status and remaining consolidation (2026-07-16)

The implemented Initial Assessment slice follows the agreed layer direction and responsibility
boundaries. Planner, Finance, Operations and Risk return drafts/signals; workflow services validate
and persist artifacts; TeamPack remains read-only; Finance and Operations run concurrently; Risk
starts with a pre-scan and finalizes after both fact artifacts are ready.

Completed consolidation:

1. Master Workflow and Approval now use the same `CaseWorkflowRun` and `WorkflowNodeState` source
   of truth.
2. Pending approval survives restart; approval resumes the exact run without rerunning completed
   Initial Assessment nodes; Banking-precheck rejection deterministically closes only that route.
3. `APPROVAL_GATE` records `WAITING_FOR_APPROVAL`, `COMPLETED`, `BLOCKED` or
   `WAITING_FOR_INPUT` in the Master node-state repository.
4. Subject artifact supersession expires the pending request before authorization.
5. Risk Pre-scan and Risk Finalization are separate nodes. The Risk business component completes
   each explicit mode; `INITIAL_RISK_FINALIZATION` owns dependency waiting in the Master Workflow.

Before implementing external Banking execution and Decision Phase 3, the following consolidation
remains:

1. Extend the protected-action enum and Approval Policy Registry only when future protected
   actions receive explicit policy sources; Banking precheck policy-source loading is complete.
2. Extend the implemented Banking supplement-specific input-hash invalidation into generic `STALE`
   and transitive downstream invalidation before supporting arbitrary DataPatch/resume.
3. Complete persistence for validation reports, approval requirements/decisions, and full audit
   events; the Banking requested-amount missing-data lifecycle is already durable.
4. Freeze the public case/dataset API contract before a frontend or external consumer depends on
   the current prototype routes.

This consolidation changes orchestration and governance plumbing only. It must not move Finance,
Operations, Risk, Decision, Banking or Document business rules into the Workflow Orchestrator.

## 20. Governance and post-precheck alignment (2026-07-18)

The Banking precheck control now follows these enforced rules:

1. The Risk pre-scan registers future evidence-backed checkpoints early, but no registration pauses
   a case. A consuming protected action is the only point where Workflow calls Governance.
2. Banking precheck policy is created only after a validated proposal exists. It uses the exact API
   IDs and policy facts carried from `12_API_CATALOG` plus explicitly mapped
   `22_API_HANDLING_RULES`; it is never inferred from names or hard-coded per contract.
3. `ApprovalGate` evaluates both the API policy and applicable amount checkpoints. The current
   TeamPack `API-002` requires the Founder before submission. `RR-005` uses its source `>` operator,
   so the exact threshold does not trigger that rule; an amount above it adds the amount checkpoint
   to the same approval request.
4. Loaded explicit no-human policy creates a durable `AUTHORIZED_WITHOUT_HUMAN` record. Missing,
   malformed, conflicting, or uncovered policy fails closed.
5. Founder approval and machine authorization are both proposal-, policy-, case-, action-, and
   hash-bound. Permit issuance revalidates the current artifacts and policy before execution.
6. Founder rejection of `SUBMIT_BANKING_PRECHECK` produces `BANKING_PRECHECK_DECLINED`, calls no
   adapter, and proceeds to Internal Decision Package assembly with one exact rejected Governance
   request reference. It is not a global case rejection or a new approval request.
7. The authorization covers only the exact precheck action. It cannot authorize final financing,
   external document release, or the final contract decision.
8. A validated `DOCUMENT_RELEASE_PACKAGE` is only an internal input for the conditional Internal
   Decision Package path; neither artifact can by itself propose
   `SEND_DOCUMENT_TO_EXTERNAL_PARTNER`. The generic protected-action endpoint cannot inject this
   action. The registered checkpoint remains dormant until a later exact Decision
   recommendation/proposal binds the proposed option and package; that proposal and its Founder
   approval flow are not implemented.

Missing-data intake is separate from approval. The current HTTP boundary records amount and
post-precheck evidence submissions as `AUTHORIZED_STAFF`; clients cannot submit a Founder identity
for these endpoints. A post-precheck evidence supplement preserves the original provider result,
creates no approval or bank claim, and moves Workflow to
`BANKING_PRECHECK_RETRY_REQUIRED`/`WAITING_FOR_DEPENDENCIES`. The fresh retry and real provider
mapping remain deliberately unimplemented until an explicit contract is available.

## 21. Conditional provider-to-Document update (2026-07-19)

The TeamPack still contains no actual VietinBank response. For workflow testing, the server-owned
`API-002` scenario now returns a non-binding conditional result with exact eligibility, guarantee,
VND amount strategy, document codes and condition codes. This scenario does not create bank
authority. Its echoed requested amount is a full-coverage mock assumption only; partial coverage
is deferred.

Decision creates one `DOCUMENT_PREPARATION_REQUEST` for every validated viable conditional result
without selection. Master Workflow proceeds only when exactly one exists. Document prepares an
internal outbound dossier, not an internal Decision package. Missing `SIGNED_CONTRACT` creates a
blocking input pause; reference-only supplement intake resumes the same run. Current minimum
company-profile fields `company_id` and `company_name` are a server assumption pending a provider
schema.

Masking occurs before the internal Decision handoff and uses server-owned minimization/classification policy,
contextual HMAC-SHA256 tokenization and fail-closed validation. The key is runtime-injected,
minimum 32 bytes; its value/digest is absent from workflow identity and artifacts. Workflow node
identity uses the canonical policy hash and key version. Tokenization is pseudonymization, not
anonymization, and Sheet `21_MASKING_EXAMPLES` never acts as executable policy.

A complete Document package is persisted and consumed by the `CONDITIONAL_DOCUMENT_READY` Internal
Decision Package path. Assembly does not trigger `SEND_DOCUMENT_TO_EXTERNAL_PARTNER`; the
registered checkpoint remains dormant. A later exact Decision recommendation/proposal must be
shown to the Founder before that action can be requested; that phase has no implementation yet.
The current boundary keeps `release_authorized = false` and `external_release_performed = false`
and has no connector invocation, provider receipt or send.

## 22. Internal Decision Package update (2026-07-19)

All eligible nonblocked Decision branches now converge through
`INTERNAL_DECISION_PACKAGE_ASSEMBLY`: direct route, no viable Banking option, no precheck path,
Founder-declined precheck, non-actionable precheck result, and conditional Document-ready. Only the
last path requires `DOCUMENT_RELEASE_PACKAGE`. Unsupported mappings, unresolved input, pending
approval, retry-required evidence, multi-option selection, masking failure, and failed-safe state do
not produce a partial package.

The assembler snapshots the exact validated common assessment chain and only the Banking,
Governance, or Document artifacts justified by that path. Package identity depends on the path,
exact source artifact ID/type/version/input hash/evidence references, and stable rejected-decision
substance when applicable. Audit-only workflow/request IDs and timestamps remain in the payload but
are excluded from identity. Evidence Validator runs before persistence; Workflow owns versioning
and the `INTERNAL_DECISION_PACKAGE_READY` milestone.

This artifact is a neutral evidence dossier for future Decision policy. It does not calculate new
Finance/Risk values, select or rank options, recommend accept/negotiate/reject, create a Decision
Card, request approval, authorize release, or call an external adapter. See
[Internal Decision Package](INTERNAL_DECISION_PACKAGE.md).
