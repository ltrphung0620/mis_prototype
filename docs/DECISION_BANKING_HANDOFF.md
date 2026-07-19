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

The component receives exactly one validated `DECISION_ROUTE_PLAN` artifact ID. It reads no Excel,
OpenAI narrative, free text, external API, or arbitrary filesystem path.

For an applicable route, it creates a draft containing:

- deterministic request, case, dataset, and contract identity;
- capability `BANKING_INTERNAL_DISCOVERY`;
- typed need such as `PERFORMANCE_BOND`;
- route-plan and upstream artifact lineage;
- exact evidence IDs supporting the handoff;
- `requested_amount: null`;
- canonical `requested_amount_currency: VND`; and
- an empty constraints collection.

The null amount is intentional. Decision cannot derive a Banking amount from contract wording,
unlinked `10_CREDIT_PROFILE` records, notes, OpenAI prose, or a demo-specific rule.

## Immutable request

`BANKING_DISCOVERY_REQUEST` is never updated after persistence. When Decision later identifies that
an amount is required, the user supplies a separate `BANKING_INPUT_SUPPLEMENT`. That supplement:

- links to the exact durable missing-data request;
- carries `USER_INPUT` evidence;
- creates new downstream artifact versions; and
- does not change the handoff artifact or original TeamPack.

This separation preserves what Decision knew at handoff time and what a human confirmed later.

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

The endpoint returns `409 WAITING_FOR_INPUT` when `DECISION_ROUTE_PLAN` is missing. Repeating the
same request reuses the same validated artifact. Direct routes return `NOT_APPLICABLE` without an
artifact.

## Downstream behavior

Banking builds a deterministic matrix and a readiness artifact. Decision post-Banking review then
either creates a durable missing-amount request or records a typed route outcome. After a valid VND
supplement, the same Master Workflow auto-resumes and may reach `BANKING_PRECHECK_READY`.

`BANKING_PRECHECK_READY` is not an external submission. Actual precheck execution, partner
responses, option selection, Document Skill, approval/action execution, and later Decision phases
remain outside this handoff. The current downstream Master Workflow can prepare a proposal, pause
for Founder approval, then run a deterministic simulated precheck to the
`BANKING_PRECHECK_RESULTS_READY` milestone. A separate deterministic post-precheck review preserves
each option/product pair and completes at `DECISION_POST_PRECHECK_REVIEW_COMPLETED` unless explicit
evidence is missing. Phase B1 remains `SIMULATED_NON_BINDING`, not a partner response, and still
performs no selection, ranking, document preparation, or final Decision.
