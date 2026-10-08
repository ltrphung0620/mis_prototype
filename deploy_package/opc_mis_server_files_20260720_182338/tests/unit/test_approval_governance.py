"""Unit tests for exact, deterministic approval policy evaluation."""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime

import pytest

from opc_mis.domain.approvals import (
    ApprovalCheckpoint,
    ApprovalCheckpointSet,
    ApprovalCondition,
    ApprovalPolicyCoverage,
)
from opc_mis.domain.artifacts import ArtifactDraft, ArtifactEnvelope
from opc_mis.domain.commands import ActionCommand
from opc_mis.domain.enums import (
    ApprovalGateStatus,
    ApprovalTriggerEvent,
    ArtifactStatus,
    ArtifactType,
    ProtectedAction,
    RuleOperator,
    SourceType,
    ValidationStatus,
)
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.risk_models import RiskPreScan
from opc_mis.governance.approval_gate import ApprovalGate
from opc_mis.governance.approval_policy_registry import (
    ApprovalPolicyError,
    ApprovalPolicyRegistry,
)
from opc_mis.governance.evidence_validator import EvidenceValidator
from tests.unit.test_banking_precheck_submission_proposal import (
    CASE_ID,
    CONTRACT_ID,
    DATASET_ID,
    _setup,
)


def amount_checkpoint_set() -> ApprovalCheckpointSet:
    return ApprovalCheckpointSet(
        evaluation_case_id="CASE-TEST",
        dataset_id="DATASET-TEST",
        contract_id="CONTRACT-TEST",
        checkpoints=(
            ApprovalCheckpoint(
                checkpoint_id="ACP-TEST",
                evaluation_case_id="CASE-TEST",
                source_rule_id="RULE-TEST",
                approval_type="HUMAN_APPROVAL",
                trigger_event=ApprovalTriggerEvent.LARGE_FINANCIAL_DECISION_REQUESTED,
                protected_action=ProtectedAction.COMMIT_LARGE_FINANCIAL_DECISION,
                condition=ApprovalCondition(
                    source_field="requested_amount",
                    operator=RuleOperator.GREATER_THAN,
                    threshold=300_000_000,
                ),
                evidence_ids=("EVD-TEST",),
            ),
        ),
    )


def command(payload: dict[str, object]) -> ActionCommand:
    return ActionCommand(
        action_type=ProtectedAction.COMMIT_LARGE_FINANCIAL_DECISION,
        evaluation_case_id="CASE-TEST",
        payload_artifact_id="ART-TEST",
        requested_by="DECISION_AGENT",
        payload=payload,
    )


def test_gate_uses_exact_threshold_and_does_not_create_approval_below_it() -> None:
    gate = ApprovalGate()

    at_threshold = gate.evaluate(
        command({"requested_amount": 300_000_000}), amount_checkpoint_set()
    )
    above_threshold = gate.evaluate(
        command({"requested_amount": 300_000_001}), amount_checkpoint_set()
    )

    assert at_threshold.status is ApprovalGateStatus.AUTHORIZED
    assert above_threshold.status is ApprovalGateStatus.WAITING_FOR_APPROVAL
    assert above_threshold.triggered_checkpoints[0].source_rule_id == "RULE-TEST"


def test_gate_fails_closed_when_required_event_value_is_missing() -> None:
    result = ApprovalGate().evaluate(command({}), amount_checkpoint_set())

    assert result.status is ApprovalGateStatus.WAITING_FOR_INPUT
    assert result.missing_fields == ("requested_amount",)


def test_gate_fails_closed_on_wrong_value_type_instead_of_authorizing() -> None:
    result = ApprovalGate().evaluate(
        command({"requested_amount": "301000000"}), amount_checkpoint_set()
    )

    assert result.status is ApprovalGateStatus.WAITING_FOR_INPUT
    assert result.missing_fields == ("requested_amount",)


def test_risk_registry_does_not_invent_a_banking_api_policy() -> None:
    draft = ApprovalPolicyRegistry().create_draft(
        pre_scan=RiskPreScan(
            evaluation_case_id="CASE-TEST",
            dataset_id="DATASET-TEST",
            contract_id="CONTRACT-TEST",
            source_rule_ids=(),
            source_rules=(),
            case_alerts=(),
            global_alerts=(),
            global_signals=(),
            rule_dependencies=(),
            source_record_counts={},
        ),
        signals=(),
    )
    checkpoint_set = ApprovalCheckpointSet.model_validate(draft.payload)

    assert checkpoint_set.checkpoints == ()
    assert checkpoint_set.policy_coverages == ()
    assert draft.evidence_refs == ()


async def _banking_policy_draft() -> tuple[
    ArtifactEnvelope,
    ApprovalCheckpointSet,
    ArtifactDraft,
]:
    _, skill, execution = await _setup()
    result = await skill.execute(execution)
    proposal = result.proposal
    assert proposal is not None
    proposal_draft = result.artifacts[0]
    proposal_artifact = ArtifactEnvelope(
        artifact_id="ART-VALIDATED-PRECHECK-PROPOSAL",
        artifact_type=proposal_draft.artifact_type,
        evaluation_case_id=CASE_ID,
        producer=proposal_draft.producer,
        version=1,
        status=ArtifactStatus.CREATED,
        payload=proposal_draft.payload,
        evidence_refs=proposal_draft.evidence_refs,
        input_artifact_ids=execution.input_artifact_ids,
        input_hash="HASH-VALIDATED-PRECHECK-PROPOSAL",
        validation_status=ValidationStatus.VALID,
        validation_notes=(),
        created_at=datetime(2026, 7, 18, tzinfo=UTC),
    )
    risk_evidence = EvidenceRef(
        evidence_id="EVD-RR-005-AMOUNT",
        source_type=SourceType.TEAM_PACK,
        sheet="13_RISK_RULES",
        row_number=6,
        record_id="RR-005",
        field="trigger_condition",
        display_value="requested_amount > 300000000",
    )
    source_set = ApprovalCheckpointSet(
        evaluation_case_id=CASE_ID,
        dataset_id=DATASET_ID,
        contract_id=CONTRACT_ID,
        checkpoints=(
            ApprovalCheckpoint(
                checkpoint_id="ACP-RR-005",
                evaluation_case_id=CASE_ID,
                source_rule_id="RR-005",
                approval_type="HUMAN_APPROVAL",
                trigger_event=(
                    ApprovalTriggerEvent.LARGE_FINANCIAL_DECISION_REQUESTED
                ),
                protected_action=ProtectedAction.COMMIT_LARGE_FINANCIAL_DECISION,
                condition=ApprovalCondition(
                    source_field="requested_amount",
                    operator=RuleOperator.GREATER_THAN,
                    threshold=300_000_000,
                ),
                evidence_ids=(risk_evidence.evidence_id,),
            ),
        ),
    )
    source_artifact = ArtifactEnvelope(
        artifact_id="ART-RISK-APPROVAL-CHECKPOINTS",
        artifact_type=ArtifactType.APPROVAL_CHECKPOINTS,
        evaluation_case_id=CASE_ID,
        producer="GOVERNANCE_APPROVAL_POLICY_REGISTRY",
        version=1,
        status=ArtifactStatus.CREATED,
        payload=source_set.model_dump(mode="json"),
        evidence_refs=(risk_evidence,),
        input_artifact_ids=(),
        input_hash="HASH-RISK-APPROVAL-CHECKPOINTS",
        validation_status=ValidationStatus.VALID,
        validation_notes=(),
        created_at=datetime(2026, 7, 18, tzinfo=UTC),
    )
    draft = ApprovalPolicyRegistry().create_banking_precheck_draft(
        proposal_artifact=proposal_artifact,
        existing_checkpoint_artifact=source_artifact,
    )
    return (
        proposal_artifact,
        ApprovalCheckpointSet.model_validate(draft.payload),
        draft,
    )


def test_banking_registry_reads_api_and_amount_policy_with_exact_lineage() -> None:
    async def scenario() -> None:
        proposal_artifact, checkpoint_set, draft = await _banking_policy_draft()

        assert len(checkpoint_set.policy_coverages) == 1
        coverage = checkpoint_set.policy_coverages[0]
        assert coverage.subject_artifact_id == proposal_artifact.artifact_id
        assert coverage.api_ids == ("API-1",)
        assert coverage.requires_human_approval is True
        assert coverage.approver_role == "FOUNDER"
        assert coverage.source_policy_ids == ("API-1", "API-H-TEST")
        precheck = tuple(
            item
            for item in checkpoint_set.checkpoints
            if item.protected_action is ProtectedAction.SUBMIT_BANKING_PRECHECK
        )
        assert {item.source_rule_id for item in precheck} == {"API-1", "RR-005"}
        amount = next(item for item in precheck if item.source_rule_id == "RR-005")
        assert amount.condition.operator is RuleOperator.GREATER_THAN
        assert amount.condition.threshold == 300_000_000
        assert amount.approver_role == "FOUNDER"
        report = await EvidenceValidator().validate(draft)
        assert report.status is ValidationStatus.VALID

    asyncio.run(scenario())


def test_banking_gate_requires_exact_scope_and_aggregates_triggered_reasons() -> None:
    async def scenario() -> None:
        proposal_artifact, checkpoint_set, _ = await _banking_policy_draft()
        proposal = proposal_artifact.payload
        command_payload = {
            "precheck_submission_requested": True,
            "api_ids": ["API-1"],
            "requested_amount": proposal["requested_amount"],
            "requested_amount_currency": "VND",
        }

        def proposal_command(payload: dict[str, object]) -> ActionCommand:
            return ActionCommand(
                action_type=ProtectedAction.SUBMIT_BANKING_PRECHECK,
                evaluation_case_id=CASE_ID,
                payload_artifact_id=proposal_artifact.artifact_id,
                requested_by="DECISION_AGENT",
                payload=payload,
            )

        missing_scope = ApprovalGate().evaluate(
            proposal_command({"precheck_submission_requested": True}),
            checkpoint_set,
        )
        requested = ApprovalGate().evaluate(
            proposal_command(command_payload),
            checkpoint_set,
        )

        assert missing_scope.status is ApprovalGateStatus.WAITING_FOR_INPUT
        assert missing_scope.missing_fields == ("api_ids",)
        assert requested.status is ApprovalGateStatus.WAITING_FOR_APPROVAL
        assert {item.source_rule_id for item in requested.triggered_checkpoints} == {
            "API-1",
            "RR-005",
        }

    asyncio.run(scenario())


def test_gate_allows_explicit_no_human_policy_when_amount_does_not_trigger() -> None:
    coverage = ApprovalPolicyCoverage(
        coverage_id="APCOV-NO-HUMAN",
        evaluation_case_id="CASE-TEST",
        protected_action=ProtectedAction.SUBMIT_BANKING_PRECHECK,
        subject_artifact_id="ART-TEST",
        api_ids=("API-NO-HUMAN",),
        source_policy_ids=("API-NO-HUMAN", "API-H-NO"),
        requires_human_approval=False,
        evidence_ids=("EVD-NO-HUMAN",),
    )
    source = amount_checkpoint_set().checkpoints[0]
    scoped_amount = source.model_copy(
        update={
            "checkpoint_id": "ACP-SCOPED-AMOUNT",
            "protected_action": ProtectedAction.SUBMIT_BANKING_PRECHECK,
            "trigger_event": ApprovalTriggerEvent.BANKING_PRECHECK_SUBMISSION_REQUESTED,
            "policy_coverage_ids": (coverage.coverage_id,),
        }
    )
    checkpoint_set = amount_checkpoint_set().model_copy(
        update={
            "checkpoints": (scoped_amount,),
            "policy_coverages": (coverage,),
        }
    )
    result = ApprovalGate().evaluate(
        ActionCommand(
            action_type=ProtectedAction.SUBMIT_BANKING_PRECHECK,
            evaluation_case_id="CASE-TEST",
            payload_artifact_id="ART-TEST",
            requested_by="DECISION_AGENT",
            payload={
                "precheck_submission_requested": True,
                "api_ids": ["API-NO-HUMAN"],
                "requested_amount": 300_000_000,
                "requested_amount_currency": "VND",
            },
        ),
        checkpoint_set,
    )

    assert result.status is ApprovalGateStatus.AUTHORIZED


def test_registry_recognizes_explicit_no_human_source_policy() -> None:
    async def scenario() -> None:
        proposal_artifact, _, source_draft = await _banking_policy_draft()
        payload = deepcopy(proposal_artifact.payload)
        facts = payload["candidates"][0]["governance_source_facts"]
        facts["api_extension_rule"] = "No human approval required"
        facts["handling_rules"][0]["requires_human_approval_text"] = "No"
        evidence = tuple(
            item.model_copy(update={"display_value": "No human approval required"})
            if item.evidence_id == facts["api_extension_rule_evidence_id"]
            else item.model_copy(update={"display_value": "No"})
            if item.evidence_id
            in facts["handling_rules"][0]["evidence_ids"]
            and item.field == "requires_human_approval"
            else item
            for item in proposal_artifact.evidence_refs
        )
        proposal_artifact = proposal_artifact.model_copy(
            update={"payload": payload, "evidence_refs": evidence}
        )
        enriched_set = ApprovalCheckpointSet.model_validate(source_draft.payload)
        base_checkpoints = tuple(
            item
            for item in enriched_set.checkpoints
            if item.protected_action
            is ProtectedAction.COMMIT_LARGE_FINANCIAL_DECISION
        )
        base_set = enriched_set.model_copy(
            update={"checkpoints": base_checkpoints, "policy_coverages": ()}
        )
        base_evidence_ids = {
            evidence_id
            for item in base_checkpoints
            for evidence_id in item.evidence_ids
        }
        source_artifact = ArtifactEnvelope(
            artifact_id="ART-SOURCE-POLICY-FOR-NO-HUMAN",
            artifact_type=ArtifactType.APPROVAL_CHECKPOINTS,
            evaluation_case_id=CASE_ID,
            producer=source_draft.producer,
            version=1,
            status=ArtifactStatus.CREATED,
            payload=base_set.model_dump(mode="json"),
            evidence_refs=tuple(
                item
                for item in source_draft.evidence_refs
                if item.evidence_id in base_evidence_ids
            ),
            input_artifact_ids=(),
            input_hash="HASH-SOURCE-POLICY-FOR-NO-HUMAN",
            validation_status=ValidationStatus.VALID,
            validation_notes=(),
            created_at=datetime(2026, 7, 18, tzinfo=UTC),
        )

        draft = ApprovalPolicyRegistry().create_banking_precheck_draft(
            proposal_artifact=proposal_artifact,
            existing_checkpoint_artifact=source_artifact,
        )
        checkpoint_set = ApprovalCheckpointSet.model_validate(draft.payload)
        coverage = checkpoint_set.policy_coverages[0]

        assert coverage.requires_human_approval is False
        assert all(
            item.approval_type != "BANKING_PRECHECK_API_POLICY"
            for item in checkpoint_set.checkpoints
        )

    asyncio.run(scenario())


def test_banking_policy_fails_closed_without_unique_amount_checkpoint() -> None:
    async def scenario() -> None:
        _, skill, execution = await _setup()
        result = await skill.execute(execution)
        draft = result.artifacts[0]
        proposal_artifact = ArtifactEnvelope(
            artifact_id="ART-PROPOSAL-NO-AMOUNT-POLICY",
            artifact_type=draft.artifact_type,
            evaluation_case_id=CASE_ID,
            producer=draft.producer,
            version=1,
            status=ArtifactStatus.CREATED,
            payload=draft.payload,
            evidence_refs=draft.evidence_refs,
            input_artifact_ids=execution.input_artifact_ids,
            input_hash="HASH-PROPOSAL-NO-AMOUNT-POLICY",
            validation_status=ValidationStatus.VALID,
            validation_notes=(),
            created_at=datetime(2026, 7, 18, tzinfo=UTC),
        )

        with pytest.raises(ApprovalPolicyError, match="requested_amount"):
            ApprovalPolicyRegistry().create_banking_precheck_draft(
                proposal_artifact=proposal_artifact,
                existing_checkpoint_artifact=None,
            )

    asyncio.run(scenario())
