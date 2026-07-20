# Decision, final approval, and external-release readiness

## Implemented scope

The Master Workflow now continues beyond `FINAL_RISK_READY`. It creates a deterministic Decision
scenario, allows OpenAI to compose only a bounded proposal, applies deterministic guards, persists
an evidence-validated `DECISION_CARD`, and pauses for the Founder's decision on that exact Card.
After an affirmative decision, Workflow creates a deterministic `POST_DECISION_UPDATE` and routes
the approved recommendation.

An `ACCEPT` route that includes an exact masked `DOCUMENT_RELEASE_PACKAGE` has one additional,
separate control plane. Decision creates an `EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL`; Governance
must authorize `SEND_DOCUMENT_TO_EXTERNAL_PARTNER` for that exact proposal before Workflow may
reach `READY_FOR_EXTERNAL_SUBMISSION`.

`READY_FOR_EXTERNAL_SUBMISSION` is the implemented terminal safety boundary. It does not call an
adapter, transmit a document, or create a submission/provider receipt.

## Exact workflow graph

```text
FINAL_RISK_READY
  -> DECISION_CARD_COMPOSITION
     -> build deterministic DecisionScenarioPacket
        from exact INTERNAL_DECISION_PACKAGE + FINAL_RISK_ASSESSMENT
     -> bounded OpenAI composition (or deterministic safe fallback)
     -> deterministic composition/domain guard
     -> Evidence Validator
     -> persist AI_DECISION_ANALYSIS
     -> rebuild the deterministic packet and replay the guard
     -> assemble DECISION_CARD
     -> Evidence Validator
     -> persist DECISION_CARD
  -> DECISION_CARD_READY
     -> recommendation = NOT_EVALUABLE
        -> DECISION_NOT_EVALUABLE
        -> COMPLETED at DECISION_CARD_READY
        -> no approval request and no PostDecision route
     -> approvable recommendation
        -> register exact Founder checkpoint for this Decision Card
        -> FINAL_DECISION_APPROVAL / WAITING_FOR_APPROVAL
           -> reject
              -> FINAL_DECISION_REJECTED
              -> no POST_DECISION_UPDATE
           -> approve exact DECISION_CARD
              -> POST_DECISION_UPDATE
                 -> NEGOTIATE_CONDITIONS_TO_ACCEPT
                    -> NEGOTIATION_IN_PROGRESS
                 -> DO_NOT_ACCEPT
                    -> FINAL_DECISION_NOT_ACCEPTED
                 -> ACCEPT without a Document release package
                    -> FINAL_DECISION_ACCEPTED
                 -> ACCEPT with an exact Document release package
                    -> EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL
                    -> Evidence Validator
                    -> persist exact proposal
                    -> separate CHECK SEND_DOCUMENT_TO_EXTERNAL_PARTNER
                       -> WAITING_FOR_APPROVAL
                          -> reject
                             -> EXTERNAL_DOCUMENT_SUBMISSION_DECLINED
                          -> approve exact proposal
                             -> build non-persisted readiness proof
                             -> READY_FOR_EXTERNAL_SUBMISSION
                                adapter_invoked = false
                                external_submission_performed = false
                                submission_receipt_created = false
```

The approved recommendation maps deterministically to the post-decision route:

| Approved Card recommendation | `PostDecisionOutcome` | Workflow destination |
|---|---|---|
| `ACCEPT` | `FINAL_DECISION_ACCEPTED` | `FINAL_DECISION_ACCEPTED`, or the separate external-proposal path when the Card contains a release package |
| `NEGOTIATE_CONDITIONS_TO_ACCEPT` | `NEGOTIATION_AUTHORIZED` | `NEGOTIATION_IN_PROGRESS` |
| `DO_NOT_ACCEPT` | `CASE_CLOSED_NO_EXTERNAL_ACTION` | `FINAL_DECISION_NOT_ACCEPTED` |
| `NOT_EVALUABLE` | none | Stops safely at `DECISION_CARD_READY`; it cannot become an approved final decision |

## Deterministic scenario and bounded OpenAI role

`DecisionScenarioPacket` is a deterministic in-memory contract, not a separately persisted
artifact. It is rebuilt from one validated `FINAL_RISK_ASSESSMENT` and the exact validated
`INTERNAL_DECISION_PACKAGE` referenced by that assessment. The packet pins both upstream artifacts
by `artifact_id`, `artifact_type`, `version`, and `input_hash` and contains only deterministic
facts and choices:

- contract-attributable Finance and Operations metrics;
- deterministic calculations and their operands/evidence;
- deterministic gross-margin calculations and mutually exclusive
  `negotiation_strategy_candidates`;
- real configured Banking candidates and allowed option combinations;
- residual findings, required controls, limitations, and major-exception status;
- an optional reference-only masked Document release snapshot;
- allowed recommendation, reason, condition, target, and evidence candidates; and
- an allowlist of numeric display values.

OpenAI may compose prose and select only from these supplied choices. It may not calculate values,
invent a reason/condition/reference, add unrelated evidence, choose an unconfigured option
combination, decide approval, or execute an action. Numeric prose is checked against the supplied
display allowlist. The deterministic domain guard then requires exact candidate equality, exact
packet input hash, valid evidence lineage, recommendation eligibility, option-combination policy,
and recommendation-specific condition rules.

Before validation, model-selected reason/condition codes are hydrated back to the exact
deterministic candidates. For `NEGOTIATE_CONDITIONS_TO_ACCEPT`, every mandatory `OPEN` or
`NOT_EVALUABLE` condition is attached by policy rather than relying on the model to reproduce it.

Only an `OPENAI` composition may produce the three approvable business recommendations: `ACCEPT`,
`NEGOTIATE_CONDITIONS_TO_ACCEPT` (displayed as `ACCEPT_WITH_CONDITIONS`), or `DO_NOT_ACCEPT`
(displayed as `REJECT`). If OpenAI is unavailable, times out, or returns an invalid proposal, the
deterministic fallback returns only `NOT_EVALUABLE` with a stable, non-sensitive diagnostic code.
It cannot impersonate an AI recommendation.

### Gross-margin negotiation strategies

When the validated Finance chain contains explicit linked-order revenue, explicit linked-order
estimated cost, a current linked-order gross margin, and an OPC target margin, and the current
margin is below target, Decision precomputes bounded negotiation alternatives.

The deterministic engine, not OpenAI, calculates:

1. `INCREASE_CUSTOMER_PRICE`: the minimum linked-order revenue increase required while holding
   evidenced estimated cost constant.
2. `REDUCE_EVIDENCED_COST_AT_FIXED_REVENUE`: the minimum evidenced cost reduction required while
   holding linked-order revenue constant.

These candidates are alternatives, not cumulative requirements. If OpenAI proposes
`NEGOTIATE_CONDITIONS_TO_ACCEPT` with `MEET_OPC_GROSS_MARGIN_TARGET`, it must select exactly one
supplied `strategy_id`. It may not change the amount, combine both candidates, invent another
lever, or claim that the target has already been met. The selected `strategy_id` is the model's
bounded contribution; no separate model-authored
margin rationale is persisted. After selection, the canonical guard discards the model's free-form
margin/status summary and renders the Founder-facing instruction deterministically from the exact
selected strategy snapshot.
The packet validator binds the condition target, current-margin Finance fact, policy-target Finance
fact, revenue/cost operands, formulas, evidence, and strategy values so a re-hashed but inconsistent
packet fails closed.
The deterministic guard rejects a missing, unknown, unrelated, or multiple strategy selection.

Customer agreement and updated commercial or cost evidence are still required. Finance and Final
Risk must run again before the condition can be treated as satisfied.

Missing or invalid margin inputs fail closed. If either the current linked-order margin or the OPC
target is absent, has the wrong role/unit, or is not a plausible ratio, Decision creates
`OBTAIN_GROSS_MARGIN_BENCHMARKS` with `NOT_EVALUABLE`. If both benchmarks are valid and show a gap
but attributable linked-order revenue/cost cannot support exact calculation, it creates
`OBTAIN_MARGIN_STRATEGY_INPUTS` with `NOT_EVALUABLE`. Either evidence-repair condition removes
`ACCEPT` and `NEGOTIATE_CONDITIONS_TO_ACCEPT` from the deterministic eligibility set; OpenAI cannot
select a commercial strategy until corrected evidence has passed Finance again.

#### CON-004 example

The current explicitly linked-order scope has:

| Item | Value |
|---|---:|
| Linked-order revenue | VND 3,100,000,000 |
| Linked-order estimated cost | VND 2,356,000,000 |
| Current linked-order gross margin | 24% |
| OPC target gross margin | 28% |

The deterministic alternatives are:

| Strategy | Deterministic calculation | Required condition |
|---|---|---:|
| Increase customer price | `ceil(2,356,000,000 / (1 - 0.28)) - 3,100,000,000` | Increase linked-order revenue by at least VND 172,222,223, producing revenue of VND 3,272,222,223 while cost remains unchanged |
| Reduce evidenced cost | `2,356,000,000 - floor(3,100,000,000 x (1 - 0.28))` | Reduce evidenced linked-order cost by at least VND 124,000,000, producing maximum cost of VND 2,232,000,000 while revenue remains unchanged |

These figures apply only to the VND 3,100,000,000 explicitly linked-order scope. CON-004 also has
VND 1,100,000,000 of contract value not covered by explicitly linked orders. The system must not
attribute that uncovered amount to either strategy or claim that the whole-contract margin becomes
28%.

## `NOT_EVALUABLE` is a terminal safety result

`NOT_EVALUABLE` always remains available in the deterministic packet. It is not an alias for
acceptance, rejection, or absence of risk. The guarded result must have:

```text
recommendation       = NOT_EVALUABLE
confidence           = NOT_EVALUABLE
selected_option_ids  = []
conditions           = []
```

Workflow may still persist the guarded analysis and detailed Card so the evidence limitations are
auditable. It then records `DECISION_NOT_EVALUABLE` and completes at `DECISION_CARD_READY`. It does
not register/request final-decision approval, create `POST_DECISION_UPDATE`, activate the Document
checkpoint, or reach external readiness.

## Exact artifact and approval binding

Every persisted artifact draft passes `EvidenceValidator` before the Orchestrator creates or
reuses an envelope. Reuse requires the same payload, ordered evidence, exact direct inputs, valid
validation status, and deterministic input hash; an ambiguous or conflicting match fails safe.

| Stage | Exact binding |
|---|---|
| `AI_DECISION_ANALYSIS` | Directly consumes the exact Final Risk artifact. Its payload also pins the exact Final Risk and Internal Decision Package references. Envelope input identity includes `packet_id`, model source/name, prompt version, composer input hash, and server configuration hash; the typed `analysis_id` includes the guarded output, exact selected negotiation-strategy IDs, and immutable strategy snapshots. A different payload under the same envelope input identity fails safe rather than silently replacing the prior analysis. |
| `DECISION_CARD` | Directly consumes the exact `AI_DECISION_ANALYSIS`. Before assembly, the packet is rebuilt from the pinned upstream artifacts and the deterministic guard is replayed. The Card pins the analysis, Final Risk, and Internal Decision Package triplets, preserves the packet evidence index, and carries the same exact strategy IDs and snapshots without recalculation. |
| Final-decision checkpoint | Governance extends the current `APPROVAL_CHECKPOINTS` registry with `CONFIRM_FINAL_CONTRACT_DECISION`, condition `final_decision_confirmation_requested == true`, approver role `FOUNDER`, server policy ID/version/hash, and the exact Card artifact ID/version/input hash. Registration alone does not approve or pause. |
| Final-decision `ApprovalRequest` | The request subject is the current `DECISION_CARD` ID/version/input hash. It also records the exact checkpoint IDs, `APPROVAL_CHECKPOINTS` artifact ID/version/input hash, protected action, selected negotiation-strategy IDs, and exact deterministic action payload derived from the Card. A superseded subject or policy cannot authorize routing. |
| `POST_DECISION_UPDATE` | Directly consumes the approved Card, embeds the affirmative approval reference and exact `approved_negotiation_strategy_ids`, and records the deterministic contract disposition: `SIGNED` for `ACCEPT`, `PENDING_NEGOTIATION` for negotiate, and `NOT_SIGNED` for do-not-accept. The approval subject must match the Card triplet, action, case, run, and exact action payload derived from the Card. Stable artifact identity keeps the approval's business substance while excluding request/run IDs and timestamps. |
| `EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL` | Exists only for approved `ACCEPT`/`SIGNED` plus an exact package. It resolves `SIGNED_CONTRACT_PENDING_FOUNDER_ACCEPTANCE`, records `signed_contract_completed = true`, and pins the post-decision update, Decision Card, package, masking IDs, conditions, and evidence union. A `NOT_SIGNED` outcome closes without an external proposal. |
| External-release `ApprovalRequest` | This is a new request for `SEND_DOCUMENT_TO_EXTERNAL_PARTNER`, not reuse of final-decision or Banking-precheck approval. Its subject is the current proposal ID/version/input hash, and it records the exact action-specific checkpoint IDs and current checkpoint-registry artifact triplet plus the complete release action payload. |
| `READY_FOR_EXTERNAL_SUBMISSION` | An execution-only typed proof, not a persisted artifact or receipt. It pins the exact proposal triplet, proposal ID, Document release snapshot, evidence, and affirmative external-release authorization. |

The external-release checkpoint may have been registered earlier by Initial Risk for the protected
action. That checkpoint remains dormant while only a Document package, Internal Decision Package,
Final Risk assessment, Decision analysis, or Decision Card exists. Exact proposal scoping is added
by the separate external-release approval request; the final-decision request never authorizes a
send.

## Responsibility separation

| Owner | Owns | Must not own |
|---|---|---|
| Decision | Build the deterministic scenario, call the bounded composer through its port, guard the proposal, assemble the Card, and deterministically describe the post-decision route/proposal draft. | Persist artifacts, change workflow state, approve the Card, authorize release, call an external adapter, or fabricate a receipt. |
| Banking | Preserve configured options and simulated non-binding precheck evidence consumed by Decision. | Make the final contract decision, turn a simulated result into bank authority, approve a Document release, or send documents. |
| Document | Build the minimized/masked internal `DOCUMENT_RELEASE_PACKAGE`, manifest, limitations, and exact reference-only handoff. | Select a Banking option, make the final decision, activate Governance, or transmit the package. |
| Governance | Register/evaluate checkpoints, persist exact approval requests and human decisions, enforce current subject/policy identity, and honor rejection/expiry. | Compose the business recommendation, alter Decision or Document artifacts, or perform the external send. |
| Workflow Orchestrator | Select nodes, resolve exact dependencies, invoke `EvidenceValidator`, version/persist artifacts, own pause/resume/recovery, submit protected-action commands, and route approved outcomes. | Recalculate business facts, reinterpret AI prose, approve on behalf of the Founder, or claim connector effects that did not happen. |

## Safe external boundary

The final implemented state proves only that the exact masked package and exact proposal have an
affirmative, current Governance authorization. The readiness object and workflow event explicitly
keep:

```text
adapter_invoked               = false
external_submission_performed = false
submission_receipt_created     = false
```

No external document connector, repository-to-payload resolver, provider receipt, delivery
reconciliation, retry, or actual send is implemented. A future connector phase must begin after
this boundary and must not reinterpret `READY_FOR_EXTERNAL_SUBMISSION` as evidence of delivery.

Related documents:

- [Automatic Master Workflow](MASTER_WORKFLOW.md)
- [System Architecture](SYSTEM_ARCHITECTURE.md)
- [Final Risk Check](FINAL_RISK_CHECK.md)
- [Document Skill](DOCUMENT_SKILL.md)
- [Internal Decision Package](INTERNAL_DECISION_PACKAGE.md)
