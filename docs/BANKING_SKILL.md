# Banking Skill — Discovery, readiness, governed proposal, and simulated results

## Scope

Banking Skill reads the validated Decision request and the server-owned mock catalog to answer two
different questions:

1. Which configured options are explicitly related to the requested Banking need?
2. Is the evidence required for a later precheck available?

It never contacts a real bank or executes the catalog endpoint. After Governance authorizes the
exact proposal under the loaded TeamPack policy, Phase B1 invokes a server-configured deterministic
simulation adapter and persists explicitly non-binding results.

```text
BANKING_DISCOVERY_REQUEST
  -> BANKING_INTERNAL_DISCOVERY
  -> BANKING_OPTION_MATRIX + BANKING_DISCOVERY_RESULT
  -> BANKING_OPTION_ADVICE
  -> BANKING_PRECHECK_READINESS
  -> DECISION_POST_BANKING_REVIEW
      -> missing amount: WAITING_FOR_INPUT
      -> evidence ready: BANKING_PRECHECK_READY
          -> BANKING_PRECHECK_SUBMISSION_PROPOSAL
          -> proposal-scoped Governance policy
              -> explicit no-human policy: authorized
              -> human required: WAITING_FOR_APPROVAL
                 -> Founder approve: authorized
                 -> Founder reject: BANKING_PRECHECK_DECLINED
              -> authorized: BANKING_PRECHECK_EXECUTION (SIMULATED)
               -> BANKING_PRECHECK_RESULT_SET
               -> BANKING_PRECHECK_RESULTS_READY
               -> DECISION_POST_PRECHECK_REVIEW
                   -> conditional result: DECISION_DOCUMENT_HANDOFF
                      -> exactly one viable request: DOCUMENT_PREPARATION
                      -> zero/multiple requests: no auto-selection; fail safe
                   -> explicit evidence gap: WAITING_FOR_INPUT
                   -> other typed outcome: DECISION_POST_PRECHECK_REVIEW_COMPLETED
```

`BANKING_PRECHECK_READY` is a readiness milestone only. It is not bank approval, guarantee
issuance, product selection, permission to submit, or proof that a precheck ran. The subsequent
proposal is also reference-only and contains no external request body or response. Authorization
is bound to only that exact proposal envelope and action. The following execution is a local
simulation, not an external submission or provider decision.

## Authoritative inputs and explicit relationships

Initial discovery receives validated `EVALUATION_CASE` and `BANKING_DISCOVERY_REQUEST` artifacts.
The Decision request deliberately keeps:

```json
{
  "requested_amount": null,
  "requested_amount_currency": "VND"
}
```

Decision does not copy a number from contract text or from an unlinked credit profile. The request
is immutable after persistence.

Dataset Ingestion reads these exact TeamPack sheets and keys:

- `02_OPC_PROFILE`, keyed by `field`;
- `11_BANK_PRODUCTS`, keyed by `bank_product_id`;
- `12_API_CATALOG`, keyed by `api_id`; and
- `22_API_HANDLING_RULES`, keyed by `rule_id`.

No relationship is inferred from similar names or descriptions. The typed server policy at
`config/banking/catalog_mappings.json` currently declares:

```text
PERFORMANCE_BOND -> BANKPROD-002 -> API-002

API-002.contract_id     -> EVALUATION_CASE
API-002.amount          -> BANKING_INPUT_SUPPLEMENT
API-002.company_profile -> OPC_PROFILE
```

The comma-separated `required_fields` value in `12_API_CATALOG` remains source metadata. It is
compared with the explicit server mapping but is never parsed into an implicit source relationship.
The policy ID, version, and canonical hash participate in artifact and workflow identity.

`10_CREDIT_PROFILE` is used only when `EvaluationCase.related_credit_case_ids` explicitly selects a
record. Descriptive text such as `collateral_or_basis = "Contract ..."` is not a foreign key. A
missing credit-profile relationship may remain a discovery limitation, but it is not a precheck
blocker because `company_profile` has the separate explicit `02_OPC_PROFILE` source.

## Internal option matrix

`BANKING_OPTION_MATRIX` is the authoritative deterministic discovery artifact. Each candidate
contains:

- exact need, product, provider, and API catalog IDs;
- source product facts with evidence lineage;
- `MINIMUM_AMOUNT` and other typed criteria;
- mock precheck metadata with `precheck_executed: false`;
- source handling text marked `SOURCE_GUIDANCE_ONLY`; and
- explicit blocking and non-blocking limitations.

For the first run, the immutable request has no amount. Matrix version 1 therefore contains
`requested_amount: null`, emits `REQUESTED_AMOUNT_UNAVAILABLE`, and records `MINIMUM_AMOUNT` as
`NOT_EVALUABLE`. This matrix remains stored exactly as created.

When a valid supplement arrives, Workflow includes that new artifact in Banking's input identity
and runs internal discovery again. It does not overwrite version 1. It persists matrix/result/advice
version 2, where:

- `requested_amount` is the supplemented positive integer;
- currency is canonical `VND`;
- amount evidence traces to `BANKING_INPUT_SUPPLEMENT` with `source_type = USER_INPUT`;
- `REQUESTED_AMOUNT_UNAVAILABLE` is removed; and
- `MINIMUM_AMOUNT` becomes deterministic `PASS` or `FAIL` against the catalog value.

The minimum is read from `11_BANK_PRODUCTS`; Decision and Workflow contain no hard-coded monetary
threshold.

## Precheck readiness

`BANKING_PRECHECK_READINESS` is always created after a validated option matrix. It assesses each
option without constructing or sending an external request.

For every catalog-required field it records:

- the exact field name;
- `RESOLVED`, `MISSING_INPUT`, `SOURCE_UNAVAILABLE`, or `UNMAPPED`;
- the explicit policy source and source reference;
- source record/artifact IDs; and
- evidence IDs.

Option-level readiness may be:

| Status | Meaning |
|---|---|
| `READY` | Required fields and deterministic option requirements are satisfied. |
| `PARTIALLY_READY` | Some evidence is available, but the option is not ready. |
| `INPUT_REQUIRED` | A mapped user input, currently the requested amount, is absent. |
| `NOT_CONFIGURED` | The option has no mapped mock precheck API. |
| `UNSUPPORTED_MAPPING` | Catalog fields and explicit policy mapping cannot be reconciled safely. |
| `OPTION_REQUIREMENTS_NOT_MET` | A deterministic product requirement fails. |

The aggregate artifact indexes ready and pending option IDs. Every option and the aggregate keep
`precheck_executed: false`.

## Durable missing input and immutable supplement

Decision post-Banking review reads the readiness artifact. If the amount is missing, it creates a
durable blocking `MissingDataRequest`. Master Workflow persists the request and pauses at:

```text
status        = WAITING_FOR_INPUT
current_stage = DECISION_POST_BANKING_REVIEW
```

Authorized staff supplies the exact pending request through:

```http
POST /api/cases/{evaluation_case_id}/banking/input-supplements
```

```json
{
  "workflow_run_id": "CWF-...",
  "missing_request_id": "MDR-...",
  "requested_amount": 350000000,
  "requested_amount_currency": "VND",
  "evidence_note": "Amount confirmed for readiness assessment."
}
```

The numeric amount above is an API example only. No contract-specific amount is embedded in
Decision, Banking, Workflow, or policy configuration.

The amount must be a strict positive integer. Only `VND` is accepted. The server derives dataset,
contract, case, Banking-request identity, and the prototype principal `AUTHORIZED_STAFF`; the
client cannot replace or spoof them. It also verifies that the request is still open for the same
case and workflow. Founder identity is reserved for approval/business-confirmation endpoints.

The `202` response returns the immutable supplement, a compact artifact reference, and a workflow
status pointer. The Orchestrator then auto-resumes the same run. The user does not call generic
resume after a successful supplement.

Submitting input is evidence resolution, not approval. It creates no `ApprovalRequest`.

## Optional OpenAI advisor

The advisor runs only after the deterministic matrix has been validated and persisted.

- Zero or one candidate: no OpenAI call; advice is `NOT_INVOKED`.
- Two or more candidates: OpenAI may create guarded `ADVISORY_ONLY` prose.
- A multi-option suggestion is allowed only for an exact combination declared in server policy.
- Numeric values, customer/case identity, and the requested amount are not supplied to the advisor.

The guard rejects unknown option IDs, unconfigured combinations, numeric prose, selection or final
decision claims, approval claims, submission claims, and precheck-success claims. Advice never
changes readiness or Decision routing.

## Phase B1 simulated precheck after governed authorization

Governance first persists the proposal-scoped policy and a durable authorization record. That
record is either Founder-approved or `AUTHORIZED_WITHOUT_HUMAN` when a valid policy explicitly
requires no human and no other checkpoint triggers. It then issues an ephemeral
`AuthorizedActionPermit`. The permit is bound to the workflow, case, authorization record, policy,
and exact proposal artifact ID, version, and input hash. Workflow rejects stale, cross-case, or
different proposal subjects before invoking the adapter.

The request resolver then builds one in-memory request for every authorized proposal candidate, in
the same order. It resolves only the proposal's explicit bindings:

- `contract_id` from the validated `EVALUATION_CASE`;
- `amount` from the validated `BANKING_INPUT_SUPPLEMENT`; and
- `company_profile` from the explicitly indexed `02_OPC_PROFILE` records.

Request hashes and idempotency keys bind the permit, proposal artifact, proposal item, and exact
business request. Sensitive profile values are not included in the persisted result payload or in
runtime logs. No relationship is inferred from descriptions, credit-profile text, or OpenAI prose.

`SimulatedBankingPrecheckAdapter` is stateless and uses the server-owned typed configuration at
`config/banking/precheck_simulation_scenarios.json`. The current `API-002`/`VietinBank` scenario
returns:

```text
execution_mode            = SIMULATED
outcome                   = CONDITIONAL_PRECHECK
reason_code               = SIMULATED_CONDITIONAL_PRECHECK
eligibility_status        = ELIGIBLE
guarantee_decision        = CONDITIONAL
supported_amount_strategy = ECHO_REQUESTED_AMOUNT
currency                  = VND
non_binding               = true
```

The scenario also returns the exact document codes `SIGNED_CONTRACT`, `COMPANY_PROFILE`,
`PERFORMANCE_BOND_REQUEST_FORM`, and `CASHFLOW_BUFFER_EVIDENCE`, plus condition codes
`CONTRACT_SIGNED` and `CASHFLOW_BUFFER_CONFIRMED`. These are controlled mock facts. The TeamPack
does not contain a real VietinBank response or official response schema. Echoing the request amount
does not make it a real accepted limit or binding offer.

An API/provider without an explicit scenario returns non-binding `SERVICE_UNAVAILABLE`; it is not
converted into a provider recommendation. The adapter creates deterministic simulation references
and response hashes, but no external bank reference or approval.

The Banking result component validates the returned batch and creates
`BANKING_PRECHECK_RESULT_SET`. Every result has authority `SIMULATED_NON_BINDING`. The result set
also records these enforced boundaries:

```text
external_bank_submission = false
bank_approval_obtained    = false
selection_performed       = false
ranking_performed         = false
documents_prepared        = false
```

Evidence Validator runs before persistence. `BANKING_PRECHECK_RESULTS_READY` is then an intermediate
milestone. A separate deterministic Decision component preserves every option/product pair and
classifies the typed result in `DECISION_POST_PRECHECK_REVIEW`. A full-coverage conditional result
may continue to Decision-to-Document handoff. Decision preserves every viable request and does not
select one; Master Workflow auto-runs Document only when exactly one request exists. Partial
coverage is deferred and cannot be silently treated as full coverage. Phase B1 and this review use
no OpenAI call: the optional Banking advisor is a separate Phase A narrative path.

## Post-precheck missing evidence

When a typed provider result is `MISSING_EVIDENCE`, Decision creates one blocking
`MissingDataRequest` for each explicit follow-up field. Authorized staff resolves one exact request
through:

```http
POST /api/cases/{evaluation_case_id}/banking/precheck-evidence-supplements
```

```json
{
  "workflow_run_id": "CWF-...",
  "missing_request_id": "MDR-...",
  "evidence_reference_id": "DOC-REF-...",
  "evidence_note": "Linked the requested supporting evidence."
}
```

The server supplies `AUTHORIZED_STAFF`; a client cannot declare an approver identity. The
validated `BANKING_PRECHECK_EVIDENCE_SUPPLEMENT` resolves only that request and explicitly records
that the old result is unchanged, no bank approval exists, and no protected action is authorized.
When all follow-up requests are resolved, Workflow stops at
`BANKING_PRECHECK_RETRY_REQUIRED`/`WAITING_FOR_DEPENDENCIES`. A fresh provider retry must pass a new
Governance evaluation; the current slice does not yet implement that retry or invent a mapping
from a document reference into an external API request.

## Artifact ownership and versioning

Business components return drafts only. Workflow validates before persistence and owns versions,
input hashes, node attempts, pause/resume, and latest-artifact selection.

The applicable artifact chain is:

```text
BANKING_DISCOVERY_REQUEST v1 (amount remains null)
  -> BANKING_OPTION_MATRIX v1
  -> BANKING_DISCOVERY_RESULT v1
  -> BANKING_OPTION_ADVICE v1
  -> BANKING_PRECHECK_READINESS v1
  -> DECISION_POST_BANKING_REVIEW v1 + MissingDataRequest
  -> BANKING_INPUT_SUPPLEMENT v1
  -> BANKING_OPTION_MATRIX v2
  -> BANKING_DISCOVERY_RESULT v2
  -> BANKING_OPTION_ADVICE v2
  -> BANKING_PRECHECK_READINESS v2
  -> DECISION_POST_BANKING_REVIEW v2
      -> ready option: BANKING_PRECHECK_READY
         -> BANKING_PRECHECK_SUBMISSION_PROPOSAL
         -> proposal-scoped APPROVAL_CHECKPOINTS
             -> Founder approval or explicit machine authorization
             -> Founder reject: BANKING_PRECHECK_DECLINED
         -> authorized branch: BANKING_PRECHECK_EXECUTION (SIMULATED)
         -> BANKING_PRECHECK_RESULT_SET
         -> BANKING_PRECHECK_RESULTS_READY
         -> DECISION_POST_PRECHECK_REVIEW
             -> one full-coverage conditional result:
                 -> DECISION_DOCUMENT_HANDOFF
                 -> DOCUMENT_PREPARATION
             -> zero/multiple viable handoffs: no implicit selection
             -> other non-blocking typed result: DECISION_POST_PRECHECK_REVIEW_COMPLETED
             -> explicit missing evidence: WAITING_FOR_INPUT
                 -> BANKING_PRECHECK_EVIDENCE_SUPPLEMENT
                 -> BANKING_PRECHECK_RETRY_REQUIRED
      -> no ready option: typed non-ready outcome
```

Earlier envelopes are never mutated. Repeating the same supplement or workflow request reuses the
same business inputs instead of creating a third version.

## Current TeamPack behavior

With the current TeamPack and server mapping, CON-004 has one configured performance-bond
candidate, `BANKPROD-002`, mapped to mock API metadata `API-002`. Initial discovery cannot evaluate
its catalog minimum because the Decision request contains no amount. Decision review therefore
pauses for explicit input. This is observed dataset behavior, not contract-specific production
logic.

After a valid amount supplement, Banking reevaluates the catalog criterion and readiness. When a
ready option exists, Decision records `BANKING_PRECHECK_READY`. Banking then creates a proposal
containing every READY option without ranking or selection. The proposal keeps exact fee,
processing-fee, collateral-ratio, and minimum-amount catalog terms plus reference-only API field
bindings. Because there is one candidate in the current TeamPack, the OpenAI advisor remains
`NOT_INVOKED` on both matrix versions. After Founder approval, the configured `API-002` simulation
returns `CONDITIONAL_PRECHECK` with `ELIGIBLE`/`CONDITIONAL`, echoes the authorized requested amount
for the full-coverage test path, and supplies controlled document/condition codes. This remains
`SIMULATED_NON_BINDING`, not a real response, approval or offer from VietinBank. Decision preserves
the exact `BANKPROD-002` result and may create one Document handoff without claiming that the
product was selected or recommended.

## Responsibility boundary

This implemented slice does not:

- call the real `API-002` endpoint or any external bank adapter;
- transmit a request or company profile to a bank;
- produce an actual bank response, eligibility claim, or approval claim;
- select a bank, product, or combination;
- rank options or optimize a combination;
- prepare documents itself (the separate Document Skill may prepare an internal dossier after a
  validated Decision handoff);
- authorize or perform an external document release; or
- create an Internal Decision Package, deterministic recommendation, or Decision Card.

The proposal business component still creates only a reference draft. After validation and
persistence, the Orchestrator translates it into `SUBMIT_BANKING_PRECHECK`; Governance persists
either a pending human `ApprovalRequest` or an `AUTHORIZED_WITHOUT_HUMAN` record and owns
pause/resume. Authorization permits Workflow to invoke only the configured simulation adapter. A
separate result component normalizes its typed raw responses without calling the adapter itself.
Real external submission and response processing remain a later phase.

Governance does not use a global hard-coded Banking checkpoint. After proposal persistence, it
derives exact coverage from the proposal's `12_API_CATALOG.extension_rule` and explicitly mapped
`22_API_HANDLING_RULES` evidence, then merges any applicable amount checkpoint such as `RR-005`.
The current TeamPack says `API-002` requires human approval before submission, so it requires the
Founder even when the amount does not satisfy `RR-005`'s strict `>` threshold. For an API whose
valid loaded policy explicitly requires no human, the action may be machine-authorized only when
no other checkpoint triggers. Missing, invalid, or ambiguous policy fails closed.

When both API policy and `RR-005` trigger, Governance bundles both checkpoint IDs into one Founder
request for the exact proposal. At exactly 300 million VND, source operator `>` leaves `RR-005`
untriggered while current `API-002` still requires Founder approval; above that threshold both
controls are present.

This authorization scope is only `SUBMIT_BANKING_PRECHECK` for the exact proposal. It cannot be
reused for final financing commitment, external document release, bank/product selection, or the
final contract decision. Founder rejection closes the Banking branch without calling the adapter;
it does not block the whole evaluation case.

The conditional handoff, signed-contract pause, masking and separate release gate are documented in
[Document Skill](DOCUMENT_SKILL.md). The mock-provider limitations are documented in
[Banking Provider Response Assumptions](BANKING_PROVIDER_RESPONSE_ASSUMPTIONS.md).
