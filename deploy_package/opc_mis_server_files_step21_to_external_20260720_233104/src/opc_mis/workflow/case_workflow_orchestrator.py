"""Durable Master Workflow through governed Banking precheck authorization."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Protocol

from opc_mis.domain.approvals import (
    ApprovalCheckpointSet,
    ApprovalExecutionResult,
    ApprovalRequest,
)
from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.banking_input_models import (
    BankingAmountInputSubmission,
    BankingInputExecutionResult,
)
from opc_mis.domain.banking_models import (
    BankingDiscoveryExecutionResult,
    BankingDiscoveryHandoffExecutionResult,
    BankingDiscoveryRequest,
    BankingDiscoveryResult,
    BankingInputSupplement,
    BankingOptionAdvice,
    BankingOptionMatrix,
    BankingPrecheckReadiness,
    BankingPrecheckReadinessExecutionResult,
)
from opc_mis.domain.banking_precheck_evidence_models import (
    BankingPrecheckEvidenceExecutionResult,
    BankingPrecheckEvidenceSubmission,
    BankingPrecheckEvidenceSupplement,
)
from opc_mis.domain.banking_precheck_execution_models import (
    BankingPrecheckResultExecutionResult,
    BankingPrecheckResultSet,
)
from opc_mis.domain.banking_precheck_submission_models import (
    BankingPrecheckSubmissionProposal,
    BankingPrecheckSubmissionProposalExecutionResult,
    banking_precheck_action_payload,
)
from opc_mis.domain.case_workflow_models import (
    CaseWorkflowRun,
    WorkflowArtifactReference,
    WorkflowNodeState,
    WorkflowRunSummary,
)
from opc_mis.domain.commands import ActionCommand
from opc_mis.domain.decision_models import (
    AIDecisionAnalysis,
    DecisionAnalysisExecutionResult,
    DecisionAnalysisSource,
    DecisionCard,
    DecisionCardExecutionResult,
    DecisionRecommendation,
    ExactDecisionArtifactRef,
)
from opc_mis.domain.decision_post_banking_models import (
    DecisionPostBankingExecutionResult,
    DecisionPostBankingReview,
)
from opc_mis.domain.decision_post_precheck_models import (
    DecisionPostPrecheckExecutionResult,
    DecisionPostPrecheckReview,
)
from opc_mis.domain.decision_route_models import (
    DecisionRouteExecutionResult,
    DecisionRoutePlan,
)
from opc_mis.domain.document_models import (
    DecisionDocumentHandoffExecutionResult,
    DocumentChecklist,
    DocumentEvidenceExecutionResult,
    DocumentEvidenceSubmission,
    DocumentEvidenceSupplement,
    DocumentPackageDraft,
    DocumentPackageReadiness,
    DocumentPreparationRequest,
    DocumentReleasePackage,
    DocumentSkillExecutionResult,
)
from opc_mis.domain.enums import (
    ApprovalGateStatus,
    ApprovalRequestStatus,
    ArtifactType,
    ComponentStatus,
    CurrencyCode,
    DecisionPostBankingOutcome,
    DecisionPostPrecheckOutcome,
    DecisionRouteOutcome,
    EvaluationScope,
    MissingRequestStatus,
    ProtectedAction,
    ValidationStatus,
    WorkflowNodeStatus,
    WorkflowStatus,
)
from opc_mis.domain.final_risk_models import (
    FinalRiskAssessment,
    FinalRiskExecutionResult,
)
from opc_mis.domain.finance_models import FinanceExecutionResult
from opc_mis.domain.internal_decision_package_models import (
    InternalDecisionAssemblyPath,
    InternalDecisionPackage,
    InternalDecisionPackageExecutionResult,
)
from opc_mis.domain.lineage import deterministic_id
from opc_mis.domain.negotiation_models import (
    NegotiationOutcome,
    NegotiationOutcomeExecutionResult,
    NegotiationOutcomeInput,
    NegotiationOutcomeStatus,
    NegotiationTermsSentInput,
)
from opc_mis.domain.operations_models import OperationsExecutionResult
from opc_mis.domain.planner_models import PlannerExecutionResult
from opc_mis.domain.post_decision_models import (
    ExternalDocumentSubmissionProposal,
    ExternalDocumentSubmissionProposalExecutionResult,
    ExternalSubmissionReadinessExecutionResult,
    PostDecisionOutcome,
    PostDecisionUpdate,
    PostDecisionUpdateExecutionResult,
    external_document_release_action_payload,
    final_decision_action_payload,
)
from opc_mis.domain.risk_models import RiskExecutionResult
from opc_mis.domain.workflow import WorkflowNode
from opc_mis.ports.approval_request_repository import ApprovalRequestRepository
from opc_mis.ports.artifact_repository import ArtifactRepository
from opc_mis.ports.case_workflow_repository import CaseWorkflowRepository
from opc_mis.ports.runtime_event_repository import RuntimeEventRepository

_BANKING_PRECHECK_EXECUTION_FAILURE = (
    "Banking precheck execution failed safely; internal provider and "
    "infrastructure details were withheld."
)
_RECOVERABLE_DECISION_REPLAY_FAILURES = (
    "Existing AI_DECISION_ANALYSIS artifact is not reusable.",
    "Existing DECISION_CARD artifact is not reusable.",
)


@dataclass(frozen=True)
class _PersistedDecisionBundle:
    """Exact validated Decision outputs reused during workflow replay."""

    analysis_artifact: ArtifactEnvelope
    analysis: AIDecisionAnalysis
    card_artifact: ArtifactEnvelope
    card: DecisionCard


class AutomaticWorkflowServices(Protocol):
    """Application services invoked by the Master Workflow without UI dependencies."""

    dataset_id: str

    @property
    def snapshot_hash(self) -> str: ...

    async def evaluate(
        self,
        *,
        contract_id: str,
        evaluation_scope: tuple[EvaluationScope, ...],
    ) -> PlannerExecutionResult: ...

    async def finance_assessment(
        self, *, evaluation_case_id: str, resume_risk: bool = True
    ) -> FinanceExecutionResult: ...

    async def operations_assessment(
        self,
        *,
        evaluation_case_id: str,
        as_of_date: date | None = None,
        resume_risk: bool = True,
    ) -> OperationsExecutionResult: ...

    async def risk_pre_scan(self, *, evaluation_case_id: str) -> RiskExecutionResult: ...

    async def risk_finalize(self, *, evaluation_case_id: str) -> RiskExecutionResult: ...

    async def decision_initial_route(
        self, *, evaluation_case_id: str
    ) -> DecisionRouteExecutionResult: ...

    async def decision_banking_handoff(
        self, *, evaluation_case_id: str
    ) -> BankingDiscoveryHandoffExecutionResult: ...

    @property
    def banking_policy_hash(self) -> str: ...

    @property
    def banking_advisor_configuration_hash(self) -> str: ...

    @property
    def banking_precheck_adapter_id(self) -> str: ...

    @property
    def banking_precheck_adapter_configuration_hash(self) -> str: ...

    async def banking_internal_discovery(
        self, *, evaluation_case_id: str
    ) -> BankingDiscoveryExecutionResult: ...

    async def banking_precheck_readiness(
        self, *, evaluation_case_id: str
    ) -> BankingPrecheckReadinessExecutionResult: ...

    async def decision_post_banking_review(
        self, *, evaluation_case_id: str
    ) -> DecisionPostBankingExecutionResult: ...

    async def banking_precheck_submission_proposal(
        self, *, evaluation_case_id: str
    ) -> BankingPrecheckSubmissionProposalExecutionResult: ...

    async def banking_precheck_execution(
        self,
        *,
        evaluation_case_id: str,
        workflow_run_id: str,
        approval_request_id: str,
        proposal_artifact_id: str,
        reuse_existing_only: bool = False,
    ) -> BankingPrecheckResultExecutionResult: ...

    async def decision_post_precheck_review(
        self,
        *,
        evaluation_case_id: str,
        workflow_run_id: str,
        result_set_artifact_id: str,
    ) -> DecisionPostPrecheckExecutionResult: ...

    @property
    def document_masking_policy_hash(self) -> str: ...

    @property
    def document_tokenizer_key_version(self) -> str: ...

    async def decision_document_handoff(
        self,
        *,
        evaluation_case_id: str,
        workflow_run_id: str,
        review_artifact_id: str,
        result_set_artifact_id: str,
    ) -> DecisionDocumentHandoffExecutionResult: ...

    async def document_preparation(
        self,
        *,
        evaluation_case_id: str,
        workflow_run_id: str,
        preparation_request_artifact_id: str,
    ) -> DocumentSkillExecutionResult: ...

    async def internal_decision_package(
        self,
        *,
        evaluation_case_id: str,
        workflow_run_id: str,
        assembly_path: InternalDecisionAssemblyPath,
        input_artifact_ids: tuple[str, ...],
        approval_request_id: str | None = None,
    ) -> InternalDecisionPackageExecutionResult: ...

    async def final_risk_check(
        self,
        *,
        evaluation_case_id: str,
        workflow_run_id: str,
        internal_decision_package_artifact_id: str,
    ) -> FinalRiskExecutionResult: ...

    @property
    def decision_analysis_configuration_hash(self) -> str: ...

    async def decision_analysis(
        self,
        *,
        evaluation_case_id: str,
        workflow_run_id: str,
        final_risk_artifact_id: str,
    ) -> DecisionAnalysisExecutionResult: ...

    async def decision_card(
        self,
        *,
        evaluation_case_id: str,
        workflow_run_id: str,
        analysis_artifact_id: str,
    ) -> DecisionCardExecutionResult: ...

    async def post_decision_update(
        self,
        *,
        evaluation_case_id: str,
        workflow_run_id: str,
        decision_card_artifact_id: str,
        approval_request_id: str,
    ) -> PostDecisionUpdateExecutionResult: ...

    async def negotiation_outcome(
        self,
        *,
        evaluation_case_id: str,
        submission: NegotiationOutcomeInput,
    ) -> NegotiationOutcomeExecutionResult: ...

    async def finalize_negotiation(
        self,
        *,
        evaluation_case_id: str,
        workflow_run_id: str,
        original_update_artifact: ArtifactEnvelope,
        outcome_artifact: ArtifactEnvelope,
        approval_request: "ApprovalRequest",
    ) -> ArtifactEnvelope: ...

    async def external_document_submission_proposal(
        self,
        *,
        evaluation_case_id: str,
        workflow_run_id: str,
        post_decision_update_artifact_id: str,
    ) -> ExternalDocumentSubmissionProposalExecutionResult: ...

    async def external_submission_readiness(
        self,
        *,
        evaluation_case_id: str,
        workflow_run_id: str,
        proposal_artifact_id: str,
        approval_request_id: str,
    ) -> ExternalSubmissionReadinessExecutionResult: ...

    async def request_workflow_protected_action(
        self,
        *,
        command: ActionCommand,
        workflow_run_id: str,
    ) -> ApprovalExecutionResult: ...

    async def banking_input_supplement(
        self,
        *,
        evaluation_case_id: str,
        submission: BankingAmountInputSubmission,
        allowed_pending_request_id: str,
    ) -> BankingInputExecutionResult: ...

    async def banking_precheck_evidence_supplement(
        self,
        *,
        evaluation_case_id: str,
        submission: BankingPrecheckEvidenceSubmission,
        allowed_pending_request_id: str,
    ) -> BankingPrecheckEvidenceExecutionResult: ...

    async def document_evidence_supplement(
        self,
        *,
        evaluation_case_id: str,
        submission: DocumentEvidenceSubmission,
        allowed_pending_request_id: str,
    ) -> DocumentEvidenceExecutionResult: ...

    async def artifacts_for_case(
        self, evaluation_case_id: str
    ) -> tuple[ArtifactEnvelope, ...]: ...


class CaseWorkflowNotFoundError(LookupError):
    """Raised when a requested Master Workflow does not exist."""


class CaseWorkflowConflictError(ValueError):
    """Raised when a workflow cannot be resumed from its current state."""


class _DemoPauseInterrupted(Exception):
    """Internal signal that a live-demo pause won the durable state race."""


class CaseWorkflowOrchestrator:
    """Own node selection, pause/resume, state persistence, and recovery."""

    def __init__(
        self,
        *,
        services: AutomaticWorkflowServices,
        workflows: CaseWorkflowRepository,
        artifacts: ArtifactRepository,
        approvals: ApprovalRequestRepository,
        events: RuntimeEventRepository,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._services = services
        self._workflows = workflows
        self._artifacts = artifacts
        self._approvals = approvals
        self._events = events
        self._clock = clock or (lambda: datetime.now(UTC))

    async def execute(self, workflow_run_id: str) -> None:
        """Run or recover one case workflow until it completes or genuinely pauses."""
        run = await self._require_run(workflow_run_id)
        if (
            run.dataset_id != self._services.dataset_id
            or run.dataset_snapshot_hash != self._services.snapshot_hash
        ):
            await self._fail(
                run,
                WorkflowNode.DATASET_INGESTION,
                "Workflow dataset snapshot does not match the active runtime.",
            )
            return
        if run.status in {WorkflowStatus.COMPLETED, WorkflowStatus.BLOCKED}:
            return
        if run.status is WorkflowStatus.WAITING_FOR_DEMO:
            return
        run = await self._save_run(
            run,
            status=WorkflowStatus.RUNNING,
            current_stage=run.current_stage,
            failure_reason=None,
        )
        await self._event(run, "WORKFLOW_STARTED", None)
        if await self._resume_final_decision_path(run):
            return
        active_node = WorkflowNode.PLANNER_INTAKE
        try:
            run = await self._planner(run)
            if run.status is not WorkflowStatus.RUNNING:
                return
            if run.evaluation_case_id is None:  # pragma: no cover - Planner contract guard
                raise RuntimeError("Planner completed without an evaluation_case_id.")

            active_node = WorkflowNode.INITIAL_RISK_PRE_SCAN
            risk_ready = await self._risk_pre_scan(run)
            if not risk_ready:
                return

            active_node = WorkflowNode.INITIAL_ASSESSMENT
            finance_result, operations_result = await asyncio.gather(
                self._finance(run),
                self._operations(run),
            )
            if not self._upstream_completed(finance_result, operations_result):
                await self._pause_from_upstream(run, finance_result, operations_result)
                return

            active_node = WorkflowNode.INITIAL_RISK_FINALIZATION
            risk_result = await self._finalize_risk(run)
            if (
                risk_result is not None
                and risk_result.status is not WorkflowStatus.COMPLETED
            ):
                await self._fail(
                    run,
                    active_node,
                    "Risk did not finalize after FinanceFacts and OperationsFacts were ready.",
                )
                return

            active_node = WorkflowNode.DECISION_ROUTE_PLANNING
            route_result = await self._decision_initial_route(run)
            if (
                route_result is not None
                and route_result.status is WorkflowStatus.WAITING_FOR_INPUT
            ):
                await self._pause_for_decision_input(run, route_result)
                return
            if (
                route_result is not None
                and route_result.status is not WorkflowStatus.COMPLETED
            ):
                await self._fail(
                    run,
                    active_node,
                    "Decision Initial Route did not complete safely: "
                    + "; ".join(route_result.validation_errors),
                )
                return
            route_plan = (
                route_result.route_plan if route_result is not None else None
            )
            if route_plan is None:
                artifacts = await self._artifacts.list_by_case(
                    run.evaluation_case_id
                )
                route_artifact = self._latest(
                    artifacts, ArtifactType.DECISION_ROUTE_PLAN
                )
                if route_artifact is None:
                    raise RuntimeError(
                        "Decision Initial Route completed without a route artifact."
                    )
                route_plan = DecisionRoutePlan.model_validate(
                    route_artifact.payload
                )
            if (
                route_plan.route_outcome
                is DecisionRouteOutcome.BANKING_DISCOVERY_REQUIRED
            ):
                active_node = WorkflowNode.BANKING_DISCOVERY_HANDOFF
                handoff_result = await self._decision_banking_handoff(run)
                if (
                    handoff_result is not None
                    and handoff_result.status is WorkflowStatus.WAITING_FOR_INPUT
                ):
                    await self._pause_for_banking_handoff_input(
                        run, handoff_result
                    )
                    return
                if (
                    handoff_result is not None
                    and handoff_result.status is not WorkflowStatus.COMPLETED
                ):
                    await self._fail(
                        run,
                        active_node,
                        "Decision Banking handoff did not complete safely: "
                        + "; ".join(handoff_result.validation_errors),
                    )
                    return
                run = await self._save_run(
                    run,
                    status=WorkflowStatus.RUNNING,
                    current_stage=WorkflowNode.BANKING_INTERNAL_DISCOVERY.value,
                    failure_reason=None,
                )
                active_node = WorkflowNode.BANKING_INTERNAL_DISCOVERY
                banking_result = await self._banking_internal_discovery(run)
                if (
                    banking_result is not None
                    and banking_result.status is WorkflowStatus.WAITING_FOR_INPUT
                ):
                    await self._pause_for_banking_discovery_input(
                        run, banking_result
                    )
                    return
                if (
                    banking_result is not None
                    and banking_result.status is not WorkflowStatus.COMPLETED
                ):
                    await self._fail(
                        run,
                        active_node,
                        "Banking internal discovery did not complete safely: "
                        + "; ".join(banking_result.validation_errors),
                    )
                    return
                run = await self._save_run(
                    run,
                    status=WorkflowStatus.RUNNING,
                    current_stage=WorkflowNode.BANKING_PRECHECK_READINESS.value,
                    failure_reason=None,
                )
                active_node = WorkflowNode.BANKING_PRECHECK_READINESS
                readiness_result = await self._banking_precheck_readiness(run)
                if (
                    readiness_result is not None
                    and readiness_result.status is not WorkflowStatus.COMPLETED
                ):
                    await self._fail(
                        run,
                        active_node,
                        "Banking precheck readiness did not complete safely: "
                        + "; ".join(readiness_result.validation_errors),
                    )
                    return
                run = await self._save_run(
                    run,
                    status=WorkflowStatus.RUNNING,
                    current_stage=WorkflowNode.DECISION_POST_BANKING_REVIEW.value,
                    failure_reason=None,
                )
                active_node = WorkflowNode.DECISION_POST_BANKING_REVIEW
                review_result = await self._decision_post_banking_review(run)
                if (
                    review_result is not None
                    and review_result.status is WorkflowStatus.WAITING_FOR_INPUT
                ):
                    await self._pause_for_post_banking_input(run, review_result)
                    return
                if (
                    review_result is not None
                    and review_result.status is not WorkflowStatus.COMPLETED
                ):
                    await self._fail(
                        run,
                        active_node,
                        "Decision post-Banking review did not complete safely: "
                        + "; ".join(review_result.validation_errors),
                    )
                    return
                review = (
                    review_result.review if review_result is not None else None
                )
                if review is None:
                    artifacts = await self._artifacts.list_by_case(
                        run.evaluation_case_id
                    )
                    review_artifact = self._latest(
                        artifacts, ArtifactType.DECISION_POST_BANKING_REVIEW
                    )
                    if review_artifact is None:
                        raise RuntimeError(
                            "Decision post-Banking review completed without an artifact."
                        )
                    review = DecisionPostBankingReview.model_validate(
                        review_artifact.payload
                    )
                if (
                    review.outcome
                    is DecisionPostBankingOutcome.UNSUPPORTED_PRECHECK_MAPPING
                ):
                    await self._fail(
                        run,
                        active_node,
                        "Banking precheck field mapping is unsupported.",
                    )
                    return
                if (
                    review.outcome
                    is DecisionPostBankingOutcome.BANKING_PRECHECK_READY
                ):
                    run = await self._save_run(
                        run,
                        status=WorkflowStatus.RUNNING,
                        current_stage=(
                            WorkflowNode.BANKING_PRECHECK_SUBMISSION_PROPOSAL.value
                        ),
                        failure_reason=None,
                    )
                    active_node = (
                        WorkflowNode.BANKING_PRECHECK_SUBMISSION_PROPOSAL
                    )
                    proposal_result = (
                        await self._banking_precheck_submission_proposal(run)
                    )
                    if (
                        proposal_result is not None
                        and proposal_result.status is not WorkflowStatus.COMPLETED
                    ):
                        await self._fail(
                            run,
                            active_node,
                            "Banking precheck submission proposal did not complete "
                            "safely: "
                            + "; ".join(proposal_result.validation_errors),
                        )
                        return
                    artifacts = await self._artifacts.list_by_case(
                        run.evaluation_case_id
                    )
                    proposal_artifact = self._latest(
                        artifacts,
                        ArtifactType.BANKING_PRECHECK_SUBMISSION_PROPOSAL,
                    )
                    if proposal_artifact is None:
                        raise RuntimeError(
                            "Banking proposal node completed without a persisted "
                            "proposal artifact."
                        )
                    proposal = (
                        proposal_result.proposal
                        if proposal_result is not None
                        else None
                    )
                    if proposal is None:
                        proposal = BankingPrecheckSubmissionProposal.model_validate(
                            proposal_artifact.payload
                        )
                    if (
                        proposal_artifact.payload
                        != proposal.model_dump(mode="json")
                        or proposal.evaluation_case_id != run.evaluation_case_id
                        or proposal.proposed_action
                        is not ProtectedAction.SUBMIT_BANKING_PRECHECK
                        or proposal.precheck_executed
                        or proposal.submission_executed
                    ):
                        await self._fail(
                            run,
                            active_node,
                            "The persisted Banking proposal is not a valid, "
                            "unexecuted approval subject.",
                        )
                        return
                    active_node = WorkflowNode.APPROVAL_GATE
                    approval_result = (
                        await self._services.request_workflow_protected_action(
                            command=ActionCommand(
                                action_type=(
                                    ProtectedAction.SUBMIT_BANKING_PRECHECK
                                ),
                                evaluation_case_id=run.evaluation_case_id,
                                payload_artifact_id=proposal_artifact.artifact_id,
                                requested_by="CASE_WORKFLOW_ORCHESTRATOR",
                                payload=banking_precheck_action_payload(proposal),
                            ),
                            workflow_run_id=run.workflow_run_id,
                        )
                    )
                    if approval_result.action_authorized:
                        if approval_result.approval_request is None:
                            await self._fail(
                                run,
                                WorkflowNode.APPROVAL_GATE,
                                "Governance authorized the Banking precheck without "
                                "a durable action-authorization record.",
                            )
                            return
                        refreshed = await self._require_run(run.workflow_run_id)
                        refreshed = await self._save_run(
                            refreshed,
                            status=WorkflowStatus.RUNNING,
                            current_stage=WorkflowNode.BANKING_PRECHECK_EXECUTION.value,
                            pending_request_ids=(),
                            failure_reason=None,
                        )
                        await self._event(
                            refreshed,
                            "BANKING_PRECHECK_SUBMISSION_AUTHORIZED",
                            WorkflowNode.BANKING_PRECHECK_SUBMISSION_AUTHORIZED,
                            {
                                "approval_request_id": (
                                    approval_result.approval_request.request_id
                                ),
                                "proposal_artifact_id": proposal_artifact.artifact_id,
                            },
                        )
                        active_node = WorkflowNode.BANKING_PRECHECK_EXECUTION
                        execution_result = await self._banking_precheck_execution(
                            refreshed,
                            proposal_artifact=proposal_artifact,
                            approval_request_id=(
                                approval_result.approval_request.request_id
                            ),
                        )
                        if (
                            execution_result is not None
                            and execution_result.status is not WorkflowStatus.COMPLETED
                        ):
                            await self._fail(
                                refreshed,
                                active_node,
                                "Authorized Banking precheck execution did not complete "
                                "safely: "
                                + "; ".join(execution_result.validation_errors),
                            )
                            return
                        if execution_result is None:
                            await self._fail(
                                refreshed,
                                active_node,
                                "Banking precheck execution returned no exact result set.",
                            )
                            return
                        result_artifacts = tuple(
                            item
                            for item in execution_result.generated_artifacts
                            if item.artifact_type
                            is ArtifactType.BANKING_PRECHECK_RESULT_SET
                        )
                        if len(result_artifacts) != 1:
                            await self._fail(
                                refreshed,
                                active_node,
                                "Banking precheck execution did not return one exact "
                                "validated result artifact.",
                            )
                            return
                        result_artifact = result_artifacts[0]
                        result_set = BankingPrecheckResultSet.model_validate(
                            result_artifact.payload
                        )
                        if (
                            result_artifact.evaluation_case_id
                            != refreshed.evaluation_case_id
                            or execution_result.result_set != result_set
                        ):
                            await self._fail(
                                refreshed,
                                active_node,
                                "Banking precheck execution result and persisted "
                                "artifact disagree.",
                            )
                            return
                        refreshed = await self._require_run(run.workflow_run_id)
                        refreshed = await self._save_run(
                            refreshed,
                            status=WorkflowStatus.RUNNING,
                            current_stage=(
                                WorkflowNode.DECISION_POST_PRECHECK_REVIEW.value
                            ),
                            pending_request_ids=(),
                            failure_reason=None,
                        )
                        await self._event(
                            refreshed,
                            "BANKING_PRECHECK_RESULTS_READY",
                            WorkflowNode.BANKING_PRECHECK_RESULTS_READY,
                            {
                                "result_set_artifact_id": result_artifact.artifact_id,
                                "result_set_id": result_set.result_set_id,
                            },
                        )
                        active_node = WorkflowNode.DECISION_POST_PRECHECK_REVIEW
                        post_precheck_result = (
                            await self._decision_post_precheck_review(
                                refreshed,
                                result_set_artifact=result_artifact,
                            )
                        )
                        if (
                            post_precheck_result is not None
                            and post_precheck_result.status
                            is WorkflowStatus.WAITING_FOR_INPUT
                        ):
                            await self._pause_for_post_precheck_input(
                                refreshed, post_precheck_result
                            )
                            return
                        if (
                            post_precheck_result is not None
                            and post_precheck_result.status
                            is not WorkflowStatus.COMPLETED
                        ):
                            await self._fail(
                                refreshed,
                                active_node,
                                "Decision post-precheck review did not complete safely: "
                                + "; ".join(
                                    post_precheck_result.validation_errors
                                ),
                            )
                            return
                        refreshed = await self._require_run(run.workflow_run_id)
                        artifacts = await self._artifacts.list_by_case(
                            refreshed.evaluation_case_id or ""
                        )
                        post_precheck_artifact = self._latest(
                            artifacts,
                            ArtifactType.DECISION_POST_PRECHECK_REVIEW,
                        )
                        if post_precheck_artifact is None:
                            await self._fail(
                                refreshed,
                                WorkflowNode.DECISION_POST_PRECHECK_REVIEW,
                                "Decision post-precheck review has no persisted artifact.",
                            )
                            return
                        post_precheck = DecisionPostPrecheckReview.model_validate(
                            post_precheck_artifact.payload
                        )
                        if (
                            post_precheck.outcome
                            is DecisionPostPrecheckOutcome.CONDITIONAL_OPTIONS_AVAILABLE
                        ):
                            await self._document_flow(
                                refreshed,
                                review_artifact=post_precheck_artifact,
                                result_set_artifact=result_artifact,
                            )
                            return
                        if post_precheck.outcome not in {
                            DecisionPostPrecheckOutcome.ALL_OPTIONS_NOT_ELIGIBLE,
                            DecisionPostPrecheckOutcome.NO_PROVIDER_RECOMMENDATION,
                            DecisionPostPrecheckOutcome.PRECHECK_SERVICE_UNAVAILABLE,
                            DecisionPostPrecheckOutcome.MIXED_NON_ACTIONABLE_RESULTS,
                        }:
                            await self._fail(
                                refreshed,
                                active_node,
                                "Decision post-precheck outcome cannot enter internal "
                                "package assembly.",
                            )
                            return
                        await self._assemble_internal_decision_package(
                            refreshed,
                            assembly_path=(
                                InternalDecisionAssemblyPath.BANKING_NON_ACTIONABLE
                            ),
                        )
                        return
                    if (
                        approval_result.gate_status is ApprovalGateStatus.REJECTED
                        and approval_result.approval_request is not None
                        and approval_result.approval_request.status
                        is ApprovalRequestStatus.REJECTED
                    ):
                        refreshed = await self._require_run(run.workflow_run_id)
                        await self._event(
                            refreshed,
                            "BANKING_PRECHECK_DECLINED_BY_FOUNDER",
                            WorkflowNode.BANKING_PRECHECK_DECLINED,
                            {
                                "approval_request_id": (
                                    approval_result.approval_request.request_id
                                ),
                                "proposal_artifact_id": proposal_artifact.artifact_id,
                                "next_route": "INTERNAL_DECISION_CONTINUATION",
                            },
                        )
                        await self._assemble_internal_decision_package(
                            refreshed,
                            assembly_path=(
                                InternalDecisionAssemblyPath.BANKING_PRECHECK_DECLINED
                            ),
                            approval_request_id=(
                                approval_result.approval_request.request_id
                            ),
                        )
                        return
                    refreshed = await self._require_run(run.workflow_run_id)
                    if refreshed.status in {
                        WorkflowStatus.WAITING_FOR_APPROVAL,
                        WorkflowStatus.WAITING_FOR_INPUT,
                        WorkflowStatus.BLOCKED,
                    }:
                        return
                    await self._fail(
                        refreshed,
                        WorkflowNode.APPROVAL_GATE,
                        "Banking precheck submission was not authorized or paused "
                        "by Governance.",
                    )
                    return
                if review.outcome not in {
                    DecisionPostBankingOutcome.NO_VIABLE_OPTION,
                    DecisionPostBankingOutcome.NO_PRECHECK_PATH,
                }:
                    await self._fail(
                        run,
                        active_node,
                        "Decision post-Banking outcome cannot enter internal "
                        "package assembly.",
                    )
                    return
                assembly_path = (
                    InternalDecisionAssemblyPath.BANKING_NO_VIABLE_OPTION
                    if review.outcome
                    is DecisionPostBankingOutcome.NO_VIABLE_OPTION
                    else InternalDecisionAssemblyPath.BANKING_NO_PRECHECK_PATH
                )
                await self._assemble_internal_decision_package(
                    run,
                    assembly_path=assembly_path,
                )
                return
            await self._assemble_internal_decision_package(
                run,
                assembly_path=InternalDecisionAssemblyPath.DIRECT_ROUTE,
            )
        except _DemoPauseInterrupted:
            return
        except Exception as exc:  # persisted fail-safe boundary for background execution
            await self._fail(run, active_node, f"{type(exc).__name__}: {exc}")

    async def _document_flow(
        self,
        run: CaseWorkflowRun,
        *,
        review_artifact: ArtifactEnvelope,
        result_set_artifact: ArtifactEnvelope,
    ) -> None:
        """Prepare one internal package without proposing an external release."""
        if run.evaluation_case_id is None:  # pragma: no cover - Planner invariant
            raise RuntimeError("Document flow requires an evaluation case.")
        run = await self._save_run(
            run,
            status=WorkflowStatus.RUNNING,
            current_stage=WorkflowNode.DECISION_DOCUMENT_HANDOFF.value,
            pending_request_ids=(),
            failure_reason=None,
        )
        handoff = await self._decision_document_handoff(
            run,
            review_artifact=review_artifact,
            result_set_artifact=result_set_artifact,
        )
        if handoff is not None and handoff.status is not WorkflowStatus.COMPLETED:
            await self._fail(
                run,
                WorkflowNode.DECISION_DOCUMENT_HANDOFF,
                "Decision Document handoff did not complete safely: "
                + "; ".join(handoff.validation_errors),
            )
            return
        artifacts = await self._artifacts.list_by_case(run.evaluation_case_id)
        request_artifacts = tuple(
            item
            for item in artifacts
            if item.artifact_type is ArtifactType.DOCUMENT_PREPARATION_REQUEST
            and item.input_artifact_ids
            == (review_artifact.artifact_id, result_set_artifact.artifact_id)
            and item.validation_status
            in {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}
        )
        if len(request_artifacts) != 1:
            reason = (
                "MULTIPLE_DOCUMENT_OPTIONS_REQUIRE_DECISION_SELECTION"
                if len(request_artifacts) > 1
                else "CONDITIONAL_RESULT_HAS_NO_DOCUMENT_PREPARATION_REQUEST"
            )
            await self._fail(
                run,
                WorkflowNode.DECISION_DOCUMENT_HANDOFF,
                reason,
            )
            return
        request_artifact = request_artifacts[0]
        run = await self._save_run(
            run,
            status=WorkflowStatus.RUNNING,
            current_stage=WorkflowNode.DOCUMENT_PREPARATION.value,
            pending_request_ids=(),
            failure_reason=None,
        )
        preparation = await self._document_preparation(
            run, request_artifact=request_artifact
        )
        if (
            preparation is not None
            and preparation.status is WorkflowStatus.WAITING_FOR_INPUT
        ):
            await self._pause_for_document_input(run, preparation)
            return
        if preparation is not None and preparation.status is not WorkflowStatus.COMPLETED:
            await self._fail(
                run,
                WorkflowNode.DOCUMENT_PREPARATION,
                "Document preparation did not complete safely: "
                + "; ".join(preparation.validation_errors),
            )
            return
        release_candidates = tuple(
            item
            for item in (
                preparation.generated_artifacts if preparation is not None else ()
            )
            if item.artifact_type is ArtifactType.DOCUMENT_RELEASE_PACKAGE
            and item.validation_status
            in {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}
        )
        if len(release_candidates) != 1:
            await self._fail(
                run,
                WorkflowNode.DOCUMENT_PREPARATION,
                "Document preparation did not create one exact release package.",
            )
            return
        release_artifact = release_candidates[0]
        release_package = DocumentReleasePackage.model_validate(
            release_artifact.payload
        )
        await self._event(
            run,
            "DOCUMENT_RELEASE_PACKAGE_READY",
            WorkflowNode.DOCUMENT_RELEASE_PACKAGE_READY,
            {
                "release_package_id": release_package.release_package_id,
                "release_package_artifact_id": release_artifact.artifact_id,
                "ready_for_internal_decision_assembly": True,
                "release_authorized": False,
                "external_release_performed": False,
            },
        )
        await self._event(
            run,
            "READY_FOR_INTERNAL_DECISION",
            WorkflowNode.READY_FOR_INTERNAL_DECISION,
            {
                "release_package_artifact_id": release_artifact.artifact_id,
                "ready_for_internal_decision_assembly": True,
                "external_release_action_proposed": False,
            },
        )
        await self._assemble_internal_decision_package(
            run,
            assembly_path=(
                InternalDecisionAssemblyPath.CONDITIONAL_DOCUMENT_READY
            ),
        )

    async def _assemble_internal_decision_package(
        self,
        run: CaseWorkflowRun,
        *,
        assembly_path: InternalDecisionAssemblyPath,
        approval_request_id: str | None = None,
    ) -> None:
        """Converge one eligible branch into a validated read-only dossier."""
        if run.evaluation_case_id is None:  # pragma: no cover
            raise RuntimeError(
                "Cannot assemble an Internal Decision Package without a case."
            )
        run = await self._require_run(run.workflow_run_id)
        run = await self._save_run(
            run,
            status=WorkflowStatus.RUNNING,
            current_stage=(
                WorkflowNode.INTERNAL_DECISION_PACKAGE_ASSEMBLY.value
            ),
            pending_request_ids=(),
            failure_reason=None,
        )
        source_artifacts, identity_inputs = (
            await self._internal_decision_source_artifacts(
                evaluation_case_id=run.evaluation_case_id,
                assembly_path=assembly_path,
                approval_request_id=approval_request_id,
            )
        )
        expected_hash = self._node_input_hash(
            run,
            WorkflowNode.INTERNAL_DECISION_PACKAGE_ASSEMBLY,
            identity_inputs,
        )
        existing = await self._workflows.get_node(
            run.workflow_run_id,
            WorkflowNode.INTERNAL_DECISION_PACKAGE_ASSEMBLY.value,
        )
        should_finish_node = not (
            self._node_completed(existing)
            and existing is not None
            and existing.input_hash == expected_hash
        )
        node = (
            await self._start_node(
                run,
                WorkflowNode.INTERNAL_DECISION_PACKAGE_ASSEMBLY,
                identity_inputs=identity_inputs,
            )
            if should_finish_node
            else existing
        )
        if node is None:  # pragma: no cover - guarded by branch above
            raise RuntimeError("Internal Decision Package node was not initialized.")
        result = await self._services.internal_decision_package(
            evaluation_case_id=run.evaluation_case_id,
            workflow_run_id=run.workflow_run_id,
            assembly_path=assembly_path,
            input_artifact_ids=tuple(
                item.artifact_id for item in source_artifacts
            ),
            approval_request_id=approval_request_id,
        )
        if should_finish_node:
            await self._finish_node(
                node,
                self._result_node_status(result.status, result.component_status),
                result.generated_artifacts,
                waiting_for=tuple(
                    item.requirement_code
                    for item in result.missing_data_requests
                ),
                failure_reason="; ".join(result.validation_errors) or None,
            )
        if result.status is WorkflowStatus.WAITING_FOR_INPUT:
            requirement_codes = tuple(
                item.requirement_code for item in result.missing_data_requests
            )
            await self._fail(
                run,
                WorkflowNode.INTERNAL_DECISION_PACKAGE_ASSEMBLY,
                "Internal Decision Package is missing required upstream artifacts; "
                "no user-input resolver exists for this system-integrity gap: "
                + ", ".join(requirement_codes),
            )
            return
        if result.status is not WorkflowStatus.COMPLETED:
            await self._fail(
                run,
                WorkflowNode.INTERNAL_DECISION_PACKAGE_ASSEMBLY,
                "Internal Decision Package assembly failed safely: "
                + "; ".join(result.validation_errors),
            )
            return
        packages = tuple(
            item
            for item in result.generated_artifacts
            if item.artifact_type is ArtifactType.INTERNAL_DECISION_PACKAGE
            and item.validation_status
            in {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}
        )
        if len(packages) != 1 or result.package is None:
            await self._fail(
                run,
                WorkflowNode.INTERNAL_DECISION_PACKAGE_ASSEMBLY,
                "Internal Decision Package assembly did not return one exact "
                "validated package.",
            )
            return
        package_artifact = packages[0]
        package = InternalDecisionPackage.model_validate(package_artifact.payload)
        if (
            package != result.package
            or package.assembly_path is not assembly_path
            or package.source_artifact_ids
            != tuple(item.artifact_id for item in source_artifacts)
        ):
            await self._fail(
                run,
                WorkflowNode.INTERNAL_DECISION_PACKAGE_ASSEMBLY,
                "Internal Decision Package output differs from its exact branch inputs.",
            )
            return
        await self._event(
            run,
            "INTERNAL_DECISION_PACKAGE_READY",
            WorkflowNode.INTERNAL_DECISION_PACKAGE_READY,
            {
                "package_id": package.package_id,
                "package_artifact_id": package_artifact.artifact_id,
                "assembly_path": package.assembly_path.value,
                "recommendation_performed": False,
                "approval_requested": False,
                "external_action_performed": False,
            },
        )
        await self._run_final_risk_check(
            run=run,
            package_artifact=package_artifact,
        )

    async def _run_final_risk_check(
        self,
        *,
        run: CaseWorkflowRun,
        package_artifact: ArtifactEnvelope,
    ) -> None:
        """Run Final Risk from one ready package, then finish at its own milestone."""
        if run.evaluation_case_id is None:  # pragma: no cover - package guard
            raise RuntimeError("Final Risk Check requires an evaluation case ID.")
        run = await self._require_run(run.workflow_run_id)
        run = await self._save_run(
            run,
            status=WorkflowStatus.RUNNING,
            current_stage=WorkflowNode.FINAL_RISK_CHECK.value,
            pending_request_ids=(),
            failure_reason=None,
        )
        identity_inputs = (
            package_artifact.artifact_id,
            package_artifact.version,
            package_artifact.input_hash,
        )
        expected_hash = self._node_input_hash(
            run,
            WorkflowNode.FINAL_RISK_CHECK,
            identity_inputs,
        )
        existing = await self._workflows.get_node(
            run.workflow_run_id,
            WorkflowNode.FINAL_RISK_CHECK.value,
        )
        should_finish_node = not (
            self._node_completed(existing)
            and existing is not None
            and existing.input_hash == expected_hash
        )
        node = (
            await self._start_node(
                run,
                WorkflowNode.FINAL_RISK_CHECK,
                identity_inputs=identity_inputs,
            )
            if should_finish_node
            else existing
        )
        if node is None:  # pragma: no cover - guarded by branch above
            raise RuntimeError("Final Risk Check node was not initialized.")

        result = await self._services.final_risk_check(
            evaluation_case_id=run.evaluation_case_id,
            workflow_run_id=run.workflow_run_id,
            internal_decision_package_artifact_id=package_artifact.artifact_id,
        )
        if should_finish_node:
            await self._finish_node(
                node,
                self._result_node_status(result.status, result.component_status),
                result.generated_artifacts,
                waiting_for=(),
                failure_reason="; ".join(result.validation_errors) or None,
            )
        if result.status is not WorkflowStatus.COMPLETED:
            await self._fail(
                run,
                WorkflowNode.FINAL_RISK_CHECK,
                "Final Risk Check failed safely: "
                + "; ".join(result.validation_errors),
            )
            return

        assessments = tuple(
            item
            for item in result.generated_artifacts
            if item.artifact_type is ArtifactType.FINAL_RISK_ASSESSMENT
            and item.validation_status
            in {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}
        )
        if len(assessments) != 1 or result.assessment is None:
            await self._fail(
                run,
                WorkflowNode.FINAL_RISK_CHECK,
                "Final Risk Check did not return one exact validated assessment.",
            )
            return
        assessment_artifact = assessments[0]
        assessment = FinalRiskAssessment.model_validate(
            assessment_artifact.payload
        )
        if (
            assessment != result.assessment
            or assessment_artifact.input_artifact_ids
            != (package_artifact.artifact_id,)
            or assessment.internal_decision_package_artifact_id
            != package_artifact.artifact_id
            or assessment.internal_decision_package_artifact_version
            != package_artifact.version
            or assessment.internal_decision_package_input_hash
            != package_artifact.input_hash
        ):
            await self._fail(
                run,
                WorkflowNode.FINAL_RISK_CHECK,
                "Final Risk output differs from its exact Internal Decision Package input.",
            )
            return

        prior_events = await self._events.list_after(run.workflow_run_id, 0)
        event_already_recorded = any(
            item.event_type == "FINAL_RISK_CHECK_COMPLETED"
            and item.node is WorkflowNode.FINAL_RISK_READY
            and item.metadata.get("assessment_artifact_id")
            == assessment_artifact.artifact_id
            for item in prior_events
        )
        if not event_already_recorded:
            await self._event(
                run,
                "FINAL_RISK_CHECK_COMPLETED",
                WorkflowNode.FINAL_RISK_READY,
                {
                    "assessment_id": assessment.assessment_id,
                    "assessment_artifact_id": assessment_artifact.artifact_id,
                    "source_internal_decision_package_artifact_id": (
                        package_artifact.artifact_id
                    ),
                    "assessment_status": assessment.assessment_status.value,
                    "residual_risk_level": assessment.residual_risk_level.value,
                    "major_exception_status": (
                        assessment.major_exception_status.value
                    ),
                    "unresolved_approval_gate_count": len(
                        assessment.unresolved_approval_gates
                    ),
                    "required_control_count": len(
                        assessment.required_controls
                    ),
                    "approval_requested": False,
                    "external_action_performed": False,
                },
            )
        await self._run_decision_card_flow(
            run=run,
            final_risk_artifact=assessment_artifact,
        )

    async def _run_decision_card_flow(
        self,
        *,
        run: CaseWorkflowRun,
        final_risk_artifact: ArtifactEnvelope,
    ) -> None:
        """Compose one guarded Card, then trigger its dedicated Founder gate."""
        if run.evaluation_case_id is None:  # pragma: no cover - Final Risk guard
            raise RuntimeError("Decision Card requires an evaluation case ID.")
        run = await self._require_run(run.workflow_run_id)
        run = await self._save_run(
            run,
            status=WorkflowStatus.RUNNING,
            current_stage=WorkflowNode.DECISION_CARD_COMPOSITION.value,
            pending_request_ids=(),
            failure_reason=None,
        )
        identity_inputs = (
            final_risk_artifact.artifact_id,
            final_risk_artifact.version,
            final_risk_artifact.input_hash,
            self._services.decision_analysis_configuration_hash,
        )
        expected_hash = self._node_input_hash(
            run,
            WorkflowNode.DECISION_CARD_COMPOSITION,
            identity_inputs,
        )
        existing = await self._workflows.get_node(
            run.workflow_run_id,
            WorkflowNode.DECISION_CARD_COMPOSITION.value,
        )
        same_completed_input = (
            existing is not None
            and existing.input_hash == expected_hash
            and self._node_completed(existing)
        )
        bundle = await self._load_reusable_decision_bundle(
            run=run,
            node=existing,
            expected_hash=expected_hash,
            final_risk_artifact=final_risk_artifact,
        )
        if bundle is not None:
            analysis_artifact = bundle.analysis_artifact
            analysis = bundle.analysis
            card_artifact = bundle.card_artifact
            card = bundle.card
            if (
                existing is not None
                and existing.status is WorkflowNodeStatus.FAILED_SAFE
            ):
                recovered_status = (
                    WorkflowNodeStatus.COMPLETED_WITH_WARNINGS
                    if ValidationStatus.VALID_WITH_WARNINGS
                    in {
                        analysis_artifact.validation_status,
                        card_artifact.validation_status,
                    }
                    else WorkflowNodeStatus.COMPLETED
                )
                await self._finish_node(
                    existing,
                    recovered_status,
                    (analysis_artifact, card_artifact),
                )
                await self._event(
                    run,
                    "DECISION_CARD_REPLAY_RECOVERED",
                    WorkflowNode.DECISION_CARD_COMPOSITION,
                    {
                        "analysis_artifact_id": analysis_artifact.artifact_id,
                        "decision_card_artifact_id": card_artifact.artifact_id,
                    },
                )
        else:
            if same_completed_input:
                await self._fail(
                    run,
                    WorkflowNode.DECISION_CARD_COMPOSITION,
                    "Completed Decision Card outputs cannot be reconciled with their "
                    "persisted node state.",
                )
                return
            node = await self._start_node(
                run,
                WorkflowNode.DECISION_CARD_COMPOSITION,
                identity_inputs=identity_inputs,
            )
            analysis_result = await self._services.decision_analysis(
                evaluation_case_id=run.evaluation_case_id,
                workflow_run_id=run.workflow_run_id,
                final_risk_artifact_id=final_risk_artifact.artifact_id,
            )
            analysis_artifacts = tuple(
                item
                for item in analysis_result.generated_artifacts
                if item.artifact_type is ArtifactType.AI_DECISION_ANALYSIS
                and item.validation_status
                in {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}
            )
            if (
                analysis_result.status is not WorkflowStatus.COMPLETED
                or analysis_result.analysis is None
                or len(analysis_artifacts) != 1
            ):
                await self._finish_node(
                    node,
                    WorkflowNodeStatus.FAILED_SAFE,
                    analysis_result.generated_artifacts,
                    failure_reason="; ".join(analysis_result.validation_errors)
                    or "Decision analysis did not return one exact artifact.",
                )
                await self._fail(
                    run,
                    WorkflowNode.DECISION_CARD_COMPOSITION,
                    "Decision analysis failed safely: "
                    + "; ".join(analysis_result.validation_errors),
                )
                return
            analysis_artifact = analysis_artifacts[0]
            card_result = await self._services.decision_card(
                evaluation_case_id=run.evaluation_case_id,
                workflow_run_id=run.workflow_run_id,
                analysis_artifact_id=analysis_artifact.artifact_id,
            )
            card_artifacts = tuple(
                item
                for item in card_result.generated_artifacts
                if item.artifact_type is ArtifactType.DECISION_CARD
                and item.validation_status
                in {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}
            )
            if (
                card_result.status is not WorkflowStatus.COMPLETED
                or card_result.decision_card is None
                or len(card_artifacts) != 1
            ):
                await self._finish_node(
                    node,
                    WorkflowNodeStatus.FAILED_SAFE,
                    (
                        *analysis_result.generated_artifacts,
                        *card_result.generated_artifacts,
                    ),
                    failure_reason="; ".join(card_result.validation_errors)
                    or "Decision Card did not return one exact artifact.",
                )
                await self._fail(
                    run,
                    WorkflowNode.DECISION_CARD_COMPOSITION,
                    "Decision Card failed safely: "
                    + "; ".join(card_result.validation_errors),
                )
                return
            card_artifact = card_artifacts[0]
            card = DecisionCard.model_validate(card_artifact.payload)
            analysis = analysis_result.analysis
            if (
                card != card_result.decision_card
                or card_artifact.input_artifact_ids
                != (analysis_artifact.artifact_id,)
                or card.ai_analysis_artifact.artifact_id
                != analysis_artifact.artifact_id
                or card.final_risk_artifact.artifact_id
                != final_risk_artifact.artifact_id
            ):
                await self._fail(
                    run,
                    WorkflowNode.DECISION_CARD_COMPOSITION,
                    "Decision Card differs from its exact analysis and Final Risk inputs.",
                )
                return
            component_status = (
                ComponentStatus.COMPLETED_WITH_WARNINGS
                if ComponentStatus.COMPLETED_WITH_WARNINGS
                in {analysis_result.component_status, card_result.component_status}
                else ComponentStatus.COMPLETED
            )
            await self._finish_node(
                node,
                self._component_node_status(component_status),
                (*analysis_result.generated_artifacts, *card_result.generated_artifacts),
            )
        if (
            analysis.source is not DecisionAnalysisSource.OPENAI
            and card.recommendation is not DecisionRecommendation.NOT_EVALUABLE
        ):
            await self._fail(
                run,
                WorkflowNode.DECISION_CARD_COMPOSITION,
                "Only an OpenAI analysis may produce an approvable Decision Card.",
            )
            return
        prior_events = await self._events.list_after(run.workflow_run_id, 0)
        if not any(
            item.event_type == "DECISION_CARD_READY"
            and item.metadata.get("decision_card_artifact_id")
            == card_artifact.artifact_id
            for item in prior_events
        ):
            await self._event(
                run,
                "DECISION_CARD_READY",
                WorkflowNode.DECISION_CARD_READY,
                {
                    "decision_card_id": card.decision_card_id,
                    "decision_card_artifact_id": card_artifact.artifact_id,
                    "recommendation": card.recommendation.value,
                    "condition_count": len(card.conditions),
                    "founder_decision_recorded": False,
                    "approval_requested": False,
                    "external_action_performed": False,
                },
            )
        if card.recommendation is DecisionRecommendation.NOT_EVALUABLE:
            await self._event(
                run,
                "DECISION_NOT_EVALUABLE",
                WorkflowNode.DECISION_CARD_READY,
                {
                    "decision_card_artifact_id": card_artifact.artifact_id,
                    "reason": "No approvable recommendation passed deterministic guardrails.",
                },
            )
            await self._complete(run, WorkflowNode.DECISION_CARD_READY)
            return
        await self._request_final_decision_approval(
            run=run,
            card_artifact=card_artifact,
            card=card,
        )

    async def _request_final_decision_approval(
        self,
        *,
        run: CaseWorkflowRun,
        card_artifact: ArtifactEnvelope,
        card: DecisionCard,
    ) -> None:
        """Open the final Founder gate once, then continue from its exact approval."""
        approved = await self._approved_request_for_subject(
            run=run,
            action=ProtectedAction.CONFIRM_FINAL_CONTRACT_DECISION,
            subject_artifact_id=card_artifact.artifact_id,
        )
        if approved is not None:
            await self._continue_authorized_final_decision(
                run=run,
                card_artifact=card_artifact,
                card=card,
                approval=approved,
            )
            return

        run = await self._save_run(
            run,
            status=WorkflowStatus.RUNNING,
            current_stage=WorkflowNode.FINAL_DECISION_APPROVAL.value,
            pending_request_ids=(),
            failure_reason=None,
        )
        approval_result = await self._services.request_workflow_protected_action(
            command=ActionCommand(
                action_type=ProtectedAction.CONFIRM_FINAL_CONTRACT_DECISION,
                evaluation_case_id=run.evaluation_case_id or "",
                payload_artifact_id=card_artifact.artifact_id,
                requested_by="CASE_WORKFLOW_ORCHESTRATOR",
                payload=final_decision_action_payload(card),
            ),
            workflow_run_id=run.workflow_run_id,
        )
        if approval_result.action_authorized:
            approval = approval_result.approval_request
            if approval is None or approval.status is not ApprovalRequestStatus.APPROVED:
                await self._fail(
                    run,
                    WorkflowNode.FINAL_DECISION_APPROVAL,
                    "Final Decision requires an exact affirmative Founder approval.",
                )
                return
            await self._continue_authorized_final_decision(
                run=run,
                card_artifact=card_artifact,
                card=card,
                approval=approval,
            )
            return
        refreshed = await self._require_run(run.workflow_run_id)
        if refreshed.status in {
            WorkflowStatus.WAITING_FOR_APPROVAL,
            WorkflowStatus.WAITING_FOR_INPUT,
            WorkflowStatus.COMPLETED,
            WorkflowStatus.BLOCKED,
        }:
            return
        await self._fail(
            refreshed,
            WorkflowNode.FINAL_DECISION_APPROVAL,
            "Final Decision was neither authorized nor paused by Governance.",
        )

    async def _continue_authorized_final_decision(
        self,
        *,
        run: CaseWorkflowRun,
        card_artifact: ArtifactEnvelope,
        card: DecisionCard,
        approval: ApprovalRequest,
    ) -> None:
        """Record the final approval once and enter the deterministic post-update."""
        refreshed = await self._require_run(run.workflow_run_id)
        refreshed = await self._save_run(
            refreshed,
            status=WorkflowStatus.RUNNING,
            current_stage=WorkflowNode.POST_DECISION_UPDATE.value,
            pending_request_ids=(),
            failure_reason=None,
        )
        await self._event_once(
            refreshed,
            "FINAL_DECISION_AUTHORIZED",
            WorkflowNode.FINAL_DECISION_APPROVAL,
            "approval_request_id",
            approval.request_id,
            {
                "approval_request_id": approval.request_id,
                "decision_card_artifact_id": card_artifact.artifact_id,
                "recommendation": card.recommendation.value,
            },
        )
        await self._run_post_decision_update(
            run=refreshed,
            card_artifact=card_artifact,
            approval_request_id=approval.request_id,
        )

    async def _run_post_decision_update(
        self,
        *,
        run: CaseWorkflowRun,
        card_artifact: ArtifactEnvelope,
        approval_request_id: str,
    ) -> None:
        """Persist the approved outcome and route its exact deterministic branch."""
        if run.evaluation_case_id is None:  # pragma: no cover
            raise RuntimeError("Post-decision update requires an evaluation case.")
        identity_inputs = (card_artifact.artifact_id, approval_request_id)
        expected_hash = self._node_input_hash(
            run,
            WorkflowNode.POST_DECISION_UPDATE,
            identity_inputs,
        )
        existing = await self._workflows.get_node(
            run.workflow_run_id,
            WorkflowNode.POST_DECISION_UPDATE.value,
        )
        reusable = await self._initial_post_decision_update(
            run=run,
            card_artifact=card_artifact,
            approval_request_id=approval_request_id,
        )
        if reusable is not None:
            update_artifact, update = reusable
            if (
                existing is not None
                and existing.input_hash == expected_hash
                and existing.status is WorkflowNodeStatus.FAILED_SAFE
            ):
                await self._finish_node(
                    existing,
                    WorkflowNodeStatus.COMPLETED,
                    (update_artifact,),
                )
            await self._event_once(
                run,
                "POST_DECISION_UPDATE_COMPLETED",
                WorkflowNode.POST_DECISION_UPDATE,
                "update_artifact_id",
                update_artifact.artifact_id,
                {
                    "update_id": update.update_id,
                    "update_artifact_id": update_artifact.artifact_id,
                    "outcome": update.outcome.value,
                    "external_document_release_required": (
                        update.external_document_release_required
                    ),
                },
            )
            await self._route_post_decision_update(
                run=run,
                card_artifact=card_artifact,
                update_artifact=update_artifact,
                update=update,
            )
            return
        node = await self._start_node(
            run,
            WorkflowNode.POST_DECISION_UPDATE,
            identity_inputs=identity_inputs,
        )
        result = await self._services.post_decision_update(
            evaluation_case_id=run.evaluation_case_id,
            workflow_run_id=run.workflow_run_id,
            decision_card_artifact_id=card_artifact.artifact_id,
            approval_request_id=approval_request_id,
        )
        await self._finish_node(
            node,
            self._result_node_status(result.status, result.component_status),
            result.generated_artifacts,
            failure_reason="; ".join(result.validation_errors) or None,
        )
        updates = tuple(
            item
            for item in result.generated_artifacts
            if item.artifact_type is ArtifactType.POST_DECISION_UPDATE
            and item.validation_status
            in {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}
        )
        if (
            result.status is not WorkflowStatus.COMPLETED
            or result.update is None
            or len(updates) != 1
        ):
            await self._fail(
                run,
                WorkflowNode.POST_DECISION_UPDATE,
                "Post-decision update failed safely: "
                + "; ".join(result.validation_errors),
            )
            return
        update_artifact = updates[0]
        update = PostDecisionUpdate.model_validate(update_artifact.payload)
        if (
            update != result.update
            or update_artifact.input_artifact_ids != (card_artifact.artifact_id,)
            or update.decision_card_artifact.artifact_id
            != card_artifact.artifact_id
        ):
            await self._fail(
                run,
                WorkflowNode.POST_DECISION_UPDATE,
                "Post-decision update differs from its exact approved Card.",
            )
            return
        await self._event_once(
            run,
            "POST_DECISION_UPDATE_COMPLETED",
            WorkflowNode.POST_DECISION_UPDATE,
            "update_artifact_id",
            update_artifact.artifact_id,
            {
                "update_id": update.update_id,
                "update_artifact_id": update_artifact.artifact_id,
                "outcome": update.outcome.value,
                "external_document_release_required": (
                    update.external_document_release_required
                ),
            },
        )
        await self._route_post_decision_update(
            run=run,
            card_artifact=card_artifact,
            update_artifact=update_artifact,
            update=update,
        )

    async def _route_post_decision_update(
        self,
        *,
        run: CaseWorkflowRun,
        card_artifact: ArtifactEnvelope,
        update_artifact: ArtifactEnvelope,
        update: PostDecisionUpdate,
    ) -> None:
        """Route an already-validated post-decision update without recreating it."""
        if update.outcome is PostDecisionOutcome.NEGOTIATION_AUTHORIZED:
            await self._run_negotiation_flow(
                run=run,
                card_artifact=card_artifact,
                update_artifact=update_artifact,
            )
            return
        if update.outcome is PostDecisionOutcome.CASE_CLOSED_NO_EXTERNAL_ACTION:
            await self._complete(run, WorkflowNode.FINAL_DECISION_NOT_ACCEPTED)
            return
        if update.document_release_package is None:
            await self._complete(run, WorkflowNode.FINAL_DECISION_ACCEPTED)
            return
        await self._run_external_submission_proposal(
            run=run,
            update_artifact=update_artifact,
        )

    async def _run_negotiation_flow(
        self,
        *,
        run: CaseWorkflowRun,
        card_artifact: ArtifactEnvelope,
        update_artifact: ArtifactEnvelope,
    ) -> None:
        """Recover or advance the single conditional-negotiation round."""
        terms_node = await self._workflows.get_node(
            run.workflow_run_id, WorkflowNode.NEGOTIATION_TERMS_SENT.value
        )
        if not self._node_completed(terms_node):
            request_id = deterministic_id(
                "NTS", run.workflow_run_id, card_artifact.artifact_id
            )
            if terms_node is None or terms_node.status is not WorkflowNodeStatus.WAITING_FOR_INPUT:
                terms_node = await self._start_node(
                    run,
                    WorkflowNode.NEGOTIATION_TERMS_SENT,
                    identity_inputs=(card_artifact.artifact_id, card_artifact.input_hash),
                )
                await self._finish_node(
                    terms_node,
                    WorkflowNodeStatus.WAITING_FOR_INPUT,
                    (),
                    waiting_for=(request_id,),
                )
            await self._save_run(
                run,
                status=WorkflowStatus.WAITING_FOR_INPUT,
                current_stage=WorkflowNode.NEGOTIATION_TERMS_SENT.value,
                pending_request_ids=(request_id,),
                resume_stage=WorkflowNode.NEGOTIATION_TERMS_SENT.value,
                failure_reason=None,
            )
            return

        await self._route_after_negotiation_terms_sent(
            run=run,
            update_artifact=update_artifact,
        )

    async def _route_after_negotiation_terms_sent(
        self,
        *,
        run: CaseWorkflowRun,
        update_artifact: ArtifactEnvelope,
    ) -> None:
        """Continue from sent conditional terms without a customer-response form."""
        update = PostDecisionUpdate.model_validate(update_artifact.payload)
        if update.outcome is not PostDecisionOutcome.NEGOTIATION_AUTHORIZED:
            await self._fail(
                run,
                WorkflowNode.NEGOTIATION_TERMS_SENT,
                "Negotiation terms can continue only from an authorized negotiation route.",
            )
            return
        if not update.external_document_release_required:
            await self._complete(run, WorkflowNode.FINAL_DECISION_ACCEPTED)
            return
        await self._run_external_submission_proposal(
            run=run,
            update_artifact=update_artifact,
        )

    async def _run_external_submission_proposal(
        self,
        *,
        run: CaseWorkflowRun,
        update_artifact: ArtifactEnvelope,
    ) -> None:
        """Create a governed proposal and stop at connector-safe readiness."""
        if run.evaluation_case_id is None:  # pragma: no cover
            raise RuntimeError("External submission proposal requires a case.")
        run = await self._save_run(
            run,
            status=WorkflowStatus.RUNNING,
            current_stage=(
                WorkflowNode.EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL.value
            ),
            pending_request_ids=(),
            failure_reason=None,
        )
        reusable = await self._external_submission_proposal_for_update(
            run=run,
            update_artifact=update_artifact,
        )
        if reusable is not None:
            proposal_artifact, proposal = reusable
            await self._continue_external_submission_proposal(
                run=run,
                proposal_artifact=proposal_artifact,
                proposal=proposal,
            )
            return
        node = await self._start_node(
            run,
            WorkflowNode.EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL,
            identity_inputs=(
                update_artifact.artifact_id,
                update_artifact.version,
                update_artifact.input_hash,
            ),
        )
        result = await self._services.external_document_submission_proposal(
            evaluation_case_id=run.evaluation_case_id,
            workflow_run_id=run.workflow_run_id,
            post_decision_update_artifact_id=update_artifact.artifact_id,
        )
        await self._finish_node(
            node,
            self._result_node_status(result.status, result.component_status),
            result.generated_artifacts,
            failure_reason="; ".join(result.validation_errors) or None,
        )
        proposals = tuple(
            item
            for item in result.generated_artifacts
            if item.artifact_type
            is ArtifactType.EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL
            and item.validation_status
            in {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}
        )
        if (
            result.status is not WorkflowStatus.COMPLETED
            or result.proposal is None
            or len(proposals) != 1
        ):
            await self._fail(
                run,
                WorkflowNode.EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL,
                "External submission proposal failed safely: "
                + "; ".join(result.validation_errors),
            )
            return
        proposal_artifact = proposals[0]
        proposal = ExternalDocumentSubmissionProposal.model_validate(
            proposal_artifact.payload
        )
        expected_proposal_inputs = proposal.source_artifact_ids
        if (
            proposal != result.proposal
            or proposal_artifact.input_artifact_ids != expected_proposal_inputs
            or expected_proposal_inputs[0] != update_artifact.artifact_id
            or proposal.post_decision_update_artifact.artifact_id
            != update_artifact.artifact_id
        ):
            await self._fail(
                run,
                WorkflowNode.EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL,
                "External submission proposal differs from its exact approved update.",
            )
            return
        await self._continue_external_submission_proposal(
            run=run,
            proposal_artifact=proposal_artifact,
            proposal=proposal,
        )

    async def _continue_external_submission_proposal(
        self,
        *,
        run: CaseWorkflowRun,
        proposal_artifact: ArtifactEnvelope,
        proposal: ExternalDocumentSubmissionProposal,
    ) -> None:
        """Reuse one external proposal and wait for, or consume, its exact approval."""
        approval = await self._approved_request_for_subject(
            run=run,
            action=ProtectedAction.SEND_DOCUMENT_TO_EXTERNAL_PARTNER,
            subject_artifact_id=proposal_artifact.artifact_id,
        )
        if approval is None:
            approval_result = await self._services.request_workflow_protected_action(
                command=ActionCommand(
                    action_type=ProtectedAction.SEND_DOCUMENT_TO_EXTERNAL_PARTNER,
                    evaluation_case_id=run.evaluation_case_id or "",
                    payload_artifact_id=proposal_artifact.artifact_id,
                    requested_by="CASE_WORKFLOW_ORCHESTRATOR",
                    payload=external_document_release_action_payload(proposal),
                ),
                workflow_run_id=run.workflow_run_id,
            )
            if not approval_result.action_authorized:
                refreshed = await self._require_run(run.workflow_run_id)
                if refreshed.status in {
                    WorkflowStatus.WAITING_FOR_APPROVAL,
                    WorkflowStatus.WAITING_FOR_INPUT,
                    WorkflowStatus.COMPLETED,
                    WorkflowStatus.BLOCKED,
                }:
                    return
                await self._fail(
                    refreshed,
                    WorkflowNode.EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL,
                    "External submission was neither authorized nor paused by Governance.",
                )
                return
            approval = approval_result.approval_request
            if approval is None or approval.status is not ApprovalRequestStatus.APPROVED:
                await self._fail(
                    run,
                    WorkflowNode.EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL,
                    "External submission requires exact affirmative authorization.",
                )
                return
        await self._complete_external_submission_readiness(
            run=run,
            proposal_artifact=proposal_artifact,
            proposal=proposal,
            approval=approval,
        )

    async def _complete_external_submission_readiness(
        self,
        *,
        run: CaseWorkflowRun,
        proposal_artifact: ArtifactEnvelope,
        proposal: ExternalDocumentSubmissionProposal,
        approval: ApprovalRequest,
    ) -> None:
        """Create connector-safe readiness exactly once after external approval."""
        refreshed = await self._require_run(run.workflow_run_id)
        readiness_node = await self._workflows.get_node(
            refreshed.workflow_run_id,
            WorkflowNode.READY_FOR_EXTERNAL_SUBMISSION.value,
        )
        if self._node_completed(readiness_node):
            await self._complete(refreshed, WorkflowNode.READY_FOR_EXTERNAL_SUBMISSION)
            return
        readiness_node = await self._start_node(
            refreshed,
            WorkflowNode.READY_FOR_EXTERNAL_SUBMISSION,
            identity_inputs=(proposal_artifact.artifact_id, approval.request_id),
        )
        readiness_result = await self._services.external_submission_readiness(
            evaluation_case_id=run.evaluation_case_id or "",
            workflow_run_id=run.workflow_run_id,
            proposal_artifact_id=proposal_artifact.artifact_id,
            approval_request_id=approval.request_id,
        )
        await self._finish_node(
            readiness_node,
            self._result_node_status(
                readiness_result.status,
                readiness_result.component_status,
            ),
            readiness_result.generated_artifacts,
            failure_reason="; ".join(readiness_result.validation_errors) or None,
        )
        readiness = readiness_result.readiness
        if (
            readiness_result.status is not WorkflowStatus.COMPLETED
            or readiness is None
            or readiness_result.generated_artifacts
            or readiness.adapter_invoked
            or readiness.submission_receipt_created
            or readiness.external_submission_performed
        ):
            await self._fail(
                refreshed,
                WorkflowNode.READY_FOR_EXTERNAL_SUBMISSION,
                "External readiness failed or claimed an unsupported connector action.",
            )
            return
        await self._event_once(
            refreshed,
            "READY_FOR_EXTERNAL_SUBMISSION",
            WorkflowNode.READY_FOR_EXTERNAL_SUBMISSION,
            "proposal_artifact_id",
            proposal_artifact.artifact_id,
            {
                "readiness_id": readiness.readiness_id,
                "proposal_artifact_id": proposal_artifact.artifact_id,
                "approval_request_id": approval.request_id,
                "recipient": proposal.recipient,
                "external_submission_performed": False,
                "submission_receipt_created": False,
            },
        )
        await self._complete(refreshed, WorkflowNode.READY_FOR_EXTERNAL_SUBMISSION)

    async def _internal_decision_source_artifacts(
        self,
        *,
        evaluation_case_id: str,
        assembly_path: InternalDecisionAssemblyPath,
        approval_request_id: str | None,
    ) -> tuple[tuple[ArtifactEnvelope, ...], tuple[object, ...]]:
        """Resolve only explicit, validated artifacts required by one path."""
        artifacts = await self._artifacts.list_by_case(evaluation_case_id)
        required_types: list[ArtifactType] = [
            ArtifactType.EVALUATION_CASE,
            ArtifactType.FINANCE_FACTS,
            ArtifactType.FINANCE_ASSESSMENT,
            ArtifactType.OPERATIONS_FACTS,
            ArtifactType.OPERATIONS_ASSESSMENT,
            ArtifactType.INITIAL_RISK_ASSESSMENT,
            ArtifactType.APPROVAL_CHECKPOINTS,
            ArtifactType.DECISION_ROUTE_PLAN,
        ]
        if assembly_path is not InternalDecisionAssemblyPath.DIRECT_ROUTE:
            required_types.extend(
                (
                    ArtifactType.BANKING_DISCOVERY_REQUEST,
                    ArtifactType.BANKING_OPTION_MATRIX,
                    ArtifactType.BANKING_DISCOVERY_RESULT,
                    ArtifactType.BANKING_PRECHECK_READINESS,
                    ArtifactType.DECISION_POST_BANKING_REVIEW,
                )
            )
        if assembly_path is InternalDecisionAssemblyPath.BANKING_PRECHECK_DECLINED:
            required_types.append(
                ArtifactType.BANKING_PRECHECK_SUBMISSION_PROPOSAL
            )
        if assembly_path in {
            InternalDecisionAssemblyPath.BANKING_NON_ACTIONABLE,
            InternalDecisionAssemblyPath.CONDITIONAL_DOCUMENT_READY,
        }:
            required_types.extend(
                (
                    ArtifactType.BANKING_PRECHECK_SUBMISSION_PROPOSAL,
                    ArtifactType.BANKING_PRECHECK_RESULT_SET,
                    ArtifactType.DECISION_POST_PRECHECK_REVIEW,
                )
            )
        if (
            assembly_path
            is InternalDecisionAssemblyPath.CONDITIONAL_DOCUMENT_READY
        ):
            required_types.extend(
                (
                    ArtifactType.DOCUMENT_PREPARATION_REQUEST,
                    ArtifactType.DOCUMENT_RELEASE_PACKAGE,
                )
            )

        selected: list[ArtifactEnvelope] = []
        identity: list[object] = [assembly_path, approval_request_id]
        for artifact_type in required_types:
            artifact = (
                self._latest_risk_checkpoint_registry(artifacts)
                if artifact_type is ArtifactType.APPROVAL_CHECKPOINTS
                else self._latest_validated(artifacts, artifact_type)
            )
            identity.append(
                (
                    artifact_type,
                    artifact.artifact_id,
                    artifact.version,
                    artifact.input_hash,
                )
                if artifact is not None
                else (artifact_type, None)
            )
            if artifact is not None:
                selected.append(artifact)
            if artifact_type is ArtifactType.BANKING_DISCOVERY_RESULT:
                matrix_artifact = next(
                    (
                        item
                        for item in selected
                        if item.artifact_type is ArtifactType.BANKING_OPTION_MATRIX
                    ),
                    None,
                )
                advice = self._latest_advice_for_matrix(
                    artifacts,
                    matrix_artifact,
                )
                identity.append(
                    (
                        ArtifactType.BANKING_OPTION_ADVICE,
                        advice.artifact_id,
                        advice.version,
                        advice.input_hash,
                    )
                    if advice is not None
                    else (ArtifactType.BANKING_OPTION_ADVICE, None)
                )
                if advice is not None:
                    selected.append(advice)
        if approval_request_id is not None:
            approval = await self._approvals.get(approval_request_id)
            policy_artifact = (
                next(
                    (
                        item
                        for item in artifacts
                        if item.artifact_id == approval.policy_artifact_id
                        and item.artifact_type
                        is ArtifactType.APPROVAL_CHECKPOINTS
                        and item.validation_status
                        in {
                            ValidationStatus.VALID,
                            ValidationStatus.VALID_WITH_WARNINGS,
                        }
                    ),
                    None,
                )
                if approval is not None
                and approval.policy_artifact_id is not None
                else None
            )
            identity.append(
                (
                    "APPROVAL_POLICY_ARTIFACT",
                    policy_artifact.artifact_id,
                    policy_artifact.version,
                    policy_artifact.input_hash,
                )
                if policy_artifact is not None
                else ("APPROVAL_POLICY_ARTIFACT", None)
            )
            if (
                policy_artifact is not None
                and policy_artifact.artifact_id
                not in {item.artifact_id for item in selected}
            ):
                selected.append(policy_artifact)
        return tuple(selected), tuple(identity)

    async def summary(self, workflow_run_id: str) -> WorkflowRunSummary:
        """Build a compact status view from durable workflow and artifact state."""
        run = await self._require_run(workflow_run_id)
        nodes = await self._workflows.list_nodes(workflow_run_id)
        artifacts: tuple[ArtifactEnvelope, ...] = ()
        checkpoints = 0
        decision_route_outcome: DecisionRouteOutcome | None = None
        banking_discovery_request_id: str | None = None
        banking_discovery_status = None
        banking_discovery_result_id: str | None = None
        banking_option_matrix_id: str | None = None
        banking_option_advice_id: str | None = None
        banking_option_count = 0
        banking_input_supplement_id: str | None = None
        banking_precheck_readiness_id: str | None = None
        banking_precheck_readiness_status = None
        decision_post_banking_review_id: str | None = None
        decision_post_banking_outcome: DecisionPostBankingOutcome | None = None
        precheck_ready_option_ids: tuple[str, ...] = ()
        banking_precheck_submission_proposal_id: str | None = None
        banking_precheck_submission_candidate_ids: tuple[str, ...] = ()
        banking_precheck_result_set_id: str | None = None
        banking_precheck_normalized_result_ids: tuple[str, ...] = ()
        banking_precheck_outcomes = ()
        banking_precheck_eligibility_statuses = ()
        banking_precheck_guarantee_decisions = ()
        banking_precheck_supported_amounts: tuple[int | None, ...] = ()
        banking_precheck_currencies = ()
        banking_precheck_required_document_codes: tuple[tuple[str, ...], ...] = ()
        banking_precheck_approval_condition_codes: tuple[tuple[str, ...], ...] = ()
        banking_precheck_execution_mode = None
        banking_precheck_result_authority = None
        banking_precheck_external_bank_submission: bool | None = None
        banking_precheck_bank_approval_obtained: bool | None = None
        decision_post_precheck_review_id: str | None = None
        decision_post_precheck_outcome: DecisionPostPrecheckOutcome | None = None
        decision_post_precheck_candidate_option_ids: tuple[str, ...] = ()
        decision_post_precheck_candidate_product_ids: tuple[str, ...] = ()
        decision_post_precheck_conditional_option_ids: tuple[str, ...] = ()
        decision_post_precheck_inconclusive_option_ids: tuple[str, ...] = ()
        decision_post_precheck_evidence_required_option_ids: tuple[str, ...] = ()
        decision_post_precheck_not_eligible_option_ids: tuple[str, ...] = ()
        decision_post_precheck_unavailable_option_ids: tuple[str, ...] = ()
        document_preparation_request_ids: tuple[str, ...] = ()
        document_checklist_ids: tuple[str, ...] = ()
        document_package_draft_ids: tuple[str, ...] = ()
        document_package_readinesses = ()
        document_release_package_ids: tuple[str, ...] = ()
        document_evidence_supplement_ids: tuple[str, ...] = ()
        document_pending_codes = ()
        internal_decision_package_id: str | None = None
        internal_package: InternalDecisionPackage | None = None
        internal_decision_assembly_path: InternalDecisionAssemblyPath | None = None
        internal_decision_package_readiness = None
        internal_decision_source_artifact_ids: tuple[str, ...] = ()
        internal_decision_governance_reference_ids: tuple[str, ...] = ()
        final_risk_assessment_id: str | None = None
        final_risk_status = None
        final_residual_risk_level = None
        final_risk_conclusion = None
        final_major_exception = None
        final_unresolved_approval_gate_ids: tuple[str, ...] = ()
        final_required_control_codes = ()
        ai_decision_analysis_id: str | None = None
        ai_decision_analysis_source = None
        decision_card_id: str | None = None
        decision_recommendation = None
        decision_confidence = None
        decision_condition_ids: tuple[str, ...] = ()
        decision_selected_negotiation_strategy_ids: tuple[str, ...] = ()
        decision_selected_option_ids: tuple[str, ...] = ()
        post_decision_update_id: str | None = None
        post_decision_outcome: PostDecisionOutcome | None = None
        negotiation_outcome_id: str | None = None
        negotiation_outcome_status: NegotiationOutcomeStatus | None = None
        external_document_submission_proposal_id: str | None = None
        external_submission_authorized = False
        pending_approvals: tuple[str, ...] = ()
        if run.evaluation_case_id is not None:
            artifacts = await self._artifacts.list_by_case(run.evaluation_case_id)
            checkpoint_artifact = self._latest(
                artifacts, ArtifactType.APPROVAL_CHECKPOINTS
            )
            if checkpoint_artifact is not None:
                checkpoints = len(
                    ApprovalCheckpointSet.model_validate(
                        checkpoint_artifact.payload
                    ).checkpoints
                )
            route_artifact = self._latest(
                artifacts, ArtifactType.DECISION_ROUTE_PLAN
            )
            if route_artifact is not None:
                decision_route_outcome = DecisionRoutePlan.model_validate(
                    route_artifact.payload
                ).route_outcome
            banking_request_artifact = self._latest(
                artifacts, ArtifactType.BANKING_DISCOVERY_REQUEST
            )
            if banking_request_artifact is not None:
                banking_discovery_request_id = (
                    BankingDiscoveryRequest.model_validate(
                        banking_request_artifact.payload
                    ).request_id
                )
            banking_matrix_artifact = self._latest(
                artifacts, ArtifactType.BANKING_OPTION_MATRIX
            )
            if banking_matrix_artifact is not None:
                matrix = BankingOptionMatrix.model_validate(
                    banking_matrix_artifact.payload
                )
                banking_discovery_status = matrix.discovery_status
                banking_option_matrix_id = matrix.matrix_id
                banking_option_count = len(matrix.candidates)
            banking_result_artifact = self._latest(
                artifacts, ArtifactType.BANKING_DISCOVERY_RESULT
            )
            if banking_result_artifact is not None:
                banking_discovery_result_id = BankingDiscoveryResult.model_validate(
                    banking_result_artifact.payload
                ).result_id
            banking_advice_artifact = self._latest(
                artifacts, ArtifactType.BANKING_OPTION_ADVICE
            )
            if banking_advice_artifact is not None:
                banking_option_advice_id = BankingOptionAdvice.model_validate(
                    banking_advice_artifact.payload
                ).advice_id
            supplement_artifact = self._latest(
                artifacts, ArtifactType.BANKING_INPUT_SUPPLEMENT
            )
            if supplement_artifact is not None:
                banking_input_supplement_id = BankingInputSupplement.model_validate(
                    supplement_artifact.payload
                ).supplement_id
            readiness_artifact = self._latest(
                artifacts, ArtifactType.BANKING_PRECHECK_READINESS
            )
            if readiness_artifact is not None:
                readiness = BankingPrecheckReadiness.model_validate(
                    readiness_artifact.payload
                )
                banking_precheck_readiness_id = readiness.readiness_id
                banking_precheck_readiness_status = readiness.status
                precheck_ready_option_ids = readiness.ready_option_ids
            post_banking_artifact = self._latest(
                artifacts, ArtifactType.DECISION_POST_BANKING_REVIEW
            )
            if post_banking_artifact is not None:
                post_banking_review = DecisionPostBankingReview.model_validate(
                    post_banking_artifact.payload
                )
                decision_post_banking_review_id = post_banking_review.review_id
                decision_post_banking_outcome = post_banking_review.outcome
            proposal_artifact = self._latest(
                artifacts,
                ArtifactType.BANKING_PRECHECK_SUBMISSION_PROPOSAL,
            )
            if proposal_artifact is not None:
                proposal = BankingPrecheckSubmissionProposal.model_validate(
                    proposal_artifact.payload
                )
                banking_precheck_submission_proposal_id = proposal.proposal_id
                banking_precheck_submission_candidate_ids = (
                    proposal.candidate_option_ids
                )
            result_set_artifact = self._latest(
                artifacts,
                ArtifactType.BANKING_PRECHECK_RESULT_SET,
            )
            if result_set_artifact is not None:
                result_set = BankingPrecheckResultSet.model_validate(
                    result_set_artifact.payload
                )
                banking_precheck_result_set_id = result_set.result_set_id
                banking_precheck_normalized_result_ids = tuple(
                    item.normalized_result_id for item in result_set.results
                )
                banking_precheck_outcomes = tuple(
                    item.outcome for item in result_set.results
                )
                banking_precheck_eligibility_statuses = tuple(
                    item.eligibility_status for item in result_set.results
                )
                banking_precheck_guarantee_decisions = tuple(
                    item.guarantee_decision for item in result_set.results
                )
                banking_precheck_supported_amounts = tuple(
                    item.supported_amount for item in result_set.results
                )
                banking_precheck_currencies = tuple(
                    item.currency for item in result_set.results
                )
                banking_precheck_required_document_codes = tuple(
                    tuple(item.required_documents) for item in result_set.results
                )
                banking_precheck_approval_condition_codes = tuple(
                    tuple(item.approval_conditions) for item in result_set.results
                )
                banking_precheck_execution_mode = result_set.execution_mode
                banking_precheck_result_authority = result_set.authority
                banking_precheck_external_bank_submission = (
                    result_set.external_bank_submission
                )
                banking_precheck_bank_approval_obtained = (
                    result_set.bank_approval_obtained
                )
            post_precheck_artifact = self._latest(
                artifacts,
                ArtifactType.DECISION_POST_PRECHECK_REVIEW,
            )
            if post_precheck_artifact is not None:
                post_precheck = DecisionPostPrecheckReview.model_validate(
                    post_precheck_artifact.payload
                )
                decision_post_precheck_review_id = post_precheck.review_id
                decision_post_precheck_outcome = post_precheck.outcome
                decision_post_precheck_candidate_option_ids = (
                    post_precheck.candidate_option_ids
                )
                decision_post_precheck_candidate_product_ids = (
                    post_precheck.candidate_bank_product_ids
                )
                decision_post_precheck_conditional_option_ids = (
                    post_precheck.conditional_option_ids
                )
                decision_post_precheck_inconclusive_option_ids = (
                    post_precheck.no_recommendation_option_ids
                )
                decision_post_precheck_evidence_required_option_ids = (
                    post_precheck.evidence_required_option_ids
                )
                decision_post_precheck_not_eligible_option_ids = (
                    post_precheck.not_eligible_option_ids
                )
                decision_post_precheck_unavailable_option_ids = (
                    post_precheck.unavailable_option_ids
                )
            document_request_artifacts = tuple(
                item
                for item in artifacts
                if item.artifact_type
                is ArtifactType.DOCUMENT_PREPARATION_REQUEST
                and item.validation_status
                in {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}
            )
            document_preparation_request_ids = tuple(
                DocumentPreparationRequest.model_validate(item.payload).request_id
                for item in sorted(
                    document_request_artifacts,
                    key=lambda item: (item.version, item.artifact_id),
                )
            )
            checklist_artifact = self._latest(
                artifacts, ArtifactType.DOCUMENT_CHECKLIST
            )
            if checklist_artifact is not None:
                checklist = DocumentChecklist.model_validate(
                    checklist_artifact.payload
                )
                document_checklist_ids = (checklist.checklist_id,)
                document_pending_codes = checklist.missing_document_codes
            package_artifact = self._latest(
                artifacts, ArtifactType.DOCUMENT_PACKAGE_DRAFT
            )
            if package_artifact is not None:
                package = DocumentPackageDraft.model_validate(
                    package_artifact.payload
                )
                document_package_draft_ids = (package.package_draft_id,)
                document_package_readinesses = (package.readiness,)
            release_artifact = self._latest(
                artifacts, ArtifactType.DOCUMENT_RELEASE_PACKAGE
            )
            if release_artifact is not None:
                release = DocumentReleasePackage.model_validate(
                    release_artifact.payload
                )
                document_release_package_ids = (release.release_package_id,)
            document_evidence_supplement_ids = tuple(
                DocumentEvidenceSupplement.model_validate(item.payload).supplement_id
                for item in sorted(
                    (
                        item
                        for item in artifacts
                        if item.artifact_type
                        is ArtifactType.DOCUMENT_EVIDENCE_SUPPLEMENT
                        and item.validation_status
                        in {
                            ValidationStatus.VALID,
                            ValidationStatus.VALID_WITH_WARNINGS,
                        }
                    ),
                    key=lambda item: (item.version, item.artifact_id),
                )
            )
            internal_package_artifact = self._latest_validated(
                artifacts, ArtifactType.INTERNAL_DECISION_PACKAGE
            )
            if internal_package_artifact is not None:
                internal_package = InternalDecisionPackage.model_validate(
                    internal_package_artifact.payload
                )
                internal_decision_package_id = internal_package.package_id
                internal_decision_assembly_path = internal_package.assembly_path
                internal_decision_package_readiness = internal_package.readiness
                internal_decision_source_artifact_ids = (
                    internal_package.source_artifact_ids
                )
                internal_decision_governance_reference_ids = (
                    internal_package.governance_reference_ids
                )
            final_risk_artifact = self._latest_validated(
                artifacts, ArtifactType.FINAL_RISK_ASSESSMENT
            )
            if (
                final_risk_artifact is not None
                and internal_package_artifact is not None
                and internal_package is not None
            ):
                final_risk = FinalRiskAssessment.model_validate(
                    final_risk_artifact.payload
                )
                final_risk_is_current = (
                    final_risk_artifact.input_artifact_ids
                    == (internal_package_artifact.artifact_id,)
                    and final_risk.internal_decision_package_artifact_id
                    == internal_package_artifact.artifact_id
                    and final_risk.internal_decision_package_artifact_version
                    == internal_package_artifact.version
                    and final_risk.internal_decision_package_input_hash
                    == internal_package_artifact.input_hash
                    and final_risk.internal_decision_package_id
                    == internal_package.package_id
                )
                if final_risk_is_current:
                    final_risk_assessment_id = final_risk.assessment_id
                    final_risk_status = final_risk.assessment_status
                    final_residual_risk_level = final_risk.residual_risk_level
                    final_risk_conclusion = final_risk.conclusion
                    final_major_exception = final_risk.major_exception_status
                    final_unresolved_approval_gate_ids = (
                        final_risk.unresolved_approval_gate_ids
                    )
                    final_required_control_codes = tuple(
                        dict.fromkeys(
                            item.code for item in final_risk.required_controls
                        )
                    )
            analysis_artifact = self._latest_validated(
                artifacts, ArtifactType.AI_DECISION_ANALYSIS
            )
            analysis: AIDecisionAnalysis | None = None
            if analysis_artifact is not None and final_risk_artifact is not None:
                candidate_analysis = AIDecisionAnalysis.model_validate(
                    analysis_artifact.payload
                )
                if (
                    analysis_artifact.input_artifact_ids
                    == (final_risk_artifact.artifact_id,)
                    and candidate_analysis.final_risk_artifact.artifact_id
                    == final_risk_artifact.artifact_id
                ):
                    analysis = candidate_analysis
                    ai_decision_analysis_id = analysis.analysis_id
                    ai_decision_analysis_source = analysis.source
            decision_card_artifact = self._latest_validated(
                artifacts, ArtifactType.DECISION_CARD
            )
            decision_card: DecisionCard | None = None
            if decision_card_artifact is not None and analysis_artifact is not None:
                candidate_card = DecisionCard.model_validate(
                    decision_card_artifact.payload
                )
                if (
                    decision_card_artifact.input_artifact_ids
                    == (analysis_artifact.artifact_id,)
                    and candidate_card.ai_analysis_artifact.artifact_id
                    == analysis_artifact.artifact_id
                ):
                    decision_card = candidate_card
                    decision_card_id = decision_card.decision_card_id
                    decision_recommendation = decision_card.recommendation
                    decision_confidence = decision_card.confidence
                    decision_condition_ids = tuple(
                        item.condition_id for item in decision_card.conditions
                    )
                    decision_selected_negotiation_strategy_ids = (
                        decision_card.selected_negotiation_strategy_ids
                    )
                    decision_selected_option_ids = (
                        decision_card.selected_option_ids
                    )
            post_update_artifact = self._latest_validated(
                artifacts, ArtifactType.POST_DECISION_UPDATE
            )
            post_update: PostDecisionUpdate | None = None
            if post_update_artifact is not None and decision_card_artifact is not None:
                candidate_update = PostDecisionUpdate.model_validate(
                    post_update_artifact.payload
                )
                if (
                    candidate_update.decision_card_artifact.artifact_id
                    == decision_card_artifact.artifact_id
                    and (
                        post_update_artifact.input_artifact_ids
                        == (decision_card_artifact.artifact_id,)
                        or (
                            candidate_update.negotiation_outcome_artifact is not None
                            and len(post_update_artifact.input_artifact_ids) == 2
                            and post_update_artifact.input_artifact_ids[1]
                            == candidate_update.negotiation_outcome_artifact.artifact_id
                        )
                    )
                ):
                    post_update = candidate_update
                    post_decision_update_id = post_update.update_id
                    post_decision_outcome = post_update.outcome
            negotiation_artifact = self._latest_validated(
                artifacts, ArtifactType.NEGOTIATION_OUTCOME
            )
            if negotiation_artifact is not None:
                candidate_negotiation_outcome = NegotiationOutcome.model_validate(
                    negotiation_artifact.payload
                )
                if (
                    decision_card_artifact is not None
                    and candidate_negotiation_outcome.decision_card_artifact.artifact_id
                    == decision_card_artifact.artifact_id
                    and candidate_negotiation_outcome.decision_card_artifact.version
                    == decision_card_artifact.version
                    and candidate_negotiation_outcome.decision_card_artifact.input_hash
                    == decision_card_artifact.input_hash
                ):
                    negotiation_outcome_id = (
                        candidate_negotiation_outcome.negotiation_outcome_id
                    )
                    negotiation_outcome_status = (
                        candidate_negotiation_outcome.outcome_status
                    )
            external_proposal_artifact = self._latest_validated(
                artifacts,
                ArtifactType.EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL,
            )
            if external_proposal_artifact is not None and post_update_artifact is not None:
                candidate_external_proposal = (
                    ExternalDocumentSubmissionProposal.model_validate(
                        external_proposal_artifact.payload
                    )
                )
                proposal_sources = candidate_external_proposal.source_artifact_ids
                release_reference = (
                    candidate_external_proposal.document_release_package.artifact
                )
                release_artifact = next(
                    (
                        item
                        for item in artifacts
                        if item.artifact_id == release_reference.artifact_id
                        and item.artifact_type
                        is ArtifactType.DOCUMENT_RELEASE_PACKAGE
                        and item.version == release_reference.version
                        and item.input_hash == release_reference.input_hash
                        and item.validation_status
                        in {
                            ValidationStatus.VALID,
                            ValidationStatus.VALID_WITH_WARNINGS,
                        }
                    ),
                    None,
                )
                if (
                    external_proposal_artifact.input_artifact_ids
                    == proposal_sources
                    and proposal_sources[0] == post_update_artifact.artifact_id
                    and decision_card_artifact is not None
                    and proposal_sources[1] == decision_card_artifact.artifact_id
                    and release_artifact is not None
                    and proposal_sources[2] == release_artifact.artifact_id
                    and candidate_external_proposal.post_decision_update_artifact.artifact_id
                    == post_update_artifact.artifact_id
                    and candidate_external_proposal.decision_card_artifact.artifact_id
                    == decision_card_artifact.artifact_id
                ):
                    external_document_submission_proposal_id = (
                        candidate_external_proposal.proposal_id
                    )
            requests = await self._approvals.list_by_case(run.evaluation_case_id)
            pending_approvals = tuple(
                item.request_id
                for item in requests
                if item.workflow_run_id == run.workflow_run_id
                and item.status.value == "PENDING"
            )
            if external_document_submission_proposal_id is not None:
                external_submission_authorized = any(
                    item.workflow_run_id == run.workflow_run_id
                    and item.status is ApprovalRequestStatus.APPROVED
                    and item.command.action_type
                    is ProtectedAction.SEND_DOCUMENT_TO_EXTERNAL_PARTNER
                    and external_proposal_artifact is not None
                    and item.subject_artifact_id
                    == external_proposal_artifact.artifact_id
                    and item.subject_artifact_version
                    == external_proposal_artifact.version
                    and item.subject_input_hash
                    == external_proposal_artifact.input_hash
                    for item in requests
                )
        return WorkflowRunSummary(
            workflow_run_id=run.workflow_run_id,
            evaluation_case_id=run.evaluation_case_id,
            contract_id=run.contract_id,
            status=run.status,
            current_stage=run.current_stage,
            nodes=nodes,
            artifact_refs=tuple(
                WorkflowArtifactReference(
                    artifact_id=item.artifact_id,
                    artifact_type=item.artifact_type,
                    version=item.version,
                    validation_status=item.validation_status,
                )
                for item in artifacts
            ),
            approval_checkpoint_count=checkpoints,
            decision_route_outcome=decision_route_outcome,
            banking_discovery_request_id=banking_discovery_request_id,
            banking_discovery_status=banking_discovery_status,
            banking_discovery_result_id=banking_discovery_result_id,
            banking_option_matrix_id=banking_option_matrix_id,
            banking_option_advice_id=banking_option_advice_id,
            banking_option_count=banking_option_count,
            banking_input_supplement_id=banking_input_supplement_id,
            banking_precheck_readiness_id=banking_precheck_readiness_id,
            banking_precheck_readiness_status=banking_precheck_readiness_status,
            decision_post_banking_review_id=decision_post_banking_review_id,
            decision_post_banking_outcome=decision_post_banking_outcome,
            precheck_ready_option_ids=precheck_ready_option_ids,
            banking_precheck_submission_proposal_id=(
                banking_precheck_submission_proposal_id
            ),
            banking_precheck_submission_candidate_ids=(
                banking_precheck_submission_candidate_ids
            ),
            banking_precheck_result_set_id=banking_precheck_result_set_id,
            banking_precheck_normalized_result_ids=(
                banking_precheck_normalized_result_ids
            ),
            banking_precheck_outcomes=banking_precheck_outcomes,
            banking_precheck_eligibility_statuses=(
                banking_precheck_eligibility_statuses
            ),
            banking_precheck_guarantee_decisions=(
                banking_precheck_guarantee_decisions
            ),
            banking_precheck_supported_amounts=(
                banking_precheck_supported_amounts
            ),
            banking_precheck_currencies=banking_precheck_currencies,
            banking_precheck_required_document_codes=(
                banking_precheck_required_document_codes
            ),
            banking_precheck_approval_condition_codes=(
                banking_precheck_approval_condition_codes
            ),
            banking_precheck_execution_mode=banking_precheck_execution_mode,
            banking_precheck_result_authority=banking_precheck_result_authority,
            banking_precheck_external_bank_submission=(
                banking_precheck_external_bank_submission
            ),
            banking_precheck_bank_approval_obtained=(
                banking_precheck_bank_approval_obtained
            ),
            decision_post_precheck_review_id=decision_post_precheck_review_id,
            decision_post_precheck_outcome=decision_post_precheck_outcome,
            decision_post_precheck_candidate_option_ids=(
                decision_post_precheck_candidate_option_ids
            ),
            decision_post_precheck_candidate_product_ids=(
                decision_post_precheck_candidate_product_ids
            ),
            decision_post_precheck_conditional_option_ids=(
                decision_post_precheck_conditional_option_ids
            ),
            decision_post_precheck_inconclusive_option_ids=(
                decision_post_precheck_inconclusive_option_ids
            ),
            decision_post_precheck_evidence_required_option_ids=(
                decision_post_precheck_evidence_required_option_ids
            ),
            decision_post_precheck_not_eligible_option_ids=(
                decision_post_precheck_not_eligible_option_ids
            ),
            decision_post_precheck_unavailable_option_ids=(
                decision_post_precheck_unavailable_option_ids
            ),
            document_preparation_request_ids=document_preparation_request_ids,
            document_checklist_ids=document_checklist_ids,
            document_package_draft_ids=document_package_draft_ids,
            document_package_readinesses=document_package_readinesses,
            document_release_package_ids=document_release_package_ids,
            document_evidence_supplement_ids=(
                document_evidence_supplement_ids
            ),
            document_pending_codes=document_pending_codes,
            document_release_package_ready=bool(document_release_package_ids),
            ready_for_internal_decision=(
                internal_decision_package_id is not None
            ),
            document_release_authorized=external_submission_authorized,
            document_external_release_performed=False,
            internal_decision_package_id=internal_decision_package_id,
            internal_decision_assembly_path=internal_decision_assembly_path,
            internal_decision_package_readiness=(
                internal_decision_package_readiness
            ),
            internal_decision_source_artifact_ids=(
                internal_decision_source_artifact_ids
            ),
            internal_decision_governance_reference_ids=(
                internal_decision_governance_reference_ids
            ),
            internal_decision_package_ready=(
                internal_decision_package_id is not None
            ),
            final_risk_assessment_id=final_risk_assessment_id,
            final_risk_status=final_risk_status,
            final_residual_risk_level=final_residual_risk_level,
            final_risk_conclusion=final_risk_conclusion,
            final_major_exception=final_major_exception,
            final_unresolved_approval_gate_ids=(
                final_unresolved_approval_gate_ids
            ),
            final_required_control_codes=final_required_control_codes,
            ai_decision_analysis_id=ai_decision_analysis_id,
            ai_decision_analysis_source=ai_decision_analysis_source,
            decision_card_id=decision_card_id,
            decision_recommendation=decision_recommendation,
            decision_confidence=decision_confidence,
            decision_condition_ids=decision_condition_ids,
            decision_selected_negotiation_strategy_ids=(
                decision_selected_negotiation_strategy_ids
            ),
            decision_selected_option_ids=decision_selected_option_ids,
            post_decision_update_id=post_decision_update_id,
            post_decision_outcome=post_decision_outcome,
            negotiation_outcome_id=negotiation_outcome_id,
            negotiation_outcome_status=negotiation_outcome_status,
            external_document_submission_proposal_id=(
                external_document_submission_proposal_id
            ),
            external_submission_authorized=external_submission_authorized,
            ready_for_external_submission=(
                run.status is WorkflowStatus.COMPLETED
                and run.current_stage
                == WorkflowNode.READY_FOR_EXTERNAL_SUBMISSION.value
                and external_submission_authorized
            ),
            external_submission_performed=False,
            pending_approval_ids=pending_approvals,
            pending_missing_data_ids=run.pending_request_ids,
            resume_stage=run.resume_stage,
            blocked_action=run.blocked_action,
            failure_reason=run.failure_reason,
        )

    async def confirm_negotiation_terms_sent(
        self,
        *,
        evaluation_case_id: str,
        confirmation: NegotiationTermsSentInput,
    ) -> CaseWorkflowRun:
        """Record only that Founder sent the terms through an external channel."""
        run = await self._require_run(confirmation.workflow_run_id)
        if run.evaluation_case_id != evaluation_case_id:
            raise CaseWorkflowConflictError("Workflow and evaluation case do not match.")
        expected_request = deterministic_id(
            "NTS", run.workflow_run_id, confirmation.decision_card_artifact_id
        )
        if (
            run.status is not WorkflowStatus.WAITING_FOR_INPUT
            or run.current_stage != WorkflowNode.NEGOTIATION_TERMS_SENT.value
            or expected_request not in run.pending_request_ids
        ):
            raise CaseWorkflowConflictError(
                "Terms confirmation is accepted only at the active negotiation step."
            )
        artifact = await self._artifacts.get(confirmation.decision_card_artifact_id)
        if (
            artifact is None
            or artifact.evaluation_case_id != evaluation_case_id
            or artifact.artifact_type is not ArtifactType.DECISION_CARD
        ):
            raise CaseWorkflowConflictError("Decision Card is not the active case Card.")
        card = DecisionCard.model_validate(artifact.payload)
        if card.recommendation is not DecisionRecommendation.NEGOTIATE_CONDITIONS_TO_ACCEPT:
            raise CaseWorkflowConflictError("Decision Card does not require negotiation.")
        node = await self._workflows.get_node(
            run.workflow_run_id, WorkflowNode.NEGOTIATION_TERMS_SENT.value
        )
        if node is None:
            raise CaseWorkflowConflictError("Negotiation terms node does not exist.")
        await self._finish_node(node, WorkflowNodeStatus.COMPLETED, ())
        updated = await self._save_run(
            run,
            status=WorkflowStatus.PENDING,
            current_stage=WorkflowNode.NEGOTIATION_TERMS_SENT.value,
            pending_request_ids=(),
            resume_stage=None,
            failure_reason=None,
        )
        await self._event(
            updated,
            "NEGOTIATION_TERMS_SENT_CONFIRMED",
            WorkflowNode.NEGOTIATION_TERMS_SENT,
            {"decision_card_artifact_id": artifact.artifact_id},
        )
        return updated

    async def submit_negotiation_outcome(
        self,
        *,
        evaluation_case_id: str,
        submission: NegotiationOutcomeInput,
    ) -> tuple[NegotiationOutcomeExecutionResult, CaseWorkflowRun]:
        """Persist all condition responses and schedule final Founder confirmation."""
        run = await self._require_run(submission.workflow_run_id)
        if run.evaluation_case_id != evaluation_case_id:
            raise CaseWorkflowConflictError("Workflow and evaluation case do not match.")
        expected_request = deterministic_id(
            "NIN", run.workflow_run_id, submission.decision_card_artifact_id
        )
        if (
            run.status is not WorkflowStatus.WAITING_FOR_INPUT
            or run.current_stage
            not in {
                WorkflowNode.NEGOTIATION_TERMS_SENT.value,
                WorkflowNode.NEGOTIATION_OUTCOME_RECEIVED.value,
            }
            or expected_request not in run.pending_request_ids
        ):
            raise CaseWorkflowConflictError(
                "Negotiation responses are accepted only while this step is active."
            )
        result = await self._services.negotiation_outcome(
            evaluation_case_id=evaluation_case_id,
            submission=submission,
        )
        outcome_node = await self._workflows.get_node(
            run.workflow_run_id, WorkflowNode.NEGOTIATION_OUTCOME_RECEIVED.value
        )
        if outcome_node is not None:
            await self._finish_node(
                outcome_node,
                self._result_node_status(result.status, result.component_status),
                result.generated_artifacts,
                failure_reason="; ".join(result.validation_errors) or None,
            )
        if result.status is not WorkflowStatus.COMPLETED:
            return result, run
        updated = await self._save_run(
            run,
            status=WorkflowStatus.PENDING,
            current_stage=WorkflowNode.NEGOTIATION_FINAL_CONFIRMATION.value,
            pending_request_ids=(),
            resume_stage=None,
            failure_reason=None,
        )
        await self._event(
            updated,
            "NEGOTIATION_OUTCOME_RECORDED",
            WorkflowNode.NEGOTIATION_OUTCOME_RECEIVED,
            {
                "negotiation_outcome_id": (
                    result.outcome.negotiation_outcome_id if result.outcome else None
                ),
                "all_conditions_accepted": (
                    result.outcome.all_conditions_accepted if result.outcome else False
                ),
            },
        )
        return result, updated

    async def submit_banking_input(
        self,
        *,
        evaluation_case_id: str,
        submission: BankingAmountInputSubmission,
    ) -> tuple[BankingInputExecutionResult, CaseWorkflowRun]:
        """Persist a verified amount supplement, then atomically schedule re-evaluation."""
        run = await self._require_run(submission.workflow_run_id)
        if run.evaluation_case_id != evaluation_case_id:
            raise CaseWorkflowConflictError(
                "Workflow and evaluation case do not match."
            )
        existing_result = await self._existing_banking_input_result(
            run=run,
            evaluation_case_id=evaluation_case_id,
            submission=submission,
        )
        if existing_result is not None:
            if (
                run.status is WorkflowStatus.WAITING_FOR_INPUT
                and run.current_stage
                == WorkflowNode.DECISION_POST_BANKING_REVIEW.value
                and run.resume_stage
                == WorkflowNode.DECISION_POST_BANKING_REVIEW.value
                and submission.missing_request_id in run.pending_request_ids
            ):
                run = await self._schedule_after_banking_input(
                    run=run,
                    submission=submission,
                    result=existing_result,
                )
            return existing_result, run
        if (
            run.status is not WorkflowStatus.WAITING_FOR_INPUT
            or run.current_stage != WorkflowNode.DECISION_POST_BANKING_REVIEW.value
            or run.resume_stage != WorkflowNode.DECISION_POST_BANKING_REVIEW.value
        ):
            raise CaseWorkflowConflictError(
                "Banking input is accepted only while Decision post-Banking review waits."
            )
        if submission.missing_request_id not in run.pending_request_ids:
            raise CaseWorkflowConflictError(
                "missing_request_id is not pending on this workflow."
            )
        artifacts = await self._artifacts.list_by_case(evaluation_case_id)
        case_artifact = self._latest(artifacts, ArtifactType.EVALUATION_CASE)
        review_artifact = self._latest(
            artifacts, ArtifactType.DECISION_POST_BANKING_REVIEW
        )
        current_supplement = self._latest(
            artifacts, ArtifactType.BANKING_INPUT_SUPPLEMENT
        )
        node = await self._start_node(
            run,
            WorkflowNode.BANKING_INPUT_SUPPLEMENT,
            identity_inputs=(
                case_artifact.artifact_id if case_artifact is not None else None,
                review_artifact.artifact_id if review_artifact is not None else None,
                (
                    current_supplement.artifact_id
                    if current_supplement is not None
                    else None
                ),
                submission.missing_request_id,
                submission.requested_amount,
                submission.requested_amount_currency,
                submission.provided_by,
                submission.evidence_note,
            ),
        )
        result = await self._services.banking_input_supplement(
            evaluation_case_id=evaluation_case_id,
            submission=submission,
            allowed_pending_request_id=submission.missing_request_id,
        )
        await self._finish_node(
            node,
            self._result_node_status(result.status, result.component_status),
            result.generated_artifacts,
            failure_reason="; ".join(result.validation_errors) or None,
        )
        if result.status is not WorkflowStatus.COMPLETED:
            return result, run
        updated = await self._schedule_after_banking_input(
            run=run,
            submission=submission,
            result=result,
        )
        return result, updated

    async def _schedule_after_banking_input(
        self,
        *,
        run: CaseWorkflowRun,
        submission: BankingAmountInputSubmission,
        result: BankingInputExecutionResult,
    ) -> CaseWorkflowRun:
        """Remove only the resolved request and queue deterministic Banking rebuild."""
        remaining_request_ids = tuple(
            item
            for item in run.pending_request_ids
            if item != submission.missing_request_id
        )
        updated = await self._save_run(
            run,
            status=WorkflowStatus.PENDING,
            current_stage=WorkflowNode.BANKING_INTERNAL_DISCOVERY.value,
            pending_request_ids=remaining_request_ids,
            resume_stage=None,
            failure_reason=None,
        )
        await self._event(
            updated,
            "BANKING_INPUT_SUPPLEMENT_ACCEPTED",
            WorkflowNode.BANKING_INPUT_SUPPLEMENT,
            {
                "missing_request_id": submission.missing_request_id,
                "supplement_id": (
                    result.supplement.supplement_id
                    if result.supplement is not None
                    else None
                ),
            },
        )
        return updated

    async def _existing_banking_input_result(
        self,
        *,
        run: CaseWorkflowRun,
        evaluation_case_id: str,
        submission: BankingAmountInputSubmission,
    ) -> BankingInputExecutionResult | None:
        """Return the latest exact accepted payload for retry idempotency."""
        artifacts = await self._artifacts.list_by_case(evaluation_case_id)
        matches: list[tuple[ArtifactEnvelope, BankingInputSupplement]] = []
        for artifact in artifacts:
            if (
                artifact.artifact_type is not ArtifactType.BANKING_INPUT_SUPPLEMENT
                or artifact.validation_status
                not in {
                    ValidationStatus.VALID,
                    ValidationStatus.VALID_WITH_WARNINGS,
                }
            ):
                continue
            supplement = BankingInputSupplement.model_validate(artifact.payload)
            if submission.missing_request_id in supplement.resolved_request_ids:
                matches.append((artifact, supplement))
        if not matches:
            return None
        artifact, supplement = max(matches, key=lambda item: item[0].version)
        if (
            supplement.evaluation_case_id != evaluation_case_id
            or supplement.dataset_id != run.dataset_id
            or supplement.contract_id != run.contract_id
        ):
            raise CaseWorkflowConflictError(
                "Persisted Banking input identity does not match this workflow."
            )
        if not (
            supplement.requested_amount == submission.requested_amount
            and supplement.requested_amount_currency
            is submission.requested_amount_currency
            and supplement.provider == submission.provided_by
            and supplement.note == submission.evidence_note
            and supplement.resolved_request_ids == (submission.missing_request_id,)
        ):
            return None
        return BankingInputExecutionResult(
            status=WorkflowStatus.COMPLETED,
            component_status=ComponentStatus.COMPLETED,
            current_node=WorkflowNode.BANKING_INPUT_SUPPLEMENT.value,
            supplement=supplement,
            generated_artifacts=(artifact,),
        )

    async def submit_banking_precheck_evidence(
        self,
        *,
        evaluation_case_id: str,
        submission: BankingPrecheckEvidenceSubmission,
    ) -> tuple[BankingPrecheckEvidenceExecutionResult, CaseWorkflowRun]:
        """Resolve one exact evidence handoff without reinterpreting bank output."""
        run = await self._require_run(submission.workflow_run_id)
        if run.evaluation_case_id != evaluation_case_id:
            raise CaseWorkflowConflictError(
                "Workflow and evaluation case do not match."
            )
        artifacts = await self._artifacts.list_by_case(evaluation_case_id)
        current_supplement = self._latest_precheck_evidence_supplement(
            artifacts, submission.missing_request_id
        )
        pending_wait = (
            run.status is WorkflowStatus.WAITING_FOR_INPUT
            and run.current_stage
            == WorkflowNode.DECISION_POST_PRECHECK_REVIEW.value
            and run.resume_stage
            == WorkflowNode.DECISION_POST_PRECHECK_REVIEW.value
            and submission.missing_request_id in run.pending_request_ids
        )
        accepted_retry = (
            run.status is WorkflowStatus.WAITING_FOR_DEPENDENCIES
            and run.current_stage
            == WorkflowNode.BANKING_PRECHECK_RETRY_REQUIRED.value
            and current_supplement is not None
        )
        if not pending_wait and not accepted_retry:
            raise CaseWorkflowConflictError(
                "Evidence is accepted only for an exact pending post-precheck request."
            )
        review_artifact = self._latest(
            artifacts, ArtifactType.DECISION_POST_PRECHECK_REVIEW
        )
        node = await self._start_node(
            run,
            WorkflowNode.BANKING_PRECHECK_EVIDENCE_INTAKE,
            identity_inputs=(
                review_artifact.artifact_id if review_artifact is not None else None,
                (
                    current_supplement.artifact_id
                    if current_supplement is not None
                    else None
                ),
                submission.missing_request_id,
                submission.evidence_reference_id,
                submission.provided_by,
                submission.evidence_note,
            ),
        )
        result = await self._services.banking_precheck_evidence_supplement(
            evaluation_case_id=evaluation_case_id,
            submission=submission,
            allowed_pending_request_id=submission.missing_request_id,
        )
        await self._finish_node(
            node,
            self._result_node_status(result.status, result.component_status),
            result.generated_artifacts,
            failure_reason="; ".join(result.validation_errors) or None,
        )
        if result.status is not WorkflowStatus.COMPLETED:
            return result, run
        if accepted_retry:
            return result, run

        remaining_request_ids = tuple(
            item
            for item in run.pending_request_ids
            if item != submission.missing_request_id
        )
        if remaining_request_ids:
            updated = await self._save_run(
                run,
                status=WorkflowStatus.WAITING_FOR_INPUT,
                current_stage=WorkflowNode.DECISION_POST_PRECHECK_REVIEW.value,
                pending_request_ids=remaining_request_ids,
                resume_stage=WorkflowNode.DECISION_POST_PRECHECK_REVIEW.value,
                failure_reason=None,
            )
        else:
            updated = await self._save_run(
                run,
                status=WorkflowStatus.WAITING_FOR_DEPENDENCIES,
                current_stage=WorkflowNode.BANKING_PRECHECK_RETRY_REQUIRED.value,
                pending_request_ids=(),
                resume_stage=None,
                failure_reason=(
                    "A fresh governed precheck integration is required; the prior "
                    "provider result remains unchanged."
                ),
            )
        await self._event(
            updated,
            "BANKING_PRECHECK_EVIDENCE_REFERENCE_ACCEPTED",
            WorkflowNode.BANKING_PRECHECK_EVIDENCE_INTAKE,
            {
                "missing_request_id": submission.missing_request_id,
                "supplement_id": (
                    result.supplement.supplement_id
                    if result.supplement is not None
                    else None
                ),
                "remaining_request_ids": list(remaining_request_ids),
                "fresh_governed_precheck_required": not remaining_request_ids,
            },
        )
        return result, updated

    @staticmethod
    def _latest_precheck_evidence_supplement(
        artifacts: tuple[ArtifactEnvelope, ...], request_id: str
    ) -> ArtifactEnvelope | None:
        matches: list[ArtifactEnvelope] = []
        for artifact in artifacts:
            if (
                artifact.artifact_type
                is not ArtifactType.BANKING_PRECHECK_EVIDENCE_SUPPLEMENT
                or artifact.validation_status
                not in {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}
            ):
                continue
            supplement = BankingPrecheckEvidenceSupplement.model_validate(
                artifact.payload
            )
            if supplement.missing_request_id == request_id:
                matches.append(artifact)
        return max(matches, key=lambda item: item.version, default=None)

    async def submit_document_evidence(
        self,
        *,
        evaluation_case_id: str,
        submission: DocumentEvidenceSubmission,
    ) -> tuple[DocumentEvidenceExecutionResult, CaseWorkflowRun]:
        """Accept one opaque document reference and schedule a safe package rebuild."""
        run = await self._require_run(submission.workflow_run_id)
        if run.evaluation_case_id != evaluation_case_id:
            raise CaseWorkflowConflictError(
                "Workflow and evaluation case do not match."
            )
        artifacts = await self._artifacts.list_by_case(evaluation_case_id)
        current = self._document_supplement_for_request(
            artifacts, submission.missing_request_id
        )
        pending_wait = (
            run.status is WorkflowStatus.WAITING_FOR_INPUT
            and run.current_stage == WorkflowNode.DOCUMENT_PREPARATION.value
            and run.resume_stage == WorkflowNode.DOCUMENT_PREPARATION.value
            and submission.missing_request_id in run.pending_request_ids
        )
        if not pending_wait:
            if current is None:
                raise CaseWorkflowConflictError(
                    "Document evidence is accepted only for an exact pending request."
                )
            supplement = DocumentEvidenceSupplement.model_validate(current.payload)
            if not self._document_submission_matches(submission, supplement):
                raise CaseWorkflowConflictError(
                    "This Document request already has different accepted metadata."
                )
            return (
                DocumentEvidenceExecutionResult(
                    status=WorkflowStatus.COMPLETED,
                    component_status=ComponentStatus.COMPLETED,
                    current_node=WorkflowNode.DOCUMENT_INPUT_INTAKE.value,
                    supplement=supplement,
                    generated_artifacts=(current,),
                ),
                run,
            )
        package_artifact = self._package_for_missing_request(
            artifacts, submission.missing_request_id
        )
        if package_artifact is None:
            raise CaseWorkflowConflictError(
                "The pending Document request has no validated package draft."
            )
        node = await self._start_node(
            run,
            WorkflowNode.DOCUMENT_INPUT_INTAKE,
            identity_inputs=(
                package_artifact.artifact_id,
                package_artifact.version,
                package_artifact.input_hash,
                submission.missing_request_id,
                submission.document_reference_id,
                submission.content_sha256,
                submission.document_type,
                submission.provided_by,
                submission.evidence_note,
            ),
        )
        result = await self._services.document_evidence_supplement(
            evaluation_case_id=evaluation_case_id,
            submission=submission,
            allowed_pending_request_id=submission.missing_request_id,
        )
        await self._finish_node(
            node,
            self._result_node_status(result.status, result.component_status),
            result.generated_artifacts,
            failure_reason="; ".join(result.validation_errors) or None,
        )
        if result.status is not WorkflowStatus.COMPLETED:
            return result, run
        remaining = tuple(
            item
            for item in run.pending_request_ids
            if item != submission.missing_request_id
        )
        if remaining:
            updated = await self._save_run(
                run,
                status=WorkflowStatus.WAITING_FOR_INPUT,
                current_stage=WorkflowNode.DOCUMENT_PREPARATION.value,
                pending_request_ids=remaining,
                resume_stage=WorkflowNode.DOCUMENT_PREPARATION.value,
                failure_reason=None,
            )
        else:
            updated = await self._save_run(
                run,
                status=WorkflowStatus.PENDING,
                current_stage=WorkflowNode.DOCUMENT_PREPARATION.value,
                pending_request_ids=(),
                resume_stage=None,
                failure_reason=None,
            )
        await self._event(
            updated,
            "DOCUMENT_EVIDENCE_REFERENCE_ACCEPTED",
            WorkflowNode.DOCUMENT_INPUT_INTAKE,
            {
                "missing_request_id": submission.missing_request_id,
                "supplement_id": (
                    result.supplement.supplement_id
                    if result.supplement is not None
                    else None
                ),
                "remaining_request_ids": list(remaining),
            },
        )
        return result, updated

    @staticmethod
    def _document_supplement_for_request(
        artifacts: tuple[ArtifactEnvelope, ...], request_id: str
    ) -> ArtifactEnvelope | None:
        matches = tuple(
            item
            for item in artifacts
            if item.artifact_type is ArtifactType.DOCUMENT_EVIDENCE_SUPPLEMENT
            and DocumentEvidenceSupplement.model_validate(
                item.payload
            ).missing_request_id
            == request_id
        )
        if len(matches) > 1:
            raise CaseWorkflowConflictError(
                "Accepted Document evidence is ambiguous for this request."
            )
        return matches[0] if matches else None

    @staticmethod
    def _document_submission_matches(
        submission: DocumentEvidenceSubmission,
        supplement: DocumentEvidenceSupplement,
    ) -> bool:
        return (
            submission.missing_request_id == supplement.missing_request_id
            and submission.document_reference_id
            == supplement.document_reference_id
            and submission.content_sha256 == supplement.content_sha256
            and submission.document_type is supplement.document_type
            and submission.provided_by == supplement.provided_by
            and submission.evidence_note == supplement.evidence_note
        )

    @staticmethod
    def _package_for_missing_request(
        artifacts: tuple[ArtifactEnvelope, ...], request_id: str
    ) -> ArtifactEnvelope | None:
        matches: list[ArtifactEnvelope] = []
        for artifact in artifacts:
            if (
                artifact.artifact_type is not ArtifactType.DOCUMENT_PACKAGE_DRAFT
                or artifact.validation_status
                not in {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}
            ):
                continue
            package = DocumentPackageDraft.model_validate(artifact.payload)
            if request_id in {
                item.request_id for item in package.missing_data_requests
            }:
                matches.append(artifact)
        return max(matches, key=lambda item: item.version, default=None)

    async def resume(self, workflow_run_id: str) -> CaseWorkflowRun:
        """Move a genuine wait/failure back to PENDING; completed runs are immutable."""
        run = await self._require_run(workflow_run_id)
        if run.status not in {
            WorkflowStatus.WAITING_FOR_INPUT,
            WorkflowStatus.FAILED_SAFE,
        }:
            raise CaseWorkflowConflictError(
                f"Workflow in {run.status.value} cannot be resumed."
            )
        if (
            run.status is WorkflowStatus.WAITING_FOR_INPUT
            and run.pending_request_ids
        ):
            raise CaseWorkflowConflictError(
                "Resolve the pending MissingDataRequest through its typed input endpoint "
                "before resuming this workflow."
            )
        resumed = await self._save_run(
            run,
            status=WorkflowStatus.PENDING,
            current_stage=run.resume_stage or run.current_stage,
            failure_reason=None,
            pending_request_ids=(),
        )
        await self._event(resumed, "WORKFLOW_RESUME_REQUESTED", None)
        return resumed

    async def demo_pause(self, workflow_run_id: str, reason: str) -> CaseWorkflowRun:
        """Stop automatic progression at the current durable stage for live demos."""
        run = await self._require_run(workflow_run_id)
        if run.status in {
            WorkflowStatus.COMPLETED,
            WorkflowStatus.BLOCKED,
            WorkflowStatus.FAILED_SAFE,
            WorkflowStatus.WAITING_FOR_INPUT,
            WorkflowStatus.WAITING_FOR_APPROVAL,
            WorkflowStatus.WAITING_FOR_DEMO,
        }:
            raise CaseWorkflowConflictError(
                f"Workflow in {run.status.value} cannot be demo-paused."
            )
        paused = await self._save_run(
            run,
            status=WorkflowStatus.WAITING_FOR_DEMO,
            current_stage=run.current_stage,
            resume_stage=run.current_stage,
            failure_reason=reason,
        )
        await self._event(
            paused,
            "WORKFLOW_DEMO_PAUSED",
            None,
            {"resume_stage": paused.resume_stage, "reason": reason},
        )
        return paused

    async def demo_resume(self, workflow_run_id: str) -> CaseWorkflowRun:
        """Continue a workflow that was paused only for presentation control."""
        run = await self._require_run(workflow_run_id)
        if run.status is not WorkflowStatus.WAITING_FOR_DEMO:
            raise CaseWorkflowConflictError(
                f"Workflow in {run.status.value} cannot be demo-resumed."
            )
        resumed = await self._save_run(
            run,
            status=WorkflowStatus.PENDING,
            current_stage=run.resume_stage or run.current_stage,
            pending_request_ids=(),
            resume_stage=None,
            failure_reason=None,
            honor_demo_pause=False,
        )
        await self._event(resumed, "WORKFLOW_DEMO_RESUME_REQUESTED", None)
        return resumed

    async def _planner(self, run: CaseWorkflowRun) -> CaseWorkflowRun:
        existing = await self._workflows.get_node(
            run.workflow_run_id, WorkflowNode.PLANNER_INTAKE.value
        )
        if self._node_completed(existing) and run.evaluation_case_id is not None:
            return run
        node = await self._start_node(run, WorkflowNode.PLANNER_INTAKE)
        result = await self._services.evaluate(
            contract_id=run.contract_id,
            evaluation_scope=run.requested_scope,
        )
        if result.status is WorkflowStatus.WAITING_FOR_INPUT:
            request_ids = tuple(
                item.request_id
                for item in (
                    result.planner_result.missing_data_requests
                    if result.planner_result is not None
                    else ()
                )
            )
            await self._finish_node(
                node,
                WorkflowNodeStatus.WAITING_FOR_INPUT,
                result.generated_artifacts,
                waiting_for=request_ids,
            )
            waiting = await self._save_run(
                run,
                status=WorkflowStatus.WAITING_FOR_INPUT,
                current_stage=WorkflowNode.PLANNER_INTAKE.value,
                pending_request_ids=request_ids,
            )
            await self._event(
                waiting,
                "WORKFLOW_WAITING_FOR_INPUT",
                WorkflowNode.PLANNER_INTAKE,
                {"pending_request_ids": list(request_ids)},
            )
            return waiting
        if result.status is WorkflowStatus.FAILED_SAFE:
            raise RuntimeError("Planner failed safe: " + "; ".join(result.validation_errors))
        evaluation_case = (
            result.planner_result.evaluation_case
            if result.planner_result is not None
            else None
        )
        if evaluation_case is None:
            raise RuntimeError("Planner returned no EvaluationCase.")
        await self._finish_node(
            node,
            self._component_node_status(result.component_status),
            result.generated_artifacts,
        )
        return await self._save_run(
            run,
            status=WorkflowStatus.RUNNING,
            current_stage=WorkflowNode.INITIAL_ASSESSMENT.value,
            evaluation_case_id=evaluation_case.evaluation_case_id,
        )

    async def _risk_pre_scan(self, run: CaseWorkflowRun) -> bool:
        if run.evaluation_case_id is None:
            return False
        existing = await self._workflows.get_node(
            run.workflow_run_id, WorkflowNode.INITIAL_RISK_PRE_SCAN.value
        )
        if self._node_completed(existing):
            await self._ensure_risk_finalization_wait(run)
            return True
        node = await self._start_node(run, WorkflowNode.INITIAL_RISK_PRE_SCAN)
        result = await self._services.risk_pre_scan(
            evaluation_case_id=run.evaluation_case_id
        )
        if result.status is WorkflowStatus.FAILED_SAFE:
            raise RuntimeError("Risk pre-scan failed safe: " + "; ".join(result.validation_errors))
        await self._finish_node(
            node,
            self._component_node_status(result.component_status),
            result.generated_artifacts,
        )
        await self._event(
            run,
            "APPROVAL_CHECKPOINTS_REGISTERED",
            WorkflowNode.INITIAL_RISK_PRE_SCAN,
            {
                "count": (
                    len(result.approval_checkpoints.checkpoints)
                    if result.approval_checkpoints is not None
                    else 0
                )
            },
        )
        await self._ensure_risk_finalization_wait(run)
        return True

    async def _finance(self, run: CaseWorkflowRun) -> FinanceExecutionResult | None:
        if run.evaluation_case_id is None:
            return None
        existing = await self._workflows.get_node(
            run.workflow_run_id, WorkflowNode.FINANCE_ASSESSMENT.value
        )
        if self._node_completed(existing):
            return None
        node = await self._start_node(run, WorkflowNode.FINANCE_ASSESSMENT)
        result = await self._services.finance_assessment(
            evaluation_case_id=run.evaluation_case_id,
            resume_risk=False,
        )
        await self._finish_node(
            node,
            self._result_node_status(result.status, result.component_status),
            result.generated_artifacts,
            failure_reason="; ".join(result.validation_errors) or None,
        )
        return result

    async def _operations(self, run: CaseWorkflowRun) -> OperationsExecutionResult | None:
        if run.evaluation_case_id is None:
            return None
        existing = await self._workflows.get_node(
            run.workflow_run_id, WorkflowNode.OPERATIONS_ASSESSMENT.value
        )
        if self._node_completed(existing):
            return None
        node = await self._start_node(run, WorkflowNode.OPERATIONS_ASSESSMENT)
        result = await self._services.operations_assessment(
            evaluation_case_id=run.evaluation_case_id,
            as_of_date=run.as_of_date,
            resume_risk=False,
        )
        await self._finish_node(
            node,
            self._result_node_status(result.status, result.component_status),
            result.generated_artifacts,
            failure_reason="; ".join(result.validation_errors) or None,
        )
        return result

    async def _finalize_risk(
        self, run: CaseWorkflowRun
    ) -> RiskExecutionResult | None:
        if run.evaluation_case_id is None:  # pragma: no cover
            raise RuntimeError("Cannot finalize Risk without an evaluation case.")
        existing = await self._workflows.get_node(
            run.workflow_run_id, WorkflowNode.INITIAL_RISK_FINALIZATION.value
        )
        if self._node_completed(existing):
            return None
        node = await self._start_node(run, WorkflowNode.INITIAL_RISK_FINALIZATION)
        await self._event(
            run,
            "RISK_DEPENDENCIES_READY",
            WorkflowNode.INITIAL_RISK_FINALIZATION,
        )
        result = await self._services.risk_finalize(
            evaluation_case_id=run.evaluation_case_id
        )
        await self._finish_node(
            node,
            self._result_node_status(result.status, result.component_status),
            result.generated_artifacts,
            failure_reason="; ".join(result.validation_errors) or None,
        )
        return result

    async def _ensure_risk_finalization_wait(self, run: CaseWorkflowRun) -> None:
        """Persist dependency waiting as workflow state without invoking Risk."""
        existing = await self._workflows.get_node(
            run.workflow_run_id,
            WorkflowNode.INITIAL_RISK_FINALIZATION.value,
        )
        if existing is not None:
            return
        waiting = WorkflowNodeState(
            workflow_run_id=run.workflow_run_id,
            node=WorkflowNode.INITIAL_RISK_FINALIZATION,
            status=WorkflowNodeStatus.WAITING_FOR_DEPENDENCIES,
            attempt=0,
            input_hash=deterministic_id(
                "NIN",
                run.dataset_snapshot_hash,
                run.evaluation_case_id,
                WorkflowNode.INITIAL_RISK_FINALIZATION,
                run.as_of_date,
            ),
            waiting_for=(
                ArtifactType.FINANCE_FACTS.value,
                ArtifactType.OPERATIONS_FACTS.value,
            ),
        )
        await self._workflows.save_node(waiting)
        await self._events.append(
            workflow_run_id=run.workflow_run_id,
            event_type="NODE_WAITING",
            node=WorkflowNode.INITIAL_RISK_FINALIZATION,
            metadata={
                "status": WorkflowNodeStatus.WAITING_FOR_DEPENDENCIES.value,
                "waiting_for": list(waiting.waiting_for),
            },
            created_at=self._clock(),
        )

    async def _resume_final_decision_path(self, run: CaseWorkflowRun) -> bool:
        """Resume only the persisted decision tail instead of replaying steps 1-18."""
        late_stages = {
            WorkflowNode.FINAL_DECISION_APPROVAL.value,
            WorkflowNode.POST_DECISION_UPDATE.value,
            WorkflowNode.NEGOTIATION_TERMS_SENT.value,
            WorkflowNode.EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL.value,
        }
        if run.current_stage not in late_stages:
            return False
        if run.evaluation_case_id is None:
            await self._fail(
                run,
                WorkflowNode.DECISION_CARD_COMPOSITION,
                "Decision-tail recovery requires an evaluation case.",
            )
            return True
        artifacts = await self._artifacts.list_by_case(run.evaluation_case_id)
        card_artifact = self._latest_validated(artifacts, ArtifactType.DECISION_CARD)
        if card_artifact is None:
            await self._fail(
                run,
                WorkflowNode.DECISION_CARD_COMPOSITION,
                "Decision-tail recovery cannot find a validated Decision Card.",
            )
            return True
        try:
            card = DecisionCard.model_validate(card_artifact.payload)
        except ValueError:
            await self._fail(
                run,
                WorkflowNode.DECISION_CARD_COMPOSITION,
                "Decision-tail recovery found an invalid Decision Card.",
            )
            return True

        if run.current_stage == WorkflowNode.FINAL_DECISION_APPROVAL.value:
            await self._request_final_decision_approval(
                run=run,
                card_artifact=card_artifact,
                card=card,
            )
            return True

        final_approval = await self._approved_request_for_subject(
            run=run,
            action=ProtectedAction.CONFIRM_FINAL_CONTRACT_DECISION,
            subject_artifact_id=card_artifact.artifact_id,
        )
        if final_approval is None:
            await self._fail(
                run,
                WorkflowNode.FINAL_DECISION_APPROVAL,
                "Decision-tail recovery requires the exact approved Founder decision.",
            )
            return True
        initial_update = await self._initial_post_decision_update(
            run=run,
            card_artifact=card_artifact,
            approval_request_id=final_approval.request_id,
        )
        if initial_update is None:
            await self._run_post_decision_update(
                run=run,
                card_artifact=card_artifact,
                approval_request_id=final_approval.request_id,
            )
            return True
        update_artifact, update = initial_update

        if run.current_stage == WorkflowNode.POST_DECISION_UPDATE.value:
            await self._route_post_decision_update(
                run=run,
                card_artifact=card_artifact,
                update_artifact=update_artifact,
                update=update,
            )
            return True
        if run.current_stage in {
            WorkflowNode.NEGOTIATION_TERMS_SENT.value,
        }:
            await self._run_negotiation_flow(
                run=run,
                card_artifact=card_artifact,
                update_artifact=update_artifact,
            )
            return True

        resolved_update = await self._latest_post_decision_update_for_card(
            run=run,
            card_artifact=card_artifact,
            external_release_required=True,
        )
        if resolved_update is None:
            await self._fail(
                run,
                WorkflowNode.EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL,
                "External-release recovery cannot find its validated post-decision route.",
            )
            return True
        resolved_update_artifact, _ = resolved_update
        await self._run_external_submission_proposal(
            run=run,
            update_artifact=resolved_update_artifact,
        )
        return True

    async def _approved_request_for_subject(
        self,
        *,
        run: CaseWorkflowRun,
        action: ProtectedAction,
        subject_artifact_id: str,
    ) -> ApprovalRequest | None:
        """Return the one approved request for this run/action/artifact scope."""
        if run.evaluation_case_id is None:
            return None
        matches = tuple(
            item
            for item in await self._approvals.list_by_case(run.evaluation_case_id)
            if item.workflow_run_id == run.workflow_run_id
            and item.command.action_type is action
            and item.subject_artifact_id == subject_artifact_id
            and item.status is ApprovalRequestStatus.APPROVED
        )
        return max(matches, key=lambda item: (item.created_at, item.request_id), default=None)

    async def _initial_post_decision_update(
        self,
        *,
        run: CaseWorkflowRun,
        card_artifact: ArtifactEnvelope,
        approval_request_id: str,
    ) -> tuple[ArtifactEnvelope, PostDecisionUpdate] | None:
        """Find the immutable update produced by the initial Founder decision."""
        if run.evaluation_case_id is None:
            return None
        artifacts = await self._artifacts.list_by_case(run.evaluation_case_id)
        for artifact in sorted(
            (
                item
                for item in artifacts
                if item.artifact_type is ArtifactType.POST_DECISION_UPDATE
                and item.validation_status
                in {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}
            ),
            key=lambda item: (item.version, item.artifact_id),
            reverse=True,
        ):
            try:
                update = PostDecisionUpdate.model_validate(artifact.payload)
            except ValueError:
                continue
            if (
                artifact.input_artifact_ids == (card_artifact.artifact_id,)
                and update.decision_card_artifact.artifact_id
                == card_artifact.artifact_id
                and update.decision_card_artifact.version == card_artifact.version
                and update.decision_card_artifact.input_hash == card_artifact.input_hash
                and update.founder_approval.approval_request_id == approval_request_id
                and update.negotiation_outcome_artifact is None
            ):
                return artifact, update
        return None

    async def _resolved_negotiation_update(
        self,
        *,
        run: CaseWorkflowRun,
        original_update_artifact: ArtifactEnvelope,
        outcome_artifact: ArtifactEnvelope,
        approval_request_id: str,
    ) -> tuple[ArtifactEnvelope, PostDecisionUpdate] | None:
        """Reuse the finalized single negotiation round by its exact source artifacts."""
        if run.evaluation_case_id is None:
            return None
        artifacts = await self._artifacts.list_by_case(run.evaluation_case_id)
        for artifact in sorted(
            (
                item
                for item in artifacts
                if item.artifact_type is ArtifactType.POST_DECISION_UPDATE
                and item.validation_status
                in {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}
            ),
            key=lambda item: (item.version, item.artifact_id),
            reverse=True,
        ):
            try:
                update = PostDecisionUpdate.model_validate(artifact.payload)
            except ValueError:
                continue
            if (
                artifact.input_artifact_ids
                == (original_update_artifact.artifact_id, outcome_artifact.artifact_id)
                and update.negotiation_outcome_artifact is not None
                and update.negotiation_outcome_artifact.artifact_id
                == outcome_artifact.artifact_id
                and update.negotiation_approval_request_id == approval_request_id
            ):
                return artifact, update
        return None

    async def _latest_post_decision_update_for_card(
        self,
        *,
        run: CaseWorkflowRun,
        card_artifact: ArtifactEnvelope,
        external_release_required: bool | None = None,
    ) -> tuple[ArtifactEnvelope, PostDecisionUpdate] | None:
        """Select the latest validated route bound to this exact Decision Card."""
        if run.evaluation_case_id is None:
            return None
        artifacts = await self._artifacts.list_by_case(run.evaluation_case_id)
        for artifact in sorted(
            (
                item
                for item in artifacts
                if item.artifact_type is ArtifactType.POST_DECISION_UPDATE
                and item.validation_status
                in {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}
            ),
            key=lambda item: (item.version, item.artifact_id),
            reverse=True,
        ):
            try:
                update = PostDecisionUpdate.model_validate(artifact.payload)
            except ValueError:
                continue
            if (
                update.decision_card_artifact.artifact_id == card_artifact.artifact_id
                and update.decision_card_artifact.version == card_artifact.version
                and update.decision_card_artifact.input_hash == card_artifact.input_hash
                and (
                    external_release_required is None
                    or update.external_document_release_required
                    is external_release_required
                )
            ):
                return artifact, update
        return None

    async def _external_submission_proposal_for_update(
        self,
        *,
        run: CaseWorkflowRun,
        update_artifact: ArtifactEnvelope,
    ) -> tuple[ArtifactEnvelope, ExternalDocumentSubmissionProposal] | None:
        """Reuse only a proposal that binds the exact post-decision update."""
        if run.evaluation_case_id is None:
            return None
        artifacts = await self._artifacts.list_by_case(run.evaluation_case_id)
        for artifact in sorted(
            (
                item
                for item in artifacts
                if item.artifact_type
                is ArtifactType.EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL
                and item.validation_status
                in {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}
            ),
            key=lambda item: (item.version, item.artifact_id),
            reverse=True,
        ):
            try:
                proposal = ExternalDocumentSubmissionProposal.model_validate(artifact.payload)
            except ValueError:
                continue
            if (
                artifact.input_artifact_ids == proposal.source_artifact_ids
                and proposal.source_artifact_ids[0] == update_artifact.artifact_id
                and proposal.post_decision_update_artifact.artifact_id
                == update_artifact.artifact_id
                and proposal.post_decision_update_artifact.version
                == update_artifact.version
                and proposal.post_decision_update_artifact.input_hash
                == update_artifact.input_hash
            ):
                return artifact, proposal
        return None

    async def _complete(
        self, run: CaseWorkflowRun, current_stage: WorkflowNode
    ) -> None:
        if run.status is WorkflowStatus.COMPLETED:
            return
        completed = await self._save_run(
            run,
            status=WorkflowStatus.COMPLETED,
            current_stage=current_stage.value,
            pending_request_ids=(),
            failure_reason=None,
        )
        events = await self._events.list_after(completed.workflow_run_id, 0)
        if not any(item.event_type == "WORKFLOW_COMPLETED" for item in events):
            await self._event(completed, "WORKFLOW_COMPLETED", None)

    async def _decision_banking_handoff(
        self, run: CaseWorkflowRun
    ) -> BankingDiscoveryHandoffExecutionResult | None:
        if run.evaluation_case_id is None:  # pragma: no cover
            raise RuntimeError(
                "Cannot hand off Banking discovery without an evaluation case."
            )
        existing = await self._workflows.get_node(
            run.workflow_run_id, WorkflowNode.BANKING_DISCOVERY_HANDOFF.value
        )
        artifacts = await self._artifacts.list_by_case(run.evaluation_case_id)
        case_artifact = self._latest(artifacts, ArtifactType.EVALUATION_CASE)
        route_artifact = self._latest(artifacts, ArtifactType.DECISION_ROUTE_PLAN)
        identity_inputs = (
            (
                case_artifact.artifact_id,
                case_artifact.version,
                case_artifact.input_hash,
            )
            if case_artifact is not None
            else None,
            (
                route_artifact.artifact_id,
                route_artifact.version,
                route_artifact.input_hash,
            )
            if route_artifact is not None
            else None,
            CurrencyCode.VND,
        )
        expected_hash = self._node_input_hash(
            run,
            WorkflowNode.BANKING_DISCOVERY_HANDOFF,
            identity_inputs,
        )
        if self._node_completed(existing) and existing.input_hash == expected_hash:
            return None
        node = await self._start_node(
            run,
            WorkflowNode.BANKING_DISCOVERY_HANDOFF,
            identity_inputs=identity_inputs,
        )
        result = await self._services.decision_banking_handoff(
            evaluation_case_id=run.evaluation_case_id
        )
        await self._finish_node(
            node,
            self._result_node_status(result.status, result.component_status),
            result.generated_artifacts,
            waiting_for=tuple(
                item.requirement_code for item in result.missing_data_requests
            ),
            failure_reason="; ".join(result.validation_errors) or None,
        )
        return result

    async def _pause_for_banking_handoff_input(
        self,
        run: CaseWorkflowRun,
        result: BankingDiscoveryHandoffExecutionResult,
    ) -> None:
        request_ids = tuple(
            item.request_id for item in result.missing_data_requests
        )
        updated = await self._save_run(
            run,
            status=WorkflowStatus.WAITING_FOR_INPUT,
            current_stage=WorkflowNode.BANKING_DISCOVERY_HANDOFF.value,
            pending_request_ids=request_ids,
            resume_stage=WorkflowNode.BANKING_DISCOVERY_HANDOFF.value,
            failure_reason=None,
        )
        await self._event(
            updated,
            "WORKFLOW_WAITING_FOR_INPUT",
            WorkflowNode.BANKING_DISCOVERY_HANDOFF,
            {"request_ids": list(request_ids)},
        )

    async def _banking_internal_discovery(
        self, run: CaseWorkflowRun
    ) -> BankingDiscoveryExecutionResult | None:
        if run.evaluation_case_id is None:  # pragma: no cover
            raise RuntimeError("Cannot run Banking without an evaluation case.")
        artifacts = await self._artifacts.list_by_case(run.evaluation_case_id)
        request_artifact = self._latest(
            artifacts, ArtifactType.BANKING_DISCOVERY_REQUEST
        )
        request_artifact_id = (
            request_artifact.artifact_id if request_artifact is not None else None
        )
        case_artifact = self._latest(artifacts, ArtifactType.EVALUATION_CASE)
        case_artifact_id = (
            case_artifact.artifact_id if case_artifact is not None else None
        )
        supplement_artifact = self._latest(
            artifacts, ArtifactType.BANKING_INPUT_SUPPLEMENT
        )
        supplement_artifact_id = (
            supplement_artifact.artifact_id
            if supplement_artifact is not None
            else None
        )
        identity_inputs = (
            case_artifact_id,
            request_artifact_id,
            supplement_artifact_id,
            self._services.banking_policy_hash,
            self._services.banking_advisor_configuration_hash,
            CurrencyCode.VND,
        )
        expected_hash = self._node_input_hash(
            run,
            WorkflowNode.BANKING_INTERNAL_DISCOVERY,
            identity_inputs,
        )
        existing = await self._workflows.get_node(
            run.workflow_run_id, WorkflowNode.BANKING_INTERNAL_DISCOVERY.value
        )
        if self._node_completed(existing) and existing.input_hash == expected_hash:
            return None
        node = await self._start_node(
            run,
            WorkflowNode.BANKING_INTERNAL_DISCOVERY,
            identity_inputs=identity_inputs,
        )
        result = await self._services.banking_internal_discovery(
            evaluation_case_id=run.evaluation_case_id
        )
        await self._finish_node(
            node,
            self._result_node_status(result.status, result.component_status),
            result.generated_artifacts,
            waiting_for=tuple(
                item.requirement_code for item in result.missing_data_requests
            ),
            failure_reason="; ".join(result.validation_errors) or None,
        )
        return result

    async def _pause_for_banking_discovery_input(
        self,
        run: CaseWorkflowRun,
        result: BankingDiscoveryExecutionResult,
    ) -> None:
        request_ids = tuple(item.request_id for item in result.missing_data_requests)
        updated = await self._save_run(
            run,
            status=WorkflowStatus.WAITING_FOR_INPUT,
            current_stage=WorkflowNode.BANKING_INTERNAL_DISCOVERY.value,
            pending_request_ids=request_ids,
            resume_stage=WorkflowNode.BANKING_INTERNAL_DISCOVERY.value,
            failure_reason=None,
        )
        await self._event(
            updated,
            "WORKFLOW_WAITING_FOR_INPUT",
            WorkflowNode.BANKING_INTERNAL_DISCOVERY,
            {"request_ids": list(request_ids)},
        )

    async def _banking_precheck_readiness(
        self, run: CaseWorkflowRun
    ) -> BankingPrecheckReadinessExecutionResult | None:
        if run.evaluation_case_id is None:  # pragma: no cover
            raise RuntimeError("Cannot assess Banking readiness without a case.")
        artifacts = await self._artifacts.list_by_case(run.evaluation_case_id)
        case_artifact = self._latest(artifacts, ArtifactType.EVALUATION_CASE)
        matrix_artifact = self._latest(
            artifacts, ArtifactType.BANKING_OPTION_MATRIX
        )
        request_artifact = self._latest(
            artifacts, ArtifactType.BANKING_DISCOVERY_REQUEST
        )
        supplement_artifact = self._latest(
            artifacts, ArtifactType.BANKING_INPUT_SUPPLEMENT
        )
        identity_inputs = (
            *(
                item.artifact_id
                for item in (
                    case_artifact,
                    request_artifact,
                    matrix_artifact,
                    supplement_artifact,
                )
                if item is not None
            ),
            self._services.banking_policy_hash,
            CurrencyCode.VND,
        )
        expected_hash = self._node_input_hash(
            run,
            WorkflowNode.BANKING_PRECHECK_READINESS,
            identity_inputs,
        )
        existing = await self._workflows.get_node(
            run.workflow_run_id, WorkflowNode.BANKING_PRECHECK_READINESS.value
        )
        if self._node_completed(existing) and existing.input_hash == expected_hash:
            return None
        node = await self._start_node(
            run,
            WorkflowNode.BANKING_PRECHECK_READINESS,
            identity_inputs=identity_inputs,
        )
        result = await self._services.banking_precheck_readiness(
            evaluation_case_id=run.evaluation_case_id
        )
        await self._finish_node(
            node,
            self._result_node_status(result.status, result.component_status),
            result.generated_artifacts,
            failure_reason="; ".join(result.validation_errors) or None,
        )
        return result

    async def _decision_post_banking_review(
        self, run: CaseWorkflowRun
    ) -> DecisionPostBankingExecutionResult | None:
        if run.evaluation_case_id is None:  # pragma: no cover
            raise RuntimeError("Cannot review Banking readiness without a case.")
        artifacts = await self._artifacts.list_by_case(run.evaluation_case_id)
        matrix_artifact = self._latest(
            artifacts, ArtifactType.BANKING_OPTION_MATRIX
        )
        readiness_artifact = self._latest(
            artifacts, ArtifactType.BANKING_PRECHECK_READINESS
        )
        identity_inputs = tuple(
            (item.artifact_type, item.artifact_id, item.version, item.input_hash)
            for item in (matrix_artifact, readiness_artifact)
            if item is not None
        )
        expected_hash = self._node_input_hash(
            run,
            WorkflowNode.DECISION_POST_BANKING_REVIEW,
            identity_inputs,
        )
        existing = await self._workflows.get_node(
            run.workflow_run_id, WorkflowNode.DECISION_POST_BANKING_REVIEW.value
        )
        if self._node_completed(existing) and existing.input_hash == expected_hash:
            return None
        node = await self._start_node(
            run,
            WorkflowNode.DECISION_POST_BANKING_REVIEW,
            identity_inputs=identity_inputs,
        )
        result = await self._services.decision_post_banking_review(
            evaluation_case_id=run.evaluation_case_id
        )
        await self._finish_node(
            node,
            self._result_node_status(result.status, result.component_status),
            result.generated_artifacts,
            waiting_for=tuple(
                item.requirement_code for item in result.missing_data_requests
            ),
            failure_reason="; ".join(result.validation_errors) or None,
        )
        return result

    async def _banking_precheck_submission_proposal(
        self, run: CaseWorkflowRun
    ) -> BankingPrecheckSubmissionProposalExecutionResult | None:
        if run.evaluation_case_id is None:  # pragma: no cover
            raise RuntimeError("Cannot prepare a Banking proposal without a case.")
        artifacts = await self._artifacts.list_by_case(run.evaluation_case_id)
        matrix_artifact = self._latest(
            artifacts, ArtifactType.BANKING_OPTION_MATRIX
        )
        readiness_artifact = self._latest(
            artifacts, ArtifactType.BANKING_PRECHECK_READINESS
        )
        review_artifact = self._latest(
            artifacts, ArtifactType.DECISION_POST_BANKING_REVIEW
        )
        identity_inputs = tuple(
            item.artifact_id
            for item in (matrix_artifact, readiness_artifact, review_artifact)
            if item is not None
        )
        expected_hash = self._node_input_hash(
            run,
            WorkflowNode.BANKING_PRECHECK_SUBMISSION_PROPOSAL,
            identity_inputs,
        )
        existing = await self._workflows.get_node(
            run.workflow_run_id,
            WorkflowNode.BANKING_PRECHECK_SUBMISSION_PROPOSAL.value,
        )
        if self._node_completed(existing) and existing.input_hash == expected_hash:
            return None
        node = await self._start_node(
            run,
            WorkflowNode.BANKING_PRECHECK_SUBMISSION_PROPOSAL,
            identity_inputs=identity_inputs,
        )
        result = await self._services.banking_precheck_submission_proposal(
            evaluation_case_id=run.evaluation_case_id
        )
        await self._finish_node(
            node,
            self._result_node_status(result.status, result.component_status),
            result.generated_artifacts,
            failure_reason="; ".join(result.validation_errors) or None,
        )
        return result

    async def _banking_precheck_execution(
        self,
        run: CaseWorkflowRun,
        *,
        proposal_artifact: ArtifactEnvelope,
        approval_request_id: str,
    ) -> BankingPrecheckResultExecutionResult | None:
        """Execute one exact approved proposal with durable node idempotency."""
        if run.evaluation_case_id is None:  # pragma: no cover
            raise RuntimeError("Cannot execute a Banking precheck without a case.")
        identity_inputs = (
            proposal_artifact.artifact_id,
            proposal_artifact.version,
            proposal_artifact.input_hash,
            approval_request_id,
            self._services.banking_precheck_adapter_id,
            self._services.banking_precheck_adapter_configuration_hash,
        )
        expected_hash = self._node_input_hash(
            run,
            WorkflowNode.BANKING_PRECHECK_EXECUTION,
            identity_inputs,
        )
        existing = await self._workflows.get_node(
            run.workflow_run_id,
            WorkflowNode.BANKING_PRECHECK_EXECUTION.value,
        )
        if self._node_completed(existing) and existing.input_hash == expected_hash:
            return await self._invoke_banking_precheck_execution(
                evaluation_case_id=run.evaluation_case_id,
                workflow_run_id=run.workflow_run_id,
                approval_request_id=approval_request_id,
                proposal_artifact_id=proposal_artifact.artifact_id,
                reuse_existing_only=True,
            )
        node = await self._start_node(
            run,
            WorkflowNode.BANKING_PRECHECK_EXECUTION,
            identity_inputs=identity_inputs,
        )
        result = await self._invoke_banking_precheck_execution(
            evaluation_case_id=run.evaluation_case_id,
            workflow_run_id=run.workflow_run_id,
            approval_request_id=approval_request_id,
            proposal_artifact_id=proposal_artifact.artifact_id,
            reuse_existing_only=False,
        )
        await self._finish_node(
            node,
            self._result_node_status(result.status, result.component_status),
            result.generated_artifacts,
            failure_reason="; ".join(result.validation_errors) or None,
        )
        return result

    async def _invoke_banking_precheck_execution(
        self,
        *,
        evaluation_case_id: str,
        workflow_run_id: str,
        approval_request_id: str,
        proposal_artifact_id: str,
        reuse_existing_only: bool,
    ) -> BankingPrecheckResultExecutionResult:
        """Keep unexpected provider/infrastructure details out of durable state."""
        try:
            return await self._services.banking_precheck_execution(
                evaluation_case_id=evaluation_case_id,
                workflow_run_id=workflow_run_id,
                approval_request_id=approval_request_id,
                proposal_artifact_id=proposal_artifact_id,
                reuse_existing_only=reuse_existing_only,
            )
        except Exception:
            return BankingPrecheckResultExecutionResult(
                status=WorkflowStatus.FAILED_SAFE,
                component_status=ComponentStatus.FAILED_SAFE,
                current_node=WorkflowNode.BANKING_PRECHECK_EXECUTION.value,
                validation_errors=(_BANKING_PRECHECK_EXECUTION_FAILURE,),
            )

    async def _decision_post_precheck_review(
        self,
        run: CaseWorkflowRun,
        *,
        result_set_artifact: ArtifactEnvelope,
    ) -> DecisionPostPrecheckExecutionResult | None:
        """Run or revalidate the exact Decision review for one result envelope."""
        if run.evaluation_case_id is None:  # pragma: no cover
            raise RuntimeError("Cannot review a precheck result without a case.")
        identity_inputs = (
            result_set_artifact.artifact_id,
            result_set_artifact.version,
            result_set_artifact.input_hash,
        )
        expected_hash = self._node_input_hash(
            run,
            WorkflowNode.DECISION_POST_PRECHECK_REVIEW,
            identity_inputs,
        )
        existing = await self._workflows.get_node(
            run.workflow_run_id,
            WorkflowNode.DECISION_POST_PRECHECK_REVIEW.value,
        )
        if self._node_completed(existing) and existing.input_hash == expected_hash:
            return await self._services.decision_post_precheck_review(
                evaluation_case_id=run.evaluation_case_id,
                workflow_run_id=run.workflow_run_id,
                result_set_artifact_id=result_set_artifact.artifact_id,
            )
        node = await self._start_node(
            run,
            WorkflowNode.DECISION_POST_PRECHECK_REVIEW,
            identity_inputs=identity_inputs,
        )
        result = await self._services.decision_post_precheck_review(
            evaluation_case_id=run.evaluation_case_id,
            workflow_run_id=run.workflow_run_id,
            result_set_artifact_id=result_set_artifact.artifact_id,
        )
        await self._finish_node(
            node,
            self._result_node_status(result.status, result.component_status),
            result.generated_artifacts,
            waiting_for=tuple(
                item.requirement_code for item in result.missing_data_requests
            ),
            failure_reason="; ".join(result.validation_errors) or None,
        )
        return result

    async def _decision_document_handoff(
        self,
        run: CaseWorkflowRun,
        *,
        review_artifact: ArtifactEnvelope,
        result_set_artifact: ArtifactEnvelope,
    ) -> DecisionDocumentHandoffExecutionResult | None:
        """Create requests from the exact conditional review/result pair."""
        if run.evaluation_case_id is None:  # pragma: no cover
            raise RuntimeError("Cannot hand off documents without a case.")
        identity_inputs = (
            review_artifact.artifact_id,
            review_artifact.version,
            review_artifact.input_hash,
            result_set_artifact.artifact_id,
            result_set_artifact.version,
            result_set_artifact.input_hash,
        )
        expected_hash = self._node_input_hash(
            run,
            WorkflowNode.DECISION_DOCUMENT_HANDOFF,
            identity_inputs,
        )
        existing = await self._workflows.get_node(
            run.workflow_run_id,
            WorkflowNode.DECISION_DOCUMENT_HANDOFF.value,
        )
        if self._node_completed(existing) and existing.input_hash == expected_hash:
            return await self._services.decision_document_handoff(
                evaluation_case_id=run.evaluation_case_id,
                workflow_run_id=run.workflow_run_id,
                review_artifact_id=review_artifact.artifact_id,
                result_set_artifact_id=result_set_artifact.artifact_id,
            )
        node = await self._start_node(
            run,
            WorkflowNode.DECISION_DOCUMENT_HANDOFF,
            identity_inputs=identity_inputs,
        )
        result = await self._services.decision_document_handoff(
            evaluation_case_id=run.evaluation_case_id,
            workflow_run_id=run.workflow_run_id,
            review_artifact_id=review_artifact.artifact_id,
            result_set_artifact_id=result_set_artifact.artifact_id,
        )
        await self._finish_node(
            node,
            self._result_node_status(result.status, result.component_status),
            result.generated_artifacts,
            failure_reason="; ".join(result.validation_errors) or None,
        )
        return result

    async def _document_preparation(
        self,
        run: CaseWorkflowRun,
        *,
        request_artifact: ArtifactEnvelope,
    ) -> DocumentSkillExecutionResult | None:
        """Prepare or rebuild one masked package from exact supplement lineage."""
        if run.evaluation_case_id is None:  # pragma: no cover
            raise RuntimeError("Cannot prepare documents without a case.")
        request = DocumentPreparationRequest.model_validate(request_artifact.payload)
        artifacts = await self._artifacts.list_by_case(run.evaluation_case_id)
        case_artifact = self._latest(artifacts, ArtifactType.EVALUATION_CASE)
        if case_artifact is None:
            raise RuntimeError("Document preparation has no EvaluationCase artifact.")
        supplements: list[ArtifactEnvelope] = []
        for artifact in artifacts:
            if (
                artifact.artifact_type
                is not ArtifactType.DOCUMENT_EVIDENCE_SUPPLEMENT
                or artifact.validation_status
                not in {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}
            ):
                continue
            supplement = DocumentEvidenceSupplement.model_validate(artifact.payload)
            if supplement.preparation_request_id == request.request_id:
                supplements.append(artifact)
        supplements.sort(key=lambda item: (item.version, item.artifact_id))
        input_artifacts = (case_artifact, request_artifact, *supplements)
        identity_inputs = (
            tuple(
                (item.artifact_id, item.version, item.input_hash)
                for item in input_artifacts
            ),
            self._services.document_masking_policy_hash,
            self._services.document_tokenizer_key_version,
        )
        expected_hash = self._node_input_hash(
            run,
            WorkflowNode.DOCUMENT_PREPARATION,
            identity_inputs,
        )
        existing = await self._workflows.get_node(
            run.workflow_run_id,
            WorkflowNode.DOCUMENT_PREPARATION.value,
        )
        if self._node_completed(existing) and existing.input_hash == expected_hash:
            return await self._services.document_preparation(
                evaluation_case_id=run.evaluation_case_id,
                workflow_run_id=run.workflow_run_id,
                preparation_request_artifact_id=request_artifact.artifact_id,
            )
        node = await self._start_node(
            run,
            WorkflowNode.DOCUMENT_PREPARATION,
            identity_inputs=identity_inputs,
        )
        result = await self._services.document_preparation(
            evaluation_case_id=run.evaluation_case_id,
            workflow_run_id=run.workflow_run_id,
            preparation_request_artifact_id=request_artifact.artifact_id,
        )
        await self._finish_node(
            node,
            self._result_node_status(result.status, result.component_status),
            result.generated_artifacts,
            waiting_for=tuple(
                item.request_id for item in result.missing_data_requests
            ),
            failure_reason="; ".join(result.validation_errors) or None,
        )
        return result

    async def _pause_for_document_input(
        self,
        run: CaseWorkflowRun,
        result: DocumentSkillExecutionResult,
    ) -> None:
        """Persist a precise, typed Document evidence wait contract."""
        package = result.package_draft
        requests = result.missing_data_requests
        request_ids = tuple(item.request_id for item in requests)
        valid_wait = (
            result.component_status is ComponentStatus.WAITING_FOR_INPUT
            and package is not None
            and package.readiness is DocumentPackageReadiness.WAITING_FOR_INPUT
            and bool(request_ids)
            and len(set(request_ids)) == len(request_ids)
            and requests == package.missing_data_requests
            and all(
                item.status is MissingRequestStatus.OPEN
                and item.evaluation_case_id == run.evaluation_case_id
                and item.raised_by == "DOCUMENT_SKILL"
                for item in requests
            )
        )
        if not valid_wait:
            await self._fail(
                run,
                WorkflowNode.DOCUMENT_PREPARATION,
                "Document returned an invalid missing-evidence wait contract.",
            )
            return
        updated = await self._save_run(
            run,
            status=WorkflowStatus.WAITING_FOR_INPUT,
            current_stage=WorkflowNode.DOCUMENT_PREPARATION.value,
            pending_request_ids=request_ids,
            resume_stage=WorkflowNode.DOCUMENT_PREPARATION.value,
            failure_reason=None,
        )
        await self._event(
            updated,
            "WORKFLOW_WAITING_FOR_DOCUMENT_INPUT",
            WorkflowNode.DOCUMENT_PREPARATION,
            {"request_ids": list(request_ids)},
        )

    async def _pause_for_post_precheck_input(
        self,
        run: CaseWorkflowRun,
        result: DecisionPostPrecheckExecutionResult,
    ) -> None:
        """Persist only a precise evidence request returned by the review."""
        review = result.review
        requests = result.missing_data_requests
        request_ids = tuple(item.request_id for item in requests)
        valid_wait = (
            result.component_status is ComponentStatus.WAITING_FOR_INPUT
            and review is not None
            and review.outcome
            is DecisionPostPrecheckOutcome.FOLLOW_UP_EVIDENCE_REQUIRED
            and bool(request_ids)
            and len(set(request_ids)) == len(request_ids)
            and request_ids
            == tuple(item.request_id for item in review.missing_data_requests)
            and review.required_input_fields
            == tuple(dict.fromkeys(item.field for item in requests))
            and all(
                item.status is MissingRequestStatus.OPEN
                and item.evaluation_case_id == run.evaluation_case_id
                for item in requests
            )
        )
        if not valid_wait:
            await self._fail(
                run,
                WorkflowNode.DECISION_POST_PRECHECK_REVIEW,
                "Decision returned an invalid post-precheck evidence wait contract.",
            )
            return
        updated = await self._save_run(
            run,
            status=WorkflowStatus.WAITING_FOR_INPUT,
            current_stage=WorkflowNode.DECISION_POST_PRECHECK_REVIEW.value,
            pending_request_ids=request_ids,
            resume_stage=WorkflowNode.DECISION_POST_PRECHECK_REVIEW.value,
            failure_reason=None,
        )
        await self._event(
            updated,
            "WORKFLOW_WAITING_FOR_INPUT",
            WorkflowNode.DECISION_POST_PRECHECK_REVIEW,
            {"request_ids": list(request_ids)},
        )

    async def _pause_for_post_banking_input(
        self,
        run: CaseWorkflowRun,
        result: DecisionPostBankingExecutionResult,
    ) -> None:
        review = result.review
        requests = result.missing_data_requests
        request_ids = tuple(item.request_id for item in requests)
        review_request_ids = (
            tuple(item.request_id for item in review.missing_data_requests)
            if review is not None
            else ()
        )
        valid_wait = (
            result.component_status is ComponentStatus.WAITING_FOR_INPUT
            and review is not None
            and review.outcome is DecisionPostBankingOutcome.BANKING_INPUT_REQUIRED
            and bool(request_ids)
            and len(set(request_ids)) == len(request_ids)
            and request_ids == review_request_ids
            and review.required_input_fields == tuple(item.field for item in requests)
            and all(
                item.status is MissingRequestStatus.OPEN
                and item.evaluation_case_id == run.evaluation_case_id
                for item in requests
            )
        )
        if not valid_wait:
            await self._fail(
                run,
                WorkflowNode.DECISION_POST_BANKING_REVIEW,
                "Decision returned an invalid post-Banking input wait contract.",
            )
            return
        updated = await self._save_run(
            run,
            status=WorkflowStatus.WAITING_FOR_INPUT,
            current_stage=WorkflowNode.DECISION_POST_BANKING_REVIEW.value,
            pending_request_ids=request_ids,
            resume_stage=WorkflowNode.DECISION_POST_BANKING_REVIEW.value,
            failure_reason=None,
        )
        await self._event(
            updated,
            "WORKFLOW_WAITING_FOR_INPUT",
            WorkflowNode.DECISION_POST_BANKING_REVIEW,
            {"request_ids": list(request_ids)},
        )

    async def _decision_initial_route(
        self, run: CaseWorkflowRun
    ) -> DecisionRouteExecutionResult | None:
        if run.evaluation_case_id is None:  # pragma: no cover
            raise RuntimeError("Cannot plan a Decision route without an evaluation case.")
        artifacts = await self._artifacts.list_by_case(run.evaluation_case_id)
        authoritative = tuple(
            (
                self._latest_risk_checkpoint_registry(artifacts)
                if artifact_type is ArtifactType.APPROVAL_CHECKPOINTS
                else self._latest(artifacts, artifact_type)
            )
            for artifact_type in (
                ArtifactType.EVALUATION_CASE,
                ArtifactType.FINANCE_FACTS,
                ArtifactType.OPERATIONS_FACTS,
                ArtifactType.INITIAL_RISK_ASSESSMENT,
                ArtifactType.APPROVAL_CHECKPOINTS,
            )
        )
        identity_inputs = tuple(
            (item.artifact_type, item.artifact_id, item.version, item.input_hash)
            for item in authoritative
            if item is not None
        )
        expected_hash = self._node_input_hash(
            run,
            WorkflowNode.DECISION_ROUTE_PLANNING,
            identity_inputs,
        )
        existing = await self._workflows.get_node(
            run.workflow_run_id, WorkflowNode.DECISION_ROUTE_PLANNING.value
        )
        if self._node_completed(existing) and existing.input_hash == expected_hash:
            return None
        node = await self._start_node(
            run,
            WorkflowNode.DECISION_ROUTE_PLANNING,
            identity_inputs=identity_inputs,
        )
        result = await self._services.decision_initial_route(
            evaluation_case_id=run.evaluation_case_id
        )
        await self._finish_node(
            node,
            self._result_node_status(result.status, result.component_status),
            result.generated_artifacts,
            waiting_for=tuple(
                item.requirement_code for item in result.missing_data_requests
            ),
            failure_reason="; ".join(result.validation_errors) or None,
        )
        return result

    @staticmethod
    def _latest_risk_checkpoint_registry(
        artifacts: tuple[ArtifactEnvelope, ...],
    ) -> ArtifactEnvelope | None:
        """Select Risk's registry, excluding later proposal-scoped policy versions."""
        candidates: list[ArtifactEnvelope] = []
        for artifact in artifacts:
            if (
                artifact.artifact_type is not ArtifactType.APPROVAL_CHECKPOINTS
                or artifact.validation_status
                not in {
                    ValidationStatus.VALID,
                    ValidationStatus.VALID_WITH_WARNINGS,
                }
            ):
                continue
            try:
                checkpoint_set = ApprovalCheckpointSet.model_validate(artifact.payload)
            except ValueError:
                continue
            if not checkpoint_set.policy_coverages and not any(
                item.protected_action
                is ProtectedAction.CONFIRM_FINAL_CONTRACT_DECISION
                for item in checkpoint_set.checkpoints
            ):
                candidates.append(artifact)
        return max(candidates, key=lambda item: item.version, default=None)

    async def _pause_for_decision_input(
        self,
        run: CaseWorkflowRun,
        result: DecisionRouteExecutionResult,
    ) -> None:
        request_ids = tuple(
            item.request_id for item in result.missing_data_requests
        )
        updated = await self._save_run(
            run,
            status=WorkflowStatus.WAITING_FOR_INPUT,
            current_stage=WorkflowNode.DECISION_ROUTE_PLANNING.value,
            pending_request_ids=request_ids,
            resume_stage=WorkflowNode.DECISION_ROUTE_PLANNING.value,
            failure_reason=None,
        )
        await self._event(
            updated,
            "WORKFLOW_WAITING_FOR_INPUT",
            WorkflowNode.DECISION_ROUTE_PLANNING,
            {"request_ids": list(request_ids)},
        )

    async def _pause_from_upstream(
        self,
        run: CaseWorkflowRun,
        finance: FinanceExecutionResult | None,
        operations: OperationsExecutionResult | None,
    ) -> None:
        results = tuple(item for item in (finance, operations) if item is not None)
        if any(item.status is WorkflowStatus.WAITING_FOR_INPUT for item in results):
            status = WorkflowStatus.WAITING_FOR_INPUT
            event_type = "WORKFLOW_WAITING_FOR_INPUT"
        else:
            status = WorkflowStatus.FAILED_SAFE
            event_type = "NODE_FAILED_SAFE"
        reason = "; ".join(
            error for item in results for error in item.validation_errors
        ) or "An upstream Initial Assessment node did not complete."
        updated = await self._save_run(
            run,
            status=status,
            current_stage=WorkflowNode.INITIAL_ASSESSMENT.value,
            failure_reason=reason,
        )
        await self._event(updated, event_type, WorkflowNode.INITIAL_ASSESSMENT)

    async def _load_reusable_decision_bundle(
        self,
        *,
        run: CaseWorkflowRun,
        node: WorkflowNodeState | None,
        expected_hash: str,
        final_risk_artifact: ArtifactEnvelope,
    ) -> _PersistedDecisionBundle | None:
        """Load immutable Decision outputs instead of invoking OpenAI during replay."""

        if node is None or node.input_hash != expected_hash:
            return None
        recoverable_failed_replay = (
            node.status is WorkflowNodeStatus.FAILED_SAFE
            and any(
                fragment in (node.failure_reason or "")
                for fragment in _RECOVERABLE_DECISION_REPLAY_FAILURES
            )
        )
        if not self._node_completed(node) and not recoverable_failed_replay:
            return None
        if run.evaluation_case_id is None:  # pragma: no cover - caller guard
            return None

        artifacts = await self._artifacts.list_by_case(run.evaluation_case_id)
        artifacts_by_id = {item.artifact_id: item for item in artifacts}
        latest_card_artifact = self._latest_validated(
            artifacts, ArtifactType.DECISION_CARD
        )
        if (
            latest_card_artifact is None
            or latest_card_artifact.artifact_id not in node.output_artifact_ids
            or latest_card_artifact.evaluation_case_id != run.evaluation_case_id
        ):
            return None
        try:
            card = DecisionCard.model_validate(latest_card_artifact.payload)
        except ValueError:
            return None

        analysis_artifact = artifacts_by_id.get(card.ai_analysis_artifact.artifact_id)
        latest_analysis_artifact = self._latest_validated(
            artifacts, ArtifactType.AI_DECISION_ANALYSIS
        )
        if (
            analysis_artifact is None
            or latest_analysis_artifact is None
            or analysis_artifact.artifact_id != latest_analysis_artifact.artifact_id
            or analysis_artifact.artifact_id not in node.output_artifact_ids
            or analysis_artifact.artifact_type
            is not ArtifactType.AI_DECISION_ANALYSIS
            or analysis_artifact.validation_status
            not in {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}
            or analysis_artifact.evaluation_case_id != run.evaluation_case_id
        ):
            return None
        try:
            analysis = AIDecisionAnalysis.model_validate(analysis_artifact.payload)
        except ValueError:
            return None

        if (
            analysis_artifact.input_artifact_ids
            != (final_risk_artifact.artifact_id,)
            or latest_card_artifact.input_artifact_ids
            != (analysis_artifact.artifact_id,)
            or not self._artifact_ref_matches(
                analysis.final_risk_artifact,
                final_risk_artifact,
            )
            or not self._artifact_ref_matches(
                card.final_risk_artifact,
                final_risk_artifact,
            )
            or not self._artifact_ref_matches(
                card.ai_analysis_artifact,
                analysis_artifact,
            )
            or card.ai_analysis_id != analysis.analysis_id
            or card.internal_decision_package_artifact
            != analysis.internal_decision_package_artifact
            or card.recommendation is not analysis.recommendation
            or card.executive_summary != analysis.executive_summary
            or card.reasons != analysis.reasons
            or card.conditions != analysis.conditions
            or card.selected_negotiation_strategy_ids
            != analysis.selected_negotiation_strategy_ids
            or card.selected_negotiation_strategies
            != analysis.selected_negotiation_strategies
            or card.selected_option_ids != analysis.selected_option_ids
            or card.confidence is not analysis.confidence
            or card.human_attention_points != analysis.human_attention_points
        ):
            return None
        return _PersistedDecisionBundle(
            analysis_artifact=analysis_artifact,
            analysis=analysis,
            card_artifact=latest_card_artifact,
            card=card,
        )

    @staticmethod
    def _artifact_ref_matches(
        reference: ExactDecisionArtifactRef,
        artifact: ArtifactEnvelope,
    ) -> bool:
        return (
            reference.artifact_id == artifact.artifact_id
            and reference.artifact_type is artifact.artifact_type
            and reference.version == artifact.version
            and reference.input_hash == artifact.input_hash
        )

    async def _fail(
        self, run: CaseWorkflowRun, node: WorkflowNode, reason: str
    ) -> None:
        existing = await self._workflows.get_node(run.workflow_run_id, node.value)
        if existing is not None and not self._node_completed(existing):
            await self._finish_node(
                existing,
                WorkflowNodeStatus.FAILED_SAFE,
                (),
                failure_reason=reason,
            )
        failed = await self._save_run(
            run,
            status=WorkflowStatus.FAILED_SAFE,
            current_stage=node.value,
            failure_reason=reason,
        )
        await self._event(
            failed,
            "NODE_FAILED_SAFE",
            node,
            {"reason": reason},
        )

    async def _start_node(
        self,
        run: CaseWorkflowRun,
        node: WorkflowNode,
        *,
        identity_inputs: tuple[object, ...] = (),
    ) -> WorkflowNodeState:
        previous = await self._workflows.get_node(run.workflow_run_id, node.value)
        state = WorkflowNodeState(
            workflow_run_id=run.workflow_run_id,
            node=node,
            status=WorkflowNodeStatus.RUNNING,
            attempt=(previous.attempt if previous is not None else 0) + 1,
            input_hash=self._node_input_hash(run, node, identity_inputs),
            output_artifact_ids=(
                previous.output_artifact_ids if previous is not None else ()
            ),
            started_at=self._clock(),
        )
        await self._workflows.save_node(state)
        await self._event(run, "NODE_STARTED", node, {"attempt": state.attempt})
        return state

    @staticmethod
    def _node_input_hash(
        run: CaseWorkflowRun,
        node: WorkflowNode,
        identity_inputs: tuple[object, ...] = (),
    ) -> str:
        if not identity_inputs:
            return deterministic_id(
                "NIN",
                run.dataset_snapshot_hash,
                run.evaluation_case_id,
                node,
                run.as_of_date,
            )
        return deterministic_id(
            "NIN",
            run.dataset_snapshot_hash,
            run.evaluation_case_id,
            node,
            run.as_of_date,
            identity_inputs,
        )

    async def _finish_node(
        self,
        node: WorkflowNodeState,
        status: WorkflowNodeStatus,
        artifacts: tuple[ArtifactEnvelope, ...],
        *,
        waiting_for: tuple[str, ...] = (),
        failure_reason: str | None = None,
    ) -> None:
        artifact_ids = tuple(
            dict.fromkeys(
                (*node.output_artifact_ids, *(item.artifact_id for item in artifacts))
            )
        )
        completed = node.model_copy(
            update={
                "status": status,
                "output_artifact_ids": artifact_ids,
                "waiting_for": waiting_for,
                "failure_reason": failure_reason,
                "completed_at": (
                    self._clock()
                    if status
                    in {
                        WorkflowNodeStatus.COMPLETED,
                        WorkflowNodeStatus.COMPLETED_WITH_WARNINGS,
                        WorkflowNodeStatus.FAILED_SAFE,
                    }
                    else None
                ),
            }
        )
        await self._workflows.save_node(completed)
        await self._events.append(
            workflow_run_id=node.workflow_run_id,
            event_type=(
                "NODE_COMPLETED"
                if self._node_completed(completed)
                else "NODE_WAITING"
                if status
                in {
                    WorkflowNodeStatus.WAITING_FOR_DEPENDENCIES,
                    WorkflowNodeStatus.WAITING_FOR_INPUT,
                }
                else "NODE_FAILED_SAFE"
            ),
            node=node.node,
            metadata={
                "status": status.value,
                "artifact_ids": list(artifact_ids),
                "waiting_for": list(waiting_for),
            },
            created_at=self._clock(),
        )

    async def _save_run(
        self,
        run: CaseWorkflowRun,
        *,
        status: WorkflowStatus,
        current_stage: str,
        evaluation_case_id: str | None = None,
        pending_request_ids: tuple[str, ...] | None = None,
        resume_stage: str | None = None,
        blocked_action: ProtectedAction | None = None,
        failure_reason: str | None = None,
        honor_demo_pause: bool = True,
    ) -> CaseWorkflowRun:
        latest = await self._workflows.get_run(run.workflow_run_id)
        if (
            honor_demo_pause
            and latest is not None
            and latest.status is WorkflowStatus.WAITING_FOR_DEMO
            and status
            in {
                WorkflowStatus.PENDING,
                WorkflowStatus.RUNNING,
                WorkflowStatus.COMPLETED,
            }
        ):
            raise _DemoPauseInterrupted
        update: dict[str, object] = {
            "status": status,
            "current_stage": current_stage,
            "resume_stage": resume_stage,
            "blocked_action": blocked_action,
            "failure_reason": failure_reason,
            "updated_at": self._clock(),
        }
        if evaluation_case_id is not None:
            update["evaluation_case_id"] = evaluation_case_id
        if pending_request_ids is not None:
            update["pending_request_ids"] = pending_request_ids
        updated = run.model_copy(update=update)
        await self._workflows.save_run(updated)
        return updated

    async def _event(
        self,
        run: CaseWorkflowRun,
        event_type: str,
        node: WorkflowNode | None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        await self._events.append(
            workflow_run_id=run.workflow_run_id,
            event_type=event_type,
            node=node,
            metadata=dict(metadata or {}),
            created_at=self._clock(),
        )

    async def _event_once(
        self,
        run: CaseWorkflowRun,
        event_type: str,
        node: WorkflowNode | None,
        identity_key: str,
        identity_value: str,
        metadata: dict[str, object],
    ) -> None:
        """Append a business event once for its durable artifact or approval identity."""
        events = await self._events.list_after(run.workflow_run_id, 0)
        if any(
            item.event_type == event_type
            and item.node is node
            and item.metadata.get(identity_key) == identity_value
            for item in events
        ):
            return
        await self._event(run, event_type, node, metadata)

    async def _require_run(self, workflow_run_id: str) -> CaseWorkflowRun:
        run = await self._workflows.get_run(workflow_run_id)
        if run is None:
            raise CaseWorkflowNotFoundError("Workflow run was not found.")
        return run

    @staticmethod
    def _node_completed(node: WorkflowNodeState | None) -> bool:
        return node is not None and node.status in {
            WorkflowNodeStatus.COMPLETED,
            WorkflowNodeStatus.COMPLETED_WITH_WARNINGS,
        }

    @staticmethod
    def _component_node_status(status: ComponentStatus) -> WorkflowNodeStatus:
        if status is ComponentStatus.COMPLETED:
            return WorkflowNodeStatus.COMPLETED
        if status is ComponentStatus.COMPLETED_WITH_WARNINGS:
            return WorkflowNodeStatus.COMPLETED_WITH_WARNINGS
        if status is ComponentStatus.WAITING_FOR_INPUT:
            return WorkflowNodeStatus.WAITING_FOR_INPUT
        return WorkflowNodeStatus.FAILED_SAFE

    @classmethod
    def _result_node_status(
        cls, workflow_status: WorkflowStatus, component_status: ComponentStatus
    ) -> WorkflowNodeStatus:
        if workflow_status is WorkflowStatus.COMPLETED:
            return cls._component_node_status(component_status)
        if workflow_status is WorkflowStatus.WAITING_FOR_INPUT:
            return WorkflowNodeStatus.WAITING_FOR_INPUT
        if workflow_status is WorkflowStatus.WAITING_FOR_DEPENDENCIES:
            return WorkflowNodeStatus.WAITING_FOR_DEPENDENCIES
        return WorkflowNodeStatus.FAILED_SAFE

    @staticmethod
    def _upstream_completed(
        finance: FinanceExecutionResult | None,
        operations: OperationsExecutionResult | None,
    ) -> bool:
        return all(
            item is None or item.status is WorkflowStatus.COMPLETED
            for item in (finance, operations)
        )

    @staticmethod
    def _latest(
        artifacts: tuple[ArtifactEnvelope, ...], artifact_type: ArtifactType
    ) -> ArtifactEnvelope | None:
        matches = tuple(item for item in artifacts if item.artifact_type is artifact_type)
        return max(matches, key=lambda item: item.version, default=None)

    @staticmethod
    def _latest_validated(
        artifacts: tuple[ArtifactEnvelope, ...], artifact_type: ArtifactType
    ) -> ArtifactEnvelope | None:
        matches = tuple(
            item
            for item in artifacts
            if item.artifact_type is artifact_type
            and item.validation_status
            in {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}
        )
        return max(matches, key=lambda item: item.version, default=None)

    @staticmethod
    def _latest_advice_for_matrix(
        artifacts: tuple[ArtifactEnvelope, ...],
        matrix_artifact: ArtifactEnvelope | None,
    ) -> ArtifactEnvelope | None:
        """Keep optional advice only when it explicitly binds the chosen matrix."""
        if matrix_artifact is None:
            return None
        try:
            matrix = BankingOptionMatrix.model_validate(matrix_artifact.payload)
        except ValueError:
            return None
        matches: list[ArtifactEnvelope] = []
        for artifact in artifacts:
            if (
                artifact.artifact_type is not ArtifactType.BANKING_OPTION_ADVICE
                or artifact.validation_status
                not in {
                    ValidationStatus.VALID,
                    ValidationStatus.VALID_WITH_WARNINGS,
                }
            ):
                continue
            try:
                advice = BankingOptionAdvice.model_validate(artifact.payload)
            except ValueError:
                continue
            if advice.matrix_id == matrix.matrix_id:
                matches.append(artifact)
        return max(matches, key=lambda item: item.version, default=None)
