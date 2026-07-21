# Decision Post-Banking Review

## Purpose

Decision post-Banking review classifies what the workflow can do after Banking has produced a
validated option matrix and precheck-readiness artifact. It does not rerun Banking calculations and
does not select an option.

```text
BANKING_PRECHECK_READINESS
  -> DECISION_POST_BANKING_REVIEW
      -> BANKING_INPUT_REQUIRED
           -> durable MissingDataRequest
           -> WAITING_FOR_INPUT
      -> BANKING_PRECHECK_READY
      -> NO_PRECHECK_PATH -> INTERNAL_DECISION_PACKAGE_ASSEMBLY
      -> UNSUPPORTED_PRECHECK_MAPPING -> FAILED_SAFE
      -> NO_VIABLE_OPTION -> INTERNAL_DECISION_PACKAGE_ASSEMBLY
```

Workflow Orchestrator maps the business outcome to persisted state. Decision business code returns
an artifact draft and any missing-data request; it does not persist either one or change workflow
state.

## Authoritative inputs

The review uses validated, same-case artifacts only:

- the latest `BANKING_OPTION_MATRIX`; and
- the matching `BANKING_PRECHECK_READINESS`.

The matrix and readiness IDs must agree. Candidate, ready, and pending option IDs must form a
consistent index. Unknown, stale, cross-case, or mismatched artifacts fail safely.

The review does not use OpenAI advice, descriptions, bank-product names, or natural-language notes
to decide the route. It does not compare the requested amount with a product threshold; that
deterministic check already belongs to Banking and is represented in readiness.

## Output

`DECISION_POST_BANKING_REVIEW` contains:

- stable review, case, dataset, contract, matrix, and readiness identity;
- one typed `DecisionPostBankingOutcome`;
- all candidate option IDs;
- precheck-ready and pending option IDs;
- exact required input fields, if any;
- explicit upstream artifact IDs and evidence IDs; and
- `precheck_executed: false`.

The indexes describe readiness; they are not a bank/product selection.

| Outcome | Meaning |
|---|---|
| `BANKING_PRECHECK_READY` | At least one option is ready for a later protected precheck submission. |
| `BANKING_INPUT_REQUIRED` | Readiness identifies an explicit user-input field that is still missing. |
| `NO_PRECHECK_PATH` | No configured precheck path exists for the assessed options; preserve that outcome in the Internal Decision Package. |
| `UNSUPPORTED_PRECHECK_MAPPING` | Catalog requirements cannot be matched safely to explicit policy sources; fail safe rather than assemble a misleading package. |
| `NO_VIABLE_OPTION` | Deterministic option requirements are not met; preserve that outcome in the Internal Decision Package. |

Only the first outcome maps to the intermediate milestone `BANKING_PRECHECK_READY`. That milestone
does not authorize or execute an external action; it allows the next Banking component to prepare
a governed, reference-only submission proposal.

## Missing requested amount

The initial `BANKING_DISCOVERY_REQUEST` intentionally keeps its amount null. Initial matrix and
readiness artifacts therefore allow Decision to identify `amount` as missing without inventing a
value.

For `BANKING_INPUT_REQUIRED`, Decision emits a precise blocking `MissingDataRequest`. The
Orchestrator persists it, records its ID on the Master Workflow, and pauses at:

```text
status        = WAITING_FOR_INPUT
current_stage = DECISION_POST_BANKING_REVIEW
resume_stage  = DECISION_POST_BANKING_REVIEW
```

This is a request for evidence, not a request for approval.

## Resolution and automatic resume

The user resolves the exact open request with:

```http
POST /api/cases/{evaluation_case_id}/banking/input-supplements
```

The request includes `workflow_run_id`, `missing_request_id`, a strict positive integer
`requested_amount`, `VND`, `provided_by`, and `evidence_note`. The server validates the case and
pending request, derives all other business identity, validates the supplement, persists it as an
immutable artifact, records the resolved request ID on that append-only supplement, removes the ID
from the workflow's pending set, and queues the same workflow. The historical Decision review is
not mutated.

On resume:

1. completed Initial Assessment, Initial Route, and handoff nodes are reused;
2. Banking internal discovery sees the new supplement in its input identity;
3. matrix/result/advice version 2 are created without changing version 1;
4. readiness is rebuilt from the new matrix and explicit profile source;
5. Decision review runs again; and
6. a ready result hands off at `BANKING_PRECHECK_READY`;
7. the next component prepares the proposal and Governance decides whether the workflow must pause.

An identical retry is idempotent. A conflicting value cannot overwrite the accepted supplement.

## Governance boundary

Initial Risk may already have registered conditional approval checkpoints. Registration alone does
not pause this review. Supplying an amount does not activate a checkpoint.

Approval is evaluated only after the next component prepares a typed
`BANKING_PRECHECK_SUBMISSION_PROPOSAL`. This review itself still proposes no action and creates no
`ApprovalRequest`; the Orchestrator converts the validated downstream proposal into
`SUBMIT_BANKING_PRECHECK`.

If the Founder later approves that exact proposal, the downstream workflow invokes only the
server-configured simulated precheck and persists `BANKING_PRECHECK_RESULT_SET`.
`BANKING_PRECHECK_RESULTS_READY` is then a milestone for the separate
`DECISION_POST_PRECHECK_REVIEW`, which preserves and classifies the results. Those results are
`SIMULATED_NON_BINDING`; they are not used by this readiness review and do not cause this component
to select/rank an option or run final Decision. A later Decision-to-Document handoff may consume a
validated full-coverage conditional result; that is a separate component and Workflow node.

## Explicit non-responsibilities

Decision post-Banking review does not:

- call a bank or mock API;
- claim precheck success, eligibility, or bank approval;
- create or authorize `SUBMIT_BANKING_PRECHECK`;
- select or rank a bank product;
- use OpenAI to change the route;
- prepare or release documents;
- make the final accept/negotiate/reject recommendation; or
- create a Decision Card.

For `NO_PRECHECK_PATH` and `NO_VIABLE_OPTION`, Workflow assembles the exact validated Banking
discovery/readiness/review evidence into `INTERNAL_DECISION_PACKAGE`. This is a neutral dossier,
not a claim that the contract should be accepted or rejected. See
[Internal Decision Package](INTERNAL_DECISION_PACKAGE.md).
