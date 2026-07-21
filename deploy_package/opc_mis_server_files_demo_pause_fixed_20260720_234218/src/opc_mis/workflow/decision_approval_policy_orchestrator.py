"""Persist the exact Founder policy registry for one Decision Card."""

from opc_mis.domain.approvals import ApprovalCheckpointSet
from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.decision_governance_models import DecisionGovernancePolicy
from opc_mis.domain.enums import ArtifactType, ProtectedAction, ValidationStatus
from opc_mis.governance.decision_approval_policy import (
    DecisionApprovalPolicyError,
    DecisionApprovalPolicyRegistry,
)
from opc_mis.governance.evidence_validator import EvidenceValidator
from opc_mis.ports.artifact_repository import ArtifactRepository
from opc_mis.workflow.artifact_factory import ArtifactFactory, artifact_input_hash


class DecisionApprovalPolicyRegistrationError(RuntimeError):
    """Raised when a Decision approval policy cannot be persisted safely."""


class DecisionApprovalPolicyOrchestrator:
    """Validate, version, and persist one exact Decision policy registry."""

    def __init__(
        self,
        *,
        artifacts: ArtifactRepository,
        policy: DecisionGovernancePolicy,
        registry: DecisionApprovalPolicyRegistry | None = None,
        validator: EvidenceValidator | None = None,
        artifact_factory: ArtifactFactory | None = None,
    ) -> None:
        self._artifacts = artifacts
        self._policy = policy
        self._registry = registry or DecisionApprovalPolicyRegistry()
        self._validator = validator or EvidenceValidator()
        self._artifact_factory = artifact_factory or ArtifactFactory()

    async def register(
        self,
        *,
        decision_card_artifact: ArtifactEnvelope,
        context: ExecutionContext,
    ) -> ArtifactEnvelope:
        """Persist or reuse the policy bound to one exact current Decision Card."""
        if context.evaluation_case_id != decision_card_artifact.evaluation_case_id:
            raise DecisionApprovalPolicyRegistrationError(
                "Decision policy context and Decision Card belong to different cases."
            )
        artifacts = await self._artifacts.list_by_case(
            decision_card_artifact.evaluation_case_id
        )
        base = self._base_registry(artifacts)
        try:
            draft = self._registry.create_draft(
                decision_card_artifact=decision_card_artifact,
                existing_checkpoint_artifact=base,
                policy=self._policy,
            )
        except DecisionApprovalPolicyError as exc:
            raise DecisionApprovalPolicyRegistrationError(str(exc)) from exc
        policy_context = context.model_copy(
            update={
                "input_artifact_ids": (
                    base.artifact_id,
                    decision_card_artifact.artifact_id,
                )
            }
        )
        report = await self._validator.validate(draft)
        if report.status is ValidationStatus.BLOCKED:
            raise DecisionApprovalPolicyRegistrationError(
                "; ".join(report.blocking_errors)
                or "Final Decision approval policy failed validation."
            )
        expected_hash = artifact_input_hash(draft, policy_context)
        matches = tuple(
            item
            for item in artifacts
            if item.artifact_type is ArtifactType.APPROVAL_CHECKPOINTS
            and item.input_hash == expected_hash
        )
        if matches:
            if len(matches) != 1:
                raise DecisionApprovalPolicyRegistrationError(
                    "Final Decision policy artifact identity is ambiguous."
                )
            existing = matches[0]
            if (
                existing.payload != draft.payload
                or existing.evidence_refs != draft.evidence_refs
                or existing.input_artifact_ids != policy_context.input_artifact_ids
                or existing.validation_status
                not in {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}
            ):
                raise DecisionApprovalPolicyRegistrationError(
                    "Existing final Decision policy artifact is not safely reusable."
                )
            return existing
        version = 1 + max(
            (
                item.version
                for item in artifacts
                if item.artifact_type is ArtifactType.APPROVAL_CHECKPOINTS
            ),
            default=0,
        )
        envelope = self._artifact_factory.create(
            draft=draft,
            context=policy_context,
            validation_report=report,
            version=version,
        )
        await self._artifacts.save(envelope)
        return envelope

    async def register_negotiation(
        self,
        *,
        negotiation_outcome_artifact: ArtifactEnvelope,
        context: ExecutionContext,
    ) -> ArtifactEnvelope:
        """Persist a Founder checkpoint bound to one exact negotiation outcome."""
        artifacts = await self._artifacts.list_by_case(
            negotiation_outcome_artifact.evaluation_case_id
        )
        candidates: list[ArtifactEnvelope] = []
        for artifact in artifacts:
            if artifact.artifact_type is not ArtifactType.APPROVAL_CHECKPOINTS:
                continue
            try:
                registry = ApprovalCheckpointSet.model_validate(artifact.payload)
            except ValueError:
                continue
            if any(
                item.protected_action
                is ProtectedAction.CONFIRM_FINAL_CONTRACT_DECISION
                for item in registry.checkpoints
            ) and not any(
                item.protected_action
                is ProtectedAction.CONFIRM_NEGOTIATION_OUTCOME
                for item in registry.checkpoints
            ):
                candidates.append(artifact)
        if not candidates:
            raise DecisionApprovalPolicyRegistrationError(
                "No final Decision policy registry is available for negotiation."
            )
        base = max(candidates, key=lambda item: item.version)
        try:
            draft = self._registry.create_negotiation_draft(
                negotiation_outcome_artifact=negotiation_outcome_artifact,
                existing_checkpoint_artifact=base,
                policy=self._policy,
            )
        except DecisionApprovalPolicyError as exc:
            raise DecisionApprovalPolicyRegistrationError(str(exc)) from exc
        policy_context = context.model_copy(
            update={
                "input_artifact_ids": (
                    base.artifact_id,
                    negotiation_outcome_artifact.artifact_id,
                )
            }
        )
        report = await self._validator.validate(draft)
        if report.status is ValidationStatus.BLOCKED:
            raise DecisionApprovalPolicyRegistrationError(
                "; ".join(report.blocking_errors)
                or "Negotiation approval policy failed validation."
            )
        expected_hash = artifact_input_hash(draft, policy_context)
        matches = tuple(
            item
            for item in artifacts
            if item.artifact_type is ArtifactType.APPROVAL_CHECKPOINTS
            and item.input_hash == expected_hash
        )
        if matches:
            if len(matches) != 1 or matches[0].payload != draft.payload:
                raise DecisionApprovalPolicyRegistrationError(
                    "Existing negotiation policy artifact is not safely reusable."
                )
            return matches[0]
        version = 1 + max(
            (
                item.version
                for item in artifacts
                if item.artifact_type is ArtifactType.APPROVAL_CHECKPOINTS
            ),
            default=0,
        )
        envelope = self._artifact_factory.create(
            draft=draft,
            context=policy_context,
            validation_report=report,
            version=version,
        )
        await self._artifacts.save(envelope)
        return envelope

    @staticmethod
    def _base_registry(
        artifacts: tuple[ArtifactEnvelope, ...],
    ) -> ArtifactEnvelope:
        candidates: list[ArtifactEnvelope] = []
        for artifact in artifacts:
            if (
                artifact.artifact_type is not ArtifactType.APPROVAL_CHECKPOINTS
                or artifact.validation_status
                not in {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}
            ):
                continue
            try:
                registry = ApprovalCheckpointSet.model_validate(artifact.payload)
            except ValueError:
                continue
            if not any(
                item.protected_action
                is ProtectedAction.CONFIRM_FINAL_CONTRACT_DECISION
                for item in registry.checkpoints
            ):
                candidates.append(artifact)
        if not candidates:
            raise DecisionApprovalPolicyRegistrationError(
                "No validated base approval registry is available for final Decision."
            )
        highest = max(item.version for item in candidates)
        latest = tuple(item for item in candidates if item.version == highest)
        if len(latest) != 1:
            raise DecisionApprovalPolicyRegistrationError(
                "The base approval registry for final Decision is ambiguous."
            )
        return latest[0]
