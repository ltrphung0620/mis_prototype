# OPC MIS Agentic AI

This repository is a Python 3.12 modular monolith for the OPC decision-support system.
The implemented vertical slices cover Dataset Ingestion, Planner Intake, Finance Assessment, and
Operations Assessment using the shared async business-component contract and workflow-owned
artifact validation/persistence.

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
  --host 127.0.0.1 `
  --port 8000
```

Open `http://127.0.0.1:8000/docs` and use:

- `GET /api/contracts` to list exact contract IDs from the configured TeamPack;
- `POST /api/planner/evaluate` to run Planner Intake for one contract;
- `POST /api/cases/{evaluation_case_id}/finance-assessment` to run Finance after Planner;
- `POST /api/cases/{evaluation_case_id}/operations-assessment` to run Operations after Planner;
- `GET /api/cases/{evaluation_case_id}/artifacts` to inspect validated case artifacts;
- `GET /health` for a lightweight health check.

Example body:

```json
{
  "contract_id": "CON-004",
  "evaluation_scope": ["FINANCE", "OPERATIONS", "RISK"]
}
```

The server reads `data/input/MISTalent2026_OPC_AgenticAI_TeamPack_v3.xlsx` by default. Override it
with `OPC_MIS_TEAM_PACK_PATH` and optionally set `OPC_MIS_DATASET_ID`.

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
