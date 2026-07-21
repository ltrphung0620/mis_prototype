# Automatic Master Workflow

## Scope

The Master Workflow is the only component that selects nodes, checks dependencies, validates and
persists artifacts, records durable missing input, and owns pause/resume. Business components
return drafts, signals, and typed results; they do not change workflow state.

```text
POST /api/cases/run
  -> PLANNER_INTAKE
  -> INITIAL_RISK_PRE_SCAN
  -> FINANCE_ASSESSMENT + OPERATIONS_ASSESSMENT concurrently
  -> INITIAL_RISK_FINALIZATION
  -> INITIAL_ASSESSMENT_COMPLETED
  -> DECISION_ROUTE_PLANNING
  -> DECISION_ROUTE_PLANNED
      -> direct route: INTERNAL_DECISION_PACKAGE_ASSEMBLY
      -> Banking route:
           BANKING_DISCOVERY_HANDOFF
           BANKING_INTERNAL_DISCOVERY
           BANKING_PRECHECK_READINESS
           DECISION_POST_BANKING_REVIEW
             -> ready: BANKING_PRECHECK_READY
                -> BANKING_PRECHECK_SUBMISSION_PROPOSAL
                -> CHECK SUBMIT_BANKING_PRECHECK
                   -> explicit no-human policy and no triggered amount rule:
                      BANKING_PRECHECK_SUBMISSION_AUTHORIZED
                   -> WAITING_FOR_APPROVAL
                   -> approved: BANKING_PRECHECK_SUBMISSION_AUTHORIZED
                      -> BANKING_PRECHECK_EXECUTION (SIMULATED)
                       -> BANKING_PRECHECK_RESULT_SET
                       -> BANKING_PRECHECK_RESULTS_READY
                       -> DECISION_POST_PRECHECK_REVIEW
                          -> conditional full-coverage result:
                             DECISION_DOCUMENT_HANDOFF
                             -> exactly one request: DOCUMENT_PREPARATION
                             -> missing performance-bond request form: WAITING_FOR_INPUT
                             -> document supplement: auto-resume
                             -> DOCUMENT_RELEASE_PACKAGE_READY
                             -> INTERNAL_DECISION_PACKAGE_ASSEMBLY
                          -> other typed result: DECISION_POST_PRECHECK_REVIEW_COMPLETED
                             -> INTERNAL_DECISION_PACKAGE_ASSEMBLY
                   -> rejected: BANKING_PRECHECK_DECLINED
                      -> INTERNAL_DECISION_PACKAGE_ASSEMBLY
             -> no viable option/no precheck path:
                INTERNAL_DECISION_PACKAGE_ASSEMBLY
  -> INTERNAL_DECISION_PACKAGE_READY
     (evidence dossier only; no recommendation, approval, or external send)
  -> FINAL_RISK_CHECK
  -> FINAL_RISK_ASSESSMENT
  -> FINAL_RISK_READY
     (residual risk and required controls only; no Decision recommendation)
  -> DECISION_CARD_COMPOSITION
     -> deterministic DecisionScenarioPacket
     -> bounded OpenAI proposal
     -> deterministic guard + Evidence Validator
     -> AI_DECISION_ANALYSIS
     -> DECISION_CARD + Evidence Validator
  -> DECISION_CARD_READY
     -> NOT_EVALUABLE: complete safely without approval
     -> approvable Card: FINAL_DECISION_APPROVAL
        -> rejected: FINAL_DECISION_REJECTED
        -> approved: POST_DECISION_UPDATE
           -> negotiate: NEGOTIATION_IN_PROGRESS
           -> do not accept: FINAL_DECISION_NOT_ACCEPTED
           -> accept without package: FINAL_DECISION_ACCEPTED
           -> accept with exact package:
              EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL
              -> separate CHECK SEND_DOCUMENT_TO_EXTERNAL_PARTNER
                 -> rejected: EXTERNAL_DOCUMENT_SUBMISSION_DECLINED
                 -> approved: READY_FOR_EXTERNAL_SUBMISSION
                    (no adapter call, send, or receipt)
```

`BANKING_PRECHECK_READY` is now an internal handoff milestone. The next component creates only a
reference manifest; neither that proposal nor the approval event is itself a precheck result.
Governance derives the gate from the exact proposal and TeamPack API-handling policy. A human
approval or an explicit no-human policy authorization resumes the workflow into a
server-configured simulation. Its result is non-binding and is not a response or approval from a
real bank.

## Detailed flow

```mermaid
flowchart TD
    A[Read configured TeamPack] --> B[Hash and validate read-only dataset]
    B --> C[Build DatasetSnapshot and indexes]
    C --> D[User selects exact contract_id]
    D --> E[POST /api/cases/run]
    E --> F[Create or reuse CaseWorkflowRun]

    F --> G[PLANNER_INTAKE]
    G --> H{Blocking base data missing?}
    H -- Yes --> I[Persist missing request and WAITING_FOR_INPUT]
    H -- No --> J[Persist EVALUATION_CASE and PLANNER_RESULT]

    J --> K[INITIAL_RISK_PRE_SCAN]
    K --> L[Persist RISK_PRE_SCAN and APPROVAL_CHECKPOINTS]
    L --> M[FINANCE_ASSESSMENT]
    L --> N[OPERATIONS_ASSESSMENT]
    M --> O[INITIAL_RISK_FINALIZATION]
    N --> O
    O --> P[Persist final Risk artifacts]
    P --> Q[INITIAL_ASSESSMENT_COMPLETED]

    Q --> R[DECISION_ROUTE_PLANNING]
    R --> S{Explicit Banking need?}
    S -- No --> T[DIRECT_ROUTE]
    S -- Yes --> U[BANKING_DISCOVERY_HANDOFF]
    U --> V[Persist request with exact Planner and Credit Profile amount lineage]
    V --> W[BANKING_INTERNAL_DISCOVERY]
    W --> X[Persist matrix result and advice]
    X --> Y[Persist BANKING_PRECHECK_READINESS]
    Y --> Z[DECISION_POST_BANKING_REVIEW]
    Z --> AD{Ready option exists?}
    AD -- Yes --> AE[BANKING_PRECHECK_READY]
    AD -- No --> AF{Typed non-ready outcome}
    AF -- No viable option or no precheck path --> AF1[Persist review]
    AF -- Unsupported mapping --> FAILMAP[Fail safe; do not guess policy mapping]

    AE --> AQ[Persist BANKING_PRECHECK_SUBMISSION_PROPOSAL]
    AQ --> AR[Build proposal-scoped policy from TeamPack API facts and Risk amount rule]
    AR --> AS{Governance outcome}
    AS -- Human required --> AT[Persist ApprovalRequest and WAITING_FOR_APPROVAL]
    AT --> AU{Founder decision}
    AU -- Approve --> AV[BANKING_PRECHECK_SUBMISSION_AUTHORIZED]
    AS -- Explicit no-human policy and no amount trigger --> AX[Persist machine authorization]
    AX --> AV
    AV --> AY[Issue exact ephemeral permit]
    AY --> AZ[BANKING_PRECHECK_EXECUTION using SIMULATED adapter]
    AZ --> BA[Validate and persist BANKING_PRECHECK_RESULT_SET]
    BA --> BB[BANKING_PRECHECK_RESULTS_READY]
    BB --> BC[DECISION_POST_PRECHECK_REVIEW]
    BC --> BD{Explicit missing evidence?}
    BD -- Yes --> BE[Persist MissingDataRequest and WAITING_FOR_INPUT]
    BD -- No --> BF{Full-coverage conditional result?}
    BF -- No --> BG0[DECISION_POST_PRECHECK_REVIEW_COMPLETED]
    BF -- Yes --> BG1[DECISION_DOCUMENT_HANDOFF]
    BG1 --> BG2{Number of viable preparation requests}
    BG2 -- Exactly one --> BG3[DOCUMENT_PREPARATION]
    BG2 -- Zero or multiple --> FAIL2[Fail safe; no implicit option selection]
    BG3 --> BG4[Persist DOCUMENT_CHECKLIST and DOCUMENT_PACKAGE_DRAFT]
    BG4 --> BG5{Blocking document missing?}
    BG5 -- Yes --> BG6[WAITING_FOR_INPUT at DOCUMENT_PREPARATION]
    BG6 --> BG7[Accept opaque reference and content SHA-256]
    BG7 --> BG8[Persist DOCUMENT_EVIDENCE_SUPPLEMENT and auto-resume]
    BG8 --> BG3
    BG5 -- No --> BG9[Persist DOCUMENT_RELEASE_PACKAGE]
    BG9 --> BG10[DOCUMENT_RELEASE_PACKAGE_READY]
    BG10 --> IDP[INTERNAL_DECISION_PACKAGE_ASSEMBLY]
    BG0 --> IDP
    T --> IDP
    AF1 --> IDP
    IDP --> IDPR[Persist INTERNAL_DECISION_PACKAGE]
    IDPR --> IDPREADY[INTERNAL_DECISION_PACKAGE_READY]
    IDPREADY --> FRC[FINAL_RISK_CHECK]
    FRC --> FRA[Persist FINAL_RISK_ASSESSMENT]
    FRA --> FRREADY[FINAL_RISK_READY]
    FRREADY --> DC[DECISION_CARD_COMPOSITION]
    DC --> DSP[Build deterministic DecisionScenarioPacket]
    DSP --> OAI[Bounded OpenAI composition or safe fallback]
    OAI --> DAG[Deterministic guard and Evidence Validator]
    DAG --> AIA[Persist AI_DECISION_ANALYSIS]
    AIA --> DCA[Rebuild packet, replay guard, assemble Decision Card]
    DCA --> DCV[Evidence Validator and persist DECISION_CARD]
    DCV --> DCR[DECISION_CARD_READY]
    DCR --> DR{Recommendation}
    DR -- NOT_EVALUABLE --> DNE[Complete safely; no approval request]
    DR -- Approvable --> FDA[FINAL_DECISION_APPROVAL]
    FDA -- Reject --> FDR[FINAL_DECISION_REJECTED]
    FDA -- Approve exact Card --> PDU[Persist POST_DECISION_UPDATE]
    PDU --> PDO{Approved route}
    PDO -- Negotiate --> NIP[NEGOTIATION_IN_PROGRESS]
    PDO -- Do not accept --> FDNA[FINAL_DECISION_NOT_ACCEPTED]
    PDO -- Accept without package --> FACC[FINAL_DECISION_ACCEPTED]
    PDO -- Accept with exact package --> EDSP[Persist EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL]
    EDSP --> EGA{Separate Governance approval}
    EGA -- Reject --> EDD[EXTERNAL_DOCUMENT_SUBMISSION_DECLINED]
    EGA -- Approve exact proposal --> RFES[READY_FOR_EXTERNAL_SUBMISSION]
    RFES --> NOSEND[No adapter call, external send, or receipt]
    AU -- Reject --> AW[Close Banking route at BANKING_PRECHECK_DECLINED]
    AW --> IDP
    AS -- Missing or invalid policy/input --> FAIL[Fail closed at APPROVAL_GATE]

    BE --> BG[Authorized staff submits evidence reference]
    BG --> BH[Persist BANKING_PRECHECK_EVIDENCE_SUPPLEMENT]
    BH --> BI[Preserve old result and resolve exact MissingDataRequest]
    BI --> BJ[WAITING_FOR_DEPENDENCIES at BANKING_PRECHECK_RETRY_REQUIRED]

```

Risk pre-scan runs before the parallel tasks so future approval checkpoints exist early. Finance
and Operations then run concurrently. Risk finalization waits for both fact artifacts. This
dependency wait is Workflow state, not a Risk component pause.

## Planner requirement and Banking amount lifecycle

Planner inspects the exact selected contract and explicitly related orders during
`PLANNER_INTAKE`. It classifies configured requirement types and certainty, then resolves Credit
Profile data only through exact company, request-type, and canonical contract-ID relationships.

For `PERFORMANCE_BOND + REQUIRED`, one unique linked Credit Profile with a positive integral
`requested_amount` is required. Otherwise Planner creates a blocking `MissingDataRequest` and the
workflow stays at Planner intake. The system does not defer that amount to a Founder form.

When the requirement is valid, `EVALUATION_CASE.contract_requirements` carries the requirement ID,
Credit Profile ID, amount, VND, semantics, and evidence. Decision copies those exact fields into
`BANKING_DISCOVERY_REQUEST`; Banking can evaluate `MINIMUM_AMOUNT` on the first normal matrix.

This is a requested/reference amount from Credit Profile. It is not the amount a bank supports or
approves. A later normalized Banking result owns any separate `supported_amount` fact and authority.

## Explicit precheck field sources

Readiness uses only server-policy mappings:

```text
contract_id      -> EVALUATION_CASE
amount           -> BANKING_DISCOVERY_REQUEST
company_profile  -> 02_OPC_PROFILE
```

`12_API_CATALOG.required_fields` is compared with this mapping but does not create source
relationships. `10_CREDIT_PROFILE` supplies only the Planner-bound requested amount; it is not
substituted for `company_profile`. Similar names or unscoped descriptive text never create a link.

## Artifact flow and immutability

```text
DatasetSnapshot
  -> EVALUATION_CASE + PLANNER_RESULT (including typed contract_requirements)
  -> RISK_PRE_SCAN + APPROVAL_CHECKPOINTS
  -> FINANCE_FACTS + FINANCE_ASSESSMENT
  -> OPERATIONS_FACTS + OPERATIONS_ASSESSMENT
  -> RISK_RULE_EVALUATION + INITIAL_RISK_ASSESSMENT
  -> DECISION_ROUTE_PLAN
  -> BANKING_DISCOVERY_REQUEST (requested amount + exact evidence lineage)
  -> BANKING_OPTION_MATRIX + BANKING_DISCOVERY_RESULT
  -> BANKING_OPTION_ADVICE
  -> BANKING_PRECHECK_READINESS
  -> DECISION_POST_BANKING_REVIEW
      -> ready option: BANKING_PRECHECK_READY
         -> BANKING_PRECHECK_SUBMISSION_PROPOSAL v1
         -> proposal-scoped APPROVAL_CHECKPOINTS
             -> human required: ApprovalRequest(PENDING) + WAITING_FOR_APPROVAL
                 -> approve: BANKING_PRECHECK_SUBMISSION_AUTHORIZED
                 -> reject: BANKING_PRECHECK_DECLINED
             -> explicit no-human/no amount trigger:
                 ApprovalRequest(AUTHORIZED_WITHOUT_HUMAN)
                 -> BANKING_PRECHECK_SUBMISSION_AUTHORIZED
         -> authorized branch: BANKING_PRECHECK_EXECUTION (SIMULATED)
         -> BANKING_PRECHECK_RESULT_SET v1
         -> BANKING_PRECHECK_RESULTS_READY
         -> DECISION_POST_PRECHECK_REVIEW v1
             -> no explicit gap: DECISION_POST_PRECHECK_REVIEW_COMPLETED
                -> INTERNAL_DECISION_PACKAGE_ASSEMBLY
             -> explicit missing evidence: WAITING_FOR_INPUT
                 -> BANKING_PRECHECK_EVIDENCE_SUPPLEMENT
                 -> BANKING_PRECHECK_RETRY_REQUIRED
      -> no ready option: typed non-ready outcome
         -> INTERNAL_DECISION_PACKAGE_ASSEMBLY
  -> INTERNAL_DECISION_PACKAGE_READY
  -> FINAL_RISK_ASSESSMENT
  -> FINAL_RISK_READY
```

No earlier artifact is updated in place. The matrix traces the amount back through the immutable
Decision request and Planner case to raw Credit Profile evidence, then records deterministic
`PASS` or `FAIL`. Repeated identical business input reuses the same artifact identity.

## Idempotency, invalidation, and recovery

`workflow_run_id` depends on dataset snapshot, contract, requested Initial Assessment scope, and
explicit `as_of_date`. Repeating the same start request returns the same run.

Banking node identity includes explicit upstream artifacts, the Planner-bound request amount and
lineage, catalog-policy hash, and advisor configuration hash. Therefore:

- unchanged business inputs reuse the same artifacts;
- changed TeamPack evidence produces a changed dataset/workflow identity rather than mutating old
  envelopes;
- completed Planner, Finance, Operations, Risk, Initial Route, and handoff nodes are reused when
  their exact inputs remain unchanged;
- Phase B1 request identity binds the permit, proposal envelope, proposal item, and canonical
  request hash; and
- an identical authorized execution reuses the same validated result set instead of invoking a
  second logical simulation; and
- Internal Decision Package identity depends on its assembly path, exact validated source-envelope
  identities, and stable rejected-decision substance. Full Governance audit references remain in
  the payload, while workflow/request IDs and timestamps are excluded from artifact identity.

Generic transitive `STALE` or arbitrary DataPatch support is not implemented. Existing
post-precheck and Document evidence supplements remain narrowly scoped to their own evidence gaps;
they do not replace the Planner-owned performance-bond amount.

SQLite-backed run, node, artifact, missing-data, approval, and event state survive API restarts.
The runner recovers matching `PENDING` or interrupted `RUNNING` work. A run intentionally waiting
for genuine Planner, post-precheck, or Document evidence remains waiting until the exact request is
resolved.

## Document input, masking, and Internal Decision handoff

The current conditional `API-002` scenario is server-owned mock data; the TeamPack has no real
VietinBank response. It declares four document requirements. Structured company profile and an
masked contract snapshot are available internally, cashflow evidence keeps its OPC-global
limitation, and `PERFORMANCE_BOND_REQUEST_FORM` blocks until Founder supplies an exact reference.
`SIGNED_CONTRACT` keeps `SIGNED_CONTRACT_PENDING_FOUNDER_ACCEPTANCE` until an approved `ACCEPT`
Post-Decision Update; it does not block Internal Decision assembly.

Document intake accepts an opaque `document_reference_id`, a SHA-256 content digest, the exact
pending request/type, and an evidence note. It does not accept bytes, URL, or filesystem path.
Resolving the request creates a new supplement and package version; prior artifacts are immutable.

Before `DOCUMENT_RELEASE_PACKAGE` is created, payload construction applies minimum-field selection,
exact data classification and deterministic masking. Restricted identifiers use contextual
HMAC-SHA256 namespace `provider | purpose | field | key_version`; runtime key material must be at
least 32 bytes, while token output is at least 128 bits. Missing key or unknown policy/field fails
closed. Tokenization is pseudonymization, not anonymization. Sheet `21_MASKING_EXAMPLES` is only
example data and never executable masking policy.

The current composition root requires exact `company_id` and `company_name` profile fields. This is
a documented server assumption, not a VietinBank requirement proven by TeamPack. Partial provider
coverage is deferred, and the workflow does not silently select among multiple viable handoffs.

## API

Start and inspect:

```http
POST /api/cases/run
GET  /api/workflows/{workflow_run_id}
GET  /api/workflows/{workflow_run_id}/events?after_sequence=0
```

At `FINAL_RISK_READY`, the workflow summary exposes `final_risk_assessment_id`,
`final_risk_status`, `final_residual_risk_level`, `final_major_exception`,
`final_unresolved_approval_gate_ids`, and `final_required_control_codes`. The full validated
envelope remains available through the case artifact endpoint; the API layer does not recalculate
or reinterpret these values.

Resolve one explicit post-precheck evidence request without rewriting the old provider result:

```http
POST /api/cases/{evaluation_case_id}/banking/precheck-evidence-supplements
```

Resolve one exact Document missing-data request with reference metadata and auto-resume:

```http
POST /api/cases/{evaluation_case_id}/documents/evidence-supplements
```

Inspect and resolve a genuine pending Founder request, such as the governed Banking-precheck
proposal:

```http
GET  /api/cases/{evaluation_case_id}/artifacts
GET  /api/cases/{evaluation_case_id}/approval-requests
POST /api/approval-requests/{request_id}/decision
```

The generic protected-action endpoint cannot manually create `SUBMIT_BANKING_PRECHECK`,
`CONFIRM_FINAL_CONTRACT_DECISION`, or `SEND_DOCUMENT_TO_EXTERNAL_PARTNER`. Banking precheck is
accepted only from its exact validated proposal node. Document package readiness does not propose
the latter action; it remains dormant until the implemented Decision flow persists an exact
external submission proposal after approval of the exact `ACCEPT` Card.

The generic endpoint remains for other genuine waits or changed failure conditions:

```http
POST /api/workflows/{workflow_run_id}/resume
```

It must not be used to bypass an unresolved Planner requirement or any other missing-data request.

Standalone component endpoints remain available for Swagger inspection, but the Master Workflow
does not require the user to invoke each component manually.

## Approval boundary

Initial Risk registers only evidence-backed future checkpoints from Risk rules such as `RR-004`
and `RR-005`; registration alone never pauses the workflow. It does not create a global hard-coded
Banking-precheck checkpoint. After the exact proposal is persisted, Governance reads the
proposal-carried facts from `12_API_CATALOG` and the explicitly mapped `22_API_HANDLING_RULES`,
then creates a proposal-scoped policy artifact. Missing, ambiguous, or unsupported policy fails
closed.

For each proposal API, the policy records one `ApprovalPolicyCoverage` containing the API ID,
`12_API_CATALOG.extension_rule`, and exact mapped sheet-22 `rule_id`, `applies_to`,
`requires_human_approval`, and evidence IDs. The amount checkpoint preserves the source Risk rule
ID, operator, threshold, and evidence; Governance does not translate `>` into `>=`.

After Decision reports a ready route, Banking batches every READY option into a validated,
reference-only proposal. The Orchestrator persists that proposal first, creates an `ActionCommand`
referencing its immutable envelope, and asks Governance to evaluate all applicable controls. For
the current TeamPack, `API-002` explicitly requires human approval before submission; when the
amount is also greater than the `RR-005` threshold, both controls are retained in the same Founder
request. At the exact threshold, the `>` rule is not triggered, although the API policy can still
require Founder approval. If a future valid API policy explicitly says no human approval and no
amount rule triggers, Governance persists `AUTHORIZED_WITHOUT_HUMAN` instead of silently bypassing
the gate. Either authorization is bound to the exact policy and proposal ID, version, and hash.

Founder approval authorizes only `SUBMIT_BANKING_PRECHECK` for that proposal. It does not authorize
a final commitment, external document release, bank/product selection, or final contract decision.
Founder rejection closes only the Banking route at `BANKING_PRECHECK_DECLINED`, creates no precheck
result set, does not invoke the adapter, and does not block the whole case. Workflow then preserves
the exact rejected request as a Governance reference while assembling the Internal Decision
Package. That reference records what happened; it is not a new approval request or an instruction
to reverse the decision.

The server configuration currently maps `API-002`/`VietinBank` to a controlled
`CONDITIONAL_PRECHECK` with `SIMULATED_CONDITIONAL_PRECHECK`, `ELIGIBLE`, conditional guarantee,
VND, an echoed requested amount and exact document/condition codes. It always remains
`SIMULATED_NON_BINDING`; the TeamPack has no real VietinBank response. Missing API/provider
scenarios produce `SERVICE_UNAVAILABLE`, never an invented recommendation. The request body and
sensitive company profile remain in-memory adapter inputs and are not raw fields of
`BANKING_PRECHECK_RESULT_SET`.

When the conditional result is full coverage, Decision can create one preparation request per
viable result. It does not select. Master Workflow continues only when exactly one request exists;
zero or multiple requests fail safe. Partial coverage is deferred. This rule prevents array order
or demo data from becoming an accidental banking decision.

Document preparation is a separate internal capability. Missing `SIGNED_CONTRACT` creates a
blocking request and pauses the same workflow. Resolving it with an exact opaque document reference
and content SHA-256 creates an immutable supplement and rebuilds the package. A ready
`DOCUMENT_RELEASE_PACKAGE` is persisted as the masked Document input for Internal Decision Package
assembly. It does not trigger Governance, create an ApprovalRequest, or authorize an external
send. The registered `SEND_DOCUMENT_TO_EXTERNAL_PARTNER` checkpoint stays dormant. Precheck
authorization cannot be reused. Only the downstream evidence-bound Decision flow may activate that
separate checkpoint, and only after an exact `ACCEPT` Card is approved and an
`EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL` is persisted.

## Internal Decision Package convergence and current boundary

Every eligible nonblocked Decision branch now converges at
`INTERNAL_DECISION_PACKAGE_ASSEMBLY`: direct route, no viable Banking option, no configured
precheck path, Founder-declined Banking precheck, non-actionable precheck result, or a conditional
Document path with a ready masked release package. A pending input, pending approval, unsupported
mapping, masking failure, or other failed-safe state cannot produce a partial package.

The resulting `INTERNAL_DECISION_PACKAGE` is a deterministic snapshot of already validated
evidence and branch outcomes. It creates no new Finance/Risk facts, performs no bank/product
selection, and makes no accept/negotiate/reject recommendation. It creates no `ActionCommand` or
`ApprovalRequest` and keeps `recommendation_performed`, `selection_performed`,
`approval_requested`, and `external_action_performed` false. The successful workflow milestone is
`INTERNAL_DECISION_PACKAGE_READY`; Workflow then automatically runs Final Risk Check.

For the conditional Document branch, the source `DOCUMENT_RELEASE_PACKAGE` still has
`document_release_authorized = false` and `document_external_release_performed = false`. No real
external precheck/API call, external document send, or partial-coverage optimizer is implemented.
The later Decision flow can reference this exact package but cannot mutate it. See
[Internal Decision Package](INTERNAL_DECISION_PACKAGE.md) for exact path and source rules.

## Final Risk convergence and Decision continuation

Final Risk Check consumes exactly one validated `INTERNAL_DECISION_PACKAGE`. It carries only open
findings forward as `OPEN_UNCHANGED`, preserves evidence limitations, and creates deterministic
required controls. `residual_risk_level` is derived from the open residual set; `SAFE` requires no
residual finding, unresolved approval/confirmation, or evidence limitation. Registered checkpoints
remain dormant; they are not unresolved approval gates.

Workflow validates and persists one `FINAL_RISK_ASSESSMENT`, records
`FINAL_RISK_CHECK_COMPLETED`, and reaches `FINAL_RISK_READY`. Final Risk itself creates no
`MissingDataRequest`, `ApprovalRequest`, `ActionCommand`, recommendation, or external action. An
invalid or mismatched Internal Decision Package fails safe instead of creating a late Founder input
form.

Workflow then runs the implemented Decision composition and post-decision graph shown above.
OpenAI sees only a deterministic `DecisionScenarioPacket`; deterministic guards and Evidence
Validator run before the analysis and Card are persisted. `NOT_EVALUABLE` ends safely at
`DECISION_CARD_READY`. Every other recommendation requires the separate Founder approval bound to
the exact Card before `POST_DECISION_UPDATE` exists.

An approved `ACCEPT` with a masked package creates a reference-only
`EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL` and activates a second, proposal-bound Governance request.
Even after that authorization, Workflow stops at `READY_FOR_EXTERNAL_SUBMISSION`; the readiness
proof is not persisted as a receipt and explicitly records that no adapter or send ran. See
[Decision, Final Approval, and External-Release Readiness](DECISION_FINAL_APPROVAL_AND_RELEASE.md)
for exact artifact/checkpoint bindings and responsibility boundaries.
