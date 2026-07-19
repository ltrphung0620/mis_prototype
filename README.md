# OPC MIS Agentic AI

This repository is a Python 3.12 modular monolith for the OPC decision-support system.
The implemented vertical slices cover Dataset Ingestion, Planner Intake, Finance Assessment, and
Operations Assessment using the shared async business-component contract and workflow-owned
artifact validation/persistence. The initial Risk slice adds a TeamPack pre-scan that can pause
and resume when Finance and Operations facts arrive.
Governance now registers future approval checkpoints from the Risk pre-scan and provides a
deterministic protected-action gate with human approve/reject pause and resume.
The durable Master Workflow can now run the complete Initial Assessment, deterministic Decision
Initial Route, evidence-backed Decision-to-Banking handoff, Banking internal discovery, precheck
readiness, and Decision post-Banking review. When a required VND amount is absent, it pauses at
`DECISION_POST_BANKING_REVIEW`, accepts an immutable human input supplement, and automatically
resumes the same persisted run. A ready route then creates a reference-only
`BANKING_PRECHECK_SUBMISSION_PROPOSAL`, routes `SUBMIT_BANKING_PRECHECK` through Governance, and
pauses at `WAITING_FOR_APPROVAL` for the Founder. After approval, Workflow issues an ephemeral
permit for that exact proposal, invokes the server-configured simulated precheck adapter, validates
and persists `BANKING_PRECHECK_RESULT_SET`. Decision then preserves and classifies every exact
option/product result in `DECISION_POST_PRECHECK_REVIEW`. The current `API-002` mock returns one
full-coverage conditional result, so Decision creates a Document handoff. Workflow accepts it only
when exactly one viable request exists, prepares a minimized/masked internal dossier, pauses for a
missing signed-contract reference, and resumes to create `DOCUMENT_RELEASE_PACKAGE`. Workflow then
assembles a deterministic `INTERNAL_DECISION_PACKAGE` from the exact validated evidence. Direct,
no-viable-option, no-precheck-path, rejected-precheck, and non-actionable-precheck branches converge
on the same assembly phase without requiring Document preparation.

`BANKING_PRECHECK_READY` means only that the evidence required for a later external precheck is
ready. `BANKING_PRECHECK_SUBMISSION_AUTHORIZED` is an internal authorization transition, not the
terminal result. Phase B1 executes only a deterministic simulation: its results have
`SIMULATED_NON_BINDING` authority, do not represent a real bank response or approval, and do not
select or rank a bank product. The current `CONDITIONAL_PRECHECK` scenario is server-owned mock
data; TeamPack contains no actual VietinBank response. Its echoed requested amount and document
requirements are non-binding workflow-test assumptions. Partial coverage and multi-option
selection are deferred.

Document preparation is internal only. A complete `DOCUMENT_RELEASE_PACKAGE` remains an
unauthorized internal Decision input with `document_external_release_performed = false`.
`INTERNAL_DECISION_PACKAGE` is an evidence dossier, not a recommendation, Decision Card,
bank-option selection, approval request, or release authorization. The registered
`SEND_DOCUMENT_TO_EXTERNAL_PARTNER` checkpoint stays dormant. A later Decision policy must create
an evidence-bound recommendation/proposal for Founder review; only that later proposal may become
the subject of a protected external-release action. That recommendation/proposal and the external
connector are not implemented yet.
The release candidate preserves provider condition codes, aggregated evidence limitations and a
reference-only per-document manifest. An opaque document reference and caller-declared SHA-256
bind metadata only: the prototype does not verify repository existence, file contents, signatures
or legal validity.

The Finance slice consumes Planner artifacts, calculates verified finance facts, and optionally
uses OpenAI only to compose bounded narrative text.

## Development

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\pytest.exe -q
```

## Planner CLI

```powershell
python -m opc_mis.cli.run_planner `
  --workbook data/input/MISTalent2026_OPC_AgenticAI_TeamPack_v3.xlsx `
  --contract CON-004 `
  --scope FINANCE OPERATIONS RISK
```

The command ingests the read-only dataset, executes Planner through the Orchestrator, validates
artifact drafts, persists them in the process-local repository, and prints a JSON-safe
`PlannerExecutionResult`.

- Exit `0`: workflow `COMPLETED` (`COMPLETED` or `COMPLETED_WITH_WARNINGS` component result)
- Exit `2`: `WAITING_FOR_INPUT` (handled business/data gap)
- Exit `3`: `FAILED_SAFE` technical, ingestion, or evidence-validation failure
- Exit `4`: invalid CLI request

The official TeamPack is always read-only. Dataset Ingestion applies data patches to an isolated
snapshot. Planner receives that snapshot through `DatasetPort`; it does not read Excel, persist
artifacts, or change workflow state.

## Swagger API

```powershell
.\.venv\Scripts\python.exe -m uvicorn opc_mis.app:app `
  --env-file .env `
  --host 127.0.0.1 `
  --port 8000
```

Open `http://127.0.0.1:8000/docs` and use:

This prototype API and artifact-inspection surface does not implement authentication or RBAC. Run
it only in a trusted local environment; labels such as `AUTHORIZED_STAFF` and `FOUNDER` are workflow
roles, not authenticated principals.

- `GET /api/contracts` to list exact contract IDs from the configured TeamPack;
- `POST /api/cases/run` to run through Decision Initial Route, Banking readiness, proposal creation,
  the automatic Governance pauses, approved simulated precheck, conditional internal Document
  preparation when applicable, and deterministic Internal Decision Package assembly;
- `GET /api/workflows/{workflow_run_id}` to poll durable node and artifact status;
- `GET /api/workflows/{workflow_run_id}/events` to poll ordered workflow events;
- `POST /api/workflows/{workflow_run_id}/resume` for a genuine blocking wait/failure whose external
  condition has already changed; a Banking amount supplement resumes automatically;
- `POST /api/planner/evaluate` to run Planner Intake for one contract;
- `POST /api/cases/{evaluation_case_id}/finance-assessment` to run Finance after Planner;
- `POST /api/cases/{evaluation_case_id}/operations-assessment` to run Operations after Planner;
- `POST /api/cases/{evaluation_case_id}/initial-risk-assessment` to pre-scan or resume Risk;
- `GET /api/cases/{evaluation_case_id}/risk-status` to inspect the current Risk checkpoint;
- `POST /api/cases/{evaluation_case_id}/decision-route` to run deterministic Initial Route;
- `POST /api/cases/{evaluation_case_id}/banking-discovery-request` to create Decision's internal,
  evidence-backed Banking request when the route requires it;
- `POST /api/cases/{evaluation_case_id}/banking/internal-discovery` to build the deterministic
  mock-catalog option matrix without executing a bank precheck;
- `POST /api/cases/{evaluation_case_id}/banking/input-supplements` to persist a validated VND amount
  for the exact pending request and auto-resume its Master Workflow;
- `POST /api/cases/{evaluation_case_id}/documents/evidence-supplements` to resolve one exact
  Document request using caller-declared opaque reference metadata and a content SHA-256, then
  auto-resume; this prototype does not verify that metadata against a document repository;
- `GET /api/cases/{evaluation_case_id}/approval-checkpoints` to inspect future approval gates;
- `POST /api/cases/{evaluation_case_id}/protected-actions/{action_type}` to evaluate a proposed
  protected action; include the Master `workflow_run_id` to pause/resume that same durable run.
  `SUBMIT_BANKING_PRECHECK` is reserved for its automatic validated proposal flow.
  `SEND_DOCUMENT_TO_EXTERNAL_PARTNER` cannot be injected here and remains dormant until a future
  validated Decision proposal exists;
- `GET /api/cases/{evaluation_case_id}/approval-requests` to inspect pending/resolved requests;
- `POST /api/approval-requests/{request_id}/decision` to approve or reject a paused action;
- `GET /api/cases/{evaluation_case_id}/artifacts` to inspect validated case artifacts;
- `GET /health` for a lightweight health check.

Example body:

```json
{
  "contract_id": "CON-004",
  "evaluation_scope": ["FINANCE", "OPERATIONS", "RISK"]
}
```

For a workflow paused at `DECISION_POST_BANKING_REVIEW`, submit the exact pending request ID. The
amount below is only an example of explicit user input; it is not a system default or an inferred
CON-004 value:

```json
{
  "workflow_run_id": "CWF-...",
  "missing_request_id": "MDR-...",
  "requested_amount": 350000000,
  "requested_amount_currency": "VND",
  "evidence_note": "Amount confirmed for the Banking precheck readiness review."
}
```

The route returns `202`, persists `BANKING_INPUT_SUPPLEMENT`, and queues the same workflow. It never
rewrites the original TeamPack or the original `BANKING_DISCOVERY_REQUEST`. If an option becomes
READY, poll the workflow until it reaches `WAITING_FOR_APPROVAL`, read the proposal through the
artifact endpoint, then approve or reject its pending request through the Governance decision
endpoint. Approval resumes the workflow into the configured simulation and never calls a real bank.
For the current `API-002` scenario, poll until the workflow pauses at `DOCUMENT_PREPARATION`, then
read the exact pending signed-contract request and submit reference metadata:

```json
{
  "workflow_run_id": "CWF-...",
  "missing_request_id": "MDR-...",
  "document_reference_id": "DOCREF-550e8400-e29b-41d4-a716-446655440000",
  "content_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "document_type": "SIGNED_CONTRACT",
  "evidence_note": "REQUESTED_DOCUMENT_REFERENCE_SUPPLIED"
}
```

`evidence_note` is a controlled enum, not free text. The server does not accept raw bytes, paths,
URLs, arbitrary reference text, or client-controlled `provided_by`. The `DOCREF-<UUIDv4>` value is
still caller-declared metadata in this prototype and is not repository-verified. After
auto-resume, inspect `DOCUMENT_RELEASE_PACKAGE` as the masked Document input and
`INTERNAL_DECISION_PACKAGE` as the converged evidence dossier. No Founder request is created merely
because either package is ready, and no external release is authorized or performed.

The server reads `data/input/MISTalent2026_OPC_AgenticAI_TeamPack_v3.xlsx` by default. Override it
with `OPC_MIS_TEAM_PACK_PATH` and optionally set `OPC_MIS_DATASET_ID`.
Durable API state uses `data/runtime/opc_mis.db` by default; override it with
`OPC_MIS_DATABASE_PATH`.
Banking mappings are server-owned at `config/banking/catalog_mappings.json`; override the server
configuration with `BANKING_CATALOG_POLICY_PATH`. Simulated precheck scenarios are server-owned at
`config/banking/precheck_simulation_scenarios.json`; override them with
`BANKING_PRECHECK_SIMULATION_POLICY_PATH`. `BANKING_PROMPT_VERSION` and
`BANKING_PROMPT_PATH` configure optional advisory prose. OpenAI is not called unless the
deterministic matrix contains at least two candidates, and it is never used to produce or interpret
the Phase B1 precheck result.

Document masking policy is server-owned at `config/data_protection/masking_policy.json`; override
it with `MASKING_POLICY_PATH`. Configure `OPC_MIS_MASKING_HMAC_KEY_BASE64` with Base64-encoded secret
material that decodes to at least 32 bytes. The secret is never persisted or logged. If it is
missing, upstream workflow can still run, but Document masking fails closed and no release package
is created. Sheet `21_MASKING_EXAMPLES` is illustrative only and does not select executable policy.
Masking also fails closed when a declared `required_fields` entry is absent or the exact recipient
is outside the global allowlist. Each included field must additionally allow that same exact
recipient; wildcard recipient rules are forbidden. Declaring a field required never bypasses these
recipient/purpose checks.

## Finance CLI

```powershell
$env:OPENAI_ENABLED="false"
python -m opc_mis.cli.run_finance `
  --workbook data/input/MISTalent2026_OPC_AgenticAI_TeamPack_v3.xlsx `
  --contract CON-004
```

Finance calculates deterministic facts and emits neutral observations only. OpenAI is optional and
restricted to structured narrative composition. See [Finance Agent](docs/FINANCE_AGENT.md) for the
workflow, configuration, evidence limitations, and responsibility boundary.

## Operations CLI

```powershell
python -m opc_mis.cli.run_operations `
  --workbook data/input/MISTalent2026_OPC_AgenticAI_TeamPack_v3.xlsx `
  --contract CON-004 `
  --as-of-date 2026-07-16
```

Operations produces deterministic planned-schedule facts, neutral observations, and explicit
evidence limitations. It does not execute Risk or Approval logic. See
[Operations Skill](docs/OPERATIONS_SKILL.md).

## Risk CLI

```powershell
$env:OPENAI_ENABLED="false"
python -m opc_mis.cli.run_risk `
  --workbook data/input/MISTalent2026_OPC_AgenticAI_TeamPack_v3.xlsx `
  --contract CON-004 `
  --as-of-date 2026-07-16
```

The CLI deliberately starts Risk before Finance and Operations. It prints the initial wait state,
the checkpoint after Finance, and the finalized assessment after Operations. See
[Risk Agent](docs/RISK_AGENT.md).

See [Automatic Master Workflow](docs/MASTER_WORKFLOW.md) for persistence, recovery, idempotency,
and the one-call API flow. See [Decision Initial Route](docs/DECISION_INITIAL_ROUTE.md) for routing
inputs, outputs, evidence rules, and boundaries.
See [Decision Banking Handoff](docs/DECISION_BANKING_HANDOFF.md) for the internal request contract.
See [Banking Skill and Precheck Readiness](docs/BANKING_SKILL.md) for mappings, immutable supplement
handling, the governed submission proposal, simulated non-binding results, mock API metadata, and
OpenAI boundaries. See
[Decision Post-Banking Review](docs/DECISION_POST_BANKING_REVIEW.md) for the deterministic route and
the `BANKING_PRECHECK_READY` handoff boundary. See [Document Skill](docs/DOCUMENT_SKILL.md) for
conditional handoff, missing-document resume, data masking, and the internal Decision handoff. See
[Internal Decision Package](docs/INTERNAL_DECISION_PACKAGE.md) for convergence paths, evidence
lineage, deterministic identity, readiness behavior, and its strict no-decision/no-release
boundary.
