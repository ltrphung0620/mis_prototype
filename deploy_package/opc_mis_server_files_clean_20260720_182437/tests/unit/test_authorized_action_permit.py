"""Fail-closed tests for ephemeral protected-action permit issuance."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from opc_mis.domain.approvals import (
    ApprovalCheckpoint,
    ApprovalCheckpointSet,
    ApprovalCondition,
    ApprovalDecisionRecord,
    ApprovalPolicyCoverage,
    ApprovalRequest,
)
from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.banking_precheck_execution_models import AuthorizedActionPermit
from opc_mis.domain.banking_precheck_submission_models import (
    BankingPrecheckSubmissionProposal,
    banking_precheck_action_payload,
)
from opc_mis.domain.commands import ActionCommand
from opc_mis.domain.enums import (
    ApprovalDecision,
    ApprovalRequestStatus,
    ApprovalTriggerEvent,
    ArtifactStatus,
    ArtifactType,
    ProtectedAction,
    RuleOperator,
    ValidationStatus,
)
from opc_mis.governance.authorized_action import (
    AuthorizationPermitError,
    AuthorizedActionPermitIssuer,
)
from opc_mis.infrastructure.persistence.memory_approval_request_repository import (
    InMemoryApprovalRequestRepository,
)
from opc_mis.infrastructure.persistence.memory_artifact_repository import (
    InMemoryArtifactRepository,
)
from tests.unit.test_banking_precheck_submission_proposal import CASE_ID, _setup

WORKFLOW_ID = "WORKFLOW-AUTHORIZED-PRECHECK"
REQUEST_ID = "APPROVAL-AUTHORIZED-PRECHECK"
SUBJECT_ID = "ART-PRECHECK-PROPOSAL-V1"
SUBJECT_HASH = "HASH-PRECHECK-PROPOSAL-V1"
DECIDED_AT = datetime(2026, 7, 18, 9, 30, tzinfo=UTC)


@dataclass(frozen=True)
class _Arrangement:
    issuer: AuthorizedActionPermitIssuer
    artifacts: InMemoryArtifactRepository
    approvals: InMemoryApprovalRequestRepository
    subject: ArtifactEnvelope
    request: ApprovalRequest


async def _arrange(*, save_subject: bool = True) -> _Arrangement:
    artifacts, skill, execution = await _setup()
    result = await skill.execute(execution)
    draft = result.artifacts[0]
    proposal = BankingPrecheckSubmissionProposal.model_validate(draft.payload)
    subject = ArtifactEnvelope(
        artifact_id=SUBJECT_ID,
        artifact_type=ArtifactType.BANKING_PRECHECK_SUBMISSION_PROPOSAL,
        evaluation_case_id=CASE_ID,
        producer=draft.producer,
        version=1,
        status=ArtifactStatus.CREATED,
        payload=draft.payload,
        evidence_refs=draft.evidence_refs,
        input_artifact_ids=execution.input_artifact_ids,
        input_hash=SUBJECT_HASH,
        validation_status=ValidationStatus.VALID,
        validation_notes=(),
        created_at=datetime(2026, 7, 18, 9, 0, tzinfo=UTC),
    )
    if save_subject:
        await artifacts.save(subject)
    coverage = ApprovalPolicyCoverage(
        coverage_id="APCOV-HUMAN-PRECHECK",
        evaluation_case_id=CASE_ID,
        protected_action=ProtectedAction.SUBMIT_BANKING_PRECHECK,
        subject_artifact_id=SUBJECT_ID,
        api_ids=tuple(dict.fromkeys(item.api_id for item in proposal.candidates)),
        source_policy_ids=("API-1", "API-H-TEST"),
        requires_human_approval=True,
        evidence_ids=("EVD-HUMAN-PRECHECK",),
    )
    checkpoint = ApprovalCheckpoint(
        checkpoint_id="ACP-BANKING-PRECHECK",
        evaluation_case_id=CASE_ID,
        source_rule_id="API-1",
        approval_type="BANKING_PRECHECK_API_POLICY",
        trigger_event=ApprovalTriggerEvent.BANKING_PRECHECK_SUBMISSION_REQUESTED,
        protected_action=ProtectedAction.SUBMIT_BANKING_PRECHECK,
        condition=ApprovalCondition(
            source_field="precheck_submission_requested",
            operator=RuleOperator.EQUAL,
            threshold=True,
        ),
        evidence_ids=coverage.evidence_ids,
        policy_coverage_ids=(coverage.coverage_id,),
    )
    checkpoint_set = ApprovalCheckpointSet(
        evaluation_case_id=CASE_ID,
        dataset_id=execution.dataset_id,
        contract_id=proposal.contract_id,
        checkpoints=(checkpoint,),
        policy_coverages=(coverage,),
    )
    policy = ArtifactEnvelope(
        artifact_id="ART-HUMAN-PRECHECK-POLICY",
        artifact_type=ArtifactType.APPROVAL_CHECKPOINTS,
        evaluation_case_id=CASE_ID,
        producer="GOVERNANCE_APPROVAL_POLICY_REGISTRY",
        version=1,
        status=ArtifactStatus.CREATED,
        payload=checkpoint_set.model_dump(mode="json"),
        evidence_refs=(),
        input_artifact_ids=(SUBJECT_ID,),
        input_hash="HASH-HUMAN-PRECHECK-POLICY",
        validation_status=ValidationStatus.VALID,
        validation_notes=(),
        created_at=datetime(2026, 7, 18, 9, 10, tzinfo=UTC),
    )
    await artifacts.save(policy)
    approvals = InMemoryApprovalRequestRepository()
    request = ApprovalRequest(
        request_id=REQUEST_ID,
        workflow_run_id=WORKFLOW_ID,
        evaluation_case_id=CASE_ID,
        dataset_id=execution.dataset_id,
        subject_artifact_id=SUBJECT_ID,
        subject_artifact_version=subject.version,
        subject_input_hash=subject.input_hash,
        checkpoint_ids=(checkpoint.checkpoint_id,),
        policy_artifact_id=policy.artifact_id,
        policy_artifact_version=policy.version,
        policy_input_hash=policy.input_hash,
        policy_coverage_ids=(coverage.coverage_id,),
        command=ActionCommand(
            action_type=ProtectedAction.SUBMIT_BANKING_PRECHECK,
            evaluation_case_id=CASE_ID,
            payload_artifact_id=SUBJECT_ID,
            requested_by="CASE_WORKFLOW_ORCHESTRATOR",
            payload=banking_precheck_action_payload(proposal),
        ),
        resume_stage="BANKING_PRECHECK_SUBMISSION_PROPOSAL",
        status=ApprovalRequestStatus.APPROVED,
        created_at=datetime(2026, 7, 18, 9, 15, tzinfo=UTC),
        decision_record=ApprovalDecisionRecord(
            decision=ApprovalDecision.APPROVE,
            decided_by="FOUNDER",
            reason="Authorize this exact simulated precheck proposal.",
            decided_at=DECIDED_AT,
        ),
    )
    await approvals.save(request)
    return _Arrangement(
        issuer=AuthorizedActionPermitIssuer(
            artifacts=artifacts,
            approval_requests=approvals,
        ),
        artifacts=artifacts,
        approvals=approvals,
        subject=subject,
        request=request,
    )


async def _issue(arrangement: _Arrangement) -> AuthorizedActionPermit:
    return await arrangement.issuer.issue(
        approval_request_id=REQUEST_ID,
        workflow_run_id=WORKFLOW_ID,
        evaluation_case_id=CASE_ID,
        expected_subject_artifact_id=SUBJECT_ID,
    )


async def _save_globally_superseding_policy(
    arrangement: _Arrangement,
) -> ArtifactEnvelope:
    policy_artifact_id = arrangement.request.policy_artifact_id
    assert policy_artifact_id is not None
    bound_policy = await arrangement.artifacts.get(policy_artifact_id)
    assert bound_policy is not None
    superseding_policy = bound_policy.model_copy(
        update={
            "artifact_id": "ART-DOWNSTREAM-POLICY-V2",
            "version": 2,
            "input_hash": "HASH-DOWNSTREAM-POLICY-V2",
            "created_at": datetime(2026, 7, 18, 10, 0, tzinfo=UTC),
        }
    )
    await arrangement.artifacts.save(superseding_policy)
    return superseding_policy


def test_exact_approved_latest_subject_issues_stable_ephemeral_permit() -> None:
    async def scenario() -> None:
        arranged = await _arrange()
        artifacts_before = await arranged.artifacts.list_by_case(CASE_ID)
        approvals_before = await arranged.approvals.list_by_case(CASE_ID)

        first = await _issue(arranged)
        retried = await _issue(arranged)

        assert first == retried
        assert first.workflow_run_id == WORKFLOW_ID
        assert first.evaluation_case_id == CASE_ID
        assert first.approval_request_id == REQUEST_ID
        assert first.protected_action is ProtectedAction.SUBMIT_BANKING_PRECHECK
        assert first.subject_artifact_id == SUBJECT_ID
        assert first.subject_artifact_version == 1
        assert first.subject_input_hash == SUBJECT_HASH
        assert first.authorized_by == "FOUNDER"
        assert first.authorized_at == DECIDED_AT
        assert await arranged.artifacts.list_by_case(CASE_ID) == artifacts_before
        assert await arranged.approvals.list_by_case(CASE_ID) == approvals_before

    asyncio.run(scenario())


def test_newer_registry_preserving_exact_precheck_scope_keeps_permit_valid() -> None:
    async def scenario() -> None:
        arranged = await _arrange()
        originally_issued = await _issue(arranged)
        await _save_globally_superseding_policy(arranged)

        current = await _issue(arranged)
        assert current == originally_issued

        artifacts_before = await arranged.artifacts.list_by_case(CASE_ID)
        approvals_before = await arranged.approvals.list_by_case(CASE_ID)
        historical_id = await arranged.issuer.historical_permit_id_for_reuse(
            approval_request_id=REQUEST_ID,
            workflow_run_id=WORKFLOW_ID,
            evaluation_case_id=CASE_ID,
            expected_subject_artifact_id=SUBJECT_ID,
        )

        assert historical_id == originally_issued.permit_id
        assert isinstance(historical_id, str)
        assert not isinstance(historical_id, AuthorizedActionPermit)
        assert await arranged.artifacts.list_by_case(CASE_ID) == artifacts_before
        assert await arranged.approvals.list_by_case(CASE_ID) == approvals_before

    asyncio.run(scenario())


def test_newer_registry_changing_precheck_scope_invalidates_permit() -> None:
    async def scenario() -> None:
        arranged = await _arrange()
        superseding = await _save_globally_superseding_policy(arranged)
        registry = ApprovalCheckpointSet.model_validate(superseding.payload)
        changed_checkpoint = registry.checkpoints[0].model_copy(
            update={"approver_role": "CFO"}
        )
        changed_registry = registry.model_copy(
            update={"checkpoints": (changed_checkpoint,)}
        )
        await arranged.artifacts.save(
            superseding.model_copy(
                update={
                    "artifact_id": "ART-CHANGED-PRECHECK-POLICY-V3",
                    "version": 3,
                    "input_hash": "HASH-CHANGED-PRECHECK-POLICY-V3",
                    "payload": changed_registry.model_dump(mode="json"),
                }
            )
        )

        with pytest.raises(
            AuthorizationPermitError,
            match="policy artifact is no longer current",
        ):
            await _issue(arranged)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("tampered_binding", "expected_error"),
    (
        ("request", "version or business input hash has changed"),
        ("subject", "subject is not validated"),
        ("policy", "policy artifact identity or validation is invalid"),
    ),
)
def test_historical_reuse_still_requires_exact_bound_authorization(
    tampered_binding: str,
    expected_error: str,
) -> None:
    async def scenario() -> None:
        arranged = await _arrange()
        await _save_globally_superseding_policy(arranged)
        if tampered_binding == "request":
            await arranged.approvals.save(
                arranged.request.model_copy(
                    update={"subject_input_hash": "TAMPERED-SUBJECT-HASH"}
                )
            )
        elif tampered_binding == "subject":
            await arranged.artifacts.save(
                arranged.subject.model_copy(
                    update={"validation_status": ValidationStatus.BLOCKED}
                )
            )
        else:
            policy_artifact_id = arranged.request.policy_artifact_id
            assert policy_artifact_id is not None
            bound_policy = await arranged.artifacts.get(policy_artifact_id)
            assert bound_policy is not None
            await arranged.artifacts.save(
                bound_policy.model_copy(
                    update={"input_hash": "TAMPERED-POLICY-HASH"}
                )
            )

        with pytest.raises(
            AuthorizationPermitError,
            match=expected_error,
        ):
            await arranged.issuer.historical_permit_id_for_reuse(
                approval_request_id=REQUEST_ID,
                workflow_run_id=WORKFLOW_ID,
                evaluation_case_id=CASE_ID,
                expected_subject_artifact_id=SUBJECT_ID,
            )

    asyncio.run(scenario())


def test_exact_explicit_no_human_policy_issues_machine_authorized_permit() -> None:
    async def scenario() -> None:
        arranged = await _arrange()
        coverage = ApprovalPolicyCoverage(
            coverage_id="APCOV-AUTO-PRECHECK",
            evaluation_case_id=CASE_ID,
            protected_action=ProtectedAction.SUBMIT_BANKING_PRECHECK,
            subject_artifact_id=SUBJECT_ID,
            api_ids=("API-1",),
            source_policy_ids=("API-1", "API-H-TEST"),
            requires_human_approval=False,
            evidence_ids=("EVD-AUTO-PRECHECK",),
        )
        checkpoint_set = ApprovalCheckpointSet(
            evaluation_case_id=CASE_ID,
            dataset_id=arranged.request.dataset_id,
            contract_id="CONTRACT-PRECHECK-PROPOSAL",
            checkpoints=(),
            policy_coverages=(coverage,),
        )
        policy = ArtifactEnvelope(
            artifact_id="ART-AUTO-PRECHECK-POLICY",
            artifact_type=ArtifactType.APPROVAL_CHECKPOINTS,
            evaluation_case_id=CASE_ID,
            producer="GOVERNANCE_APPROVAL_POLICY_REGISTRY",
            version=1,
            status=ArtifactStatus.CREATED,
            payload=checkpoint_set.model_dump(mode="json"),
            evidence_refs=(),
            input_artifact_ids=(SUBJECT_ID,),
            input_hash="HASH-AUTO-PRECHECK-POLICY",
            validation_status=ValidationStatus.VALID,
            validation_notes=(),
            created_at=datetime(2026, 7, 18, 9, 10, tzinfo=UTC),
        )
        await arranged.artifacts.save(policy)
        machine = arranged.request.model_copy(
            update={
                "status": ApprovalRequestStatus.AUTHORIZED_WITHOUT_HUMAN,
                "checkpoint_ids": (),
                "policy_artifact_id": policy.artifact_id,
                "policy_artifact_version": policy.version,
                "policy_input_hash": policy.input_hash,
                "policy_coverage_ids": (coverage.coverage_id,),
                "decision_record": None,
            }
        )
        await arranged.approvals.save(machine)

        permit = await _issue(arranged)

        assert permit.authorized_by == "GOVERNANCE_POLICY"
        assert permit.authorized_at == machine.created_at

        requiring_human = coverage.model_copy(
            update={"requires_human_approval": True}
        )
        await arranged.artifacts.save(
            policy.model_copy(
                update={
                    "payload": checkpoint_set.model_copy(
                        update={"policy_coverages": (requiring_human,)}
                    ).model_dump(mode="json")
                }
            )
        )
        with pytest.raises(AuthorizationPermitError, match="no-human policy"):
            await _issue(arranged)

    asyncio.run(scenario())


def test_permit_identity_changes_when_exact_human_decision_changes() -> None:
    async def scenario() -> None:
        arranged = await _arrange()
        original = await _issue(arranged)
        decision = arranged.request.decision_record
        assert decision is not None
        changed = arranged.request.model_copy(
            update={
                "decision_record": decision.model_copy(
                    update={"reason": "A materially different approval decision."}
                )
            }
        )
        await arranged.approvals.save(changed)

        revised = await _issue(arranged)

        assert revised.permit_id != original.permit_id

    asyncio.run(scenario())


def test_superseded_approved_subject_cannot_issue_permit() -> None:
    async def scenario() -> None:
        arranged = await _arrange()
        newer = arranged.subject.model_copy(
            update={
                "artifact_id": "ART-PRECHECK-PROPOSAL-V2",
                "version": 2,
                "input_hash": "HASH-PRECHECK-PROPOSAL-V2",
                "created_at": datetime(2026, 7, 18, 9, 45, tzinfo=UTC),
            }
        )
        await arranged.artifacts.save(newer)

        with pytest.raises(AuthorizationPermitError, match="stale"):
            await _issue(arranged)

    asyncio.run(scenario())


def test_rejected_or_non_affirmative_request_cannot_issue_permit() -> None:
    async def scenario() -> None:
        arranged = await _arrange()
        rejected = arranged.request.model_copy(
            update={
                "status": ApprovalRequestStatus.REJECTED,
                "decision_record": arranged.request.decision_record.model_copy(
                    update={"decision": ApprovalDecision.REJECT}
                ),
            }
        )
        await arranged.approvals.save(rejected)

        with pytest.raises(AuthorizationPermitError, match="not authorized"):
            await _issue(arranged)

        approved_without_decision = arranged.request.model_copy(
            update={"decision_record": None}
        )
        await arranged.approvals.save(approved_without_decision)
        with pytest.raises(AuthorizationPermitError, match="affirmative"):
            await _issue(arranged)

    asyncio.run(scenario())


def test_scope_subject_and_exact_payload_mismatches_fail_closed() -> None:
    async def scenario() -> None:
        arranged = await _arrange()
        issue_kwargs = {
            "approval_request_id": REQUEST_ID,
            "workflow_run_id": WORKFLOW_ID,
            "evaluation_case_id": CASE_ID,
            "expected_subject_artifact_id": SUBJECT_ID,
        }
        for field, wrong_value in (
            ("workflow_run_id", "OTHER-WORKFLOW"),
            ("evaluation_case_id", "OTHER-CASE"),
            ("expected_subject_artifact_id", "OTHER-SUBJECT"),
        ):
            with pytest.raises(AuthorizationPermitError):
                await arranged.issuer.issue(
                    **{**issue_kwargs, field: wrong_value}
                )

        wrong_action = arranged.request.command.model_copy(
            update={
                "action_type": ProtectedAction.COMMIT_LARGE_FINANCIAL_DECISION
            }
        )
        await arranged.approvals.save(
            arranged.request.model_copy(update={"command": wrong_action})
        )
        with pytest.raises(AuthorizationPermitError, match="another action"):
            await _issue(arranged)

        changed_command = arranged.request.command.model_copy(
            update={
                "payload": {
                    "precheck_submission_requested": True,
                    "requested_amount": 350_000_000,
                }
            }
        )
        await arranged.approvals.save(
            arranged.request.model_copy(update={"command": changed_command})
        )
        with pytest.raises(AuthorizationPermitError, match="exact precheck policy scope"):
            await _issue(arranged)

    asyncio.run(scenario())


def test_missing_or_unvalidated_subject_cannot_issue_permit() -> None:
    async def scenario() -> None:
        missing = await _arrange(save_subject=False)
        with pytest.raises(AuthorizationPermitError, match="does not exist"):
            await _issue(missing)

        unvalidated = await _arrange(save_subject=False)
        await unvalidated.artifacts.save(
            unvalidated.subject.model_copy(
                update={"validation_status": ValidationStatus.BLOCKED}
            )
        )
        with pytest.raises(AuthorizationPermitError, match="not validated"):
            await _issue(unvalidated)

    asyncio.run(scenario())


def test_approved_version_and_input_hash_must_match_subject_exactly() -> None:
    async def scenario() -> None:
        arranged = await _arrange()
        for update in (
            {"subject_artifact_version": 2},
            {"subject_input_hash": "OTHER-HASH"},
        ):
            await arranged.approvals.save(arranged.request.model_copy(update=update))
            with pytest.raises(AuthorizationPermitError, match="version or business"):
                await _issue(arranged)

    asyncio.run(scenario())
