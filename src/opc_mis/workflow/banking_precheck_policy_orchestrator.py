"""Persist proposal-scoped Governance policy before a Banking precheck gate."""

from opc_mis.domain.approvals import ApprovalCheckpointSet
from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import ArtifactType, ValidationStatus
from opc_mis.governance.approval_policy_registry import (
    ApprovalPolicyError,
    ApprovalPolicyRegistry,
)
from opc_mis.governance.evidence_validator import EvidenceValidator
from opc_mis.ports.artifact_repository import ArtifactRepository
from opc_mis.workflow.artifact_factory import ArtifactFactory, artifact_input_hash


class BankingPrecheckPolicyRegistrationError(RuntimeError):
    """Raised when exact TeamPack policy cannot be validated and persisted."""


class BankingPrecheckPolicyOrchestrator:
    """Version and persist one exact proposal-scoped approval policy registry."""

    def __init__(
        self,
        *,
        artifacts: ArtifactRepository,
        registry: ApprovalPolicyRegistry | None = None,
        validator: EvidenceValidator | None = None,
        artifact_factory: ArtifactFactory | None = None,
    ) -> None:
        self._artifacts = artifacts
        self._registry = registry or ApprovalPolicyRegistry()
        self._validator = validator or EvidenceValidator()
        self._artifact_factory = artifact_factory or ArtifactFactory()

    async def register(
        self,
        *,
        proposal_artifact: ArtifactEnvelope,
        context: ExecutionContext,
    ) -> ArtifactEnvelope:
        """Persist or reuse policy bound to one exact validated proposal."""
        if context.evaluation_case_id != proposal_artifact.evaluation_case_id:
            raise BankingPrecheckPolicyRegistrationError(
                "Policy context and Banking proposal belong to different cases."
            )
        artifacts = await self._artifacts.list_by_case(
            proposal_artifact.evaluation_case_id
        )
        base = self._base_risk_registry(artifacts)
        try:
            draft = self._registry.create_banking_precheck_draft(
                proposal_artifact=proposal_artifact,
                existing_checkpoint_artifact=base,
            )
        except ApprovalPolicyError as exc:
            raise BankingPrecheckPolicyRegistrationError(str(exc)) from exc

        policy_context = context.model_copy(
            update={
                "input_artifact_ids": (base.artifact_id, proposal_artifact.artifact_id),
            }
        )
        report = await self._validator.validate(draft)
        if report.status is ValidationStatus.BLOCKED:
            raise BankingPrecheckPolicyRegistrationError(
                "; ".join(report.blocking_errors)
                or "Proposal-scoped Banking approval policy failed validation."
            )

        expected_hash = artifact_input_hash(draft, policy_context)
        same_identity = tuple(
            item
            for item in artifacts
            if item.artifact_type is ArtifactType.APPROVAL_CHECKPOINTS
            and item.input_hash == expected_hash
        )
        if same_identity:
            if len(same_identity) != 1:
                raise BankingPrecheckPolicyRegistrationError(
                    "Proposal-scoped policy artifact identity is ambiguous."
                )
            existing = same_identity[0]
            if (
                existing.payload != draft.payload
                or existing.evidence_refs != draft.evidence_refs
                or existing.input_artifact_ids != policy_context.input_artifact_ids
                or existing.validation_status
                not in {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}
            ):
                raise BankingPrecheckPolicyRegistrationError(
                    "Existing proposal-scoped policy artifact is not safely reusable."
                )
            return existing

        version = (
            max(
                (
                    item.version
                    for item in artifacts
                    if item.artifact_type is ArtifactType.APPROVAL_CHECKPOINTS
                ),
                default=0,
            )
            + 1
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
    def _base_risk_registry(
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
            if not registry.policy_coverages:
                candidates.append(artifact)
        if not candidates:
            raise BankingPrecheckPolicyRegistrationError(
                "No validated Risk approval registry is available for Banking policy."
            )
        highest = max(item.version for item in candidates)
        latest = tuple(item for item in candidates if item.version == highest)
        if len(latest) != 1:
            raise BankingPrecheckPolicyRegistrationError(
                "The base Risk approval registry is ambiguous."
            )
        return latest[0]
