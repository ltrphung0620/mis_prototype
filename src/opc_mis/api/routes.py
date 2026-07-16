"""Planner and dataset discovery HTTP routes."""

from fastapi import APIRouter, HTTPException, Request, status

from opc_mis.api.schemas import (
    ContractCatalogResponse,
    OperationsAssessmentRequest,
    PlannerEvaluationRequest,
)
from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.finance_models import FinanceExecutionResult
from opc_mis.domain.operations_models import OperationsExecutionResult
from opc_mis.domain.planner_models import PlannerExecutionResult
from opc_mis.runtime import (
    FinanceCaseNotFoundError,
    OperationsCaseNotFoundError,
    PlannerRuntime,
)

router = APIRouter(prefix="/api", tags=["Planner"])


def _runtime(request: Request) -> PlannerRuntime:
    return request.app.state.planner_runtime


@router.get(
    "/contracts",
    response_model=ContractCatalogResponse,
    summary="List contracts available in the configured TeamPack",
)
async def list_contracts(request: Request) -> ContractCatalogResponse:
    """Return exact contract IDs accepted by the Planner endpoint."""
    runtime = _runtime(request)
    return ContractCatalogResponse(
        dataset_id=runtime.dataset_id,
        snapshot_hash=runtime.snapshot_hash,
        contract_ids=runtime.contract_ids(),
    )


@router.post(
    "/planner/evaluate",
    response_model=PlannerExecutionResult,
    summary="Evaluate one contract through Planner Intake",
    response_description="Workflow, Planner result, evidence, and validated artifacts",
)
async def evaluate_contract(
    payload: PlannerEvaluationRequest,
    request: Request,
) -> PlannerExecutionResult:
    """Return contract-specific Planner output without executing downstream agents."""
    runtime = _runtime(request)
    return await runtime.evaluate(
        contract_id=payload.contract_id,
        evaluation_scope=payload.evaluation_scope,
    )


@router.post(
    "/cases/{evaluation_case_id}/finance-assessment",
    response_model=FinanceExecutionResult,
    tags=["Finance"],
    summary="Run deterministic Finance assessment for a Planner case",
)
async def finance_assessment(
    evaluation_case_id: str,
    request: Request,
) -> FinanceExecutionResult:
    """Calculate Finance facts, then compose a bounded narrative."""
    try:
        return await _runtime(request).finance_assessment(evaluation_case_id=evaluation_case_id)
    except FinanceCaseNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/cases/{evaluation_case_id}/operations-assessment",
    response_model=OperationsExecutionResult,
    tags=["Operations"],
    summary="Run deterministic Operations assessment for a Planner case",
)
async def operations_assessment(
    evaluation_case_id: str,
    payload: OperationsAssessmentRequest,
    request: Request,
) -> OperationsExecutionResult:
    """Calculate planned schedule facts and neutral source observations."""
    try:
        return await _runtime(request).operations_assessment(
            evaluation_case_id=evaluation_case_id,
            as_of_date=payload.as_of_date,
        )
    except OperationsCaseNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/cases/{evaluation_case_id}/artifacts",
    response_model=tuple[ArtifactEnvelope, ...],
    tags=["Artifacts"],
    summary="Inspect validated artifacts for a case",
)
async def case_artifacts(
    evaluation_case_id: str,
    request: Request,
) -> tuple[ArtifactEnvelope, ...]:
    """Return immutable in-process artifact envelopes for debugging and demos."""
    return await _runtime(request).artifacts_for_case(evaluation_case_id)
