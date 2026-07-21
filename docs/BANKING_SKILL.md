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
For a supported required performance-bond route, the Decision request carries:

```json
{
  "requirement_id": "CREQ-...",
  "credit_case_id": "CR-...",
  "requested_amount": 420000000,
  "requested_amount_currency": "VND",
  "amount_semantics": "CREDIT_PROFILE_REQUESTED_AMOUNT",
  "amount_evidence_ids": ["EVD-..."]
}
```

The number is illustrative. Production logic never hard-codes a contract or amount. Planner first
classifies an exact configured requirement phrase, then resolves one Credit Profile through the
conjunction of exact OPC company ID, exact request type, and one canonical contract-ID token. It
accepts only one matching record with a positive integral `requested_amount`. Similar names,
unscoped descriptions, multiple candidates, or an invalid amount are never guessed.

Decision does not calculate or reinterpret the number; it carries the exact typed Planner
requirement and evidence into an immutable request. `requested_amount` means the amount requested or
referenced by the Credit Profile. It is not a bank-supported amount, bank approval, guarantee limit,
or financing commitment.

Dataset Ingestion reads these exact TeamPack sheets and keys:

- `02_OPC_PROFILE`, keyed by `field`;
- `10_CREDIT_PROFILE`, keyed by `credit_case_id`;
- `11_BANK_PRODUCTS`, keyed by `bank_product_id`;
- `12_API_CATALOG`, keyed by `api_id`; and
- `22_API_HANDLING_RULES`, keyed by `rule_id`.

No relationship is inferred from similar names or descriptions. The typed server policy at
`config/banking/catalog_mappings.json` currently declares:

```text
PERFORMANCE_BOND -> BANKPROD-002 -> API-002

API-002.contract_id     -> EVALUATION_CASE
API-002.amount          -> BANKING_DISCOVERY_REQUEST
API-002.company_profile -> OPC_PROFILE
```

The comma-separated `required_fields` value in `12_API_CATALOG` remains source metadata. It is
compared with the explicit server mapping but is never parsed into an implicit source relationship.
The policy ID, version, and canonical hash participate in artifact and workflow identity.

`10_CREDIT_PROFILE` contributes an amount only after Planner has created the explicit
`ContractRequirement` and added the exact `credit_case_id` to
`EvaluationCase.related_credit_case_ids`. A contract ID appearing somewhere in prose is not enough
on its own. The complete configured relationship test above must be unique and evidence-backed.
`company_profile` remains a different API field sourced from `02_OPC_PROFILE`; Credit Profile is
never substituted for the company profile.

## Internal option matrix

`BANKING_OPTION_MATRIX` is the authoritative deterministic discovery artifact. Each candidate
contains:

- exact need, product, provider, and API catalog IDs;
- source product facts with evidence lineage;
- `MINIMUM_AMOUNT` and other typed criteria;
- mock precheck metadata with `precheck_executed: false`;
- source handling text marked `SOURCE_GUIDANCE_ONLY`; and
- explicit blocking and non-blocking limitations.

On the normal supported route, the first immutable request already contains the positive amount.
The first matrix therefore:

- carries the exact `requested_amount` and canonical `VND`;
- traces amount evidence through `BANKING_DISCOVERY_REQUEST` back to the raw
  `10_CREDIT_PROFILE.requested_amount` cell retained by `EVALUATION_CASE`; and
- records deterministic `PASS` or `FAIL` for `MINIMUM_AMOUNT` against the catalog value.

If the request claims an amount without matching requirement, Credit Profile, semantics, and raw
evidence, Banking fails safe. It does not ask a human for a replacement value.

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
| `INPUT_REQUIRED` | A mapped legacy input is absent; this is not expected in the normal required performance-bond route because Planner blocks first. |
| `NOT_CONFIGURED` | The option has no mapped mock precheck API. |
| `UNSUPPORTED_MAPPING` | Catalog fields and explicit policy mapping cannot be reconciled safely. |
| `OPTION_REQUIREMENTS_NOT_MET` | A deterministic product requirement fails. |

The aggregate artifact indexes ready and pending option IDs. Every option and the aggregate keep
`precheck_executed: false`.

## Amount authority and legacy compatibility

For a new required performance-bond case, Planner owns amount resolution. Missing, ambiguous, or
invalid evidence creates a blocking Planner `MissingDataRequest`; Finance, Decision, Banking, and
Founder do not invent or override the amount downstream.

`BANKING_INPUT_SUPPLEMENT` and its endpoint remain only as a compatibility/recovery mechanism for
older persisted requests that legitimately predate the Planner requirement binding. They are not
part of the normal flow described here, cannot override a non-null authoritative
`BANKING_DISCOVERY_REQUEST` amount, and are submitted by an authorized staff principal rather than
the Founder. Evidence intake is not approval and creates no `ApprovalRequest`.

Founder interaction happens only when Governance evaluates a concrete protected action or option
under loaded policy. In this slice that can be the exact `SUBMIT_BANKING_PRECHECK` proposal; it is
not an amount-capture checkpoint.

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
- `amount` from the validated `BANKING_DISCOVERY_REQUEST`, with Planner/Credit Profile lineage; and
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

The normal applicable artifact chain is:

```text
EVALUATION_CASE (typed required performance bond + exact Credit Profile amount)
  -> DECISION_ROUTE_PLAN
  -> BANKING_DISCOVERY_REQUEST (amount + requirement/evidence lineage)
  -> BANKING_OPTION_MATRIX v1
  -> BANKING_DISCOVERY_RESULT v1
  -> BANKING_OPTION_ADVICE v1
  -> BANKING_PRECHECK_READINESS v1
  -> DECISION_POST_BANKING_REVIEW v1
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

Earlier envelopes are never mutated. Repeating the same workflow request with identical business
inputs reuses the same artifact identities.

## Current TeamPack behavior

With the current TeamPack and server mapping, CON-004 is an example with one required
performance-bond requirement, one exact linked Credit Profile requested amount, and one configured
candidate, `BANKPROD-002`, mapped to mock API metadata `API-002`. Planner supplies the amount and
lineage before Initial Assessment continues, so Banking evaluates the catalog minimum on its first
normal matrix. This is observed dataset behavior, not contract-specific production logic.

When a ready option exists, Decision records `BANKING_PRECHECK_READY`. Banking then creates a proposal
containing every READY option without ranking or selection. The proposal keeps exact fee,
processing-fee, collateral-ratio, and minimum-amount catalog terms plus reference-only API field
bindings. Because there is one candidate in the current TeamPack, the OpenAI advisor remains
`NOT_INVOKED`. If Governance determines that the exact protected action requires Founder approval,
approval authorizes only that proposal. The configured `API-002` simulation then
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
