# Internal Decision Package

## Purpose

`INTERNAL_DECISION_PACKAGE` is the deterministic evidence dossier produced after an eligible,
nonblocked Decision branch has reached a stable internal outcome. It gives a later Decision policy
one validated, case-consistent snapshot instead of requiring that phase to rediscover artifacts
from the workflow history.

The package is **not** a recommendation or Decision Card. Assembly does not calculate new Finance
or Risk facts, select a bank/product, approve a protected action, authorize or send documents, or
perform any external action. OpenAI does not participate in assembly.

```text
eligible branch outcome
  -> INTERNAL_DECISION_PACKAGE_ASSEMBLY
  -> Evidence Validator
  -> persist versioned INTERNAL_DECISION_PACKAGE
  -> INTERNAL_DECISION_PACKAGE_READY
```

Workflow Orchestrator selects the path, supplies exact artifact identities, validates the returned
draft, persists its envelope, and owns wait/fail/ready state. The business assembler is
side-effect-free.

## Convergence paths

The package records why the case reached assembly through `InternalDecisionAssemblyPath`:

| Assembly path | Required branch fact | Document required? |
|---|---|---|
| `DIRECT_ROUTE` | Initial Route returned `DIRECT_INTERNAL_DECISION`. | No |
| `BANKING_NO_VIABLE_OPTION` | Post-Banking review returned `NO_VIABLE_OPTION`. | No |
| `BANKING_NO_PRECHECK_PATH` | Post-Banking review returned `NO_PRECHECK_PATH`. | No |
| `BANKING_PRECHECK_DECLINED` | The exact `SUBMIT_BANKING_PRECHECK` request was rejected. No precheck result exists. | No |
| `BANKING_NON_ACTIONABLE` | Post-precheck review returned `ALL_OPTIONS_NOT_ELIGIBLE`, `NO_PROVIDER_RECOMMENDATION`, `PRECHECK_SERVICE_UNAVAILABLE`, or `MIXED_NON_ACTIONABLE_RESULTS`. | No |
| `CONDITIONAL_DOCUMENT_READY` | Post-precheck review returned `CONDITIONAL_OPTIONS_AVAILABLE`, exactly one preparation request was followed, and its masked `DOCUMENT_RELEASE_PACKAGE` is ready. | Yes |

These paths are generic business outcomes. They do not depend on a contract ID, workbook row, mock
scenario, bank name, or array position.

The following states do **not** converge yet:

- a blocking `MissingDataRequest` is unresolved;
- a required approval is pending;
- post-precheck evidence requires a fresh governed retry;
- an explicit Banking policy/catalog mapping is unsupported;
- multiple Document requests would require an unimplemented selection;
- masking or evidence validation fails; or
- any upstream node is failed-safe.

In those cases Workflow remains at the owning upstream typed pause, or fails safely when package
assembly discovers a missing internal artifact for which no user-input resolver exists. It does
not emit a partial or apparently ready Internal Decision Package.

## Evidence contents

Every package contains exact, already validated snapshots and envelope references for the common
assessment chain:

- `EVALUATION_CASE`;
- `FINANCE_FACTS` and `FINANCE_ASSESSMENT`;
- `OPERATIONS_FACTS` and `OPERATIONS_ASSESSMENT`;
- `INITIAL_RISK_ASSESSMENT`;
- one or more applicable `APPROVAL_CHECKPOINTS` artifacts; and
- `DECISION_ROUTE_PLAN`.

Banking paths additionally carry the complete applicable discovery snapshot:

- `BANKING_DISCOVERY_REQUEST`;
- `BANKING_OPTION_MATRIX`;
- `BANKING_DISCOVERY_RESULT`;
- optional `BANKING_OPTION_ADVICE`;
- `BANKING_PRECHECK_READINESS`; and
- `DECISION_POST_BANKING_REVIEW`.

Paths that executed the simulated precheck also carry the exact
`BANKING_PRECHECK_SUBMISSION_PROPOSAL`, `BANKING_PRECHECK_RESULT_SET`, and
`DECISION_POST_PRECHECK_REVIEW`. The conditional Document path additionally carries the exact
`DOCUMENT_PREPARATION_REQUEST` and masked `DOCUMENT_RELEASE_PACKAGE`.

`BANKING_PRECHECK_DECLINED` carries one exact Governance reference for the rejected request. The
reference is bound to the request's action, subject artifact, policy artifact, checkpoints,
decision, actor, reason, and time. It records the prior rejection; it does not create or imply a new
approval request.

Each source reference preserves:

- artifact ID and type;
- version and input hash;
- validation status; and
- exact source evidence IDs.

The package-level evidence index is the ordered de-duplicated closure of those source-envelope
evidence IDs. Snapshot identities, Finance/Operations fact indexes, Risk fact references, Banking
bindings, provider results, and Document request/package bindings must all agree with the same
dataset, evaluation case, and contract.

## Readiness, identity, and persistence

`InternalDecisionPackageReadiness` currently has one value: `READY`. There is deliberately no
partially ready value. The component reports missing required sources as blocking requests and
emits no draft. In the automatic Master Workflow, such a gap is an internal dependency-integrity
failure rather than a Founder/staff input pause because no typed package-input endpoint can resolve
it. Inconsistent or contradictory lineage also fails safe.

`package_id` is deterministic over:

1. the assembly path;
2. the ordered exact source-artifact references; and
3. the stable business identity of the ordered Governance references, when applicable.

The full Governance reference remains in the payload for audit, but workflow-run IDs, approval
request IDs, and decision timestamps are deliberately excluded from package/artifact identity.
It therefore does not depend on assembly timestamps, worker-run IDs, or fresh random IDs.
Repeating assembly with unchanged business inputs reuses the logical artifact; changed explicit
upstream artifacts or decision substance produce a new input identity/version while earlier
envelopes remain auditable.

If two executions have the same stable business identity but different runtime-only Governance
provenance (for example, a different approval-request ID or decision timestamp), persistence fails
safe instead of overwriting or silently reusing the earlier audit payload. Reconciliation of such
legacy/duplicate decisions requires an explicit audited policy.

The context loader, domain invariants, and Evidence Validator form one fail-closed pipeline.
Evidence Validator always runs before persistence; together these layers reject, among other
things:

- cross-case or mismatched snapshots;
- a source envelope that was not already valid/valid-with-warnings;
- an assembly path that contradicts its route/review outcome;
- missing or unexpected Banking, precheck, Governance, or Document artifacts;
- incomplete evidence/source indexes;
- a changed or unstable package ID; or
- any ready package containing missing-data requests.

## Decision and Governance boundary

The package exposes four explicit false flags:

```text
recommendation_performed = false
selection_performed      = false
approval_requested       = false
external_action_performed = false
```

Therefore package readiness means only “the evidence dossier for the next internal Decision phase
is complete.” It does not mean:

- accept, negotiate, or reject the contract;
- a Banking option is selected or recommended;
- a simulated provider result is a real offer or bank approval;
- an existing approval authorizes another action;
- the Founder has approved a final proposal; or
- a document may be sent externally.

Approval checkpoint artifacts are evidence/context only. Assembly creates no `ActionCommand`, does
not call the Approval Gate, and does not pause merely because a checkpoint exists.

## Document and external-release boundary

Only `CONDITIONAL_DOCUMENT_READY` requires Document Skill. The included
`DOCUMENT_RELEASE_PACKAGE` is already minimized and policy-masked, and it still states that release
is unauthorized and no external send occurred. Direct, no-viable-option, no-precheck-path,
precheck-declined, and non-actionable paths must not invent or require a Document package.

The Internal Decision Package itself is also not an external-release proposal. A later explicit
Decision-policy phase must first produce an evidence-bound recommendation/proposal. If that later
proposal requests `SEND_DOCUMENT_TO_EXTERNAL_PARTNER`, Governance must evaluate the separate
protected action and the Founder must review it when policy requires. Only after authorization may
a future connector boundary be invoked. That Decision recommendation, protected-action flow, real
connector, provider receipt, retry, and delivery reconciliation are outside the current phase.

### Legacy external-release workflow states

The current workflow does not automatically reinterpret persisted legacy
`DOCUMENT_EXTERNAL_RELEASE_PROPOSAL`, `DOCUMENT_EXTERNAL_RELEASE_AUTHORIZED`, or
`DOCUMENT_EXTERNAL_RELEASE_DECLINED` runs as Internal Decision Package runs. It also does not
silently continue a legacy pending `SEND_DOCUMENT_TO_EXTERNAL_PARTNER` approval. Such a request is
expired when Governance reconciles it, after which the legacy run requires an explicit migration
or recovery policy. This is intentional: previously persisted authorization or send intent must
not be assigned new meaning without an audited migration. New runs never enter those legacy nodes
before internal Decision review.

## Inspection

Run the automatic workflow with `POST /api/cases/run`, poll its workflow status, and inspect the
validated artifact list for `INTERNAL_DECISION_PACKAGE`. A successfully converged run reports the
milestone `INTERNAL_DECISION_PACKAGE_READY`. Runs waiting for evidence/approval or stopped
failed-safe will not expose a ready package.

Related documents:

- [Automatic Master Workflow](MASTER_WORKFLOW.md)
- [Decision Initial Route](DECISION_INITIAL_ROUTE.md)
- [Decision Post-Banking Review](DECISION_POST_BANKING_REVIEW.md)
- [Decision Post-Precheck Review](DECISION_POST_PRECHECK_REVIEW.md)
- [Document Skill](DOCUMENT_SKILL.md)
- [System Architecture](SYSTEM_ARCHITECTURE.md)
