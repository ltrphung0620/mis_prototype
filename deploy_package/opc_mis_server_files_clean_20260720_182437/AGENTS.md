# OPC MIS Agentic AI — Repository Instructions

## Architecture

This project is a Python modular monolith with:

- a persisted workflow state machine;
- an approval control plane;
- an artifact and evidence store;
- deterministic business components behind one async contract.

Layer direction:

```text
CLI / FastAPI
→ Workflow Orchestrator
→ Business Components and Governance
→ Domain and Ports
→ Infrastructure Adapters
```

Business components must implement:

```python
class BusinessComponent(Protocol):
    component_id: str

    async def execute(self, context: ExecutionContext) -> ComponentResult:
        ...
```

Business components return artifact drafts and signals. They must not persist artifacts,
change workflow state, approve actions, or call protected external adapters. The Orchestrator
validates artifact drafts, creates versioned envelopes, persists them, and owns pause/resume.

## Layer rules

- `domain/` contains Pydantic models, enums, protocols-independent value objects, and pure logic.
- `domain/` must not import pandas, openpyxl, FastAPI, SQLite, or the OpenAI SDK.
- `business/` may import `domain/` and `ports/`; it must not import concrete infrastructure.
- `governance/` contains approval, evidence-validation, and audit policy execution.
- `workflow/` owns node selection, dependencies, persistence order, pause/resume, and invalidation.
- `ports/` contains infrastructure protocols.
- `infrastructure/` contains Excel, persistence, OpenAI, and external API implementations.
- `cli/` and `api/` contain request/response translation only.
- Public APIs use server-configured dataset paths; clients must not submit arbitrary filesystem
  paths.

## Technology

- Python 3.12
- Pydantic v2
- pandas and openpyxl
- FastAPI and Uvicorn for the interface layer
- pytest
- Ruff
- Type hints are required
- Core business logic must not depend on UI frameworks

## Non-negotiable rules

- Never modify the original TeamPack workbook.
- Never hard-code CON-004, CON-005, Excel row numbers, or demo outcomes in production code.
- Read Excel sheets by names and headers, not sheet indexes.
- Preserve evidence lineage for every selected record and derived warning.
- Distinguish blocking missing data from non-blocking warnings.
- Do not invent missing values or implicit entity relationships.
- Do not use an LLM for deterministic validation or calculations.
- Do not use Python `eval()` for rules.
- Do not expose secrets or API keys.
- Evidence Validator must run before artifact persistence.
- Artifact identity must depend on business inputs and explicit upstream artifacts, not runtime IDs.
- Every completed task must include tests.
- Run Ruff and pytest before reporting completion.

## Planner boundary

Planner may:

- validate case intake;
- resolve contract, customer, orders, invoices, services, and explicit references;
- assess initial-assessment data readiness;
- create `EvaluationCase`, `PlannerResult`, warnings, and `MissingDataRequest` objects;
- create an initial plan containing Finance Assessment, Operations Assessment, and Initial Risk
  Scan only.

Planner must not:

- read or write Excel directly;
- apply or persist data patches;
- persist artifact envelopes;
- change workflow node state;
- calculate margin, cashflow gap, or funding gap;
- assess delivery risk or trigger risk rules;
- emit approval signals or action commands;
- select banking products;
- prepare documents;
- create a Decision Card.

Dataset Ingestion owns Excel schema validation, hashing, indexes, and in-memory overlay application.
The Orchestrator owns artifact validation, versioning, persistence, and workflow pause/resume.

## Commands

```bash
ruff check .
pytest -q
```
