"""Approval lifecycle tests against the unified durable Master Workflow."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest

from opc_mis.domain.approvals import (
    ApprovalCheckpoint,
    ApprovalCheckpointSet,
    ApprovalCondition,
    ApprovalPolicyCoverage,
    ApprovalRequest,
)
from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.case_workflow_models import CaseWorkflowRun
from opc_mis.domain.commands import ActionCommand
from opc_mis.domain.enums import (
    ApprovalDecision,
    ApprovalGateStatus,
    ApprovalRequestStatus,
    ApprovalTriggerEvent,
    ArtifactStatus,
    ArtifactType,
    EvaluationScope,
    ProtectedAction,
    RuleOperator,
    ValidationStatus,
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
from opc_mis.workflow.approval_orchestrator import (
    ApprovalConflictError,
    ApprovalOrchestrator,
)


def envelope(
    *,
    artifact_id: str,
    artifact_type: ArtifactType,
    version: int,
    input_hash: str,
    payload: dict[str, object],
    now: datetime,
) -> ArtifactEnvelope:
    return ArtifactEnvelope(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        evaluation_case_id="CASE-TEST",
        producer="TEST",
        version=version,
        status=ArtifactStatus.CREATED,
        payload=payload,
        evidence_refs=(),
        input_artifact_ids=("UPSTREAM",),
        input_hash=input_hash,
        validation_status=ValidationStatus.VALID,
        validation_notes=(),
        created_at=now,
    )


def test_approval_expires_when_subject_artifact_is_superseded(tmp_path: Path) -> None:
    async def execute() -> None:
        now = datetime.now(UTC)
        database = SQLiteDatabase(tmp_path / "approval-expiry.db")
        await database.initialize()
        artifacts = SQLiteArtifactRepository(database)
        workflows = SQLiteCaseWorkflowRepository(database)
        requests = SQLiteApprovalRequestRepository(database)
        events = SQLiteRuntimeEventRepository(database)
        orchestrator = ApprovalOrchestrator(
            artifacts=artifacts,
            requests=requests,
            case_workflows=workflows,
            events=events,
            clock=lambda: now,
        )
        run = CaseWorkflowRun(
            workflow_run_id="CWF-TEST",
            dataset_id="DATASET-TEST",
            dataset_snapshot_hash="SNAPSHOT-TEST",
            evaluation_case_id="CASE-TEST",
            contract_id="CONTRACT-TEST",
            status=WorkflowStatus.COMPLETED,
            current_stage=WorkflowNode.INITIAL_ASSESSMENT_COMPLETED.value,
            requested_scope=(
                EvaluationScope.FINANCE,
                EvaluationScope.OPERATIONS,
                EvaluationScope.RISK,
            ),
            created_at=now,
            updated_at=now,
        )
        await workflows.save_run(run)
        subject_v1 = envelope(
            artifact_id="ART-SUBJECT-V1",
            artifact_type=ArtifactType.EVALUATION_CASE,
            version=1,
            input_hash="HASH-V1",
            payload={"version": 1},
            now=now,
        )
        await artifacts.save(subject_v1)
        checkpoints = ApprovalCheckpointSet(
            evaluation_case_id="CASE-TEST",
            dataset_id="DATASET-TEST",
            contract_id="CONTRACT-TEST",
            checkpoints=(
                ApprovalCheckpoint(
                    checkpoint_id="ACP-TEST",
                    evaluation_case_id="CASE-TEST",
                    source_rule_id="RULE-TEST",
                    approval_type="HUMAN_APPROVAL",
                    trigger_event=(
                        ApprovalTriggerEvent.LARGE_FINANCIAL_DECISION_REQUESTED
                    ),
                    protected_action=(
                        ProtectedAction.COMMIT_LARGE_FINANCIAL_DECISION
                    ),
                    condition=ApprovalCondition(
                        source_field="requested_amount",
                        operator=RuleOperator.GREATER_THAN,
                        threshold=300_000_000,
                    ),
                    evidence_ids=(),
                ),
            ),
        )
        await artifacts.save(
            envelope(
                artifact_id="ART-CHECKPOINTS",
                artifact_type=ArtifactType.APPROVAL_CHECKPOINTS,
                version=1,
                input_hash="CHECKPOINT-HASH",
                payload=checkpoints.model_dump(mode="json"),
                now=now,
            )
        )
        pending = await orchestrator.request_action(
            ActionCommand(
                action_type=ProtectedAction.COMMIT_LARGE_FINANCIAL_DECISION,
                evaluation_case_id="CASE-TEST",
                payload_artifact_id=subject_v1.artifact_id,
                requested_by="TEST",
                payload={"requested_amount": 300_000_001},
            ),
            workflow_run_id=run.workflow_run_id,
        )
        assert pending.status is WorkflowStatus.WAITING_FOR_APPROVAL
        assert pending.approval_request is not None

        await artifacts.save(
            envelope(
                artifact_id="ART-SUBJECT-V2",
                artifact_type=ArtifactType.EVALUATION_CASE,
                version=2,
                input_hash="HASH-V2",
                payload={"version": 2},
                now=now,
            )
        )
        expired = await orchestrator.decide(
            request_id=pending.approval_request.request_id,
            decision=ApprovalDecision.APPROVE,
            decided_by="FOUNDER",
            reason="Attempt to approve stale evidence.",
        )
        persisted_request = await requests.get(pending.approval_request.request_id)
        persisted_run = await workflows.get_run(run.workflow_run_id)
        audit_events = await events.list_after(run.workflow_run_id, 0)
        await database.close()

        assert expired.gate_status is ApprovalGateStatus.EXPIRED
        assert expired.action_authorized is False
        assert persisted_request is not None
        assert persisted_request.status is ApprovalRequestStatus.EXPIRED
        assert persisted_run is not None
        assert persisted_run.status is WorkflowStatus.WAITING_FOR_INPUT
        assert persisted_run.current_stage == WorkflowNode.APPROVAL_GATE.value
        assert "APPROVAL_EXPIRED" in {item.event_type for item in audit_events}

    asyncio.run(execute())


def test_raw_document_package_cannot_create_approval_request(tmp_path: Path) -> None:
    async def execute() -> None:
        now = datetime.now(UTC)
        database = SQLiteDatabase(tmp_path / "raw-document-package.db")
        await database.initialize()
        artifacts = SQLiteArtifactRepository(database)
        requests = SQLiteApprovalRequestRepository(database)
        orchestrator = ApprovalOrchestrator(
            artifacts=artifacts,
            requests=requests,
            case_workflows=SQLiteCaseWorkflowRepository(database),
            events=SQLiteRuntimeEventRepository(database),
            clock=lambda: now,
        )
        release_package = envelope(
            artifact_id="ART-DOCUMENT-RELEASE-PACKAGE",
            artifact_type=ArtifactType.DOCUMENT_RELEASE_PACKAGE,
            version=1,
            input_hash="DOCUMENT-RELEASE-HASH",
            payload={"release_package_id": "DRP-TEST"},
            now=now,
        )
        await artifacts.save(release_package)
        with pytest.raises(ApprovalConflictError, match="internal Decision input"):
            await orchestrator.request_action(
                ActionCommand(
                    action_type=ProtectedAction.SEND_DOCUMENT_TO_EXTERNAL_PARTNER,
                    evaluation_case_id="CASE-TEST",
                    payload_artifact_id=release_package.artifact_id,
                    requested_by="CASE_WORKFLOW_ORCHESTRATOR",
                    payload={"document_sent_to_partner": True},
                )
            )
        persisted_requests = await requests.list_by_case("CASE-TEST")
        await database.close()

        assert persisted_requests == ()

    asyncio.run(execute())


def test_final_decision_and_external_submission_use_separate_exact_approvals(
    tmp_path: Path,
) -> None:
    async def execute() -> None:
        now = datetime.now(UTC)
        database = SQLiteDatabase(tmp_path / "separate-decision-release-approvals.db")
        await database.initialize()
        artifacts = SQLiteArtifactRepository(database)
        requests = SQLiteApprovalRequestRepository(database)
        events = SQLiteRuntimeEventRepository(database)
        orchestrator = ApprovalOrchestrator(
            artifacts=artifacts,
            requests=requests,
            case_workflows=SQLiteCaseWorkflowRepository(database),
            events=events,
            clock=lambda: now,
        )
        decision_card = envelope(
            artifact_id="ART-DECISION-CARD",
            artifact_type=ArtifactType.DECISION_CARD,
            version=1,
            input_hash="DECISION-CARD-HASH",
            payload={"decision_card_id": "DCARD-TEST"},
            now=now,
        )
        external_proposal = envelope(
            artifact_id="ART-EXTERNAL-SUBMISSION-PROPOSAL",
            artifact_type=ArtifactType.EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL,
            version=1,
            input_hash="EXTERNAL-PROPOSAL-HASH",
            payload={"proposal_id": "EDSP-TEST"},
            now=now,
        )
        await artifacts.save(decision_card)
        await artifacts.save(external_proposal)
        checkpoints = ApprovalCheckpointSet(
            evaluation_case_id="CASE-TEST",
            dataset_id="DATASET-TEST",
            contract_id="CONTRACT-TEST",
            checkpoints=(
                ApprovalCheckpoint(
                    checkpoint_id="ACP-FINAL-DECISION",
                    evaluation_case_id="CASE-TEST",
                    source_rule_id="FINAL-DECISION-POLICY",
                    approval_type="FINAL_DECISION_FOUNDER_APPROVAL",
                    trigger_event=(
                        ApprovalTriggerEvent.FINAL_CONTRACT_DECISION_CONFIRMATION_REQUESTED
                    ),
                    protected_action=(
                        ProtectedAction.CONFIRM_FINAL_CONTRACT_DECISION
                    ),
                    condition=ApprovalCondition(
                        source_field="final_decision_confirmation_requested",
                        operator=RuleOperator.EQUAL,
                        threshold=True,
                    ),
                    evidence_ids=(),
                ),
                ApprovalCheckpoint(
                    checkpoint_id="ACP-EXTERNAL-SUBMISSION",
                    evaluation_case_id="CASE-TEST",
                    source_rule_id="EXTERNAL-RELEASE-POLICY",
                    approval_type="DOCUMENT_EXTERNAL_RELEASE_APPROVAL",
                    trigger_event=(
                        ApprovalTriggerEvent.DOCUMENT_EXTERNAL_RELEASE_REQUESTED
                    ),
                    protected_action=(
                        ProtectedAction.SEND_DOCUMENT_TO_EXTERNAL_PARTNER
                    ),
                    condition=ApprovalCondition(
                        source_field="document_sent_to_partner",
                        operator=RuleOperator.EQUAL,
                        threshold=True,
                    ),
                    evidence_ids=(),
                ),
            ),
        )
        await artifacts.save(
            envelope(
                artifact_id="ART-DECISION-RELEASE-POLICY",
                artifact_type=ArtifactType.APPROVAL_CHECKPOINTS,
                version=1,
                input_hash="DECISION-RELEASE-POLICY-HASH",
                payload=checkpoints.model_dump(mode="json"),
                now=now,
            )
        )

        decision_wait = await orchestrator.request_action(
            ActionCommand(
                action_type=ProtectedAction.CONFIRM_FINAL_CONTRACT_DECISION,
                evaluation_case_id="CASE-TEST",
                payload_artifact_id=decision_card.artifact_id,
                requested_by="CASE_WORKFLOW_ORCHESTRATOR",
                payload={
                    "final_decision_confirmation_requested": True,
                    "decision_card_id": "DCARD-TEST",
                },
            )
        )
        release_wait = await orchestrator.request_action(
            ActionCommand(
                action_type=ProtectedAction.SEND_DOCUMENT_TO_EXTERNAL_PARTNER,
                evaluation_case_id="CASE-TEST",
                payload_artifact_id=external_proposal.artifact_id,
                requested_by="CASE_WORKFLOW_ORCHESTRATOR",
                payload={
                    "document_sent_to_partner": True,
                    "proposal_id": "EDSP-TEST",
                },
            )
        )

        assert decision_wait.gate_status is ApprovalGateStatus.WAITING_FOR_APPROVAL
        assert release_wait.gate_status is ApprovalGateStatus.WAITING_FOR_APPROVAL
        assert decision_wait.approval_request is not None
        assert release_wait.approval_request is not None
        assert decision_wait.approval_request.request_id != (
            release_wait.approval_request.request_id
        )
        assert decision_wait.approval_request.subject_artifact_id == (
            decision_card.artifact_id
        )
        assert release_wait.approval_request.subject_artifact_id == (
            external_proposal.artifact_id
        )
        assert decision_wait.approval_request.checkpoint_ids == (
            "ACP-FINAL-DECISION",
        )
        assert release_wait.approval_request.checkpoint_ids == (
            "ACP-EXTERNAL-SUBMISSION",
        )

        decision_approved = await orchestrator.decide(
            request_id=decision_wait.approval_request.request_id,
            decision=ApprovalDecision.APPROVE,
            decided_by="FOUNDER",
            reason="HUMAN_REVIEW_COMPLETED",
        )
        release_approved = await orchestrator.decide(
            request_id=release_wait.approval_request.request_id,
            decision=ApprovalDecision.APPROVE,
            decided_by="FOUNDER",
            reason="HUMAN_REVIEW_COMPLETED",
        )
        audit_events = (
            *(await events.list_after(
                decision_wait.approval_request.workflow_run_id, 0
            )),
            *(await events.list_after(
                release_wait.approval_request.workflow_run_id, 0
            )),
        )
        await database.close()

        assert decision_approved.action_authorized is True
        assert release_approved.action_authorized is True
        assert decision_approved.approval_request is not None
        assert release_approved.approval_request is not None
        assert decision_approved.approval_request.status is (
            ApprovalRequestStatus.APPROVED
        )
        assert release_approved.approval_request.status is (
            ApprovalRequestStatus.APPROVED
        )
        assert not any(
            item.event_type in {
                "EXTERNAL_SUBMISSION_PERFORMED",
                "EXTERNAL_SUBMISSION_RECEIPT_CREATED",
            }
            for item in audit_events
        )

    asyncio.run(execute())


def test_legacy_pending_document_approval_expires_before_authorization(
    tmp_path: Path,
) -> None:
    async def execute() -> None:
        now = datetime.now(UTC)
        database = SQLiteDatabase(tmp_path / "legacy-document-approval.db")
        await database.initialize()
        artifacts = SQLiteArtifactRepository(database)
        workflows = SQLiteCaseWorkflowRepository(database)
        requests = SQLiteApprovalRequestRepository(database)
        events = SQLiteRuntimeEventRepository(database)
        orchestrator = ApprovalOrchestrator(
            artifacts=artifacts,
            requests=requests,
            case_workflows=workflows,
            events=events,
            clock=lambda: now,
        )
        run = CaseWorkflowRun(
            workflow_run_id="CWF-LEGACY-DOCUMENT-APPROVAL",
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
            resume_stage=WorkflowNode.DOCUMENT_EXTERNAL_RELEASE_PROPOSAL.value,
            blocked_action=ProtectedAction.SEND_DOCUMENT_TO_EXTERNAL_PARTNER,
            created_at=now,
            updated_at=now,
        )
        await workflows.save_run(run)
        release_package = envelope(
            artifact_id="ART-LEGACY-RELEASE-PACKAGE",
            artifact_type=ArtifactType.DOCUMENT_RELEASE_PACKAGE,
            version=1,
            input_hash="LEGACY-RELEASE-HASH",
            payload={"release_package_id": "DRP-LEGACY"},
            now=now,
        )
        await artifacts.save(release_package)
        checkpoints = ApprovalCheckpointSet(
            evaluation_case_id="CASE-TEST",
            dataset_id="DATASET-TEST",
            contract_id="CONTRACT-TEST",
            checkpoints=(
                ApprovalCheckpoint(
                    checkpoint_id="ACP-LEGACY-DOCUMENT-RELEASE",
                    evaluation_case_id="CASE-TEST",
                    source_rule_id="RULE-LEGACY-DOCUMENT-RELEASE",
                    approval_type="DOCUMENT_EXTERNAL_RELEASE_APPROVAL",
                    trigger_event=(
                        ApprovalTriggerEvent.DOCUMENT_EXTERNAL_RELEASE_REQUESTED
                    ),
                    protected_action=(
                        ProtectedAction.SEND_DOCUMENT_TO_EXTERNAL_PARTNER
                    ),
                    condition=ApprovalCondition(
                        source_field="document_sent_to_partner",
                        operator=RuleOperator.EQUAL,
                        threshold=True,
                    ),
                    evidence_ids=(),
                ),
            ),
        )
        await artifacts.save(
            envelope(
                artifact_id="ART-LEGACY-DOCUMENT-POLICY",
                artifact_type=ArtifactType.APPROVAL_CHECKPOINTS,
                version=1,
                input_hash="LEGACY-DOCUMENT-POLICY-HASH",
                payload=checkpoints.model_dump(mode="json"),
                now=now,
            )
        )
        legacy_request = ApprovalRequest(
            request_id="APR-LEGACY-DOCUMENT-RELEASE",
            workflow_run_id=run.workflow_run_id,
            evaluation_case_id="CASE-TEST",
            dataset_id="DATASET-TEST",
            subject_artifact_id=release_package.artifact_id,
            subject_artifact_version=release_package.version,
            subject_input_hash=release_package.input_hash,
            checkpoint_ids=("ACP-LEGACY-DOCUMENT-RELEASE",),
            policy_artifact_id="ART-LEGACY-DOCUMENT-POLICY",
            policy_artifact_version=1,
            policy_input_hash="LEGACY-DOCUMENT-POLICY-HASH",
            command=ActionCommand(
                action_type=ProtectedAction.SEND_DOCUMENT_TO_EXTERNAL_PARTNER,
                evaluation_case_id="CASE-TEST",
                payload_artifact_id=release_package.artifact_id,
                requested_by="CASE_WORKFLOW_ORCHESTRATOR",
                payload={"document_sent_to_partner": True},
            ),
            resume_stage=WorkflowNode.DOCUMENT_EXTERNAL_RELEASE_PROPOSAL.value,
            status=ApprovalRequestStatus.PENDING,
            created_at=now,
        )
        await requests.save(legacy_request)
        expired = await orchestrator.decide(
            request_id=legacy_request.request_id,
            decision=ApprovalDecision.APPROVE,
            decided_by="FOUNDER",
            reason="HUMAN_REVIEW_COMPLETED",
        )
        persisted_request = await requests.get(legacy_request.request_id)
        persisted_run = await workflows.get_run(run.workflow_run_id)
        audit_events = await events.list_after(run.workflow_run_id, 0)
        event_types = {item.event_type for item in audit_events}
        await database.close()

        assert expired.gate_status is ApprovalGateStatus.EXPIRED
        assert expired.action_authorized is False
        assert persisted_request is not None
        assert persisted_request.status is ApprovalRequestStatus.EXPIRED
        assert persisted_request.decision_record is None
        assert persisted_run is not None
        assert persisted_run.status is WorkflowStatus.WAITING_FOR_INPUT
        assert persisted_run.current_stage == WorkflowNode.APPROVAL_GATE.value
        assert "APPROVAL_EXPIRED" in event_types
        assert "PROTECTED_ACTION_ALLOWED" not in event_types
        assert "DOCUMENT_EXTERNAL_RELEASE_AUTHORIZED" not in event_types
        expired_event = next(
            item for item in audit_events if item.event_type == "APPROVAL_EXPIRED"
        )
        assert expired_event.metadata["invalidated_decision"] is None

    asyncio.run(execute())


def test_standalone_approval_identity_distinguishes_requesters(tmp_path: Path) -> None:
    async def execute() -> None:
        now = datetime.now(UTC)
        database = SQLiteDatabase(tmp_path / "approval-requester-identity.db")
        await database.initialize()
        artifacts = SQLiteArtifactRepository(database)
        requests = SQLiteApprovalRequestRepository(database)
        orchestrator = ApprovalOrchestrator(
            artifacts=artifacts,
            requests=requests,
            case_workflows=SQLiteCaseWorkflowRepository(database),
            events=SQLiteRuntimeEventRepository(database),
            clock=lambda: now,
        )
        subject = envelope(
            artifact_id="ART-REQUESTER-SUBJECT",
            artifact_type=ArtifactType.EVALUATION_CASE,
            version=1,
            input_hash="REQUESTER-SUBJECT-HASH",
            payload={"version": 1},
            now=now,
        )
        await artifacts.save(subject)
        checkpoints = ApprovalCheckpointSet(
            evaluation_case_id="CASE-TEST",
            dataset_id="DATASET-TEST",
            contract_id="CONTRACT-TEST",
            checkpoints=(
                ApprovalCheckpoint(
                    checkpoint_id="ACP-REQUESTER-AMOUNT",
                    evaluation_case_id="CASE-TEST",
                    source_rule_id="RULE-REQUESTER-AMOUNT",
                    approval_type="HUMAN_APPROVAL",
                    trigger_event=(
                        ApprovalTriggerEvent.LARGE_FINANCIAL_DECISION_REQUESTED
                    ),
                    protected_action=(
                        ProtectedAction.COMMIT_LARGE_FINANCIAL_DECISION
                    ),
                    condition=ApprovalCondition(
                        source_field="requested_amount",
                        operator=RuleOperator.GREATER_THAN,
                        threshold=300_000_000,
                    ),
                    evidence_ids=(),
                ),
            ),
        )
        await artifacts.save(
            envelope(
                artifact_id="ART-REQUESTER-POLICY",
                artifact_type=ArtifactType.APPROVAL_CHECKPOINTS,
                version=1,
                input_hash="REQUESTER-POLICY-HASH",
                payload=checkpoints.model_dump(mode="json"),
                now=now,
            )
        )

        def action(*, requested_by: str, requested_amount: int) -> ActionCommand:
            return ActionCommand(
                action_type=ProtectedAction.COMMIT_LARGE_FINANCIAL_DECISION,
                evaluation_case_id="CASE-TEST",
                payload_artifact_id=subject.artifact_id,
                requested_by=requested_by,
                payload={"requested_amount": requested_amount},
            )

        pending_a = await orchestrator.request_action(
            action(requested_by="ACTOR-A", requested_amount=300_000_001)
        )
        pending_a_retry = await orchestrator.request_action(
            action(requested_by="ACTOR-A", requested_amount=300_000_001)
        )
        pending_b = await orchestrator.request_action(
            action(requested_by="ACTOR-B", requested_amount=300_000_001)
        )
        authorized_a = await orchestrator.request_action(
            action(requested_by="ACTOR-A", requested_amount=300_000_000)
        )
        authorized_b = await orchestrator.request_action(
            action(requested_by="ACTOR-B", requested_amount=300_000_000)
        )
        stored = await requests.list_by_case("CASE-TEST")
        await database.close()

        assert pending_a.approval_request is not None
        assert pending_a_retry.approval_request == pending_a.approval_request
        assert pending_b.approval_request is not None
        assert pending_a.approval_request.request_id != (
            pending_b.approval_request.request_id
        )
        assert pending_a.approval_request.workflow_run_id != (
            pending_b.approval_request.workflow_run_id
        )
        assert pending_a.approval_request.command.requested_by == "ACTOR-A"
        assert pending_b.approval_request.command.requested_by == "ACTOR-B"

        assert authorized_a.approval_request is not None
        assert authorized_b.approval_request is not None
        assert authorized_a.approval_request.request_id != (
            authorized_b.approval_request.request_id
        )
        assert authorized_a.approval_request.workflow_run_id != (
            authorized_b.approval_request.workflow_run_id
        )
        assert authorized_a.approval_request.command.requested_by == "ACTOR-A"
        assert authorized_b.approval_request.command.requested_by == "ACTOR-B"
        assert len(stored) == 4

    asyncio.run(execute())


def test_explicit_no_human_precheck_policy_creates_durable_authorization(
    tmp_path: Path,
) -> None:
    async def execute() -> None:
        now = datetime.now(UTC)
        database = SQLiteDatabase(tmp_path / "machine-authorization.db")
        await database.initialize()
        artifacts = SQLiteArtifactRepository(database)
        workflows = SQLiteCaseWorkflowRepository(database)
        requests = SQLiteApprovalRequestRepository(database)
        events = SQLiteRuntimeEventRepository(database)
        orchestrator = ApprovalOrchestrator(
            artifacts=artifacts,
            requests=requests,
            case_workflows=workflows,
            events=events,
            clock=lambda: now,
        )
        run = CaseWorkflowRun(
            workflow_run_id="CWF-AUTO-PRECHECK",
            dataset_id="DATASET-TEST",
            dataset_snapshot_hash="SNAPSHOT-TEST",
            evaluation_case_id="CASE-TEST",
            contract_id="CONTRACT-TEST",
            status=WorkflowStatus.RUNNING,
            current_stage=WorkflowNode.BANKING_PRECHECK_SUBMISSION_PROPOSAL.value,
            requested_scope=(
                EvaluationScope.FINANCE,
                EvaluationScope.OPERATIONS,
                EvaluationScope.RISK,
            ),
            created_at=now,
            updated_at=now,
        )
        await workflows.save_run(run)
        subject = envelope(
            artifact_id="ART-PRECHECK-PROPOSAL",
            artifact_type=ArtifactType.BANKING_PRECHECK_SUBMISSION_PROPOSAL,
            version=1,
            input_hash="PRECHECK-PROPOSAL-HASH",
            payload={"proposal_id": "PROPOSAL-TEST"},
            now=now,
        )
        await artifacts.save(subject)
        coverage = ApprovalPolicyCoverage(
            coverage_id="APCOV-NO-HUMAN",
            evaluation_case_id="CASE-TEST",
            protected_action=ProtectedAction.SUBMIT_BANKING_PRECHECK,
            subject_artifact_id=subject.artifact_id,
            api_ids=("API-NO-HUMAN",),
            source_policy_ids=("API-NO-HUMAN",),
            requires_human_approval=False,
            evidence_ids=("EVD-NO-HUMAN",),
        )
        checkpoints = ApprovalCheckpointSet(
            evaluation_case_id="CASE-TEST",
            dataset_id="DATASET-TEST",
            contract_id="CONTRACT-TEST",
            checkpoints=(
                ApprovalCheckpoint(
                    checkpoint_id="ACP-PRECHECK-AMOUNT",
                    evaluation_case_id="CASE-TEST",
                    source_rule_id="RR-AMOUNT",
                    approval_type="BANKING_PRECHECK_AMOUNT_APPROVAL",
                    trigger_event=(
                        ApprovalTriggerEvent.BANKING_PRECHECK_SUBMISSION_REQUESTED
                    ),
                    protected_action=ProtectedAction.SUBMIT_BANKING_PRECHECK,
                    condition=ApprovalCondition(
                        source_field="requested_amount",
                        operator=RuleOperator.GREATER_THAN,
                        threshold=300_000_000,
                    ),
                    evidence_ids=(),
                    policy_coverage_ids=(coverage.coverage_id,),
                ),
            ),
            policy_coverages=(coverage,),
        )
        policy = envelope(
            artifact_id="ART-PRECHECK-POLICY",
            artifact_type=ArtifactType.APPROVAL_CHECKPOINTS,
            version=1,
            input_hash="PRECHECK-POLICY-HASH",
            payload=checkpoints.model_dump(mode="json"),
            now=now,
        )
        await artifacts.save(policy)
        command = ActionCommand(
            action_type=ProtectedAction.SUBMIT_BANKING_PRECHECK,
            evaluation_case_id="CASE-TEST",
            payload_artifact_id=subject.artifact_id,
            requested_by="CASE_WORKFLOW_ORCHESTRATOR",
            payload={
                "precheck_submission_requested": True,
                "api_ids": ["API-NO-HUMAN"],
                "requested_amount": 300_000_000,
                "requested_amount_currency": "VND",
            },
        )

        first = await orchestrator.request_action(
            command,
            workflow_run_id=run.workflow_run_id,
            allow_running_workflow=True,
        )
        retried = await orchestrator.request_action(
            command,
            workflow_run_id=run.workflow_run_id,
            allow_running_workflow=True,
        )
        stored = await requests.list_by_case("CASE-TEST")
        persisted_run = await workflows.get_run(run.workflow_run_id)
        audit_events = await events.list_after(run.workflow_run_id, 0)
        await database.close()

        assert first.gate_status is ApprovalGateStatus.AUTHORIZED
        assert first.action_authorized is True
        assert first.approval_request is not None
        assert first.approval_request.status is (
            ApprovalRequestStatus.AUTHORIZED_WITHOUT_HUMAN
        )
        assert first.approval_request.policy_artifact_id == policy.artifact_id
        assert first.approval_request.policy_coverage_ids == (
            coverage.coverage_id,
        )
        assert retried.approval_request == first.approval_request
        assert stored == (first.approval_request,)
        assert persisted_run is not None
        assert persisted_run.status is WorkflowStatus.RUNNING
        assert sum(
            item.event_type == "PROTECTED_ACTION_ALLOWED"
            for item in audit_events
        ) == 1

    asyncio.run(execute())
