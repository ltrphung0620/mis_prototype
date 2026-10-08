"""Side-effect-free intake for post-precheck evidence references."""

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from opc_mis.domain.artifacts import ArtifactDraft, ArtifactEnvelope
from opc_mis.domain.banking_precheck_evidence_models import (
    BankingPrecheckEvidenceCommand,
    BankingPrecheckEvidenceComponentResult,
    BankingPrecheckEvidenceSubmission,
    BankingPrecheckEvidenceSupplement,
)
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.decision_post_precheck_models import (
    DecisionPostPrecheckOptionReview,
    DecisionPostPrecheckReview,
)
from opc_mis.domain.enums import (
    ArtifactType,
    BankingPrecheckOutcome,
    ComponentStatus,
    DecisionPostPrecheckOutcome,
    MissingRequestStatus,
    SourceType,
    ValidationStatus,
)
from opc_mis.domain.events import RuntimeEvent
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.lineage import deterministic_id
from opc_mis.domain.missing_data import MissingDataRequest
from opc_mis.domain.serialization import json_safe
from opc_mis.ports.artifact_repository import ArtifactRepository

_ALLOWED_TYPES = {
    ArtifactType.DECISION_POST_PRECHECK_REVIEW,
    ArtifactType.BANKING_PRECHECK_EVIDENCE_SUPPLEMENT,
}
_VALID_STATUSES = {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}
_REQUIREMENT_CODE = "BANKING_PRECHECK_FOLLOW_UP_EVIDENCE_REQUIRED"
_EVIDENCE_SHEET = "BANKING_PRECHECK_EVIDENCE_SUPPLEMENT"


class BankingPrecheckEvidenceContextError(ValueError):
    """Raised for stale, ambiguous, or out-of-bound evidence input."""


@dataclass(frozen=True)
class _EvidenceInputContext:
    review_artifact: ArtifactEnvelope
    review: DecisionPostPrecheckReview
    request: MissingDataRequest
    option_review: DecisionPostPrecheckOptionReview
    current_artifact: ArtifactEnvelope | None
    current: BankingPrecheckEvidenceSupplement | None


class BankingPrecheckEvidenceIntake:
    """Accept one evidence reference without changing a provider outcome."""

    component_id = "DECISION_POST_PRECHECK_EVIDENCE_INTAKE"

    def __init__(self, *, artifacts: ArtifactRepository) -> None:
        self._artifacts = artifacts

    async def execute(
        self, context: ExecutionContext
    ) -> BankingPrecheckEvidenceComponentResult:
        """Build or reuse one immutable evidence-reference supplement draft."""
        try:
            command = BankingPrecheckEvidenceCommand.model_validate(
                context.component_input
            )
            intake_context = await self._load_context(context, command)
            self._validate_command(context, command, intake_context)
            supplement, evidence_refs, reused = self._supplement(
                context=context,
                command=command,
                intake_context=intake_context,
            )
        except (ValidationError, BankingPrecheckEvidenceContextError) as exc:
            return self._failed_safe(str(exc))

        draft = ArtifactDraft(
            artifact_type=ArtifactType.BANKING_PRECHECK_EVIDENCE_SUPPLEMENT,
            evaluation_case_id=supplement.evaluation_case_id,
            producer=self.component_id,
            payload=supplement.model_dump(mode="json"),
            evidence_refs=evidence_refs,
            identity_inputs={
                "evaluation_case_id": supplement.evaluation_case_id,
                "source_review_artifact_id": supplement.source_review_artifact_id,
                "source_review_id": supplement.source_review_id,
                "source_result_set_artifact_id": (
                    supplement.source_result_set_artifact_id
                ),
                "source_result_set_id": supplement.source_result_set_id,
                "normalized_result_id": supplement.normalized_result_id,
                "option_id": supplement.option_id,
                "bank_product_id": supplement.bank_product_id,
                "required_field": supplement.required_field,
                "missing_request_id": supplement.missing_request_id,
                "evidence_reference_id": supplement.evidence_reference_id,
                "provided_by": supplement.provided_by,
                "evidence_note": supplement.evidence_note,
                "previous_supplement_artifact_id": (
                    supplement.previous_supplement_artifact_id
                ),
                "source_artifact_ids": supplement.source_artifact_ids,
                "evidence_ids": supplement.evidence_ids,
                "fresh_governed_precheck_required": True,
            },
        )
        return BankingPrecheckEvidenceComponentResult(
            status=ComponentStatus.COMPLETED,
            supplement=supplement,
            artifacts=(draft,),
            runtime_events=(
                RuntimeEvent(
                    event_type=(
                        "BANKING_PRECHECK_EVIDENCE_SUPPLEMENT_REUSED"
                        if reused
                        else "BANKING_PRECHECK_EVIDENCE_REFERENCE_ACCEPTED"
                    ),
                    message=(
                        "The current evidence-reference handoff was reused; the "
                        "provider result remains unchanged and a fresh governed "
                        "precheck is still required."
                        if reused
                        else "A staff evidence reference was accepted for the exact "
                        "missing-data request. The provider result remains unchanged "
                        "and a fresh governed precheck is required."
                    ),
                    metadata={
                        "supplement_id": supplement.supplement_id,
                        "missing_request_id": supplement.missing_request_id,
                        "required_field": supplement.required_field,
                        "fresh_governed_precheck_required": True,
                        "source_precheck_result_unchanged": True,
                        "bank_approval_obtained": False,
                    },
                ),
            ),
        )

    async def _load_context(
        self,
        context: ExecutionContext,
        command: BankingPrecheckEvidenceCommand,
    ) -> _EvidenceInputContext:
        if context.evaluation_case_id is None:
            raise BankingPrecheckEvidenceContextError(
                "Post-precheck evidence intake requires evaluation_case_id."
            )
        supplied: list[ArtifactEnvelope] = []
        for artifact_id in context.input_artifact_ids:
            artifact = await self._artifacts.get(artifact_id)
            if artifact is None:
                raise BankingPrecheckEvidenceContextError(
                    f"Evidence intake received an unknown artifact: {artifact_id}."
                )
            if artifact.validation_status not in _VALID_STATUSES:
                raise BankingPrecheckEvidenceContextError(
                    f"Evidence intake received an unvalidated artifact: {artifact_id}."
                )
            if artifact.artifact_type not in _ALLOWED_TYPES:
                raise BankingPrecheckEvidenceContextError(
                    "Evidence intake received an unexpected artifact type: "
                    f"{artifact.artifact_type.value}."
                )
            if artifact.evaluation_case_id != context.evaluation_case_id:
                raise BankingPrecheckEvidenceContextError(
                    "A post-precheck evidence artifact belongs to another case."
                )
            supplied.append(artifact)

        review_artifact = self._exactly_one(
            supplied, ArtifactType.DECISION_POST_PRECHECK_REVIEW
        )
        supplied_supplements = tuple(
            item
            for item in supplied
            if item.artifact_type
            is ArtifactType.BANKING_PRECHECK_EVIDENCE_SUPPLEMENT
        )
        if len(supplied_supplements) > 1:
            raise BankingPrecheckEvidenceContextError(
                "Evidence intake accepts at most one current supplement revision."
            )
        current_artifact = supplied_supplements[0] if supplied_supplements else None

        try:
            review = DecisionPostPrecheckReview.model_validate(review_artifact.payload)
            current = (
                BankingPrecheckEvidenceSupplement.model_validate(
                    current_artifact.payload
                )
                if current_artifact is not None
                else None
            )
        except ValidationError as exc:
            raise BankingPrecheckEvidenceContextError(
                f"Invalid post-precheck evidence context: {exc}"
            ) from exc

        all_case_artifacts = await self._artifacts.list_by_case(
            context.evaluation_case_id
        )
        latest_review = self._latest_review(all_case_artifacts)
        if latest_review is None or latest_review.artifact_id != review_artifact.artifact_id:
            raise BankingPrecheckEvidenceContextError(
                "Evidence intake requires the current Decision post-precheck review."
            )
        expected_current = self._latest_supplement_for_request(
            all_case_artifacts,
            command.submission.missing_request_id,
        )
        expected_current_id = (
            expected_current.artifact_id if expected_current is not None else None
        )
        supplied_current_id = (
            current_artifact.artifact_id if current_artifact is not None else None
        )
        if supplied_current_id != expected_current_id:
            raise BankingPrecheckEvidenceContextError(
                "Evidence intake requires the current supplement for this exact request."
            )
        expected_order = (
            review_artifact.artifact_id,
            *((expected_current_id,) if expected_current_id is not None else ()),
        )
        if context.input_artifact_ids != expected_order:
            raise BankingPrecheckEvidenceContextError(
                "Evidence-intake artifacts must use stable review then revision order."
            )
        if (
            review.evaluation_case_id,
            review.dataset_id,
        ) != (context.evaluation_case_id, context.dataset_id):
            raise BankingPrecheckEvidenceContextError(
                "Post-precheck review identity does not match evidence intake."
            )
        if current is not None and (
            current.evaluation_case_id,
            current.dataset_id,
            current.contract_id,
            current.source_review_artifact_id,
            current.source_review_id,
            current.missing_request_id,
        ) != (
            review.evaluation_case_id,
            review.dataset_id,
            review.contract_id,
            review_artifact.artifact_id,
            review.review_id,
            command.submission.missing_request_id,
        ):
            raise BankingPrecheckEvidenceContextError(
                "Current evidence supplement does not match the exact review request."
            )

        request = self._request(review, command.submission.missing_request_id)
        option_review = self._option_review(review, request.target_record)
        return _EvidenceInputContext(
            review_artifact=review_artifact,
            review=review,
            request=request,
            option_review=option_review,
            current_artifact=current_artifact,
            current=current,
        )

    @staticmethod
    def _validate_command(
        context: ExecutionContext,
        command: BankingPrecheckEvidenceCommand,
        intake_context: _EvidenceInputContext,
    ) -> None:
        submission = command.submission
        request = intake_context.request
        option = intake_context.option_review
        review = intake_context.review
        if submission.workflow_run_id != context.workflow_run_id:
            raise BankingPrecheckEvidenceContextError(
                "Submission workflow_run_id does not match the execution context."
            )
        if submission.missing_request_id != command.allowed_pending_request_id:
            raise BankingPrecheckEvidenceContextError(
                "Submission does not resolve the currently allowed pending request."
            )
        if review.outcome is not DecisionPostPrecheckOutcome.FOLLOW_UP_EVIDENCE_REQUIRED:
            raise BankingPrecheckEvidenceContextError(
                "Decision post-precheck review is not waiting for follow-up evidence."
            )
        if request.status is not MissingRequestStatus.OPEN:
            raise BankingPrecheckEvidenceContextError(
                "Submitted post-precheck missing-data request is not open."
            )
        if request.evaluation_case_id != context.evaluation_case_id:
            raise BankingPrecheckEvidenceContextError(
                "Submitted missing-data request belongs to another case."
            )
        if (
            request.raised_by != "DECISION_POST_PRECHECK_REVIEW"
            or request.requirement_code != _REQUIREMENT_CODE
            or request.target_record != option.normalized_result_id
            or request.field not in option.required_follow_up_fields
            or option.source_outcome is not BankingPrecheckOutcome.MISSING_EVIDENCE
        ):
            raise BankingPrecheckEvidenceContextError(
                "Submission is not bound to an exact post-precheck MISSING_EVIDENCE "
                "field request."
            )
        request_evidence_ids = tuple(
            item.evidence_id for item in request.evidence_refs
        )
        if not request_evidence_ids or request_evidence_ids != option.evidence_ids:
            raise BankingPrecheckEvidenceContextError(
                "Missing-data request evidence does not match its exact option review."
            )

    def _supplement(
        self,
        *,
        context: ExecutionContext,
        command: BankingPrecheckEvidenceCommand,
        intake_context: _EvidenceInputContext,
    ) -> tuple[BankingPrecheckEvidenceSupplement, tuple[EvidenceRef, ...], bool]:
        submission = command.submission
        current = intake_context.current
        current_artifact = intake_context.current_artifact
        if current is not None and self._same_submission(current, submission):
            if current_artifact is None:  # pragma: no cover
                raise BankingPrecheckEvidenceContextError(
                    "Current evidence supplement envelope is missing."
                )
            return current, current_artifact.evidence_refs, True

        supplement_id = deterministic_id(
            "BPES",
            intake_context.review_artifact.artifact_id,
            intake_context.review.review_id,
            intake_context.review.result_set_artifact_id,
            intake_context.review.result_set_id,
            intake_context.option_review.normalized_result_id,
            intake_context.option_review.option_id,
            intake_context.option_review.bank_product_id,
            intake_context.request.field,
            intake_context.request.request_id,
            submission.evidence_reference_id,
            submission.provided_by,
            submission.evidence_note,
            current_artifact.artifact_id if current_artifact is not None else None,
        )
        source_refs = self._request_evidence_closure(
            intake_context.review_artifact,
            intake_context.request,
        )
        user_refs = tuple(
            self._user_evidence(
                dataset_id=context.dataset_id,
                supplement_id=supplement_id,
                field=field,
                value=value,
            )
            for field, value in (
                ("evidence_reference_id", submission.evidence_reference_id),
                ("provided_by", submission.provided_by),
                ("evidence_note", submission.evidence_note),
            )
        )
        resolution_display = {
            "missing_request_id": intake_context.request.request_id,
            "normalized_result_id": intake_context.option_review.normalized_result_id,
            "option_id": intake_context.option_review.option_id,
            "bank_product_id": intake_context.option_review.bank_product_id,
            "required_field": intake_context.request.field,
            "evidence_reference_id": submission.evidence_reference_id,
            "input_handoff_resolved": True,
            "fresh_governed_precheck_required": True,
            "source_precheck_result_unchanged": True,
            "bank_approval_obtained": False,
        }
        derived_sources = tuple(
            dict.fromkeys(
                (
                    *(item.evidence_id for item in intake_context.request.evidence_refs),
                    *(item.evidence_id for item in user_refs),
                )
            )
        )
        resolution_evidence = EvidenceRef(
            evidence_id=deterministic_id(
                "EVD",
                context.dataset_id,
                SourceType.DERIVED,
                _EVIDENCE_SHEET,
                supplement_id,
                "input_handoff_resolution",
                resolution_display,
                derived_sources,
            ),
            source_type=SourceType.DERIVED,
            sheet=_EVIDENCE_SHEET,
            row_number=0,
            record_id=supplement_id,
            field="input_handoff_resolution",
            display_value=json_safe(resolution_display),
            source_evidence_ids=derived_sources,
        )
        evidence_refs = (*source_refs, *user_refs, resolution_evidence)
        source_artifact_ids = (
            intake_context.review_artifact.artifact_id,
            *((current_artifact.artifact_id,) if current_artifact is not None else ()),
        )
        supplement = BankingPrecheckEvidenceSupplement(
            supplement_id=supplement_id,
            evaluation_case_id=intake_context.review.evaluation_case_id,
            dataset_id=intake_context.review.dataset_id,
            contract_id=intake_context.review.contract_id,
            source_review_artifact_id=intake_context.review_artifact.artifact_id,
            source_review_id=intake_context.review.review_id,
            source_result_set_artifact_id=(
                intake_context.review.result_set_artifact_id
            ),
            source_result_set_id=intake_context.review.result_set_id,
            normalized_result_id=(
                intake_context.option_review.normalized_result_id
            ),
            option_id=intake_context.option_review.option_id,
            bank_product_id=intake_context.option_review.bank_product_id,
            required_field=intake_context.request.field,
            missing_request_id=intake_context.request.request_id,
            evidence_reference_id=submission.evidence_reference_id,
            provided_by=submission.provided_by,
            evidence_note=submission.evidence_note,
            previous_supplement_artifact_id=(
                current_artifact.artifact_id if current_artifact is not None else None
            ),
            source_artifact_ids=source_artifact_ids,
            evidence_ids=tuple(item.evidence_id for item in evidence_refs),
        )
        return supplement, evidence_refs, False

    @staticmethod
    def _request(
        review: DecisionPostPrecheckReview, request_id: str
    ) -> MissingDataRequest:
        matches = tuple(
            item
            for item in review.missing_data_requests
            if item.request_id == request_id
        )
        if len(matches) != 1:
            raise BankingPrecheckEvidenceContextError(
                "Submitted missing_request_id is not present exactly once in the "
                "Decision post-precheck review."
            )
        return matches[0]

    @staticmethod
    def _option_review(
        review: DecisionPostPrecheckReview, normalized_result_id: str
    ) -> DecisionPostPrecheckOptionReview:
        matches = tuple(
            item
            for item in review.option_reviews
            if item.normalized_result_id == normalized_result_id
        )
        if len(matches) != 1:
            raise BankingPrecheckEvidenceContextError(
                "Missing-data target does not resolve to exactly one option review."
            )
        return matches[0]

    @staticmethod
    def _request_evidence_closure(
        artifact: ArtifactEnvelope,
        request: MissingDataRequest,
    ) -> tuple[EvidenceRef, ...]:
        by_id = {item.evidence_id: item for item in artifact.evidence_refs}
        for embedded in request.evidence_refs:
            if by_id.get(embedded.evidence_id) != embedded:
                raise BankingPrecheckEvidenceContextError(
                    "Missing-data request evidence differs from its validated envelope."
                )
        selected: dict[str, EvidenceRef] = {}
        pending = [item.evidence_id for item in request.evidence_refs]
        while pending:
            evidence_id = pending.pop()
            if evidence_id in selected:
                continue
            evidence = by_id.get(evidence_id)
            if evidence is None:
                raise BankingPrecheckEvidenceContextError(
                    "Missing-data request evidence lineage is incomplete."
                )
            selected[evidence_id] = evidence
            pending.extend(evidence.source_evidence_ids)
        return tuple(selected[key] for key in sorted(selected))

    @staticmethod
    def _same_submission(
        current: BankingPrecheckEvidenceSupplement,
        submission: BankingPrecheckEvidenceSubmission,
    ) -> bool:
        return (
            current.missing_request_id == submission.missing_request_id
            and current.evidence_reference_id == submission.evidence_reference_id
            and current.provided_by == submission.provided_by
            and current.evidence_note == submission.evidence_note
        )

    @staticmethod
    def _user_evidence(
        *, dataset_id: str, supplement_id: str, field: str, value: Any
    ) -> EvidenceRef:
        display = json_safe(value)
        return EvidenceRef(
            evidence_id=deterministic_id(
                "EVD",
                dataset_id,
                SourceType.USER_INPUT,
                _EVIDENCE_SHEET,
                supplement_id,
                field,
                display,
            ),
            source_type=SourceType.USER_INPUT,
            sheet=_EVIDENCE_SHEET,
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
            raise BankingPrecheckEvidenceContextError(
                "Evidence intake requires exactly one validated "
                f"{artifact_type.value} artifact."
            )
        return matches[0]

    @staticmethod
    def _latest_review(
        artifacts: tuple[ArtifactEnvelope, ...],
    ) -> ArtifactEnvelope | None:
        return max(
            (
                item
                for item in artifacts
                if item.artifact_type is ArtifactType.DECISION_POST_PRECHECK_REVIEW
            ),
            key=lambda item: item.version,
            default=None,
        )

    @staticmethod
    def _latest_supplement_for_request(
        artifacts: tuple[ArtifactEnvelope, ...], request_id: str
    ) -> ArtifactEnvelope | None:
        matches: list[ArtifactEnvelope] = []
        for artifact in artifacts:
            if (
                artifact.artifact_type
                is not ArtifactType.BANKING_PRECHECK_EVIDENCE_SUPPLEMENT
            ):
                continue
            if artifact.validation_status not in _VALID_STATUSES:
                raise BankingPrecheckEvidenceContextError(
                    "Stored evidence supplement is not validated."
                )
            try:
                supplement = BankingPrecheckEvidenceSupplement.model_validate(
                    artifact.payload
                )
            except ValidationError as exc:
                raise BankingPrecheckEvidenceContextError(
                    "Stored evidence supplement has an invalid schema."
                ) from exc
            if supplement.missing_request_id == request_id:
                matches.append(artifact)
        if not matches:
            return None
        maximum = max(item.version for item in matches)
        current = tuple(item for item in matches if item.version == maximum)
        if len(current) != 1:
            raise BankingPrecheckEvidenceContextError(
                "Current evidence supplement revision is ambiguous."
            )
        return current[0]

    @staticmethod
    def _failed_safe(message: str) -> BankingPrecheckEvidenceComponentResult:
        return BankingPrecheckEvidenceComponentResult(
            status=ComponentStatus.FAILED_SAFE,
            runtime_events=(
                RuntimeEvent(
                    event_type="BANKING_PRECHECK_EVIDENCE_INTAKE_FAILED_SAFE",
                    message=message,
                ),
            ),
        )
