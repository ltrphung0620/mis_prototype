# Finance Agent

Finance is the first component inside `INITIAL_ASSESSMENT`. It consumes the validated
`EVALUATION_CASE` and `PLANNER_RESULT` artifacts; it never resolves entities by similar names or
natural-language descriptions.

## Processing flow

1. Load the exact EvaluationCase and PlannerResult artifact IDs supplied by workflow.
2. Confirm Planner readiness and resolve the contract, orders, and invoices by their explicit IDs.
3. Validate the numeric fields needed for deterministic calculations. An actual blocking gap
   returns `WAITING_FOR_INPUT` and `MissingDataRequest`; no Finance artifact is created.
4. Calculate profitability and coverage from the selected orders.
5. Aggregate invoices by their source status. Finance does not calculate overdue days without an
   explicit assessment date.
6. Calculate cashflow projection facts at `OPC_GLOBAL` scope because `09_CASHFLOW` has no
   `contract_id`.
7. Record neutral `FinanceObservation` objects and evidence limitations. These are inputs for the
   future Risk Agent, not activated risk findings.
8. Persist validated `FINANCE_FACTS`.
9. Ask OpenAI, when enabled, to compose text from sanitized verified facts. Structured output is
   checked for fact references, invented numbers, and downstream responsibilities. Expected API,
   refusal, parse, or validation errors use a deterministic fallback.
10. Persist `FINANCE_ASSESSMENT`, explicitly dependent on `FINANCE_FACTS`.

The authoritative output is `FINANCE_FACTS`. Narrative composition cannot change any fact.

## Swagger workflow

Start the server:

```powershell
.\.venv\Scripts\python.exe -m uvicorn opc_mis.app:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/docs`, then:

1. Call `POST /api/planner/evaluate` with a contract ID.
2. Copy `planner_result.evaluation_case.evaluation_case_id`.
3. Call `POST /api/cases/{evaluation_case_id}/finance-assessment`.
4. Optionally inspect all envelopes through `GET /api/cases/{evaluation_case_id}/artifacts`.

The prototype artifact repository is process-local. Restarting the server clears cases, so Planner
must be called again before Finance.

## OpenAI configuration

Copy the variable names from `.env.example` into your environment. Keep the key outside source
control.

```powershell
$env:OPENAI_ENABLED="true"
$env:OPENAI_API_KEY="your-key-from-a-secret-store"
$env:OPENAI_MODEL="gpt-5.6-terra"
```

If OpenAI is disabled or no key is configured, Finance still completes with
`narrative_source=DETERMINISTIC_FALLBACK`. Tests never call the live API.

## Responsibility boundary

Finance does not read `13_RISK_RULES`, assign risk level/score/severity, create approval signals or
requests, select banking products, prepare documents, execute actions, or create a Decision Card.
`08_BANK_TXN` has no structured contract/order/invoice relationship in the current TeamPack, so
Finance records `TRANSACTION_LINKAGE_UNAVAILABLE` and does not parse transaction descriptions.
