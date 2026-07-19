"""Planner and dataset discovery HTTP routes."""

from fastapi import APIRouter, HTTPException, Request, Response, status

from opc_mis.api.dashboard_projection import build_dashboard_projection
from opc_mis.api.dashboard_schemas import DashboardWorkflowProjection
from opc_mis.api.schemas import (
    ApprovalDecisionRequest,
    AutomaticCaseWorkflowRequest,
    BankingAmountInputSubmissionRequest,
    BankingDiscoveryHandoffResponse,
    BankingDiscoveryResponse,
    BankingInputSupplementResponse,
    BankingPrecheckEvidenceSubmissionRequest,
    BankingPrecheckEvidenceSupplementResponse,
    BankingPrecheckReadinessResponse,
    ContractCatalogResponse,
    DecisionDocumentHandoffResponse,
    DecisionPostBankingResponse,
    DecisionPostPrecheckResponse,
    DecisionRouteResponse,
    DocumentEvidenceSubmissionRequest,
    DocumentEvidenceSupplementResponse,
    DocumentPreparationResponse,
    FinanceAssessmentResponse,
    OperationsAssessmentRequest,
    PlannerEvaluationRequest,
    ProtectedActionRequest,
    RiskAssessmentResponse,
)
from opc_mis.domain.approvals import (
    ApprovalCheckpointSet,
    ApprovalExecutionResult,
    ApprovalRequest,
)
from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.banking_input_models import BankingAmountInputSubmission
from opc_mis.domain.banking_precheck_evidence_models import (
    BankingPrecheckEvidenceSubmission,
)
from opc_mis.domain.case_workflow_models import (
    WorkflowEvent,
    WorkflowRunSummary,
    WorkflowStartResult,
)
from opc_mis.domain.document_models import DocumentEvidenceSubmission
from opc_mis.domain.enums import ProtectedAction, WorkflowStatus
from opc_mis.domain.operations_models import OperationsExecutionResult
from opc_mis.domain.planner_models import PlannerExecutionResult
from opc_mis.runtime import (
    BankingDiscoveryCaseNotFoundError,
    BankingPrecheckCaseNotFoundError,
    DecisionHandoffCaseNotFoundError,
    DecisionPostBankingCaseNotFoundError,
    DecisionPostPrecheckCaseNotFoundError,
    DecisionRouteCaseNotFoundError,
    DocumentCaseNotFoundError,
    FinanceCaseNotFoundError,
    OperationsCaseNotFoundError,
    PlannerRuntime,
    RiskCaseNotFoundError,
)
from opc_mis.workflow.approval_orchestrator import (
    ApprovalConflictError,
    ApprovalControlError,
)
from opc_mis.workflow.case_workflow_orchestrator import (
    CaseWorkflowConflictError,
    CaseWorkflowNotFoundError,
)

router = APIRouter(prefix="/api")


def _runtime(request: Request) -> PlannerRuntime:
    return request.app.state.planner_runtime


@router.get(
    "/contracts",
    response_model=ContractCatalogResponse,
    tags=["Planner"],
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
    tags=["Planner"],
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
    "/cases/run",
    response_model=WorkflowStartResult,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Workflow"],
    summary="Run the automatic case workflow through Final Risk readiness",
)
async def start_case_workflow(
    payload: AutomaticCaseWorkflowRequest,
    request: Request,
) -> WorkflowStartResult:
    """Run until a typed pause, fail-safe boundary, or Final Risk readiness."""
    return await _runtime(request).start_case_workflow(
        contract_id=payload.contract_id,
        evaluation_scope=payload.evaluation_scope,
        as_of_date=payload.as_of_date,
        run_request_id=payload.run_request_id,
    )


@router.get(
    "/workflows/{workflow_run_id}",
    response_model=WorkflowRunSummary,
    tags=["Workflow"],
    summary="Inspect durable automatic workflow progress",
)
async def case_workflow_status(
    workflow_run_id: str,
    request: Request,
) -> WorkflowRunSummary:
    """Return node states, compact artifact references, and pending controls."""
    try:
        return await _runtime(request).case_workflow_summary(workflow_run_id)
    except CaseWorkflowNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/workflows/{workflow_run_id}/dashboard",
    response_model=DashboardWorkflowProjection,
    tags=["Workflow"],
    summary="Inspect the Founder-facing projection for one workflow run",
)
async def case_workflow_dashboard(
    workflow_run_id: str,
    request: Request,
) -> DashboardWorkflowProjection:
    """Return canonical stages and run-scoped presentation data without evidence detail."""

    runtime = _runtime(request)
    try:
        summary = await runtime.case_workflow_summary(workflow_run_id)
    except CaseWorkflowNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if summary.evaluation_case_id is None:
        artifacts: tuple[ArtifactEnvelope, ...] = ()
        approvals: tuple[ApprovalRequest, ...] = ()
    else:
        artifacts = await runtime.artifacts_for_case(summary.evaluation_case_id)
        approvals = await runtime.approval_requests(summary.evaluation_case_id)
    return build_dashboard_projection(
        summary=summary,
        artifacts=artifacts,
        approvals=approvals,
    )


@router.post(
    "/workflows/{workflow_run_id}/resume",
    response_model=WorkflowStartResult,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Workflow"],
    summary="Resume a workflow after its blocking condition changes",
)
async def resume_case_workflow(
    workflow_run_id: str,
    request: Request,
) -> WorkflowStartResult:
    """Resume only WAITING_FOR_INPUT or FAILED_SAFE workflows."""
    try:
        return await _runtime(request).resume_case_workflow(workflow_run_id)
    except CaseWorkflowNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except CaseWorkflowConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get(
    "/workflows/{workflow_run_id}/events",
    response_model=tuple[WorkflowEvent, ...],
    tags=["Workflow"],
    summary="Poll ordered workflow events",
)
async def case_workflow_events(
    workflow_run_id: str,
    request: Request,
    after_sequence: int = 0,
) -> tuple[WorkflowEvent, ...]:
    """Return append-only events with sequence greater than the supplied cursor."""
    if after_sequence < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="after_sequence must be non-negative",
        )
    try:
        return await _runtime(request).case_workflow_events(
            workflow_run_id, after_sequence
        )
    except CaseWorkflowNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/cases/{evaluation_case_id}/finance-assessment",
    response_model=FinanceAssessmentResponse,
    tags=["Finance"],
    summary="Run deterministic Finance assessment for a Planner case",
)
async def finance_assessment(
    evaluation_case_id: str,
    request: Request,
) -> FinanceAssessmentResponse:
    """Calculate Finance facts, then compose a bounded narrative."""
    try:
        result = await _runtime(request).finance_assessment(evaluation_case_id=evaluation_case_id)
        return FinanceAssessmentResponse.from_execution_result(result)
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


@router.post(
    "/cases/{evaluation_case_id}/initial-risk-assessment",
    response_model=RiskAssessmentResponse,
    tags=["Risk"],
    summary="Start or resume the deterministic initial Risk scan",
    responses={202: {"description": "Pre-scan persisted; waiting for upstream facts"}},
)
async def initial_risk_assessment(
    evaluation_case_id: str,
    request: Request,
    response: Response,
) -> RiskAssessmentResponse:
    """Pre-scan immediately, then pause until Finance and Operations facts exist."""
    try:
        result = await _runtime(request).risk_assessment(
            evaluation_case_id=evaluation_case_id,
        )
        if result.status is WorkflowStatus.WAITING_FOR_DEPENDENCIES:
            response.status_code = status.HTTP_202_ACCEPTED
        return RiskAssessmentResponse.from_execution_result(result)
    except RiskCaseNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/cases/{evaluation_case_id}/risk-status",
    response_model=RiskAssessmentResponse,
    tags=["Risk"],
    summary="Inspect the latest Risk checkpoint without changing it",
)
async def risk_status(
    evaluation_case_id: str,
    request: Request,
) -> RiskAssessmentResponse:
    """Return WAITING or finalized Risk output from the persisted checkpoint."""
    try:
        result = await _runtime(request).risk_status(evaluation_case_id=evaluation_case_id)
        return RiskAssessmentResponse.from_execution_result(result)
    except RiskCaseNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/cases/{evaluation_case_id}/decision-route",
    response_model=DecisionRouteResponse,
    tags=["Decision"],
    summary="Plan the deterministic initial Decision route",
    responses={409: {"description": "Initial Assessment artifacts are incomplete"}},
)
async def decision_initial_route(
    evaluation_case_id: str,
    request: Request,
    response: Response,
) -> DecisionRouteResponse:
    """Classify Banking discovery versus direct internal Decision preparation."""
    try:
        result = await _runtime(request).decision_initial_route(
            evaluation_case_id=evaluation_case_id
        )
        if result.status is WorkflowStatus.WAITING_FOR_INPUT:
            response.status_code = status.HTTP_409_CONFLICT
        return DecisionRouteResponse.from_execution_result(result)
    except DecisionRouteCaseNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/cases/{evaluation_case_id}/banking-discovery-request",
    response_model=BankingDiscoveryHandoffResponse,
    tags=["Decision"],
    summary="Create Decision's internal Banking discovery request",
    responses={409: {"description": "Decision Initial Route is incomplete"}},
)
async def decision_banking_handoff(
    evaluation_case_id: str,
    request: Request,
    response: Response,
) -> BankingDiscoveryHandoffResponse:
    """Hand off only an evidence-backed Banking route; do not run Banking."""
    try:
        result = await _runtime(request).decision_banking_handoff(
            evaluation_case_id=evaluation_case_id
        )
        if result.status is WorkflowStatus.WAITING_FOR_INPUT:
            response.status_code = status.HTTP_409_CONFLICT
        return BankingDiscoveryHandoffResponse.from_execution_result(result)
    except DecisionHandoffCaseNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/cases/{evaluation_case_id}/banking/internal-discovery",
    response_model=BankingDiscoveryResponse,
    tags=["Banking"],
    summary="Build the deterministic internal Banking option matrix",
    responses={409: {"description": "Decision Banking request is incomplete"}},
)
async def banking_internal_discovery(
    evaluation_case_id: str,
    request: Request,
    response: Response,
) -> BankingDiscoveryResponse:
    """Read mock catalog metadata without executing a precheck or external call."""
    try:
        result = await _runtime(request).banking_internal_discovery(
            evaluation_case_id=evaluation_case_id
        )
        if result.status is WorkflowStatus.WAITING_FOR_INPUT:
            response.status_code = status.HTTP_409_CONFLICT
        return BankingDiscoveryResponse.from_execution_result(result)
    except BankingDiscoveryCaseNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/cases/{evaluation_case_id}/banking/precheck-readiness",
    response_model=BankingPrecheckReadinessResponse,
    tags=["Banking"],
    summary="Assess Banking precheck input readiness without calling a bank",
)
async def banking_precheck_readiness(
    evaluation_case_id: str,
    request: Request,
) -> BankingPrecheckReadinessResponse:
    """Resolve configured field sources and deterministic product requirements."""
    try:
        result = await _runtime(request).banking_precheck_readiness(
            evaluation_case_id=evaluation_case_id
        )
        return BankingPrecheckReadinessResponse.from_execution_result(result)
    except BankingPrecheckCaseNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/cases/{evaluation_case_id}/decision/post-banking-review",
    response_model=DecisionPostBankingResponse,
    tags=["Decision"],
    summary="Review Banking readiness and create blocking data requests",
    responses={409: {"description": "Typed Banking input is required"}},
)
async def decision_post_banking_review(
    evaluation_case_id: str,
    request: Request,
    response: Response,
) -> DecisionPostBankingResponse:
    """Classify the next route without selecting a bank or invoking a precheck."""
    try:
        result = await _runtime(request).decision_post_banking_review(
            evaluation_case_id=evaluation_case_id
        )
        if result.status is WorkflowStatus.WAITING_FOR_INPUT:
            response.status_code = status.HTTP_409_CONFLICT
        return DecisionPostBankingResponse.from_execution_result(result)
    except DecisionPostBankingCaseNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/cases/{evaluation_case_id}/decision/post-precheck-review",
    response_model=DecisionPostPrecheckResponse,
    tags=["Decision"],
    summary="Classify persisted Banking precheck results without selecting an option",
    responses={409: {"description": "Explicit follow-up evidence is required"}},
)
async def decision_post_precheck_review(
    evaluation_case_id: str,
    request: Request,
    response: Response,
) -> DecisionPostPrecheckResponse:
    """Inspect the deterministic review of the latest validated precheck batch."""
    try:
        result = await _runtime(request).decision_post_precheck_review_latest(
            evaluation_case_id=evaluation_case_id
        )
        if result.status is WorkflowStatus.WAITING_FOR_INPUT:
            response.status_code = status.HTTP_409_CONFLICT
        return DecisionPostPrecheckResponse.from_execution_result(result)
    except DecisionPostPrecheckCaseNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.post(
    "/cases/{evaluation_case_id}/decision/document-handoff",
    response_model=DecisionDocumentHandoffResponse,
    tags=["Decision"],
    summary="Create Document requests from conditional provider results",
    responses={409: {"description": "No single viable conditional result is available"}},
)
async def decision_document_handoff(
    evaluation_case_id: str,
    request: Request,
    response: Response,
) -> DecisionDocumentHandoffResponse:
    """Preserve viable options without selecting or releasing a document."""
    try:
        result = await _runtime(request).decision_document_handoff_latest(
            evaluation_case_id=evaluation_case_id
        )
    except DocumentCaseNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    if result.status is not WorkflowStatus.COMPLETED:
        response.status_code = status.HTTP_409_CONFLICT
    return DecisionDocumentHandoffResponse.from_execution_result(result)


@router.post(
    "/cases/{evaluation_case_id}/documents/prepare",
    response_model=DocumentPreparationResponse,
    tags=["Document"],
    summary="Prepare a masked internal partner dossier",
    responses={409: {"description": "Document input or masking configuration is unavailable"}},
)
async def document_preparation(
    evaluation_case_id: str,
    request: Request,
    response: Response,
) -> DocumentPreparationResponse:
    """Prepare an internal draft; this endpoint never authorizes external release."""
    try:
        result = await _runtime(request).document_preparation_latest(
            evaluation_case_id=evaluation_case_id
        )
    except DocumentCaseNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    if result.status is not WorkflowStatus.COMPLETED:
        response.status_code = status.HTTP_409_CONFLICT
    return DocumentPreparationResponse.from_execution_result(result)


@router.post(
    "/cases/{evaluation_case_id}/banking/input-supplements",
    response_model=BankingInputSupplementResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Banking"],
    summary="Resolve a legacy pending Banking amount gap",
    responses={
        404: {"description": "Workflow or evaluation case was not found"},
        409: {"description": "Workflow/request is not waiting for this input"},
    },
)
async def submit_banking_input(
    evaluation_case_id: str,
    payload: BankingAmountInputSubmissionRequest,
    request: Request,
    response: Response,
) -> BankingInputSupplementResponse:
    """Handle only an explicit legacy amount gap; normal Planner-linked cases reject it."""
    try:
        result, workflow = await _runtime(request).submit_banking_input(
            evaluation_case_id=evaluation_case_id,
            submission=BankingAmountInputSubmission(
                workflow_run_id=payload.workflow_run_id,
                missing_request_id=payload.missing_request_id,
                requested_amount=payload.requested_amount,
                requested_amount_currency=payload.requested_amount_currency,
                provided_by="AUTHORIZED_STAFF",
                evidence_note=payload.evidence_note,
            ),
        )
    except CaseWorkflowNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (CaseWorkflowConflictError, DecisionPostBankingCaseNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if result.status is not WorkflowStatus.COMPLETED:
        response.status_code = status.HTTP_409_CONFLICT
    return BankingInputSupplementResponse.from_results(result, workflow)


@router.post(
    "/cases/{evaluation_case_id}/banking/precheck-evidence-supplements",
    response_model=BankingPrecheckEvidenceSupplementResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Banking"],
    summary="Resolve one post-precheck evidence handoff without changing its result",
    responses={
        404: {"description": "Workflow or evaluation case was not found"},
        409: {"description": "Workflow/request is not waiting for this evidence"},
    },
)
async def submit_banking_precheck_evidence(
    evaluation_case_id: str,
    payload: BankingPrecheckEvidenceSubmissionRequest,
    request: Request,
    response: Response,
) -> BankingPrecheckEvidenceSupplementResponse:
    """Persist a staff evidence reference; a fresh governed precheck remains required."""
    try:
        result, workflow = await _runtime(request).submit_banking_precheck_evidence(
            evaluation_case_id=evaluation_case_id,
            submission=BankingPrecheckEvidenceSubmission(
                workflow_run_id=payload.workflow_run_id,
                missing_request_id=payload.missing_request_id,
                evidence_reference_id=payload.evidence_reference_id,
                provided_by="AUTHORIZED_STAFF",
                evidence_note=payload.evidence_note,
            ),
        )
    except CaseWorkflowNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except (CaseWorkflowConflictError, DecisionPostPrecheckCaseNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    if result.status is not WorkflowStatus.COMPLETED:
        response.status_code = status.HTTP_409_CONFLICT
    return BankingPrecheckEvidenceSupplementResponse.from_results(
        result, workflow
    )


@router.post(
    "/cases/{evaluation_case_id}/documents/evidence-supplements",
    response_model=DocumentEvidenceSupplementResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Document"],
    summary="Resolve one pending Document requirement with an opaque reference",
    responses={
        404: {"description": "Workflow, case, or pending package was not found"},
        409: {"description": "Workflow is not waiting for this exact document"},
    },
)
async def submit_document_evidence(
    evaluation_case_id: str,
    payload: DocumentEvidenceSubmissionRequest,
    request: Request,
    response: Response,
) -> DocumentEvidenceSupplementResponse:
    """Accept no file path or bytes; persist only reference metadata and a hash."""
    try:
        result, workflow = await _runtime(request).submit_document_evidence(
            evaluation_case_id=evaluation_case_id,
            submission=DocumentEvidenceSubmission(
                workflow_run_id=payload.workflow_run_id,
                missing_request_id=payload.missing_request_id,
                document_reference_id=payload.document_reference_id,
                content_sha256=payload.content_sha256,
                document_type=payload.document_type,
                provided_by="AUTHORIZED_STAFF",
                evidence_note=payload.evidence_note,
            ),
        )
    except (CaseWorkflowNotFoundError, DocumentCaseNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except CaseWorkflowConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    if result.status is not WorkflowStatus.COMPLETED:
        response.status_code = status.HTTP_409_CONFLICT
    return DocumentEvidenceSupplementResponse.from_results(result, workflow)


@router.get(
    "/cases/{evaluation_case_id}/approval-checkpoints",
    response_model=ApprovalCheckpointSet,
    tags=["Governance"],
    summary="Inspect future approval gates registered by Initial Risk Scan",
)
async def approval_checkpoints(
    evaluation_case_id: str,
    request: Request,
) -> ApprovalCheckpointSet:
    """Return checkpoints; their presence alone does not pause the workflow."""
    try:
        return await _runtime(request).approval_checkpoints(evaluation_case_id)
    except ApprovalControlError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/cases/{evaluation_case_id}/protected-actions/{action_type}",
    response_model=ApprovalExecutionResult,
    tags=["Governance"],
    summary="Evaluate a protected action and pause if human approval is required",
    responses={
        202: {"description": "Checkpoint triggered; waiting for human approval"},
        409: {"description": "Checkpoint input or registration is unavailable"},
    },
)
async def request_protected_action(
    evaluation_case_id: str,
    action_type: ProtectedAction,
    payload: ProtectedActionRequest,
    request: Request,
    response: Response,
) -> ApprovalExecutionResult:
    """Run the gate; Banking submission and Document release are workflow-only."""
    try:
        result = await _runtime(request).request_protected_action(
            evaluation_case_id=evaluation_case_id,
            workflow_run_id=payload.workflow_run_id,
            action_type=action_type,
            payload_artifact_id=payload.payload_artifact_id,
            requested_by=payload.requested_by,
            payload=payload.payload,
        )
    except (ApprovalControlError, ApprovalConflictError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if result.status is WorkflowStatus.WAITING_FOR_APPROVAL:
        response.status_code = status.HTTP_202_ACCEPTED
    elif result.status is WorkflowStatus.WAITING_FOR_INPUT:
        response.status_code = status.HTTP_409_CONFLICT
    return result


@router.get(
    "/cases/{evaluation_case_id}/approval-requests",
    response_model=tuple[ApprovalRequest, ...],
    tags=["Governance"],
    summary="List approval requests created for a case",
)
async def approval_requests(
    evaluation_case_id: str,
    request: Request,
) -> tuple[ApprovalRequest, ...]:
    """Return pending and resolved requests; checkpoints alone are not requests."""
    return await _runtime(request).approval_requests(evaluation_case_id)


@router.post(
    "/approval-requests/{request_id}/decision",
    response_model=ApprovalExecutionResult,
    tags=["Governance"],
    summary="Approve or reject one pending protected action",
)
async def decide_approval(
    request_id: str,
    payload: ApprovalDecisionRequest,
    request: Request,
    response: Response,
) -> ApprovalExecutionResult:
    """Record a human decision and let the Orchestrator resume or reject."""
    try:
        result = await _runtime(request).decide_approval(
            request_id=request_id,
            decision=payload.decision,
            decided_by=payload.decided_by,
            reason=payload.reason,
        )
        if result.gate_status.value == "EXPIRED":
            response.status_code = status.HTTP_409_CONFLICT
        return result
    except ApprovalControlError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ApprovalConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


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
