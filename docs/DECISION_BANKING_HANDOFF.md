# Decision-managed Banking discovery handoff

## Purpose

This component converts a validated `BANKING_DISCOVERY_REQUIRED` route into an internal
`BANKING_DISCOVERY_REQUEST`. It establishes Decision as the business coordinator of Banking while
Workflow remains responsible for validation, persistence, execution order, and pause/resume.

```text
DECISION_ROUTE_PLANNED
  -> BANKING_DISCOVERY_HANDOFF
  -> BANKING_DISCOVERY_REQUESTED
  -> BANKING_INTERNAL_DISCOVERY
  -> BANKING_PRECHECK_READINESS
  -> DECISION_POST_BANKING_REVIEW
```

For `DIRECT_INTERNAL_DECISION`, the handoff returns `NOT_APPLICABLE`, creates no Banking artifact,
and leaves the workflow at `DECISION_ROUTE_PLANNED`.

## Input and output

The component receives exactly one validated `EVALUATION_CASE` and one validated
`DECISION_ROUTE_PLAN`, in stable case/route order. It reads no Excel, OpenAI narrative, free text,
external API, or arbitrary filesystem path. It rejects a route whose requirement or amount lineage
does not exactly match the Planner case.

For an applicable route, it creates a draft containing:

- deterministic request, case, dataset, and contract identity;
- capability `BANKING_INTERNAL_DISCOVERY`;
- typed need such as `PERFORMANCE_BOND`;
- route-plan and upstream artifact lineage;
- exact evidence IDs supporting the handoff;
- exact `requirement_id` and `credit_case_id`;
- positive `requested_amount` copied from the linked Planner requirement;
- canonical `requested_amount_currency: VND`;
- `amount_semantics = CREDIT_PROFILE_REQUESTED_AMOUNT` and the exact raw amount evidence ID; and
- an empty constraints collection.

Decision does not calculate this amount and does not copy it from contract wording, an unlinked
Credit Profile, notes, OpenAI prose, or a demo-specific rule. It carries only the evidence-backed
amount that Planner already bound to the exact contract requirement.

## Immutable request

`BANKING_DISCOVERY_REQUEST` is never updated after persistence. For the supported required
performance-bond route, a missing, ambiguous, non-positive, or non-integral Credit Profile amount
is a Planner blocker. The normal flow therefore does not pause here for a Founder to provide or
override `requested_amount`, and it does not create `BANKING_INPUT_SUPPLEMENT`.

The request amount is a requested/reference amount only. It is not the amount supported by a bank,
an approved limit, an issued guarantee, or a financing commitment. A later Banking result must use
separate fields and authority to state any supported amount.

## Ownership boundary

Decision business code returns an artifact draft only. It does not persist it, choose a workflow
node, invoke Banking, contact a bank, create an approval request, or emit an action command.
Workflow validates the draft, creates an immutable versioned envelope, persists it, and records the
handoff node.

The handoff is internal discovery, not a protected external action. Approval checkpoints may be
referenced by the broader Decision route, but this step does not activate them.

## API

The automatic workflow performs the handoff when applicable:

```http
POST /api/cases/run
```

Swagger/debug execution for an existing case:

```http
POST /api/cases/{evaluation_case_id}/banking-discovery-request
```

The endpoint returns `409 WAITING_FOR_INPUT` when the authoritative case or route artifact is
missing. Repeating the same request reuses the same validated artifact. Direct routes return
`NOT_APPLICABLE` without an artifact.

## Downstream behavior

Banking builds a deterministic matrix and a readiness artifact from the request amount. Decision
post-Banking review records a typed route outcome; the supported performance-bond path does not use
a human amount-capture cycle. If the carried requirement/amount evidence is inconsistent, the
component fails safe rather than asking a user to invent a replacement.

`BANKING_PRECHECK_READY` is not an external submission. Actual precheck execution, partner
responses, option selection, Document Skill, approval/action execution, and later Decision phases
remain outside this handoff. The current downstream Master Workflow can prepare a proposal, pause
for Founder approval only when Governance policy requires approval for the exact protected action,
then run a deterministic simulated precheck to the
`BANKING_PRECHECK_RESULTS_READY` milestone. A separate deterministic post-precheck review preserves
each option/product pair and completes at `DECISION_POST_PRECHECK_REVIEW_COMPLETED` unless explicit
evidence is missing. Phase B1 remains `SIMULATED_NON_BINDING`, not a partner response, and still
performs no selection, ranking, document preparation, or final Decision.
