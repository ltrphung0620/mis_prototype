"""Register the server-owned Founder checkpoint for one exact Decision Card."""

from __future__ import annotations

from opc_mis.domain.approvals import (
    ApprovalCheckpoint,
    ApprovalCheckpointSet,
    ApprovalCondition,
)
from opc_mis.domain.artifacts import ArtifactDraft, ArtifactEnvelope
from opc_mis.domain.decision_governance_models import DecisionGovernancePolicy
from opc_mis.domain.enums import (
    ApprovalTriggerEvent,
    ArtifactType,
    ProtectedAction,
    RuleOperator,
    SourceType,
    ValidationStatus,
)
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.lineage import deterministic_id


class DecisionApprovalPolicyError(ValueError):
    """Raised when an exact Decision Card cannot be governed safely."""


class DecisionApprovalPolicyRegistry:
    """Create a non-executing Founder checkpoint from server policy."""

    component_id = "GOVERNANCE_FINAL_DECISION_POLICY"
    _SOURCE_FIELD = "final_decision_confirmation_requested"

    def create_draft(
        self,
        *,
        decision_card_artifact: ArtifactEnvelope,
        existing_checkpoint_artifact: ArtifactEnvelope,
        policy: DecisionGovernancePolicy,
    ) -> ArtifactDraft:
        """Extend the exact existing registry without activating an approval."""
        if (
            decision_card_artifact.artifact_type is not ArtifactType.DECISION_CARD
            or decision_card_artifact.validation_status
            not in {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}
        ):
            raise DecisionApprovalPolicyError(
                "Final Decision Governance requires a validated Decision Card."
            )
        if (
            existing_checkpoint_artifact.artifact_type
            is not ArtifactType.APPROVAL_CHECKPOINTS
            or existing_checkpoint_artifact.validation_status
            not in {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}
        ):
            raise DecisionApprovalPolicyError(
                "Final Decision Governance requires a validated checkpoint registry."
            )
        try:
            existing = ApprovalCheckpointSet.model_validate(
                existing_checkpoint_artifact.payload
            )
        except ValueError as exc:
            raise DecisionApprovalPolicyError(
                "The existing approval checkpoint registry is invalid."
            ) from exc
        if (
            existing.evaluation_case_id != decision_card_artifact.evaluation_case_id
            or existing.dataset_id != decision_card_artifact.payload.get("dataset_id")
        ):
            raise DecisionApprovalPolicyError(
                "Decision Card and approval registry belong to different scopes."
            )
        if not policy.final_decision_requires_founder:
            raise DecisionApprovalPolicyError(
                "The configured final Decision policy must explicitly require Founder."
            )

        policy_evidence = self._policy_evidence(
            dataset_id=existing.dataset_id,
            policy=policy,
        )
        card_evidence = tuple(decision_card_artifact.evidence_refs)
        source_evidence = (*card_evidence, *policy_evidence)
        derived = self._derived_evidence(
            dataset_id=existing.dataset_id,
            artifact=decision_card_artifact,
            policy=policy,
            sources=source_evidence,
        )
        condition = ApprovalCondition(
            source_field=self._SOURCE_FIELD,
            operator=RuleOperator.EQUAL,
            threshold=True,
        )
        checkpoint = ApprovalCheckpoint(
            checkpoint_id=deterministic_id(
                "ACP",
                existing.evaluation_case_id,
                policy.policy_id,
                policy.policy_version,
                policy.policy_hash,
                decision_card_artifact.artifact_id,
                decision_card_artifact.version,
                decision_card_artifact.input_hash,
                condition.model_dump(mode="json"),
            ),
            evaluation_case_id=existing.evaluation_case_id,
            source_rule_id=policy.policy_id,
            approval_type="FINAL_CONTRACT_DECISION_CONFIRMATION",
            trigger_event=(
                ApprovalTriggerEvent.FINAL_CONTRACT_DECISION_CONFIRMATION_REQUESTED
            ),
            protected_action=ProtectedAction.CONFIRM_FINAL_CONTRACT_DECISION,
            condition=condition,
            evidence_ids=tuple(item.evidence_id for item in (*policy_evidence, derived)),
            approver_role=policy.approver_role,
        )
        base_checkpoints = tuple(
            item
            for item in existing.checkpoints
            if item.protected_action
            is not ProtectedAction.CONFIRM_FINAL_CONTRACT_DECISION
        )
        checkpoint_set = ApprovalCheckpointSet(
            evaluation_case_id=existing.evaluation_case_id,
            dataset_id=existing.dataset_id,
            contract_id=existing.contract_id,
            checkpoints=(*base_checkpoints, checkpoint),
            policy_coverages=existing.policy_coverages,
        )
        evidence_by_id: dict[str, EvidenceRef] = {}
        for item in (
            *existing_checkpoint_artifact.evidence_refs,
            *card_evidence,
            *policy_evidence,
            derived,
        ):
            prior = evidence_by_id.get(item.evidence_id)
            if prior is not None and prior != item:
                raise DecisionApprovalPolicyError(
                    f"Conflicting evidence payload for {item.evidence_id}."
                )
            evidence_by_id[item.evidence_id] = item
        return ArtifactDraft(
            artifact_type=ArtifactType.APPROVAL_CHECKPOINTS,
            evaluation_case_id=existing.evaluation_case_id,
            producer=self.component_id,
            payload=checkpoint_set.model_dump(mode="json"),
            evidence_refs=tuple(evidence_by_id[key] for key in sorted(evidence_by_id)),
            identity_inputs={
                "source_checkpoint_artifact_id": (
                    existing_checkpoint_artifact.artifact_id
                ),
                "source_checkpoint_artifact_version": (
                    existing_checkpoint_artifact.version
                ),
                "source_checkpoint_input_hash": (
                    existing_checkpoint_artifact.input_hash
                ),
                "decision_card_artifact_id": decision_card_artifact.artifact_id,
                "decision_card_artifact_version": decision_card_artifact.version,
                "decision_card_input_hash": decision_card_artifact.input_hash,
                "policy_id": policy.policy_id,
                "policy_version": policy.policy_version,
                "policy_hash": policy.policy_hash,
                "checkpoint_ids": tuple(
                    item.checkpoint_id for item in checkpoint_set.checkpoints
                ),
            },
        )

    @staticmethod
    def _policy_evidence(
        *, dataset_id: str, policy: DecisionGovernancePolicy
    ) -> tuple[EvidenceRef, ...]:
        values = (
            ("final_decision_requires_founder", policy.final_decision_requires_founder),
            ("approver_role", policy.approver_role),
        )
        return tuple(
            EvidenceRef(
                evidence_id=deterministic_id(
                    "EVD",
                    dataset_id,
                    SourceType.POLICY_CONFIG,
                    "DECISION_GOVERNANCE_POLICY",
                    policy.policy_id,
                    policy.policy_version,
                    policy.policy_hash,
                    field,
                    value,
                ),
                source_type=SourceType.POLICY_CONFIG,
                sheet="DECISION_GOVERNANCE_POLICY",
                row_number=0,
                record_id=policy.policy_id,
                field=field,
                display_value=value,
            )
            for field, value in values
        )

    @staticmethod
    def _derived_evidence(
        *,
        dataset_id: str,
        artifact: ArtifactEnvelope,
        policy: DecisionGovernancePolicy,
        sources: tuple[EvidenceRef, ...],
    ) -> EvidenceRef:
        display = {
            "protected_action": (
                ProtectedAction.CONFIRM_FINAL_CONTRACT_DECISION.value
            ),
            "subject_artifact_id": artifact.artifact_id,
            "subject_artifact_version": artifact.version,
            "subject_input_hash": artifact.input_hash,
            "policy_id": policy.policy_id,
            "policy_version": policy.policy_version,
            "policy_hash": policy.policy_hash,
            "approver_role": policy.approver_role,
        }
        source_ids = tuple(item.evidence_id for item in sources)
        return EvidenceRef(
            evidence_id=deterministic_id(
                "EVD",
                dataset_id,
                SourceType.DERIVED,
                "GOVERNANCE_APPROVAL_POLICY",
                artifact.artifact_id,
                display,
                source_ids,
            ),
            source_type=SourceType.DERIVED,
            sheet="GOVERNANCE_APPROVAL_POLICY",
            row_number=0,
            record_id=artifact.artifact_id,
            field="final_decision_confirmation_scope",
            display_value=display,
            source_evidence_ids=source_ids,
        )
