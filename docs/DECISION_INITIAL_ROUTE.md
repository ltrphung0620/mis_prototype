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
          -> WAITING_FOR_INPUT, or
          -> BANKING_PRECHECK_READY
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

The current policy supports the one typed banking signal already emitted with exact source
lineage:

| Typed Finance observation | Banking need | Outcome |
|---|---|---|
| `PERFORMANCE_BOND_REQUIREMENT_OBSERVED` | `PERFORMANCE_BOND` | `BANKING_DISCOVERY_REQUIRED` |

If no supported typed signal exists, the outcome is `DIRECT_INTERNAL_DECISION`. Text in a title,
detail, note, contract description, or Risk narrative cannot activate a banking route. Working
capital, LC, and trade-finance routes require future typed upstream signals; the Decision component
does not infer them from natural language.

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

- source Finance artifact ID;
- exact observation ID; and
- exact evidence IDs.

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

When Decision post-Banking review pauses for the explicit amount, resolve the exact pending request
through:

```http
POST /api/cases/{evaluation_case_id}/banking/input-supplements
```

The validated supplement auto-resumes the same Master Workflow; it does not modify the Initial
Route or Banking discovery request.

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

For CON-004, the validated performance-bond observation produces
`BANKING_DISCOVERY_REQUIRED`, after which Decision creates `BANKING_DISCOVERY_REQUEST`. No
requested amount is assigned and no approval request is created. If later readiness needs that
amount, Decision post-Banking review—not Initial Route—creates the durable `MissingDataRequest`.

Reaching `BANKING_PRECHECK_READY` later does not revise the Initial Route and does not mean that an
external precheck, approval, bank selection, document, or Decision Card exists.

See [Internal Decision Package](INTERNAL_DECISION_PACKAGE.md) for the direct-route convergence and
the downstream evidence-dossier boundary.
