"""Run Planner then Finance end-to-end for one TeamPack contract."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from opc_mis.config import AppSettings
from opc_mis.domain.enums import EvaluationScope, WorkflowStatus
from opc_mis.domain.finance_models import FinanceExecutionResult
from opc_mis.domain.planner_models import PlannerExecutionResult
from opc_mis.runtime import PlannerRuntime


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run OPC MIS Planner and Finance")
    parser.add_argument("--workbook", required=True, type=Path)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--dataset-id", default="MISTalent2026_OPC_AgenticAI_TeamPack_v3")
    return parser


async def _run(
    args: argparse.Namespace,
) -> tuple[PlannerExecutionResult, FinanceExecutionResult | None]:
    settings = AppSettings.from_environment()
    runtime = PlannerRuntime(
        workbook_path=args.workbook,
        dataset_id=args.dataset_id,
        settings=settings,
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
    if planner.status is not WorkflowStatus.COMPLETED or case is None:
        return planner, None
    finance = await runtime.finance_assessment(evaluation_case_id=case.evaluation_case_id)
    return planner, finance


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    planner, finance = asyncio.run(_run(args))
    print(
        json.dumps(
            {
                "planner": planner.model_dump(mode="json"),
                "finance": finance.model_dump(mode="json") if finance else None,
            },
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
    )
    if finance is None:
        return 2
    return 0 if finance.status is WorkflowStatus.COMPLETED else 3


if __name__ == "__main__":
    sys.exit(main())
