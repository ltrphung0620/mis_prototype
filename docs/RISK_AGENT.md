# Initial Risk Agent

## Responsibility

Risk is the first component that may interpret Finance and Operations facts as risk. It reads the
actual TeamPack rules and alerts, evaluates only typed conditions, assigns case risk severity, and
identifies human-confirmation points. It does not recalculate upstream facts.

Risk may emit an evidence-bound `ApprovalSignal` checkpoint candidate. Governance converts valid
candidates into `APPROVAL_CHECKPOINTS`; Risk never creates an `ApprovalRequest`, makes an approval
decision, executes an action, selects a bank product, prepares a document, or creates a Decision
Card.

## Parallel workflow and pause/resume

Planner keeps all three initial tasks in `parallel_initial_tasks`:

```text
Finance Assessment
Operations Assessment
Initial Risk Scan
```

Risk executes in two phases:

```text
INITIAL_RISK_PRE_SCAN
  -> read named TeamPack sheets
  -> resolve exact case alerts and OPC-global context
  -> persist RISK_PRE_SCAN
  -> Governance validates and persists APPROVAL_CHECKPOINTS
  -> business component returns COMPLETED
INITIAL_RISK_FINALIZATION [WorkflowNodeStatus.WAITING_FOR_DEPENDENCIES]
  -> Workflow waits for FINANCE_FACTS and OPERATIONS_FACTS
  -> Workflow invokes Risk with mode FINALIZE
  -> evaluate typed rules
  -> persist RISK_RULE_EVALUATION and INITIAL_RISK_ASSESSMENT
```

The HTTP request does not sleep or hold a worker while waiting. The Master Workflow persists
`INITIAL_RISK_FINALIZATION` with `WorkflowNodeStatus.WAITING_FOR_DEPENDENCIES`. Completing Finance
and Operations makes that node eligible to run. Risk does not return a dependency-waiting
`ComponentStatus`, select the next phase, or own pause/resume. The standalone Risk endpoint keeps a
backward-compatible `RiskRunState` artifact index, but phase selection still happens in the
application/workflow layer. Duplicate notifications are idempotent.

The configured runtime uses SQLite-backed workflow and Risk state repositories; in-memory adapters
remain available for isolated tests. Neither adapter changes Risk business code.

## Source sheets

Risk uses sheet names and actual headers, never numeric Excel indexes:

- `13_RISK_RULES`
- `14_ALERTS`
- `08_BANK_TXN`
- `20_DATA_CLASS`

The original workbook remains read-only.

`related_record` is split only on commas. A token must equal a case entity ID or a known global
record ID. Names, descriptions, dates, and substrings are never used to infer a relationship.

## Safe rule evaluation

The parser accepts one comparison:

```text
field >= value
field <= value
field > value
field < value
field = value
```

It rejects compound expressions, functions, and arbitrary code. Python `eval()` is never used.

Current initial-scan mappings are:

| Source field | Scope | Treatment |
|---|---|---|
| `transaction_risk_score` | OPC global | Evaluated from bank transactions; never assigned to a contract |
| `gross_margin` | Case | Evaluated from `CONTRACT_GROSS_MARGIN_SOURCE` in `FinanceFacts` |
| `closing_cash` | OPC global | Not evaluable because the source dataset exposes `projected_closing_cash`; no silent alias |
| `delivery_delay_days` | Case | Not evaluable because Operations does not produce this exact fact |
| document release and requested amount | Event-specific | Registered as future approval checkpoints; they do not pause the initial scan |
| confidence events | Event-specific | Not applicable during initial contract scan |

`owner_agent` in the workbook is preserved as source metadata. Under the current architecture only
Risk activates risk rules; Finance and Operations provide facts and neutral observations.

## Case severity

`overall_risk_level` is the maximum severity across:

- triggered `CASE_SPECIFIC` rules; and
- alerts with an exact relationship to a case entity.

OPC-global signals are returned in `global_context_signals` and excluded from case severity. The
system does not invent an overall numeric score. A source alert's `risk_score` is preserved as
`source_risk_score` only. With no case-specific signal, the level is `NO_CASE_SIGNAL`, not `LOW`.

## Artifacts and evidence

- `RISK_PRE_SCAN`: source rules, resolved alerts, global signals, dependency map, and source counts.
- `APPROVAL_CHECKPOINTS`: registered event, protected action, typed condition, source rule, and
  evidence lineage. RR-001 remains OPC-global and is not attached to a contract checkpoint.
- `RISK_RULE_EVALUATION`: status, operator, threshold, actual value, source fact IDs, explanation,
  and evidence IDs for every rule.
- `INITIAL_RISK_ASSESSMENT`: overall level, findings, case alerts, separated global context,
  human-confirmation points, limitations, and exact Finance/Operations artifact IDs.

Every artifact draft passes `EvidenceValidator` before workflow persistence. Artifact identity uses
the case, source snapshot, explicit upstream artifact IDs, typed outputs, and evidence IDs. It does
not depend on runtime timestamps.

## Swagger test sequence

1. `POST /api/planner/evaluate` and copy `evaluation_case_id`.
2. `POST /api/cases/{id}/initial-risk-assessment`.
3. Confirm workflow `WAITING_FOR_DEPENDENCIES`, component `COMPLETED`, and both pending facts.
4. Run `POST /api/cases/{id}/finance-assessment`.
5. `GET /api/cases/{id}/risk-status` now waits only for Operations.
6. Run `POST /api/cases/{id}/operations-assessment`.
7. `GET /api/cases/{id}/risk-status` returns the final assessment.
8. Use `GET /api/cases/{id}/artifacts` for full envelopes and evidence records.

## Protected-action approval flow

Checkpoint registration is non-blocking. A workflow pauses only when a later component proposes a
matching protected action and the deterministic condition evaluates to true:

```text
Risk ApprovalSignal
  -> Governance ApprovalCheckpoint
  -> protected ActionCommand arrives
  -> ApprovalGate evaluates the exact typed payload field
  -> condition false: AUTHORIZED
  -> value missing/invalid: WAITING_FOR_INPUT
  -> condition true: ApprovalRequest + WAITING_FOR_APPROVAL
  -> APPROVE: protected action authorized
  -> REJECT: protected action blocked
```

Implemented mappings are source-field based, not contract-ID or rule-row based:

| Source field | Trigger event | Protected action |
|---|---|---|
| `document_sent_to_partner` | `DOCUMENT_EXTERNAL_RELEASE_REQUESTED` | `SEND_DOCUMENT_TO_EXTERNAL_PARTNER` |
| `requested_amount` | `LARGE_FINANCIAL_DECISION_REQUESTED` | `COMMIT_LARGE_FINANCIAL_DECISION` |

The document-send checkpoint remains registered but dormant when Document merely creates
`DOCUMENT_RELEASE_PACKAGE`. Package readiness is an internal Decision handoff, not the
`DOCUMENT_EXTERNAL_RELEASE_REQUESTED` event. The implemented downstream Decision flow may supply
the matching protected action only after an exact `ACCEPT` Card is approved and an
`EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL` is validated. That later request is separate from the
final-decision approval and still stops before any external connector call.

Swagger exposes checkpoint inspection, protected-action evaluation, approval request listing, and
human approve/reject endpoints under the `Governance` tag. Approval requests bind the subject
artifact ID, version, and input hash. The current prototype authorizes or blocks the command but
does not call a Document, Decision, Banking, or other external adapter.

Swagger responses use compact artifact references, so domain payloads are not repeated.

## Optional OpenAI narrative prompt

The bounded founder-facing prompt is stored at
`config/prompts/risk_narrative.md`. It separates emitted approval signals, scanned approval
conditions, and non-approval human-confirmation points. The prompt is not part of rule activation;
the deterministic Risk output remains authoritative.
