"""Issue an ephemeral permit for one exactly approved protected action."""

from datetime import datetime

from opc_mis.domain.approvals import (
    ApprovalCheckpointSet,
    ApprovalRequest,
    approval_policy_scope_is_preserved,
)
from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.banking_precheck_execution_models import AuthorizedActionPermit
from opc_mis.domain.banking_precheck_submission_models import (
    BankingPrecheckSubmissionProposal,
    banking_precheck_action_payload,
)
from opc_mis.domain.enums import (
    ApprovalDecision,
    ApprovalGateStatus,
    ApprovalRequestStatus,
    ArtifactType,
    ProtectedAction,
    ValidationStatus,
)
from opc_mis.domain.lineage import deterministic_id
from opc_mis.governance.approval_gate import ApprovalGate
from opc_mis.ports.approval_request_repository import ApprovalRequestRepository
from opc_mis.ports.artifact_repository import ArtifactRepository

_VALID_ARTIFACT_STATUSES = {
    ValidationStatus.VALID,
    ValidationStatus.VALID_WITH_WARNINGS,
}


class AuthorizationPermitError(RuntimeError):
    """Raised when exact approval authority cannot be proven."""


class AuthorizedActionPermitIssuer:
    """Verify persisted Governance state and issue no-side-effect authority."""

    def __init__(
        self,
        *,
        artifacts: ArtifactRepository,
        approval_requests: ApprovalRequestRepository,
    ) -> None:
        self._artifacts = artifacts
        self._approval_requests = approval_requests

    async def issue(
        self,
        *,
        approval_request_id: str,
        workflow_run_id: str,
        evaluation_case_id: str,
        expected_subject_artifact_id: str,
    ) -> AuthorizedActionPermit:
        """Issue a stable permit only for the latest exactly approved proposal."""
        return await self._build_permit(
            approval_request_id=approval_request_id,
            workflow_run_id=workflow_run_id,
            evaluation_case_id=evaluation_case_id,
            expected_subject_artifact_id=expected_subject_artifact_id,
            require_current_policy=True,
        )

    async def historical_permit_id_for_reuse(
        self,
        *,
        approval_request_id: str,
        workflow_run_id: str,
        evaluation_case_id: str,
        expected_subject_artifact_id: str,
    ) -> str:
        """Reconstruct lineage for an existing result without granting authority.

        This method returns only the deterministic permit identity. Callers may use
        it to revalidate an already persisted result, but cannot pass an executable
        permit to a protected adapter. The exact request-bound policy is validated;
        only the global latest-policy check is omitted because unrelated downstream
        policy registries must not invalidate completed historical evidence.
        """
        permit = await self._build_permit(
            approval_request_id=approval_request_id,
            workflow_run_id=workflow_run_id,
            evaluation_case_id=evaluation_case_id,
            expected_subject_artifact_id=expected_subject_artifact_id,
            require_current_policy=False,
        )
        return permit.permit_id

    async def _build_permit(
        self,
        *,
        approval_request_id: str,
        workflow_run_id: str,
        evaluation_case_id: str,
        expected_subject_artifact_id: str,
        require_current_policy: bool,
    ) -> AuthorizedActionPermit:
        """Validate exact authority and build its deterministic permit value."""
        request = await self._approval_requests.get(approval_request_id)
        if request is None:
            raise AuthorizationPermitError("Approval request does not exist.")
        authorized_by, authorized_at, authorization_identity = self._require_exact_request(
            request,
            approval_request_id=approval_request_id,
            workflow_run_id=workflow_run_id,
            evaluation_case_id=evaluation_case_id,
            expected_subject_artifact_id=expected_subject_artifact_id,
        )

        subject = await self._artifacts.get(expected_subject_artifact_id)
        if subject is None:
            raise AuthorizationPermitError("Approved subject artifact does not exist.")
        await self._require_exact_subject(
            subject,
            request=request,
            evaluation_case_id=evaluation_case_id,
        )
        await self._require_policy_scope(
            request,
            subject,
            require_current_policy=require_current_policy,
        )
        protected_action = ProtectedAction.SUBMIT_BANKING_PRECHECK
        permit_id = deterministic_id(
            "AAP",
            workflow_run_id,
            evaluation_case_id,
            approval_request_id,
            protected_action,
            subject.artifact_id,
            subject.version,
            subject.input_hash,
            request.checkpoint_ids,
            request.policy_coverage_ids,
            authorization_identity,
        )
        return AuthorizedActionPermit(
            permit_id=permit_id,
            workflow_run_id=workflow_run_id,
            evaluation_case_id=evaluation_case_id,
            approval_request_id=approval_request_id,
            protected_action=protected_action,
            subject_artifact_id=subject.artifact_id,
            subject_artifact_version=subject.version,
            subject_input_hash=subject.input_hash,
            authorized_by=authorized_by,
            authorized_at=authorized_at,
        )

    @staticmethod
    def _require_exact_request(
        request: ApprovalRequest,
        *,
        approval_request_id: str,
        workflow_run_id: str,
        evaluation_case_id: str,
        expected_subject_artifact_id: str,
    ) -> tuple[str, datetime, dict[str, object]]:
        decision = request.decision_record
        if request.request_id != approval_request_id:
            raise AuthorizationPermitError("Repository returned another approval request.")
        if request.status is ApprovalRequestStatus.APPROVED:
            if decision is None or decision.decision is not ApprovalDecision.APPROVE:
                raise AuthorizationPermitError(
                    "Approval request lacks an affirmative human decision."
                )
            authorized_by = decision.decided_by
            authorized_at = decision.decided_at
            identity: dict[str, object] = decision.model_dump(mode="json")
        elif request.status is ApprovalRequestStatus.AUTHORIZED_WITHOUT_HUMAN:
            if decision is not None:
                raise AuthorizationPermitError(
                    "Machine policy authorization cannot contain a human decision."
                )
            if (
                request.policy_artifact_id is None
                or request.policy_artifact_version is None
                or request.policy_input_hash is None
                or not request.policy_coverage_ids
            ):
                raise AuthorizationPermitError(
                    "Machine authorization lacks exact policy artifact lineage."
                )
            authorized_by = "GOVERNANCE_POLICY"
            authorized_at = request.created_at
            identity = {
                "status": request.status.value,
                "policy_artifact_id": request.policy_artifact_id,
                "policy_artifact_version": request.policy_artifact_version,
                "policy_input_hash": request.policy_input_hash,
                "policy_coverage_ids": list(request.policy_coverage_ids),
            }
        else:
            raise AuthorizationPermitError("Approval request is not authorized.")
        if request.workflow_run_id != workflow_run_id:
            raise AuthorizationPermitError("Approval request belongs to another run.")
        if request.evaluation_case_id != evaluation_case_id:
            raise AuthorizationPermitError("Approval request belongs to another case.")
        if request.subject_artifact_id != expected_subject_artifact_id:
            raise AuthorizationPermitError("Approval subject artifact does not match.")

        command = request.command
        if command.action_type is not ProtectedAction.SUBMIT_BANKING_PRECHECK:
            raise AuthorizationPermitError("Approval protects another action.")
        if command.evaluation_case_id != evaluation_case_id:
            raise AuthorizationPermitError("Approval command belongs to another case.")
        if command.payload_artifact_id != expected_subject_artifact_id:
            raise AuthorizationPermitError("Approval command references another subject.")
        return authorized_by, authorized_at, identity

    async def _require_exact_subject(
        self,
        subject: ArtifactEnvelope,
        *,
        request: ApprovalRequest,
        evaluation_case_id: str,
    ) -> None:
        if subject.artifact_id != request.subject_artifact_id:
            raise AuthorizationPermitError("Repository returned another subject artifact.")
        if subject.evaluation_case_id != evaluation_case_id:
            raise AuthorizationPermitError("Approved subject belongs to another case.")
        if subject.artifact_type is not ArtifactType.BANKING_PRECHECK_SUBMISSION_PROPOSAL:
            raise AuthorizationPermitError("Approved subject is not a precheck proposal.")
        if subject.validation_status not in _VALID_ARTIFACT_STATUSES:
            raise AuthorizationPermitError("Approved subject is not validated.")
        if (
            subject.version != request.subject_artifact_version
            or subject.input_hash != request.subject_input_hash
        ):
            raise AuthorizationPermitError(
                "Approved subject version or business input hash has changed."
            )

        case_artifacts = await self._artifacts.list_by_case(evaluation_case_id)
        same_type = tuple(
            artifact
            for artifact in case_artifacts
            if artifact.artifact_type is subject.artifact_type
        )
        latest_version = max((artifact.version for artifact in same_type), default=None)
        latest = tuple(
            artifact
            for artifact in same_type
            if artifact.version == latest_version
        )
        if (
            len(latest) != 1
            or latest[0].artifact_id != subject.artifact_id
            or latest[0] != subject
        ):
            raise AuthorizationPermitError(
                "Approved subject is stale or the latest version is ambiguous."
            )

        try:
            proposal = BankingPrecheckSubmissionProposal.model_validate(subject.payload)
        except ValueError as exc:
            raise AuthorizationPermitError(
                "Approved subject has an invalid proposal payload."
            ) from exc
        if proposal.evaluation_case_id != evaluation_case_id:
            raise AuthorizationPermitError("Proposal payload belongs to another case.")
        if (
            proposal.proposed_action is not ProtectedAction.SUBMIT_BANKING_PRECHECK
            or proposal.precheck_executed
            or proposal.submission_executed
        ):
            raise AuthorizationPermitError(
                "Proposal is not an unexecuted protected-action subject."
            )
        if request.command.payload != banking_precheck_action_payload(proposal):
            raise AuthorizationPermitError(
                "Authorization command payload is not the exact precheck policy scope."
            )

    async def _require_policy_scope(
        self,
        request: ApprovalRequest,
        subject: ArtifactEnvelope,
        *,
        require_current_policy: bool,
    ) -> None:
        """Verify human or machine authority against one exact policy artifact."""
        policy_artifact_id = request.policy_artifact_id
        if policy_artifact_id is None:
            raise AuthorizationPermitError("Authorization has no policy artifact.")
        policy_artifact = await self._artifacts.get(policy_artifact_id)
        if policy_artifact is None:
            raise AuthorizationPermitError("Authorization policy artifact does not exist.")
        if (
            policy_artifact.artifact_type is not ArtifactType.APPROVAL_CHECKPOINTS
            or policy_artifact.validation_status not in _VALID_ARTIFACT_STATUSES
            or policy_artifact.evaluation_case_id != request.evaluation_case_id
            or policy_artifact.version != request.policy_artifact_version
            or policy_artifact.input_hash != request.policy_input_hash
        ):
            raise AuthorizationPermitError(
                "Authorization policy artifact identity or validation is invalid."
            )
        case_artifacts = await self._artifacts.list_by_case(
            request.evaluation_case_id
        )
        try:
            checkpoint_set = ApprovalCheckpointSet.model_validate(policy_artifact.payload)
        except ValueError as exc:
            raise AuthorizationPermitError(
                "Authorization policy artifact payload is invalid."
            ) from exc
        latest_policy = max(
            (
                item
                for item in case_artifacts
                if item.artifact_type is ArtifactType.APPROVAL_CHECKPOINTS
            ),
            key=lambda item: item.version,
            default=None,
        )
        if require_current_policy and (
            latest_policy is None
            or latest_policy.validation_status not in _VALID_ARTIFACT_STATUSES
        ):
            raise AuthorizationPermitError(
                "Authorization policy artifact is no longer current."
            )
        if (
            require_current_policy
            and latest_policy is not None
            and latest_policy.artifact_id != policy_artifact.artifact_id
        ):
            try:
                current_checkpoint_set = ApprovalCheckpointSet.model_validate(
                    latest_policy.payload
                )
            except ValueError as exc:
                raise AuthorizationPermitError(
                    "Authorization policy artifact is no longer current."
                ) from exc
            if not approval_policy_scope_is_preserved(
                request=request,
                bound_registry=checkpoint_set,
                current_registry=current_checkpoint_set,
            ):
                raise AuthorizationPermitError(
                    "Authorization policy artifact is no longer current."
                )
        selected_coverages = tuple(
            coverage
            for coverage in checkpoint_set.policy_coverages
            if coverage.coverage_id in request.policy_coverage_ids
        )
        if (
            len(selected_coverages) != len(request.policy_coverage_ids)
            or {item.coverage_id for item in selected_coverages}
            != set(request.policy_coverage_ids)
            or any(
                item.protected_action is not ProtectedAction.SUBMIT_BANKING_PRECHECK
                or item.subject_artifact_id != subject.artifact_id
                for item in selected_coverages
            )
        ):
            raise AuthorizationPermitError(
                "Authorization is not covered by the exact proposal policy."
            )
        evaluation = ApprovalGate().evaluate(request.command, checkpoint_set)
        if request.status is ApprovalRequestStatus.AUTHORIZED_WITHOUT_HUMAN:
            if (
                any(item.requires_human_approval for item in selected_coverages)
                or evaluation.status is not ApprovalGateStatus.AUTHORIZED
            ):
                raise AuthorizationPermitError(
                    "Machine authorization is not covered by explicit no-human policy."
                )
            return
        if request.status is not ApprovalRequestStatus.APPROVED:
            raise AuthorizationPermitError("Authorization is not approved.")
        triggered_ids = tuple(
            item.checkpoint_id for item in evaluation.triggered_checkpoints
        )
        if (
            evaluation.status is not ApprovalGateStatus.WAITING_FOR_APPROVAL
            or triggered_ids != request.checkpoint_ids
        ):
            raise AuthorizationPermitError(
                "Human approval is not bound to the currently triggered checkpoints."
            )
