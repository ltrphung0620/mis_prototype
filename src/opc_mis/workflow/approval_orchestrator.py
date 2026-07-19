"""Workflow-owned approval pause, human resolution, and safe resume."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

from opc_mis.domain.approvals import (
    ApprovalCheckpointSet,
    ApprovalDecisionRecord,
    ApprovalExecutionResult,
    ApprovalRequest,
)
from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.case_workflow_models import CaseWorkflowRun, WorkflowNodeState
from opc_mis.domain.commands import ActionCommand
from opc_mis.domain.enums import (
    ApprovalDecision,
    ApprovalGateStatus,
    ApprovalRequestStatus,
    ArtifactType,
    ProtectedAction,
    ValidationStatus,
    WorkflowNodeStatus,
    WorkflowStatus,
)
from opc_mis.domain.lineage import deterministic_id
from opc_mis.domain.workflow import WorkflowNode
from opc_mis.governance.approval_gate import ApprovalGate
from opc_mis.ports.approval_request_repository import ApprovalRequestRepository
from opc_mis.ports.artifact_repository import ArtifactRepository
from opc_mis.ports.case_workflow_repository import CaseWorkflowRepository
from opc_mis.ports.runtime_event_repository import RuntimeEventRepository


class ApprovalControlError(LookupError):
    """Raised when an approval operation cannot be tied to validated case state."""


class ApprovalConflictError(ValueError):
    """Raised when an approval transition conflicts with persisted workflow state."""


class ApprovalOrchestrator:
    """Apply Governance results to the same durable Master Workflow when supplied."""

    def __init__(
        self,
        *,
        artifacts: ArtifactRepository,
        requests: ApprovalRequestRepository,
        case_workflows: CaseWorkflowRepository,
        events: RuntimeEventRepository,
        gate: ApprovalGate | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._artifacts = artifacts
        self._requests = requests
        self._case_workflows = case_workflows
        self._events = events
        self._gate = gate or ApprovalGate()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._decision_locks: dict[str, asyncio.Lock] = {}

    async def request_action(
        self,
        command: ActionCommand,
        *,
        workflow_run_id: str | None = None,
        allow_running_workflow: bool = False,
    ) -> ApprovalExecutionResult:
        """Evaluate an action and pause its Master Workflow only when a gate triggers.

        ``allow_running_workflow`` is reserved for the Master Workflow while it is
        proposing its own protected action. Public/manual callers keep the default
        fail-closed behavior and cannot inject an action into an executing run.
        """
        payload_artifact = await self._require_current_subject(command)
        if command.action_type is ProtectedAction.SEND_DOCUMENT_TO_EXTERNAL_PARTNER:
            raise ApprovalConflictError(
                "DOCUMENT_RELEASE_PACKAGE is internal Decision input. External Document "
                "submission cannot be proposed until a validated final Decision "
                "submission proposal exists."
            )
        checkpoint_artifact, checkpoint_set = await self._require_checkpoint_registry(
            command.evaluation_case_id
        )
        run = await self._optional_case_workflow(
            workflow_run_id,
            command.evaluation_case_id,
            allow_running_workflow=allow_running_workflow,
        )
        evaluation = self._gate.evaluate(command, checkpoint_set)
        action_checkpoints = tuple(
            item
            for item in checkpoint_set.checkpoints
            if item.protected_action is command.action_type
        )
        policy_coverage_ids = tuple(
            item.coverage_id
            for item in checkpoint_set.policy_coverages
            if item.protected_action is command.action_type
            and item.evaluation_case_id == command.evaluation_case_id
            and item.subject_artifact_id == payload_artifact.artifact_id
        )

        if evaluation.status is ApprovalGateStatus.AUTHORIZED:
            request_workflow_id = (
                run.workflow_run_id
                if run is not None
                else deterministic_id(
                    "APR-STANDALONE",
                    command.evaluation_case_id,
                    command.action_type,
                    payload_artifact.artifact_id,
                    payload_artifact.version,
                    payload_artifact.input_hash,
                    command.requested_by,
                    command.payload,
                )
            )
            authorization_id = deterministic_id(
                "APR",
                request_workflow_id,
                command.action_type,
                payload_artifact.artifact_id,
                payload_artifact.version,
                payload_artifact.input_hash,
                command.requested_by,
                command.payload,
                checkpoint_artifact.artifact_id,
                checkpoint_artifact.version,
                checkpoint_artifact.input_hash,
                tuple(item.checkpoint_id for item in action_checkpoints),
                policy_coverage_ids,
                ApprovalRequestStatus.AUTHORIZED_WITHOUT_HUMAN,
            )
            authorization = await self._requests.get(authorization_id)
            if authorization is None:
                authorization = ApprovalRequest(
                    request_id=authorization_id,
                    workflow_run_id=request_workflow_id,
                    evaluation_case_id=command.evaluation_case_id,
                    dataset_id=checkpoint_set.dataset_id,
                    subject_artifact_id=payload_artifact.artifact_id,
                    subject_artifact_version=payload_artifact.version,
                    subject_input_hash=payload_artifact.input_hash,
                    checkpoint_ids=tuple(
                        item.checkpoint_id for item in action_checkpoints
                    ),
                    policy_artifact_id=checkpoint_artifact.artifact_id,
                    policy_artifact_version=checkpoint_artifact.version,
                    policy_input_hash=checkpoint_artifact.input_hash,
                    policy_coverage_ids=policy_coverage_ids,
                    command=command,
                    resume_stage=(
                        run.resume_stage or run.current_stage
                        if run is not None
                        else None
                    ),
                    status=ApprovalRequestStatus.AUTHORIZED_WITHOUT_HUMAN,
                    created_at=self._clock(),
                )
                await self._requests.save(authorization)
            elif authorization.status is not ApprovalRequestStatus.AUTHORIZED_WITHOUT_HUMAN:
                raise ApprovalConflictError(
                    "The deterministic action-authorization identity is already used."
                )

            status = run.status if run is not None else WorkflowStatus.COMPLETED
            resuming_input_wait = (
                run is not None and run.status is WorkflowStatus.WAITING_FOR_INPUT
            )
            if run is not None and run.status is WorkflowStatus.WAITING_FOR_INPUT:
                run = await self._resume_run(run)
                status = run.status
                await self._event_once(
                    run,
                    "WORKFLOW_RESUME_REQUESTED",
                    WorkflowNode.APPROVAL_GATE,
                    {
                        "request_id": authorization.request_id,
                        "action_type": command.action_type.value,
                    },
                )
            if run is not None:
                await self._save_gate_node(
                    run,
                    status=WorkflowNodeStatus.COMPLETED,
                    action=command.action_type,
                    waiting_for=(),
                    failure_reason=None,
                    begin_attempt=not resuming_input_wait,
                )
                await self._event_once(
                    run,
                    "PROTECTED_ACTION_ALLOWED",
                    WorkflowNode.PROTECTED_ACTION_AUTHORIZED,
                    {
                        "request_id": authorization.request_id,
                        "action_type": command.action_type.value,
                        "authorization_mode": "POLICY_NO_HUMAN_REQUIRED",
                    },
                )
            return ApprovalExecutionResult(
                status=status,
                gate_status=ApprovalGateStatus.AUTHORIZED,
                current_node=WorkflowNode.PROTECTED_ACTION_AUTHORIZED.value,
                workflow_run_id=run.workflow_run_id if run is not None else None,
                evaluation_case_id=command.evaluation_case_id,
                action_authorized=True,
                approval_request=authorization,
                reason=evaluation.reason,
            )

        if evaluation.status is ApprovalGateStatus.WAITING_FOR_INPUT:
            if run is not None:
                already_paused = (
                    run.status is WorkflowStatus.WAITING_FOR_INPUT
                    and run.blocked_action is command.action_type
                )
                run = await self._pause_run(
                    run,
                    status=WorkflowStatus.WAITING_FOR_INPUT,
                    current_stage=WorkflowNode.APPROVAL_GATE.value,
                    action=command.action_type,
                    reason=evaluation.reason,
                )
                await self._save_gate_node(
                    run,
                    status=WorkflowNodeStatus.WAITING_FOR_INPUT,
                    action=command.action_type,
                    waiting_for=evaluation.missing_fields,
                    failure_reason=evaluation.reason,
                    begin_attempt=not already_paused,
                )
                await self._event(
                    run,
                    "WORKFLOW_PAUSED",
                    WorkflowNode.APPROVAL_GATE,
                    {
                        "reason": "WAITING_FOR_INPUT",
                        "action_type": command.action_type.value,
                        "missing_fields": list(evaluation.missing_fields),
                    },
                )
            return ApprovalExecutionResult(
                status=WorkflowStatus.WAITING_FOR_INPUT,
                gate_status=evaluation.status,
                current_node=WorkflowNode.APPROVAL_GATE.value,
                workflow_run_id=run.workflow_run_id if run is not None else None,
                evaluation_case_id=command.evaluation_case_id,
                action_authorized=False,
                missing_fields=evaluation.missing_fields,
                reason=evaluation.reason,
            )

        request_workflow_id = (
            run.workflow_run_id
            if run is not None
            else deterministic_id(
                "APR-STANDALONE",
                command.evaluation_case_id,
                command.action_type,
                payload_artifact.artifact_id,
                payload_artifact.version,
                payload_artifact.input_hash,
                command.requested_by,
                command.payload,
            )
        )
        request_id = deterministic_id(
            "APR",
            request_workflow_id,
            command.action_type,
            payload_artifact.artifact_id,
            payload_artifact.version,
            payload_artifact.input_hash,
            command.requested_by,
            command.payload,
            tuple(item.checkpoint_id for item in evaluation.triggered_checkpoints),
            checkpoint_artifact.artifact_id,
            checkpoint_artifact.version,
            checkpoint_artifact.input_hash,
            policy_coverage_ids,
        )
        if run is not None:
            await self._ensure_no_other_pending_request(run, request_id)
        approval_request = await self._requests.get(request_id)
        created = approval_request is None
        if approval_request is None:
            approval_request = ApprovalRequest(
                request_id=request_id,
                workflow_run_id=request_workflow_id,
                evaluation_case_id=command.evaluation_case_id,
                dataset_id=checkpoint_set.dataset_id,
                subject_artifact_id=payload_artifact.artifact_id,
                subject_artifact_version=payload_artifact.version,
                subject_input_hash=payload_artifact.input_hash,
                checkpoint_ids=tuple(
                    item.checkpoint_id for item in evaluation.triggered_checkpoints
                ),
                policy_artifact_id=checkpoint_artifact.artifact_id,
                policy_artifact_version=checkpoint_artifact.version,
                policy_input_hash=checkpoint_artifact.input_hash,
                policy_coverage_ids=policy_coverage_ids,
                command=command,
                resume_stage=(
                    run.resume_stage or run.current_stage if run is not None else None
                ),
                status=ApprovalRequestStatus.PENDING,
                created_at=self._clock(),
            )
            await self._requests.save(approval_request)

        if approval_request.status is ApprovalRequestStatus.PENDING:
            if run is not None:
                already_paused = (
                    run.status is WorkflowStatus.WAITING_FOR_APPROVAL
                    and run.blocked_action is command.action_type
                )
                run = await self._pause_run(
                    run,
                    status=WorkflowStatus.WAITING_FOR_APPROVAL,
                    current_stage=WorkflowNode.WAITING_FOR_APPROVAL.value,
                    action=command.action_type,
                    reason=evaluation.reason,
                )
                if created:
                    await self._event(
                        run,
                        "APPROVAL_REQUESTED",
                        WorkflowNode.APPROVAL_GATE,
                        {
                            "request_id": request_id,
                            "action_type": command.action_type.value,
                        },
                    )
                if not already_paused:
                    await self._save_gate_node(
                        run,
                        status=WorkflowNodeStatus.WAITING_FOR_APPROVAL,
                        action=command.action_type,
                        waiting_for=(request_id,),
                        failure_reason=evaluation.reason,
                        begin_attempt=True,
                    )
                    await self._event(
                        run,
                        "WORKFLOW_PAUSED",
                        WorkflowNode.WAITING_FOR_APPROVAL,
                        {"reason": "WAITING_FOR_APPROVAL", "request_id": request_id},
                    )
            return ApprovalExecutionResult(
                status=WorkflowStatus.WAITING_FOR_APPROVAL,
                gate_status=ApprovalGateStatus.WAITING_FOR_APPROVAL,
                current_node=WorkflowNode.WAITING_FOR_APPROVAL.value,
                workflow_run_id=request_workflow_id if run is not None else None,
                evaluation_case_id=command.evaluation_case_id,
                action_authorized=False,
                approval_request=approval_request,
                reason=evaluation.reason,
            )
        return self._resolved_result(approval_request, evaluation.reason, run)

    async def decide(
        self,
        *,
        request_id: str,
        decision: ApprovalDecision,
        decided_by: str,
        reason: str,
    ) -> ApprovalExecutionResult:
        """Persist a human decision and transition the same Master Workflow safely."""
        lock = self._decision_locks.setdefault(request_id, asyncio.Lock())
        async with lock:
            return await self._decide_locked(
                request_id=request_id,
                decision=decision,
                decided_by=decided_by,
                reason=reason,
            )

    async def _decide_locked(
        self,
        *,
        request_id: str,
        decision: ApprovalDecision,
        decided_by: str,
        reason: str,
    ) -> ApprovalExecutionResult:
        """Resolve one request under a process lock and repository compare-and-set."""
        request = await self._requests.get(request_id)
        if request is None:
            raise ApprovalControlError("Approval request was not found.")
        run = await self._case_workflows.get_run(request.workflow_run_id)

        target_status = (
            ApprovalRequestStatus.APPROVED
            if decision is ApprovalDecision.APPROVE
            else ApprovalRequestStatus.REJECTED
        )
        stale_scope_reason: str | None = None
        if request.status is ApprovalRequestStatus.PENDING:
            stale_scope_reason = await self._stale_scope_reason(request)
        if stale_scope_reason is not None:
            expired = request.model_copy(
                update={"status": ApprovalRequestStatus.EXPIRED}
            )
            stored, _ = await self._requests.compare_and_set(
                expired,
                expected_status=ApprovalRequestStatus.PENDING,
            )
            if stored is None:
                raise ApprovalControlError("Approval request was not found.")
            if stored.status not in {
                ApprovalRequestStatus.EXPIRED,
                target_status,
            }:
                raise ApprovalConflictError(
                    "A resolved approval request cannot receive a conflicting decision."
                )
            return await self._reconcile_resolution(
                stored,
                run,
                reason=(
                    stale_scope_reason
                    if stored.status is ApprovalRequestStatus.EXPIRED
                    else "Approval decision is unchanged."
                ),
            )

        if request.status is not ApprovalRequestStatus.PENDING:
            if request.status not in {ApprovalRequestStatus.EXPIRED, target_status}:
                raise ApprovalConflictError(
                    "A resolved approval request cannot receive a conflicting decision."
                )
            if (
                request.status is ApprovalRequestStatus.APPROVED
                and not await self._approved_reconciliation_is_complete(request, run)
                and (stale_scope_reason := await self._stale_scope_reason(request))
                is not None
            ):
                expired = request.model_copy(
                    update={"status": ApprovalRequestStatus.EXPIRED}
                )
                stored, _ = await self._requests.compare_and_set(
                    expired,
                    expected_status=ApprovalRequestStatus.APPROVED,
                )
                if stored is None:
                    raise ApprovalControlError("Approval request was not found.")
                if stored.status is not ApprovalRequestStatus.EXPIRED:
                    raise ApprovalConflictError(
                        "Approval recovery conflicted with another request transition."
                    )
                return await self._reconcile_resolution(
                    stored,
                    run,
                    reason=stale_scope_reason,
                )
            return await self._reconcile_resolution(
                request,
                run,
                reason=(
                    "Approval request expired."
                    if request.status is ApprovalRequestStatus.EXPIRED
                    else "Approval decision is unchanged."
                ),
            )

        resolved = request.model_copy(
            update={
                "status": target_status,
                "decision_record": ApprovalDecisionRecord(
                    decision=decision,
                    decided_by=decided_by,
                    reason=reason,
                    decided_at=self._clock(),
                ),
            }
        )
        stored, updated = await self._requests.compare_and_set(
            resolved,
            expected_status=ApprovalRequestStatus.PENDING,
        )
        if stored is None:
            raise ApprovalControlError("Approval request was not found.")
        if stored.status is not target_status:
            raise ApprovalConflictError(
                "A resolved approval request cannot receive a conflicting decision."
            )
        return await self._reconcile_resolution(
            stored,
            run,
            reason=(
                "Human approval decision recorded."
                if updated
                else "Approval decision is unchanged."
            ),
        )

    async def list_requests(self, evaluation_case_id: str) -> tuple[ApprovalRequest, ...]:
        """Return auditable approval requests for one case."""
        return await self._requests.list_by_case(evaluation_case_id)

    async def checkpoints(self, evaluation_case_id: str) -> ApprovalCheckpointSet:
        """Return the registered checkpoint artifact for one case."""
        _, checkpoint_set = await self._require_checkpoint_registry(
            evaluation_case_id
        )
        return checkpoint_set

    async def _require_current_subject(
        self, command: ActionCommand
    ) -> ArtifactEnvelope:
        artifact = await self._artifacts.get(command.payload_artifact_id)
        if artifact is None or artifact.evaluation_case_id != command.evaluation_case_id:
            raise ApprovalControlError(
                "payload_artifact_id must reference a validated artifact from this case."
            )
        if artifact.validation_status not in {
            ValidationStatus.VALID,
            ValidationStatus.VALID_WITH_WARNINGS,
        }:
            raise ApprovalControlError("The protected-action subject artifact is not valid.")
        artifacts = await self._artifacts.list_by_case(command.evaluation_case_id)
        latest = self._latest(artifacts, artifact.artifact_type)
        if latest is None or latest.artifact_id != artifact.artifact_id:
            raise ApprovalControlError(
                "payload_artifact_id is not the current version of its artifact type."
            )
        return artifact

    async def _subject_is_current(self, request: ApprovalRequest) -> bool:
        artifact = await self._artifacts.get(request.subject_artifact_id)
        if (
            artifact is None
            or artifact.evaluation_case_id != request.evaluation_case_id
            or artifact.version != request.subject_artifact_version
            or artifact.input_hash != request.subject_input_hash
        ):
            return False
        artifacts = await self._artifacts.list_by_case(request.evaluation_case_id)
        latest = self._latest(artifacts, artifact.artifact_type)
        return latest is not None and latest.artifact_id == artifact.artifact_id

    async def _stale_scope_reason(self, request: ApprovalRequest) -> str | None:
        """Explain which exact authorization input has been superseded."""
        if (
            request.command.action_type
            is ProtectedAction.SEND_DOCUMENT_TO_EXTERNAL_PARTNER
        ):
            return (
                "Direct Document release approval scope is obsolete; the release package "
                "is internal Decision input and cannot authorize external submission."
            )
        if not await self._subject_is_current(request):
            return "Approval subject artifact is no longer current."
        if not await self._policy_is_current(request):
            return "Approval policy artifact is no longer current."
        return None

    async def _approved_reconciliation_is_complete(
        self,
        request: ApprovalRequest,
        run: CaseWorkflowRun | None,
    ) -> bool:
        """Recognize a durable authorization before applying recovery checks."""
        if run is None:
            return True
        gate_node = await self._case_workflows.get_node(
            run.workflow_run_id,
            WorkflowNode.APPROVAL_GATE.value,
        )
        if (
            gate_node is None
            or gate_node.status is not WorkflowNodeStatus.COMPLETED
            or gate_node.waiting_for
        ):
            return False
        events = await self._events.list_after(run.workflow_run_id, 0)
        return any(
            item.event_type == "PROTECTED_ACTION_ALLOWED"
            and item.metadata.get("request_id") == request.request_id
            for item in events
        )

    async def _policy_is_current(self, request: ApprovalRequest) -> bool:
        """Require the exact bound policy envelope to remain current at decision time."""
        if (
            request.policy_artifact_id is None
            or request.policy_artifact_version is None
            or request.policy_input_hash is None
        ):
            return False
        artifact = await self._artifacts.get(request.policy_artifact_id)
        if (
            artifact is None
            or artifact.artifact_type is not ArtifactType.APPROVAL_CHECKPOINTS
            or artifact.evaluation_case_id != request.evaluation_case_id
            or artifact.version != request.policy_artifact_version
            or artifact.input_hash != request.policy_input_hash
            or artifact.validation_status
            not in {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}
        ):
            return False
        artifacts = await self._artifacts.list_by_case(request.evaluation_case_id)
        latest = self._latest(artifacts, ArtifactType.APPROVAL_CHECKPOINTS)
        return latest is not None and latest.artifact_id == artifact.artifact_id

    async def _require_checkpoint_registry(
        self, evaluation_case_id: str
    ) -> tuple[ArtifactEnvelope, ApprovalCheckpointSet]:
        artifacts = await self._artifacts.list_by_case(evaluation_case_id)
        artifact = self._latest(artifacts, ArtifactType.APPROVAL_CHECKPOINTS)
        if artifact is None:
            raise ApprovalControlError(
                "No approval checkpoints exist; run Initial Risk Scan first."
            )
        if artifact.validation_status not in {
            ValidationStatus.VALID,
            ValidationStatus.VALID_WITH_WARNINGS,
        }:
            raise ApprovalControlError("The approval checkpoint artifact is not valid.")
        return artifact, ApprovalCheckpointSet.model_validate(artifact.payload)

    async def _optional_case_workflow(
        self,
        workflow_run_id: str | None,
        evaluation_case_id: str,
        *,
        allow_running_workflow: bool = False,
    ) -> CaseWorkflowRun | None:
        if workflow_run_id is None:
            return None
        run = await self._case_workflows.get_run(workflow_run_id)
        if run is None:
            raise ApprovalControlError("Master Workflow was not found.")
        if run.evaluation_case_id != evaluation_case_id:
            raise ApprovalControlError(
                "workflow_run_id does not belong to this evaluation case."
            )
        if run.status is WorkflowStatus.PENDING or (
            run.status is WorkflowStatus.RUNNING and not allow_running_workflow
        ):
            raise ApprovalConflictError(
                "Protected actions cannot be submitted while the Master Workflow is executing."
            )
        if run.status is WorkflowStatus.BLOCKED:
            raise ApprovalConflictError("A blocked Master Workflow cannot start another action.")
        return run

    async def _ensure_no_other_pending_request(
        self, run: CaseWorkflowRun, request_id: str
    ) -> None:
        requests = await self._requests.list_by_case(run.evaluation_case_id or "")
        conflicts = tuple(
            item.request_id
            for item in requests
            if item.workflow_run_id == run.workflow_run_id
            and item.status is ApprovalRequestStatus.PENDING
            and item.request_id != request_id
        )
        if conflicts:
            raise ApprovalConflictError(
                "Master Workflow already has a different pending approval request."
            )

    async def _pause_run(
        self,
        run: CaseWorkflowRun,
        *,
        status: WorkflowStatus,
        current_stage: str,
        action: ProtectedAction,
        reason: str,
    ) -> CaseWorkflowRun:
        resume_stage = run.resume_stage or run.current_stage
        paused = run.model_copy(
            update={
                "status": status,
                "current_stage": current_stage,
                "resume_stage": resume_stage,
                "blocked_action": action,
                "failure_reason": reason,
                "updated_at": self._clock(),
            }
        )
        await self._case_workflows.save_run(paused)
        return paused

    async def _resume_run(
        self,
        run: CaseWorkflowRun,
        *,
        resume_stage: str | None = None,
    ) -> CaseWorkflowRun:
        resumed = run.model_copy(
            update={
                "status": WorkflowStatus.PENDING,
                "current_stage": resume_stage
                or run.resume_stage
                or WorkflowNode.DECISION_ROUTE_PLANNED.value,
                "resume_stage": None,
                "blocked_action": None,
                "failure_reason": None,
                "updated_at": self._clock(),
            }
        )
        await self._case_workflows.save_run(resumed)
        return resumed

    async def _reconcile_resolution(
        self,
        request: ApprovalRequest,
        run: CaseWorkflowRun | None,
        *,
        reason: str,
    ) -> ApprovalExecutionResult:
        """Finish workflow side effects idempotently after a durable request transition."""
        if run is not None:
            run = await self._case_workflows.get_run(run.workflow_run_id) or run
        if request.status is ApprovalRequestStatus.APPROVED:
            run = await self._reconcile_approved(request, run)
        elif request.status is ApprovalRequestStatus.REJECTED:
            run = await self._reconcile_rejected(request, run)
        elif request.status is ApprovalRequestStatus.EXPIRED:
            run = await self._reconcile_expired(request, run)
        return self._resolved_result(request, reason, run)

    async def _reconcile_approved(
        self,
        request: ApprovalRequest,
        run: CaseWorkflowRun | None,
    ) -> CaseWorkflowRun | None:
        if run is None:
            return None
        gate_node = await self._case_workflows.get_node(
            run.workflow_run_id,
            WorkflowNode.APPROVAL_GATE.value,
        )
        self._require_matching_wait(request, run, gate_node)
        if run.status is WorkflowStatus.WAITING_FOR_APPROVAL:
            run = await self._resume_run(run, resume_stage=request.resume_stage)
        elif run.status in {WorkflowStatus.WAITING_FOR_INPUT, WorkflowStatus.BLOCKED}:
            raise ApprovalConflictError(
                "The Master Workflow no longer waits for this approval request."
            )

        await self._event_once(
            run,
            "APPROVAL_RESOLVED",
            WorkflowNode.APPROVAL_GATE,
            {
                "request_id": request.request_id,
                "decision": ApprovalDecision.APPROVE.value,
            },
        )
        if gate_node is None or request.request_id in gate_node.waiting_for:
            await self._save_gate_node(
                run,
                status=WorkflowNodeStatus.COMPLETED,
                action=request.command.action_type,
                waiting_for=(),
                failure_reason=None,
                begin_attempt=False,
            )
        await self._event_once(
            run,
            "PROTECTED_ACTION_ALLOWED",
            WorkflowNode.PROTECTED_ACTION_AUTHORIZED,
            {
                "request_id": request.request_id,
                "action_type": request.command.action_type.value,
            },
        )
        await self._event_once(
            run,
            "WORKFLOW_RESUME_REQUESTED",
            WorkflowNode.PROTECTED_ACTION_AUTHORIZED,
            {"request_id": request.request_id},
        )
        return run

    async def _reconcile_rejected(
        self,
        request: ApprovalRequest,
        run: CaseWorkflowRun | None,
    ) -> CaseWorkflowRun | None:
        if run is None:
            return None
        gate_node = await self._case_workflows.get_node(
            run.workflow_run_id,
            WorkflowNode.APPROVAL_GATE.value,
        )
        self._require_matching_wait(request, run, gate_node)
        continue_without_action = (
            request.command.action_type is ProtectedAction.SUBMIT_BANKING_PRECHECK
        )
        document_release_declined = (
            request.command.action_type
            is ProtectedAction.SEND_DOCUMENT_TO_EXTERNAL_PARTNER
        )
        if run.status is WorkflowStatus.WAITING_FOR_APPROVAL:
            if continue_without_action:
                run = await self._resume_run(run, resume_stage=request.resume_stage)
            else:
                run = run.model_copy(
                    update={
                        "status": WorkflowStatus.BLOCKED,
                        "current_stage": (
                            WorkflowNode.DOCUMENT_EXTERNAL_RELEASE_DECLINED.value
                            if document_release_declined
                            else WorkflowNode.PROTECTED_ACTION_REJECTED.value
                        ),
                        "blocked_action": request.command.action_type,
                        "failure_reason": (
                            "Protected action was rejected by a human approver."
                        ),
                        "updated_at": self._clock(),
                    }
                )
                await self._case_workflows.save_run(run)
        elif run.status is WorkflowStatus.WAITING_FOR_INPUT:
            raise ApprovalConflictError(
                "The Master Workflow no longer waits for this approval request."
            )

        await self._event_once(
            run,
            "APPROVAL_RESOLVED",
            WorkflowNode.APPROVAL_GATE,
            {
                "request_id": request.request_id,
                "decision": ApprovalDecision.REJECT.value,
            },
        )
        if gate_node is None or request.request_id in gate_node.waiting_for:
            await self._save_gate_node(
                run,
                status=WorkflowNodeStatus.BLOCKED,
                action=request.command.action_type,
                waiting_for=(),
                failure_reason="Protected action was rejected by a human approver.",
                begin_attempt=False,
            )
        await self._event_once(
            run,
            "PROTECTED_ACTION_BLOCKED",
            (
                WorkflowNode.DOCUMENT_EXTERNAL_RELEASE_DECLINED
                if document_release_declined
                else WorkflowNode.PROTECTED_ACTION_REJECTED
            ),
            {
                "request_id": request.request_id,
                "action_type": request.command.action_type.value,
            },
        )
        if document_release_declined:
            await self._save_document_release_declined_node(run, request)
            await self._event_once(
                run,
                "DOCUMENT_EXTERNAL_RELEASE_DECLINED",
                WorkflowNode.DOCUMENT_EXTERNAL_RELEASE_DECLINED,
                {
                    "request_id": request.request_id,
                    "release_package_artifact_id": request.subject_artifact_id,
                    "external_release_performed": False,
                },
            )
        if continue_without_action:
            await self._event_once(
                run,
                "WORKFLOW_RESUME_REQUESTED",
                WorkflowNode.PROTECTED_ACTION_REJECTED,
                {
                    "request_id": request.request_id,
                    "outcome": "CONTINUE_WITHOUT_BANKING_PRECHECK",
                },
            )
        return run

    async def _save_document_release_declined_node(
        self,
        run: CaseWorkflowRun,
        request: ApprovalRequest,
    ) -> None:
        """Record the completed rejection outcome while keeping the workflow blocked."""
        previous = await self._case_workflows.get_node(
            run.workflow_run_id,
            WorkflowNode.DOCUMENT_EXTERNAL_RELEASE_DECLINED.value,
        )
        if previous is not None and previous.status is WorkflowNodeStatus.COMPLETED:
            return
        now = self._clock()
        await self._case_workflows.save_node(
            WorkflowNodeState(
                workflow_run_id=run.workflow_run_id,
                node=WorkflowNode.DOCUMENT_EXTERNAL_RELEASE_DECLINED,
                status=WorkflowNodeStatus.COMPLETED,
                attempt=1,
                input_hash=deterministic_id(
                    "NIN",
                    run.workflow_run_id,
                    request.request_id,
                    request.subject_artifact_id,
                    request.subject_artifact_version,
                    request.subject_input_hash,
                ),
                output_artifact_ids=(request.subject_artifact_id,),
                waiting_for=(),
                started_at=now,
                completed_at=now,
            )
        )

    async def _reconcile_expired(
        self,
        request: ApprovalRequest,
        run: CaseWorkflowRun | None,
    ) -> CaseWorkflowRun | None:
        if run is None:
            return None
        gate_node = await self._case_workflows.get_node(
            run.workflow_run_id,
            WorkflowNode.APPROVAL_GATE.value,
        )
        self._require_matching_wait(request, run, gate_node)
        if run.status in {
            WorkflowStatus.PENDING,
            WorkflowStatus.WAITING_FOR_APPROVAL,
        }:
            run = await self._pause_run(
                run,
                status=WorkflowStatus.WAITING_FOR_INPUT,
                current_stage=WorkflowNode.APPROVAL_GATE.value,
                action=request.command.action_type,
                reason=(
                    "Approval subject or policy changed; submit a new "
                    "protected-action request."
                ),
            )
        prior_events = await self._events.list_after(run.workflow_run_id, 0)
        partially_reconciled_approval = (
            gate_node is not None
            and gate_node.status is WorkflowNodeStatus.COMPLETED
            and any(
                item.event_type == "APPROVAL_RESOLVED"
                and item.metadata.get("request_id") == request.request_id
                for item in prior_events
            )
        )
        if (
            gate_node is None
            or request.request_id in gate_node.waiting_for
            or partially_reconciled_approval
        ):
            await self._save_gate_node(
                run,
                status=WorkflowNodeStatus.WAITING_FOR_INPUT,
                action=request.command.action_type,
                waiting_for=("CURRENT_AUTHORIZATION_SCOPE",),
                failure_reason=(
                    "Approval subject or policy artifact is no longer current."
                ),
                begin_attempt=False,
            )
        await self._event_once(
            run,
            "APPROVAL_EXPIRED",
            WorkflowNode.APPROVAL_GATE,
            {
                "request_id": request.request_id,
                "invalidated_decision": (
                    request.decision_record.model_dump(mode="json")
                    if request.decision_record is not None
                    else None
                ),
            },
        )
        return run

    @staticmethod
    def _require_matching_wait(
        request: ApprovalRequest,
        run: CaseWorkflowRun,
        gate_node: WorkflowNodeState | None,
    ) -> None:
        if run.status is not WorkflowStatus.WAITING_FOR_APPROVAL:
            return
        if run.blocked_action is not request.command.action_type:
            raise ApprovalConflictError(
                "The Master Workflow is waiting for a different protected action."
            )
        if gate_node is not None and gate_node.waiting_for and (
            request.request_id not in gate_node.waiting_for
        ):
            raise ApprovalConflictError(
                "The Master Workflow is waiting for a different approval request."
            )

    async def _event_once(
        self,
        run: CaseWorkflowRun,
        event_type: str,
        node: WorkflowNode,
        metadata: dict[str, object],
    ) -> None:
        request_id = metadata.get("request_id")
        events = await self._events.list_after(run.workflow_run_id, 0)
        if any(
            item.event_type == event_type
            and item.metadata.get("request_id") == request_id
            for item in events
        ):
            return
        await self._event(run, event_type, node, metadata)

    async def _event(
        self,
        run: CaseWorkflowRun,
        event_type: str,
        node: WorkflowNode,
        metadata: dict[str, object],
    ) -> None:
        await self._events.append(
            workflow_run_id=run.workflow_run_id,
            event_type=event_type,
            node=node,
            metadata=metadata,
            created_at=self._clock(),
        )

    async def _save_gate_node(
        self,
        run: CaseWorkflowRun,
        *,
        status: WorkflowNodeStatus,
        action: ProtectedAction,
        waiting_for: tuple[str, ...],
        failure_reason: str | None,
        begin_attempt: bool,
    ) -> None:
        previous = await self._case_workflows.get_node(
            run.workflow_run_id,
            WorkflowNode.APPROVAL_GATE.value,
        )
        attempt = (
            (previous.attempt if previous is not None else 0) + 1
            if begin_attempt
            else previous.attempt
            if previous is not None
            else 1
        )
        node = WorkflowNodeState(
            workflow_run_id=run.workflow_run_id,
            node=WorkflowNode.APPROVAL_GATE,
            status=status,
            attempt=attempt,
            input_hash=deterministic_id(
                "AGN",
                run.workflow_run_id,
                action,
                run.evaluation_case_id,
                attempt,
            ),
            output_artifact_ids=(
                previous.output_artifact_ids if previous is not None else ()
            ),
            waiting_for=waiting_for,
            failure_reason=failure_reason,
            started_at=(
                self._clock()
                if begin_attempt or previous is None
                else previous.started_at
            ),
            completed_at=(
                self._clock()
                if status in {WorkflowNodeStatus.COMPLETED, WorkflowNodeStatus.BLOCKED}
                else None
            ),
        )
        await self._case_workflows.save_node(node)

    @staticmethod
    def _resolved_result(
        request: ApprovalRequest,
        reason: str,
        run: CaseWorkflowRun | None,
    ) -> ApprovalExecutionResult:
        if request.status is ApprovalRequestStatus.APPROVED:
            status = run.status if run is not None else WorkflowStatus.COMPLETED
            gate_status = ApprovalGateStatus.APPROVED
            current_node = WorkflowNode.PROTECTED_ACTION_AUTHORIZED.value
            authorized = True
        elif request.status is ApprovalRequestStatus.REJECTED:
            status = (
                run.status
                if run is not None
                and request.command.action_type
                is ProtectedAction.SUBMIT_BANKING_PRECHECK
                else WorkflowStatus.BLOCKED
            )
            gate_status = ApprovalGateStatus.REJECTED
            current_node = (
                WorkflowNode.DOCUMENT_EXTERNAL_RELEASE_DECLINED.value
                if request.command.action_type
                is ProtectedAction.SEND_DOCUMENT_TO_EXTERNAL_PARTNER
                else WorkflowNode.PROTECTED_ACTION_REJECTED.value
            )
            authorized = False
        elif request.status is ApprovalRequestStatus.EXPIRED:
            status = WorkflowStatus.WAITING_FOR_INPUT
            gate_status = ApprovalGateStatus.EXPIRED
            current_node = WorkflowNode.APPROVAL_GATE.value
            authorized = False
        else:
            status = WorkflowStatus.WAITING_FOR_APPROVAL
            gate_status = ApprovalGateStatus.WAITING_FOR_APPROVAL
            current_node = WorkflowNode.WAITING_FOR_APPROVAL.value
            authorized = False
        return ApprovalExecutionResult(
            status=status,
            gate_status=gate_status,
            current_node=current_node,
            workflow_run_id=run.workflow_run_id if run is not None else None,
            evaluation_case_id=request.evaluation_case_id,
            action_authorized=authorized,
            approval_request=request,
            reason=reason,
        )

    @staticmethod
    def _latest(
        artifacts: tuple[ArtifactEnvelope, ...], artifact_type: ArtifactType
    ) -> ArtifactEnvelope | None:
        matches = tuple(item for item in artifacts if item.artifact_type is artifact_type)
        return max(matches, key=lambda item: item.version, default=None)
