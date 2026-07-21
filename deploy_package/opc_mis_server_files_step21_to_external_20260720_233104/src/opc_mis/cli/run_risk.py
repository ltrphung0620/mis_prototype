"""Run Planner, Risk pre-scan, Finance, Operations, and resumed Risk for one contract."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path

from opc_mis.config import AppSettings
from opc_mis.domain.enums import EvaluationScope, WorkflowStatus
from opc_mis.runtime import PlannerRuntime


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("as-of-date must use YYYY-MM-DD") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the resumable OPC MIS Risk workflow")
    parser.add_argument("--workbook", required=True, type=Path)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--as-of-date", type=_iso_date)
    parser.add_argument("--dataset-id", default="MISTalent2026_OPC_AgenticAI_TeamPack_v3")
    return parser


async def _run(args: argparse.Namespace) -> dict[str, object]:
    runtime = PlannerRuntime(
        workbook_path=args.workbook,
        dataset_id=args.dataset_id,
        settings=AppSettings.from_environment(),
    )
    await runtime.startup()
    planner = await runtime.evaluate(
        contract_id=args.contract,
        evaluation_scope=(
            EvaluationScope.FINANCE,
            EvaluationScope.OPERATIONS,
            EvaluationScope.RISK,
        ),
    )
    case = planner.planner_result.evaluation_case if planner.planner_result else None
    output: dict[str, object] = {"planner": planner.model_dump(mode="json")}
    if planner.status is not WorkflowStatus.COMPLETED or case is None:
        return output
    first_risk = await runtime.risk_assessment(evaluation_case_id=case.evaluation_case_id)
    output["risk_pre_scan"] = first_risk.model_dump(mode="json")
    finance = await runtime.finance_assessment(evaluation_case_id=case.evaluation_case_id)
    output["finance_status"] = finance.status
    after_finance = await runtime.risk_status(evaluation_case_id=case.evaluation_case_id)
    output["risk_after_finance"] = after_finance.model_dump(mode="json")
    operations = await runtime.operations_assessment(
        evaluation_case_id=case.evaluation_case_id,
        as_of_date=args.as_of_date,
    )
    output["operations_status"] = operations.status
    final_risk = await runtime.risk_status(evaluation_case_id=case.evaluation_case_id)
    output["risk_final"] = final_risk.model_dump(mode="json")
    return output


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    output = asyncio.run(_run(args))
    print(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False))
    final = output.get("risk_final")
    return 0 if isinstance(final, dict) and final.get("status") == "COMPLETED" else 3


if __name__ == "__main__":
    sys.exit(main())
