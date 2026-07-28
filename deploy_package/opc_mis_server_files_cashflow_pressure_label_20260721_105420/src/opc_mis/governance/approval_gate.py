"""Pure deterministic gate for case-scoped protected actions."""

from dataclasses import dataclass
from numbers import Real

from opc_mis.domain.approvals import (
    ApprovalCheckpoint,
    ApprovalCheckpointSet,
    ApprovalPolicyCoverage,
)
from opc_mis.domain.commands import ActionCommand
from opc_mis.domain.enums import ApprovalGateStatus, ProtectedAction, RuleOperator


@dataclass(frozen=True)
class ApprovalGateEvaluation:
    """Internal policy result consumed by workflow orchestration."""

    status: ApprovalGateStatus
    triggered_checkpoints: tuple[ApprovalCheckpoint, ...] = ()
    missing_fields: tuple[str, ...] = ()
    reason: str = ""


class ApprovalGate:
    """Evaluate only registered conditions; never execute the protected action."""

    def evaluate(
        self,
        command: ActionCommand,
        checkpoint_set: ApprovalCheckpointSet,
    ) -> ApprovalGateEvaluation:
        """Return authorization, missing input, or a human-approval requirement."""
        if checkpoint_set.evaluation_case_id != command.evaluation_case_id:
            return ApprovalGateEvaluation(
                status=ApprovalGateStatus.WAITING_FOR_INPUT,
                reason="Approval policy registry belongs to another evaluation case.",
            )
        matches = tuple(
            checkpoint
            for checkpoint in checkpoint_set.checkpoints
            if checkpoint.protected_action is command.action_type
        )
        coverages = tuple(
            coverage
            for coverage in checkpoint_set.policy_coverages
            if coverage.protected_action is command.action_type
        )
        if command.action_type is ProtectedAction.SUBMIT_BANKING_PRECHECK:
            coverage_error = self._precheck_coverage_error(
                command=command,
                coverages=coverages,
                checkpoints=matches,
            )
            if coverage_error is not None:
                missing_fields, reason = coverage_error
                return ApprovalGateEvaluation(
                    status=ApprovalGateStatus.WAITING_FOR_INPUT,
                    missing_fields=missing_fields,
                    reason=reason,
                )
        if not matches and not coverages:
            return ApprovalGateEvaluation(
                status=ApprovalGateStatus.WAITING_FOR_INPUT,
                reason=(
                    "No valid policy coverage or checkpoint exists for this "
                    "protected action."
                ),
            )

        missing = tuple(
            sorted(
                {
                    checkpoint.condition.source_field
                    for checkpoint in matches
                    if checkpoint.condition.source_field not in command.payload
                }
            )
        )
        if missing:
            return ApprovalGateEvaluation(
                status=ApprovalGateStatus.WAITING_FOR_INPUT,
                missing_fields=missing,
                reason="The protected-action payload is missing checkpoint input.",
            )

        invalid = tuple(
            sorted(
                {
                    checkpoint.condition.source_field
                    for checkpoint in matches
                    if not self._compatible_value(
                        command.payload[checkpoint.condition.source_field],
                        checkpoint.condition.threshold,
                    )
                }
            )
        )
        if invalid:
            return ApprovalGateEvaluation(
                status=ApprovalGateStatus.WAITING_FOR_INPUT,
                missing_fields=invalid,
                reason="The protected-action payload contains an invalid checkpoint value.",
            )

        triggered = tuple(
            checkpoint
            for checkpoint in matches
            if self._compare(
                command.payload[checkpoint.condition.source_field],
                checkpoint.condition.operator,
                checkpoint.condition.threshold,
            )
        )
        if triggered:
            return ApprovalGateEvaluation(
                status=ApprovalGateStatus.WAITING_FOR_APPROVAL,
                triggered_checkpoints=triggered,
                reason="One or more registered approval checkpoints were triggered.",
            )
        return ApprovalGateEvaluation(
            status=ApprovalGateStatus.AUTHORIZED,
            reason=(
                "Registered policy coverage is valid and no checkpoint condition "
                "was triggered."
            ),
        )

    @staticmethod
    def _precheck_coverage_error(
        *,
        command: ActionCommand,
        coverages: tuple[ApprovalPolicyCoverage, ...],
        checkpoints: tuple[ApprovalCheckpoint, ...],
    ) -> tuple[tuple[str, ...], str] | None:
        """Require exact proposal/API coverage before evaluating precheck conditions."""
        if not coverages:
            return (), "Banking precheck has no evaluated API approval policy coverage."
        if any(
            coverage.subject_artifact_id != command.payload_artifact_id
            or coverage.evaluation_case_id != command.evaluation_case_id
            for coverage in coverages
        ):
            return (), "Banking precheck policy coverage does not match this proposal."
        raw_api_ids = command.payload.get("api_ids")
        if (
            not isinstance(raw_api_ids, (list, tuple))
            or not raw_api_ids
            or any(not isinstance(item, str) or not item for item in raw_api_ids)
            or len(set(raw_api_ids)) != len(raw_api_ids)
        ):
            return ("api_ids",), "Banking precheck API policy scope is missing or invalid."
        expected_api_ids = tuple(
            dict.fromkeys(
                api_id for coverage in coverages for api_id in coverage.api_ids
            )
        )
        if tuple(raw_api_ids) != expected_api_ids:
            return ("api_ids",), "Banking precheck API policy scope is incomplete."
        checkpoint_coverage_ids = {
            coverage_id
            for checkpoint in checkpoints
            if checkpoint.approval_type == "BANKING_PRECHECK_API_POLICY"
            for coverage_id in checkpoint.policy_coverage_ids
        }
        missing_required = tuple(
            coverage.coverage_id
            for coverage in coverages
            if coverage.requires_human_approval
            and coverage.coverage_id not in checkpoint_coverage_ids
        )
        if missing_required:
            return (), "A human-approval API policy has no registered checkpoint."
        return None

    @staticmethod
    def _compatible_value(actual: object, threshold: object) -> bool:
        if isinstance(threshold, bool):
            return isinstance(actual, bool)
        if isinstance(threshold, Real):
            return isinstance(actual, Real) and not isinstance(actual, bool)
        return isinstance(actual, str)

    @staticmethod
    def _compare(actual: object, operator: RuleOperator, threshold: object) -> bool:
        if operator is RuleOperator.EQUAL:
            return actual == threshold
        if isinstance(actual, bool) or isinstance(threshold, bool):
            return False
        if not isinstance(actual, Real) or not isinstance(threshold, Real):
            return False
        if operator is RuleOperator.GREATER_THAN:
            return actual > threshold
        if operator is RuleOperator.GREATER_THAN_OR_EQUAL:
            return actual >= threshold
        if operator is RuleOperator.LESS_THAN:
            return actual < threshold
        return actual <= threshold
