"""Side-effect-free intake for immutable Banking amount supplements."""

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from opc_mis.domain.artifacts import ArtifactDraft, ArtifactEnvelope
from opc_mis.domain.banking_input_models import (
    BankingAmountInputCommand,
    BankingAmountInputSubmission,
    BankingInputComponentResult,
)
from opc_mis.domain.banking_models import BankingInputSupplement
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.decision_post_banking_models import DecisionPostBankingReview
from opc_mis.domain.enums import (
    ArtifactType,
    ComponentStatus,
    DecisionPostBankingOutcome,
    MissingRequestStatus,
    SourceType,
    ValidationStatus,
)
from opc_mis.domain.events import RuntimeEvent
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.lineage import deterministic_id
from opc_mis.domain.planner_models import EvaluationCase
from opc_mis.domain.serialization import json_safe
from opc_mis.ports.artifact_repository import ArtifactRepository

_ALLOWED_TYPES = {
    ArtifactType.EVALUATION_CASE,
    ArtifactType.DECISION_POST_BANKING_REVIEW,
    ArtifactType.BANKING_INPUT_SUPPLEMENT,
}
_VALID_STATUSES = {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}
_AMOUNT_REQUIRED_FIELD = "requested_amount"
_AMOUNT_REQUEST_FIELD = "requested_amount"
_AMOUNT_REQUIREMENT_CODE = "BANKING_PRECHECK_AMOUNT_REQUIRED"


class BankingInputContextError(ValueError):
    """Raised for inconsistent, stale, or unauthorized Banking intake inputs."""


@dataclass(frozen=True)
class _BankingInputContext:
    evaluation_case_artifact: ArtifactEnvelope
    review_artifact: ArtifactEnvelope
    current_supplement_artifact: ArtifactEnvelope | None
    evaluation_case: EvaluationCase
    review: DecisionPostBankingReview
    current_supplement: BankingInputSupplement | None


class BankingAmountInputIntake:
    """Validate human amount input and return one artifact draft without persisting it."""

    component_id = "BANKING_AMOUNT_INPUT_INTAKE"

    def __init__(self, *, artifacts: ArtifactRepository) -> None:
        self._artifacts = artifacts

    async def execute(
        self, context: ExecutionContext
    ) -> BankingInputComponentResult:
        """Build or reuse the semantic payload for one immutable supplement revision."""
        try:
            command = BankingAmountInputCommand.model_validate(context.component_input)
            intake_context = await self._load_context(context)
            self._validate_command(context, command, intake_context.review)
            supplement, evidence_refs, reused = self._supplement(
                context=context,
                command=command,
                intake_context=intake_context,
            )
        except (ValidationError, BankingInputContextError) as exc:
            return self._failed_safe(str(exc))

        draft = ArtifactDraft(
            artifact_type=ArtifactType.BANKING_INPUT_SUPPLEMENT,
            evaluation_case_id=supplement.evaluation_case_id,
            producer=self.component_id,
            payload=supplement.model_dump(mode="json"),
            evidence_refs=evidence_refs,
            identity_inputs={
                "evaluation_case_id": supplement.evaluation_case_id,
                "review_id": intake_context.review.review_id,
                "banking_request_id": supplement.banking_request_id,
                "previous_supplement_artifact_id": (
                    intake_context.current_supplement_artifact.artifact_id
                    if intake_context.current_supplement_artifact is not None
                    else None
                ),
                "requested_amount": supplement.requested_amount,
                "requested_amount_currency": supplement.requested_amount_currency,
                "provider": supplement.provider,
                "note": supplement.note,
                "resolved_request_ids": supplement.resolved_request_ids,
                "source_artifact_ids": supplement.source_artifact_ids,
                "evidence_ids": supplement.evidence_ids,
            },
        )
        return BankingInputComponentResult(
            status=ComponentStatus.COMPLETED,
            supplement=supplement,
            artifacts=(draft,),
            runtime_events=(
                RuntimeEvent(
                    event_type=(
                        "BANKING_INPUT_SUPPLEMENT_REUSED"
                        if reused
                        else "BANKING_INPUT_SUPPLEMENT_PREPARED"
                    ),
                    message=(
                        "The current immutable Banking amount input was reused."
                        if reused
                        else "A new immutable Banking amount input draft was prepared."
                    ),
                    metadata={
                        "supplement_id": supplement.supplement_id,
                        "is_revision": (
                            intake_context.current_supplement_artifact is not None
                            and not reused
                        ),
                    },
                ),
            ),
        )

    async def _load_context(self, context: ExecutionContext) -> _BankingInputContext:
        if context.evaluation_case_id is None:
            raise BankingInputContextError(
                "Banking amount input requires evaluation_case_id."
            )
        supplied: list[ArtifactEnvelope] = []
        for artifact_id in context.input_artifact_ids:
            artifact = await self._artifacts.get(artifact_id)
            if artifact is None:
                raise BankingInputContextError(
                    f"Banking amount input received an unknown artifact: {artifact_id}."
                )
            if artifact.validation_status not in _VALID_STATUSES:
                raise BankingInputContextError(
                    f"Banking amount input received an unvalidated artifact: {artifact_id}."
                )
            if artifact.artifact_type not in _ALLOWED_TYPES:
                raise BankingInputContextError(
                    "Banking amount input received an unexpected artifact type: "
                    f"{artifact.artifact_type.value}."
                )
            if artifact.evaluation_case_id != context.evaluation_case_id:
                raise BankingInputContextError(
                    "A Banking amount-input artifact belongs to another case."
                )
            supplied.append(artifact)

        case_artifact = self._exactly_one(supplied, ArtifactType.EVALUATION_CASE)
        review_artifact = self._exactly_one(
            supplied, ArtifactType.DECISION_POST_BANKING_REVIEW
        )
        supplements = tuple(
            item
            for item in supplied
            if item.artifact_type is ArtifactType.BANKING_INPUT_SUPPLEMENT
        )
        if len(supplements) > 1:
            raise BankingInputContextError(
                "Banking amount input accepts at most one current supplement."
            )
        current_artifact = supplements[0] if supplements else None

        all_case_artifacts = await self._artifacts.list_by_case(
            context.evaluation_case_id
        )
        latest_case = self._latest(all_case_artifacts, ArtifactType.EVALUATION_CASE)
        latest_review = self._latest(
            all_case_artifacts, ArtifactType.DECISION_POST_BANKING_REVIEW
        )
        latest_supplement = self._latest(
            all_case_artifacts, ArtifactType.BANKING_INPUT_SUPPLEMENT
        )
        expected_ids = (
            latest_case.artifact_id if latest_case is not None else None,
            latest_review.artifact_id if latest_review is not None else None,
            latest_supplement.artifact_id if latest_supplement is not None else None,
        )
        supplied_ids = (
            case_artifact.artifact_id,
            review_artifact.artifact_id,
            current_artifact.artifact_id if current_artifact is not None else None,
        )
        if supplied_ids != expected_ids:
            raise BankingInputContextError(
                "Banking amount input requires the current case, review, and supplement."
            )
        expected_order = tuple(item for item in supplied_ids if item is not None)
        if context.input_artifact_ids != expected_order:
            raise BankingInputContextError(
                "Banking amount-input artifacts must use stable semantic order."
            )

        try:
            evaluation_case = EvaluationCase.model_validate(case_artifact.payload)
            review = DecisionPostBankingReview.model_validate(review_artifact.payload)
            current = (
                BankingInputSupplement.model_validate(current_artifact.payload)
                if current_artifact is not None
                else None
            )
        except ValidationError as exc:
            raise BankingInputContextError(
                f"Invalid Banking amount-input context: {exc}"
            ) from exc

        expected_identity = (
            context.evaluation_case_id,
            context.dataset_id,
            evaluation_case.contract_id,
        )
        if (
            evaluation_case.evaluation_case_id,
            evaluation_case.dataset_id,
            evaluation_case.contract_id,
        ) != expected_identity:
            raise BankingInputContextError(
                "EvaluationCase identity does not match the Banking amount input."
            )
        if (review.evaluation_case_id, review.dataset_id, review.contract_id) != (
            expected_identity
        ):
            raise BankingInputContextError(
                "Decision post-Banking review identity does not match EvaluationCase."
            )
        if current is not None and (
            current.evaluation_case_id,
            current.dataset_id,
            current.contract_id,
        ) != expected_identity:
            raise BankingInputContextError(
                "Current Banking input supplement identity does not match EvaluationCase."
            )
        if current is not None and (
            current.banking_request_id != review.banking_request_id
        ):
            raise BankingInputContextError(
                "Current Banking input supplement belongs to another Banking request."
            )
        return _BankingInputContext(
            evaluation_case_artifact=case_artifact,
            review_artifact=review_artifact,
            current_supplement_artifact=current_artifact,
            evaluation_case=evaluation_case,
            review=review,
            current_supplement=current,
        )

    @staticmethod
    def _validate_command(
        context: ExecutionContext,
        command: BankingAmountInputCommand,
        review: DecisionPostBankingReview,
    ) -> None:
        submission = command.submission
        if submission.workflow_run_id != context.workflow_run_id:
            raise BankingInputContextError(
                "Submission workflow_run_id does not match the execution context."
            )
        if submission.missing_request_id != command.allowed_pending_request_id:
            raise BankingInputContextError(
                "Submission does not resolve the currently allowed pending request."
            )
        if review.outcome is not DecisionPostBankingOutcome.BANKING_INPUT_REQUIRED:
            raise BankingInputContextError(
                "Decision post-Banking review is not waiting for Banking input."
            )
        if _AMOUNT_REQUIRED_FIELD not in review.required_input_fields:
            raise BankingInputContextError(
                "Decision post-Banking review does not require the amount field."
            )
        matching_requests = tuple(
            request
            for request in review.missing_data_requests
            if request.request_id == submission.missing_request_id
        )
        if len(matching_requests) != 1:
            raise BankingInputContextError(
                "Submitted missing_request_id is not present exactly once in the "
                "Decision post-Banking review."
            )
        request = matching_requests[0]
        if request.status is not MissingRequestStatus.OPEN:
            raise BankingInputContextError(
                "Submitted Banking amount request is not open."
            )
        if request.evaluation_case_id != context.evaluation_case_id:
            raise BankingInputContextError(
                "Submitted Banking amount request belongs to another case."
            )
        if (
            request.requirement_code != _AMOUNT_REQUIREMENT_CODE
            or request.field != _AMOUNT_REQUEST_FIELD
            or request.target_record != review.banking_request_id
        ):
            raise BankingInputContextError(
                "Submitted request is not the explicit Banking requested-amount request."
            )

    def _supplement(
        self,
        *,
        context: ExecutionContext,
        command: BankingAmountInputCommand,
        intake_context: _BankingInputContext,
    ) -> tuple[BankingInputSupplement, tuple[EvidenceRef, ...], bool]:
        submission = command.submission
        current = intake_context.current_supplement
        current_artifact = intake_context.current_supplement_artifact
        if current is not None and self._same_submission(current, submission):
            if current_artifact is None:  # pragma: no cover - paired context invariant
                raise BankingInputContextError("Current supplement envelope is missing.")
            return current, current_artifact.evidence_refs, True

        supplement_id = deterministic_id(
            "BIS",
            context.evaluation_case_id,
            intake_context.review.review_id,
            intake_context.review.banking_request_id,
            current_artifact.artifact_id if current_artifact is not None else None,
            submission.requested_amount,
            submission.requested_amount_currency,
            submission.provided_by,
            submission.evidence_note,
            submission.missing_request_id,
        )
        values: tuple[tuple[str, Any], ...] = (
            ("requested_amount", submission.requested_amount),
            ("requested_amount_currency", submission.requested_amount_currency.value),
            ("provider", submission.provided_by),
            ("note", submission.evidence_note),
            ("resolved_request_id", submission.missing_request_id),
        )
        evidence_refs = tuple(
            self._user_evidence(
                dataset_id=context.dataset_id,
                supplement_id=supplement_id,
                field=field,
                value=value,
            )
            for field, value in values
        )
        supplement = BankingInputSupplement(
            supplement_id=supplement_id,
            evaluation_case_id=intake_context.evaluation_case.evaluation_case_id,
            dataset_id=intake_context.evaluation_case.dataset_id,
            contract_id=intake_context.evaluation_case.contract_id,
            banking_request_id=intake_context.review.banking_request_id,
            requested_amount=submission.requested_amount,
            requested_amount_currency=submission.requested_amount_currency,
            provider=submission.provided_by,
            note=submission.evidence_note,
            resolved_request_ids=(submission.missing_request_id,),
            source_artifact_ids=(
                intake_context.evaluation_case_artifact.artifact_id,
                intake_context.review_artifact.artifact_id,
                *(
                    (current_artifact.artifact_id,)
                    if current_artifact is not None
                    else ()
                ),
            ),
            evidence_ids=tuple(item.evidence_id for item in evidence_refs),
        )
        return supplement, evidence_refs, False

    @staticmethod
    def _same_submission(
        current: BankingInputSupplement,
        submission: BankingAmountInputSubmission,
    ) -> bool:
        return (
            current.requested_amount == submission.requested_amount
            and current.requested_amount_currency
            is submission.requested_amount_currency
            and current.provider == submission.provided_by
            and current.note == submission.evidence_note
            and current.resolved_request_ids == (submission.missing_request_id,)
        )

    @staticmethod
    def _user_evidence(
        *,
        dataset_id: str,
        supplement_id: str,
        field: str,
        value: Any,
    ) -> EvidenceRef:
        display = json_safe(value)
        return EvidenceRef(
            evidence_id=deterministic_id(
                "EVD",
                dataset_id,
                SourceType.USER_INPUT,
                supplement_id,
                field,
                display,
            ),
            source_type=SourceType.USER_INPUT,
            sheet="BANKING_INPUT_SUPPLEMENT",
            row_number=0,
            record_id=supplement_id,
            field=field,
            display_value=display,
        )

    @staticmethod
    def _exactly_one(
        artifacts: list[ArtifactEnvelope], artifact_type: ArtifactType
    ) -> ArtifactEnvelope:
        matches = tuple(
            item for item in artifacts if item.artifact_type is artifact_type
        )
        if len(matches) != 1:
            raise BankingInputContextError(
                "Banking amount input requires exactly one validated "
                f"{artifact_type.value} artifact."
            )
        return matches[0]

    @staticmethod
    def _latest(
        artifacts: tuple[ArtifactEnvelope, ...], artifact_type: ArtifactType
    ) -> ArtifactEnvelope | None:
        return max(
            (item for item in artifacts if item.artifact_type is artifact_type),
            key=lambda item: item.version,
            default=None,
        )

    @classmethod
    def _failed_safe(cls, message: str) -> BankingInputComponentResult:
        return BankingInputComponentResult(
            status=ComponentStatus.FAILED_SAFE,
            runtime_events=(
                RuntimeEvent(
                    event_type="BANKING_INPUT_INTAKE_FAILED_SAFE",
                    message=message,
                ),
            ),
        )
