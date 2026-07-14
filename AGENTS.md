# OPC MIS Agentic AI — Repository Instructions

## Architecture

This project is a modular monolith for an OPC decision-support system.

Business components:
- Planner Skill
- Data & Finance Agent
- Operations Skill
- Risk & Compliance Agent
- Decision & Partner Agent
- Banking Integration Skill
- Document Skill

Technical components:
- Workflow Orchestrator
- Approval Control Plane
- Artifact and Evidence Store

## Technology

- Python 3.12
- Pydantic v2
- pandas and openpyxl
- pytest
- Ruff
- Type hints are required
- Core business logic must not depend on UI frameworks

## Non-negotiable rules

- Never modify the original TeamPack workbook.
- Never hard-code CON-004, CON-005, Excel row numbers, or demo outcomes.
- Read Excel sheets by names and headers, not sheet indexes.
- Preserve evidence lineage for every selected record and derived warning.
- Distinguish blocking missing data from non-blocking warnings.
- Do not invent missing values.
- Do not use an LLM for deterministic validation or calculations.
- Do not use Python eval() for rules.
- Do not expose secrets or API keys.
- Every completed task must include tests.
- Run Ruff and pytest before reporting completion.

## Agent boundaries

Planner Skill may:
- validate case intake;
- resolve contract, customer, orders, invoices and explicit references;
- assess data readiness;
- create EvaluationCase;
- create MissingDataRequest;
- create the initial run plan.

Planner Skill must not:
- calculate margin or funding gap;
- assess delivery risk;
- trigger risk rules;
- create Founder approval requests;
- select banking products;
- prepare external documents;
- create a Decision Card.

## Commands

```bash
ruff check .
pytest -q