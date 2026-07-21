# Decision Phase 1 — Initial Route

## Scope

Decision Initial Route classifies the next required business capability after the validated Initial
Assessment. It does not execute that capability or change workflow state.

```text
INITIAL_ASSESSMENT_COMPLETED
  -> DECISION_ROUTE_PLANNING
      -> BANKING_DISCOVERY_REQUIRED
      or DIRECT_INTERNAL_DECISION
  -> DECISION_ROUTE_PLANNED
      -> INTERNAL_DECISION_PACKAGE_ASSEMBLY (for DIRECT_INTERNAL_DECISION)
      -> BANKING_DISCOVERY_HANDOFF (only for BANKING_DISCOVERY_REQUIRED)
      -> BANKING_DISCOVERY_REQUESTED
      -> BANKING_INTERNAL_DISCOVERY (owned by Workflow and Banking Skill)
      -> BANKING_INTERNAL_OPTIONS_READY
      -> BANKING_PRECHECK_READINESS
      -> DECISION_POST_BANKING_REVIEW
          -> BANKING_PRECHECK_READY or a typed non-ready outcome
```

Decision's internal Banking discovery handoff is implemented as the immediate conditional step.
Banking then builds internal mock-catalog options and deterministic readiness. A separate Decision
post-Banking component reviews that readiness. Neither component changes the Initial Route artifact
or selects an option. A direct route now proceeds to deterministic Internal Decision Package
assembly. That package is not Decision policy or a Decision Card.

## Authoritative inputs

The component receives only explicit validated artifact IDs through `ExecutionContext`:

- `EVALUATION_CASE`;
- `FINANCE_FACTS`;
- `OPERATIONS_FACTS`;
- `INITIAL_RISK_ASSESSMENT`; and
- `APPROVAL_CHECKPOINTS`.

It does not read Excel, descriptions, OpenAI narratives, or arbitrary filesystem paths. Identity of
every input must match the same evaluation case, dataset, and contract. Missing required artifacts
produce deterministic `MissingDataRequest` objects and `WAITING_FOR_INPUT`.

## Routing policy

The route is driven by typed `EvaluationCase.contract_requirements` created by Planner, not by a
Finance observation, OpenAI narrative, or a user-entered amount:

| Planner requirement | Banking need | Outcome |
|---|---|---|
| `requirement_type = PERFORMANCE_BOND` and `certainty = REQUIRED` | `PERFORMANCE_BOND` | `BANKING_DISCOVERY_REQUIRED` |

For this route, Planner must already have resolved one exact linked Credit Profile and its positive
integral `requested_amount`. The requirement carries `requirement_id`, `credit_case_id`, canonical
`VND`, `amount_semantics = CREDIT_PROFILE_REQUESTED_AMOUNT`, and the raw amount evidence ID. An
unlinked, ambiguous, or invalid required performance-bond amount is blocking at Planner intake; it
is not deferred to a Founder input step.

`POSSIBLE` does not become a required Banking route. If no supported required Planner requirement
exists, the outcome is `DIRECT_INTERNAL_DECISION`. Working-capital and LC requirements can be
represented by Planner, but route support for them is outside this current Decision slice. Decision
does not infer any route from free text.

The route output requests a business capability, not a concrete workflow node:

- `BANKING_INTERNAL_DISCOVERY`; or
- `INTERNAL_DECISION_PACKAGE`.

The Master Workflow owns mapping that business outcome to the corresponding downstream node.

## Approval checkpoints

Registered checkpoint IDs are copied into `conditional_approval_checkpoint_ids` for future
orchestration visibility. Their presence does not create an `ApprovalRequest`, pause the workflow,
or assert that approval is currently required.

## Evidence and identity

Every banking route reason preserves:

- source `EVALUATION_CASE` artifact ID;
- exact Planner `requirement_id` and requirement certainty;
- exact linked `credit_case_id`;
- the positive `requested_amount`, `VND`, and its explicit amount semantics; and
- exact requirement and raw Credit Profile amount evidence IDs.

`DecisionRoutePlan` and its artifact identity depend on the route outcome, typed reasons,
conditional checkpoints, and explicit upstream artifacts. They do not depend on timestamps,
contract-specific demo logic, or OpenAI prose. Repeating the same request reuses the same artifact.

## API

Automatic execution:

```http
POST /api/cases/run
```

Standalone inspection after Initial Assessment:

```http
POST /api/cases/{evaluation_case_id}/decision-route
```

Conditional internal handoff after a Banking route:

```http
POST /api/cases/{evaluation_case_id}/banking-discovery-request
```

Banking Phase A inspection after that request:

```http
POST /api/cases/{evaluation_case_id}/banking/internal-discovery
```

The standalone endpoint returns `409 WAITING_FOR_INPUT` when authoritative assessment artifacts are
missing. It is a debug/Swagger surface; the automatic Master Workflow invokes the component without
requiring a user call.

## Boundary

Initial Route does not:

- calculate Finance or Operations facts;
- activate Risk rules or change risk level;
- parse natural-language notes to invent banking needs;
- attach unlinked credit profiles or amounts to the case;
- create an approval request or protected action;
- select a bank, product, option, or option combination;
- invoke Banking or Document;
- prepare an internal decision package;
- recommend accept/reject; or
- create a Decision Card.

For example, in the current TeamPack CON-004 has a required performance-bond requirement and one
exact linked Credit Profile amount. Planner places both the typed requirement and the amount
lineage in `EVALUATION_CASE`; Decision therefore routes to Banking and carries that amount into
`BANKING_DISCOVERY_REQUEST` without asking the Founder to enter it. CON-004 is an observed example,
not a contract-specific production rule.

The carried amount means only "the amount requested/reference amount recorded in the linked Credit
Profile". It is not proof that a bank supports, approves, or will issue a guarantee for that amount.
Those later facts require a validated Banking result. No approval request is created by Initial
Route.

Reaching `BANKING_PRECHECK_READY` later does not revise the Initial Route and does not mean that an
external precheck, approval, bank selection, document, or Decision Card exists.

See [Internal Decision Package](INTERNAL_DECISION_PACKAGE.md) for the direct-route convergence and
the downstream evidence-dossier boundary.
