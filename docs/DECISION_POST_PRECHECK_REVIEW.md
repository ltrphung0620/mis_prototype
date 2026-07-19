# Decision Post-Precheck Review

`DECISION_POST_PRECHECK_REVIEW` is the deterministic Decision component that runs after a validated
`BANKING_PRECHECK_RESULT_SET` has been persisted. It is distinct from
`DECISION_POST_BANKING_REVIEW`, which runs before precheck execution and reviews only the Banking
option matrix and input readiness.

## Responsibility

The component receives exactly:

- the validated `BANKING_PRECHECK_RESULT_SET`; and
- the exact authorized `BANKING_PRECHECK_SUBMISSION_PROPOSAL` referenced by that result set.

It verifies the ordered `proposal_item_id -> option_id -> bank_product_id -> API/provider` binding,
preserves every candidate, creates one evidence-bound disposition per result, and emits
`DECISION_POST_PRECHECK_REVIEW`.

It does not select or rank a bank/product, claim bank approval or eligibility, request an approval,
prepare documents, call OpenAI, call an external provider, or create a final Decision artifact.

## Deterministic mapping

| Precheck outcome | Option disposition | Effect |
|---|---|---|
| `CONDITIONAL_PRECHECK` | `CONDITIONAL_REVIEW` | Makes the full-coverage non-binding conditional result available to Decision-to-Document handoff. |
| `MISSING_EVIDENCE` | `FOLLOW_UP_EVIDENCE_REQUIRED` | Creates one blocking `MissingDataRequest` per explicit follow-up field. |
| `NOT_ELIGIBLE` | `NOT_ELIGIBLE` | Preserves the option as a non-binding negative precheck result. |
| `NO_RECOMMENDATION` | `NO_PROVIDER_RECOMMENDATION` | Preserves the candidate without treating it as rejected, selected, or recommended. |
| `SERVICE_UNAVAILABLE` | `PRECHECK_UNAVAILABLE` | Records a provider/service limitation; it is not Founder-supplied missing data. |

Aggregate priority is deterministic: any explicit missing evidence pauses first; otherwise any
conditional result is carried forward; homogeneous non-actionable batches receive their exact
typed outcome; mixed non-actionable batches use `MIXED_NON_ACTIONABLE_RESULTS`.

`MISSING_EVIDENCE` without a nonblank `required_follow_up_fields` list fails safe because Decision
must not invent a requirement. Non-`MISSING_EVIDENCE` follow-up fields are preserved as source
facts but do not create an input pause in this phase.

## Workflow

```text
BANKING_PRECHECK_EXECUTION
  -> BANKING_PRECHECK_RESULT_SET persisted
  -> BANKING_PRECHECK_RESULTS_READY milestone
  -> DECISION_POST_PRECHECK_REVIEW
       -> explicit missing evidence: WAITING_FOR_INPUT
          -> authorized staff submits exact evidence reference
          -> BANKING_PRECHECK_EVIDENCE_SUPPLEMENT persisted
          -> old result remains unchanged
          -> BANKING_PRECHECK_RETRY_REQUIRED / WAITING_FOR_DEPENDENCIES
       -> full-coverage conditional result: DECISION_DOCUMENT_HANDOFF
          -> one preparation request per viable result; no selection
          -> Workflow continues only when exactly one request exists
       -> other typed result: DECISION_POST_PRECHECK_REVIEW_COMPLETED
```

Evidence intake is not approval and does not reinterpret the prior result. The API excludes a
client-supplied identity; the server currently records `AUTHORIZED_STAFF`. Each supplement resolves
only its exact `MissingDataRequest` and states that a fresh governed precheck is required. The
current slice deliberately stops at `BANKING_PRECHECK_RETRY_REQUIRED` because it has no explicit
TeamPack mapping from an evidence reference into a new provider request.

The review remains a neutral classifier: it does not prepare documents. A separate Decision
handoff converts validated full-coverage conditional items into independent
`DOCUMENT_PREPARATION_REQUEST` drafts. Master Workflow does not select among them; it invokes
Document only when there is exactly one viable request. Partial coverage remains deferred.

## Current CON-004 behavior

The current TeamPack mapping carries the exact catalog product `BANKPROD-002` into the authorized
proposal. The server-owned `API-002` simulation now returns `CONDITIONAL_PRECHECK` with
`SIMULATED_NON_BINDING` authority, so the review returns:

```text
candidate product     = BANKPROD-002
option disposition    = CONDITIONAL_REVIEW
aggregate outcome     = CONDITIONAL_OPTIONS_AVAILABLE
missing-data requests = none
selection/ranking     = false/false
```

The configured mock supplies eligibility, conditional guarantee, echoed VND amount and exact
document/condition codes for workflow testing. TeamPack contains no real VietinBank response, so
this still is not a provider recommendation, official offer or bank approval. If this is the only
viable full-coverage request, Document preparation begins and pauses for a signed-contract
reference; any later external release has a separate Founder checkpoint.
