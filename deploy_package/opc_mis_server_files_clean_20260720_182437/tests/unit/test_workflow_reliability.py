"""Deterministic regression tests for workflow wake-up and approval recovery."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from opc_mis.domain.approvals import (
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
    ArtifactStatus,
    ArtifactType,
    EvaluationScope,
    ProtectedAction,
    ValidationStatus,
    WorkflowNodeStatus,
    WorkflowStatus,
)
from opc_mis.domain.workflow import WorkflowNode
from opc_mis.infrastructure.persistence.sqlite_approval_request_repository import (
    SQLiteApprovalRequestRepository,
)
from opc_mis.infrastructure.persistence.sqlite_artifact_repository import (
    SQLiteArtifactRepository,
)
from opc_mis.infrastructure.persistence.sqlite_database import SQLiteDatabase
from opc_mis.infrastructure.persistence.sqlite_runtime_event_repository import (
    SQLiteRuntimeEventRepository,
)
from opc_mis.infrastructure.persistence.sqlite_workflow_repository import (
    SQLiteCaseWorkflowRepository,
)
from opc_mis.ports.case_workflow_repository import CaseWorkflowRepository
from opc_mis.workflow.approval_orchestrator import (
    ApprovalConflictError,
    ApprovalOrchestrator,
)
from opc_mis.workflow.case_workflow_orchestrator import CaseWorkflowOrchestrator
from opc_mis.workflow.workflow_runner import WorkflowRunner


class _EmptyWorkflowRepository:
    async def list_recoverable(
        self, dataset_id: str, dataset_snapshot_hash: str
    ) -> tuple[CaseWorkflowRun, ...]:
        return ()


class _ControlledOrchestrator:
    def __init__(self) -> None:
        self.call_count = 0
        self.first_started = asyncio.Event()
        self.release_first = asyncio.Event()
        self.second_finished = asyncio.Event()

    async def execute(self, workflow_run_id: str) -> None:
        assert workflow_run_id == "CWF-RERUN"
        self.call_count += 1
        if self.call_count == 1:
            self.first_started.set()
            await self.release_first.wait()
        elif self.call_count == 2:
            self.second_finished.set()


def _run(now: datetime) -> CaseWorkflowRun:
    return CaseWorkflowRun(
        workflow_run_id="CWF-RELIABILITY",
        dataset_id="DATASET-TEST",
        dataset_snapshot_hash="SNAPSHOT-TEST",
        evaluation_case_id="CASE-TEST",
        contract_id="CONTRACT-TEST",
        status=WorkflowStatus.WAITING_FOR_APPROVAL,
        current_stage=WorkflowNode.WAITING_FOR_APPROVAL.value,
        requested_scope=(
            EvaluationScope.FINANCE,
            EvaluationScope.OPERATIONS,
            EvaluationScope.RISK,
        ),
        resume_stage=WorkflowNode.DECISION_ROUTE_PLANNED.value,
        blocked_action=ProtectedAction.COMMIT_LARGE_FINANCIAL_DECISION,
        failure_reason="Waiting for human approval.",
        created_at=now,
        updated_at=now,
    )


def _request(
    now: datetime,
    *,
    action: ProtectedAction = ProtectedAction.COMMIT_LARGE_FINANCIAL_DECISION,
) -> ApprovalRequest:
    return ApprovalRequest(
        request_id="APR-RELIABILITY",
        workflow_run_id="CWF-RELIABILITY",
        evaluation_case_id="CASE-TEST",
        dataset_id="DATASET-TEST",
        subject_artifact_id="ART-SUBJECT",
        subject_artifact_version=1,
        subject_input_hash="SUBJECT-HASH",
        checkpoint_ids=("ACP-TEST",),
        policy_artifact_id=(
            "ART-PRECHECK-POLICY"
            if action is ProtectedAction.SUBMIT_BANKING_PRECHECK
            else "ART-APPROVAL-POLICY"
        ),
        policy_artifact_version=1,
        policy_input_hash=(
            "PRECHECK-POLICY-HASH"
            if action is ProtectedAction.SUBMIT_BANKING_PRECHECK
            else "APPROVAL-POLICY-HASH"
        ),
        policy_coverage_ids=(
            ("APCOV-PRECHECK",)
            if action is ProtectedAction.SUBMIT_BANKING_PRECHECK
            else ()
        ),
        command=ActionCommand(
            action_type=action,
            evaluation_case_id="CASE-TEST",
            payload_artifact_id="ART-SUBJECT",
            requested_by="TEST",
            payload={"requested_amount": 350_000_000},
        ),
        resume_stage=WorkflowNode.DECISION_ROUTE_PLANNED.value,
        status=ApprovalRequestStatus.PENDING,
        created_at=now,
    )


async def _save_waiting_state(
    workflows: SQLiteCaseWorkflowRepository,
    requests: SQLiteApprovalRequestRepository,
    run: CaseWorkflowRun,
    request: ApprovalRequest,
    now: datetime,
) -> None:
    run = run.model_copy(update={"blocked_action": request.command.action_type})
    await workflows.save_run(run)
    await workflows.save_node(
        WorkflowNodeState(
            workflow_run_id=run.workflow_run_id,
            node=WorkflowNode.APPROVAL_GATE,
            status=WorkflowNodeStatus.WAITING_FOR_APPROVAL,
            attempt=1,
            input_hash="GATE-HASH",
            waiting_for=(request.request_id,),
            failure_reason="Waiting for human approval.",
            started_at=now,
        )
    )
    await requests.save(request)


async def _save_current_approval_artifacts(
    artifacts: SQLiteArtifactRepository,
    request: ApprovalRequest,
    now: datetime,
) -> None:
    """Persist the exact subject and policy scope bound to a valid request."""
    await artifacts.save(
        ArtifactEnvelope(
            artifact_id=request.subject_artifact_id,
            artifact_type=ArtifactType.EVALUATION_CASE,
            evaluation_case_id=request.evaluation_case_id,
            producer="TEST",
            version=request.subject_artifact_version,
            status=ArtifactStatus.CREATED,
            payload={"case": "test"},
            evidence_refs=(),
            input_artifact_ids=("UPSTREAM",),
            input_hash=request.subject_input_hash,
            validation_status=ValidationStatus.VALID,
            validation_notes=(),
            created_at=now,
        )
    )
    assert request.policy_artifact_id is not None
    assert request.policy_artifact_version is not None
    assert request.policy_input_hash is not None
    await artifacts.save(
        ArtifactEnvelope(
            artifact_id=request.policy_artifact_id,
            artifact_type=ArtifactType.APPROVAL_CHECKPOINTS,
            evaluation_case_id=request.evaluation_case_id,
            producer="TEST",
            version=request.policy_artifact_version,
            status=ArtifactStatus.CREATED,
            payload={"checkpoints": []},
            evidence_refs=(),
            input_artifact_ids=("UPSTREAM",),
            input_hash=request.policy_input_hash,
            validation_status=ValidationStatus.VALID,
            validation_notes=(),
            created_at=now,
        )
    )


def _resolved_request(
    request: ApprovalRequest,
    decision: ApprovalDecision,
    now: datetime,
) -> ApprovalRequest:
    status = (
        ApprovalRequestStatus.APPROVED
        if decision is ApprovalDecision.APPROVE
        else ApprovalRequestStatus.REJECTED
    )
    return request.model_copy(
        update={
            "status": status,
            "decision_record": ApprovalDecisionRecord(
                decision=decision,
                decided_by="FOUNDER",
                reason="Reliability test decision.",
                decided_at=now,
            ),
        }
    )


def test_runner_preserves_one_wakeup_requested_while_run_is_active() -> None:
    async def execute() -> None:
        controlled = _ControlledOrchestrator()
        runner = WorkflowRunner(
            orchestrator=cast(CaseWorkflowOrchestrator, controlled),
            workflows=cast(CaseWorkflowRepository, _EmptyWorkflowRepository()),
        )
        await runner.start(dataset_id="DATASET", dataset_snapshot_hash="SNAPSHOT")
        try:
            await runner.enqueue("CWF-RERUN")
            await asyncio.wait_for(controlled.first_started.wait(), timeout=1)
            await runner.enqueue("CWF-RERUN")
            await runner.enqueue("CWF-RERUN")
            await runner.enqueue("CWF-RERUN")
            controlled.release_first.set()
            await asyncio.wait_for(controlled.second_finished.wait(), timeout=1)
            assert controlled.call_count == 2
        finally:
            controlled.release_first.set()
            await runner.stop()

    asyncio.run(execute())


@pytest.mark.parametrize(
    ("decision", "expected_run_status", "expected_node_status"),
    (
        (
            ApprovalDecision.APPROVE,
            WorkflowStatus.PENDING,
            WorkflowNodeStatus.COMPLETED,
        ),
        (
            ApprovalDecision.REJECT,
            WorkflowStatus.BLOCKED,
            WorkflowNodeStatus.BLOCKED,
        ),
    ),
)
def test_retry_reconciles_resolved_request_with_stale_waiting_run(
    tmp_path: Path,
    decision: ApprovalDecision,
    expected_run_status: WorkflowStatus,
    expected_node_status: WorkflowNodeStatus,
) -> None:
    async def execute() -> None:
        now = datetime.now(UTC)
        database = SQLiteDatabase(tmp_path / f"approval-{decision.value}.db")
        await database.initialize()
        artifacts = SQLiteArtifactRepository(database)
        workflows = SQLiteCaseWorkflowRepository(database)
        requests = SQLiteApprovalRequestRepository(database)
        events = SQLiteRuntimeEventRepository(database)
        request = _request(now)
        await _save_waiting_state(workflows, requests, _run(now), request, now)
        await _save_current_approval_artifacts(artifacts, request, now)

        # Simulate a crash after the durable request transition and before workflow state.
        stored, updated = await requests.compare_and_set(
            _resolved_request(request, decision, now),
            expected_status=ApprovalRequestStatus.PENDING,
        )
        assert stored is not None
        assert updated is True
        stale = await workflows.get_run(request.workflow_run_id)
        assert stale is not None
        assert stale.status is WorkflowStatus.WAITING_FOR_APPROVAL

        orchestrator = ApprovalOrchestrator(
            artifacts=artifacts,
            requests=requests,
            case_workflows=workflows,
            events=events,
            clock=lambda: now,
        )
        first = await orchestrator.decide(
            request_id=request.request_id,
            decision=decision,
            decided_by="FOUNDER",
            reason="Retry after simulated crash.",
        )
        second = await orchestrator.decide(
            request_id=request.request_id,
            decision=decision,
            decided_by="FOUNDER",
            reason="Idempotent retry.",
        )
        persisted_run = await workflows.get_run(request.workflow_run_id)
        gate_node = await workflows.get_node(
            request.workflow_run_id, WorkflowNode.APPROVAL_GATE.value
        )
        audit_events = await events.list_after(request.workflow_run_id, 0)
        await database.close()

        assert first.status is expected_run_status
        assert second.status is expected_run_status
        assert persisted_run is not None
        assert persisted_run.status is expected_run_status
        assert gate_node is not None
        assert gate_node.status is expected_node_status
        assert sum(
            item.event_type == "APPROVAL_RESOLVED" for item in audit_events
        ) == 1
        expected_action_event = (
            "PROTECTED_ACTION_ALLOWED"
            if decision is ApprovalDecision.APPROVE
            else "PROTECTED_ACTION_BLOCKED"
        )
        assert sum(
            item.event_type == expected_action_event for item in audit_events
        ) == 1

    asyncio.run(execute())


def test_rejected_banking_precheck_resumes_without_authorizing_action(
    tmp_path: Path,
) -> None:
    async def execute() -> None:
        now = datetime.now(UTC)
        database = SQLiteDatabase(tmp_path / "banking-rejection.db")
        await database.initialize()
        artifacts = SQLiteArtifactRepository(database)
        workflows = SQLiteCaseWorkflowRepository(database)
        requests = SQLiteApprovalRequestRepository(database)
        events = SQLiteRuntimeEventRepository(database)
        request = _request(now, action=ProtectedAction.SUBMIT_BANKING_PRECHECK)
        await _save_waiting_state(workflows, requests, _run(now), request, now)
        stored, updated = await requests.compare_and_set(
            _resolved_request(request, ApprovalDecision.REJECT, now),
            expected_status=ApprovalRequestStatus.PENDING,
        )
        assert stored is not None
        assert updated is True

        orchestrator = ApprovalOrchestrator(
            artifacts=artifacts,
            requests=requests,
            case_workflows=workflows,
            events=events,
            clock=lambda: now,
        )
        result = await orchestrator.decide(
            request_id=request.request_id,
            decision=ApprovalDecision.REJECT,
            decided_by="FOUNDER",
            reason="Continue without Banking precheck.",
        )
        retry = await orchestrator.decide(
            request_id=request.request_id,
            decision=ApprovalDecision.REJECT,
            decided_by="FOUNDER",
            reason="Idempotent retry.",
        )
        persisted_run = await workflows.get_run(request.workflow_run_id)
        audit_events = await events.list_after(request.workflow_run_id, 0)
        await database.close()

        assert result.status is WorkflowStatus.PENDING
        assert retry.status is WorkflowStatus.PENDING
        assert result.gate_status is ApprovalGateStatus.REJECTED
        assert result.action_authorized is False
        assert persisted_run is not None
        assert persisted_run.status is WorkflowStatus.PENDING
        assert persisted_run.current_stage == WorkflowNode.DECISION_ROUTE_PLANNED.value
        assert persisted_run.blocked_action is None
        assert sum(
            item.event_type == "WORKFLOW_RESUME_REQUESTED"
            for item in audit_events
        ) == 1

    asyncio.run(execute())


def test_concurrent_conflicting_decisions_have_one_repository_winner(
    tmp_path: Path,
) -> None:
    async def execute() -> None:
        now = datetime.now(UTC)
        database = SQLiteDatabase(tmp_path / "approval-race.db")
        await database.initialize()
        artifacts = SQLiteArtifactRepository(database)
        workflows = SQLiteCaseWorkflowRepository(database)
        requests = SQLiteApprovalRequestRepository(database)
        events = SQLiteRuntimeEventRepository(database)
        request = _request(now)
        await _save_waiting_state(workflows, requests, _run(now), request, now)
        await _save_current_approval_artifacts(artifacts, request, now)
        first = ApprovalOrchestrator(
            artifacts=artifacts,
            requests=requests,
            case_workflows=workflows,
            events=events,
            clock=lambda: now,
        )
        second = ApprovalOrchestrator(
            artifacts=artifacts,
            requests=requests,
            case_workflows=workflows,
            events=events,
            clock=lambda: now,
        )
        results = await asyncio.gather(
            first.decide(
                request_id=request.request_id,
                decision=ApprovalDecision.APPROVE,
                decided_by="FOUNDER-A",
                reason="Approve concurrently.",
            ),
            second.decide(
                request_id=request.request_id,
                decision=ApprovalDecision.REJECT,
                decided_by="FOUNDER-B",
                reason="Reject concurrently.",
            ),
            return_exceptions=True,
        )
        persisted_request = await requests.get(request.request_id)
        persisted_run = await workflows.get_run(request.workflow_run_id)
        audit_events = await events.list_after(request.workflow_run_id, 0)
        await database.close()

        successes = [item for item in results if isinstance(item, ApprovalExecutionResult)]
        conflicts = [item for item in results if isinstance(item, ApprovalConflictError)]
        assert len(successes) == 1
        assert len(conflicts) == 1
        assert persisted_request is not None
        assert persisted_run is not None
        if persisted_request.status is ApprovalRequestStatus.APPROVED:
            assert persisted_run.status is WorkflowStatus.PENDING
        else:
            assert persisted_request.status is ApprovalRequestStatus.REJECTED
            assert persisted_run.status is WorkflowStatus.BLOCKED
        assert sum(
            item.event_type == "APPROVAL_RESOLVED" for item in audit_events
        ) == 1

    asyncio.run(execute())
