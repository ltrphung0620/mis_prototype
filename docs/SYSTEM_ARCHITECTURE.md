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
      Excel · SQLite · OpenAI · Mock Bank · Files
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

## 5. Protected action và Approval Control Plane

Business component không được trực tiếp thực hiện hành động nhạy cảm.

Ví dụ Banking Skill muốn gửi hồ sơ precheck sẽ chỉ tạo:

```json
{
  "action_type": "SUBMIT_BANKING_PRECHECK",
  "evaluation_case_id": "CASE-ID",
  "payload_artifact_id": "DOCUMENT-PACKAGE-ID",
  "requested_by": "BANKING_INTEGRATION_SKILL"
}
```

Luồng xử lý:

```text
ActionCommand
  → Evidence Validator
  → Approval Policy Registry
  → Approval Gate Coordinator
  → ALLOW / WAIT_FOR_APPROVAL / WAIT_FOR_EVIDENCE / BLOCK
  → External Adapter chỉ khi ALLOW
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

Recommendation chỉ do deterministic policy tạo:

- `ACCEPT`
- `NEGOTIATE_CONDITIONS_TO_ACCEPT`
- `DO_NOT_ACCEPT`

OpenAI không được thay đổi recommendation.

### 6.6 Banking Integration Skill

Phase A — Internal discovery, chưa cần approval:

- Credit Profile Reader.
- Bank Product Matcher.
- Eligibility Checker.
- Required Field Checker.
- Option Matrix Builder.
- Banking Recommendation Builder.

Output: `BankingRoutePackage` với trạng thái `INTERNAL_OPTIONS_READY`.

Phase B — Mock external precheck:

- Protected action: `SUBMIT_BANKING_PRECHECK`.
- Banking Skill chỉ tạo `ActionCommand`.
- Mock Bank Adapter chỉ chạy sau khi gate trả `ALLOW`.

Các response được phép:

- `CONDITIONAL_PRECHECK`
- `MISSING_EVIDENCE`
- `NOT_ELIGIBLE`
- `NO_RECOMMENDATION`

Không được tuyên bố loan/bank approval hoặc guarantee issuance.

### 6.7 Document Skill

Tạo `DocumentReleasePackage` gồm:

- Masked payload draft.
- External checklist.
- Executive summary.
- Email draft.
- Missing documents.

Document Skill không tự gửi payload. Việc gửi được biểu diễn bằng
`RELEASE_EXTERNAL_PAYLOAD` và phải qua Approval Gate Coordinator.

## 7. Governance components

### 7.1 Approval Policy Registry

Registry hợp nhất:

- TeamPack `13_RISK_RULES`.
- TeamPack `22_API_HANDLING_RULES`.
- Repository policy tại `config/governance/approval_policies.yml`.

Output là `ApprovalRequirement` gắn signal, context và protected action.

Không dùng `eval()` hoặc lưu Python expression dạng string. Chỉ dùng typed condition evaluator:

- `amount_threshold`
- `boolean_flag`
- `external_payload_present`
- `classification_threshold`
- `always`

### 7.2 Approval Gate Coordinator

Gate result:

- `ALLOW`
- `WAIT_FOR_APPROVAL`
- `WAIT_FOR_EVIDENCE`
- `BLOCK`

Approval phải gắn với:

```text
subject_artifact_id
subject_artifact_version
subject_input_hash
```

Nếu subject artifact thay đổi, approval cũ chuyển thành `EXPIRED` và phải approve lại.

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
INITIAL_ASSESSMENT, chạy song song
  ├── FINANCE_ASSESSMENT
  ├── OPERATIONS_ASSESSMENT
  └── INITIAL_RISK_SCAN
            ↓
REGISTER_APPROVAL_REQUIREMENTS
  → DECISION_ROUTE
      ├── không cần Banking/Document
      │     → INTERNAL_DECISION_PACKAGE
      └── cần Banking
            → BANKING_INTERNAL_DISCOVERY
            → DOCUMENT_PREPARATION
            → CHECK EXTERNAL_RELEASE GATE
            → CHECK BANKING_PREAPPROVAL GATE
            → BANKING_MOCK_PRECHECK
            → INTERNAL_DECISION_PACKAGE
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
| `SUBMIT_BANKING_PRECHECK` | `BANKING_PREAPPROVAL` | Initial Risk / policy registry |
| `RELEASE_EXTERNAL_PAYLOAD` | `EXTERNAL_RELEASE` | Classification / document package |
| `PROCEED_WITH_MAJOR_EXCEPTION` | `MAJOR_RISK_EXCEPTION` | Final Risk |
| `COMMIT_BUSINESS_DECISION` | `FINAL_DECISION` | System governance |

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
  governance/
  prompts/
  fallback/
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
    excel/
    persistence/
    openai/
    banking_mock/
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
| Evidence validation trước persistence | Đã implement cho Planner/Finance/Operations slice |
| Artifact versioning và idempotency | Đã implement cho Planner/Finance/Operations slice |
| Swagger Planner/Finance/Operations | Đã implement |
| Persistent SQLite repositories | Chưa implement; hiện dùng process-local memory |
| Full persisted state machine | Chưa implement |
| Parallel Initial Assessment | Chưa implement đầy đủ |
| Operations Skill | Đã implement |
| Risk Agent | Chưa implement |
| Approval Policy Registry / Gate | Chưa implement |
| Decision Agent | Chưa implement |
| Banking Integration Skill | Chưa implement |
| Document Skill | Chưa implement |
| Append-only Audit Logger | Chưa implement |

Prototype hiện tại hoàn thành vertical slice:

```text
Dataset Ingestion
  → Planner Intake
  → Finance Assessment / Operations Assessment
  → validated, versioned artifacts
```

Việc tiếp tục build phải giữ nguyên responsibility boundaries trong tài liệu này.
