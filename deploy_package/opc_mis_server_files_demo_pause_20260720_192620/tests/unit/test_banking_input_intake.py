"""Immutable Banking amount-input component and persistence tests."""

import asyncio
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from opc_mis.business.agents.decision.post_banking_component import (
    DecisionPostBankingReviewer,
)
from opc_mis.business.skills.banking.input_component import (
    BankingAmountInputIntake,
)
from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.banking_input_models import (
    BankingAmountInputCommand,
    BankingAmountInputSubmission,
)
from opc_mis.domain.banking_models import BankingInputSupplement
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.decision_post_banking_models import DecisionPostBankingReview
from opc_mis.domain.enums import (
    ArtifactStatus,
    ArtifactType,
    BankingPrecheckFieldSource,
    CashflowScope,
    CurrencyCode,
    DecisionPostBankingOutcome,
    EvaluationScope,
    MissingRequestStatus,
    SourceType,
    ValidationStatus,
    WorkflowStatus,
)
from opc_mis.domain.missing_data import MissingDataRequest
from opc_mis.domain.planner_models import EvaluationCase
from opc_mis.domain.validation_reports import ValidationReport
from opc_mis.governance.evidence_validator import EvidenceValidator
from opc_mis.infrastructure.persistence.memory_artifact_repository import (
    InMemoryArtifactRepository,
)
from opc_mis.workflow.banking_input_orchestrator import BankingInputOrchestrator

CASE_ID = "CASE-BANKING-INPUT"
DATASET_ID = "DATASET-BANKING-INPUT"
CONTRACT_ID = "CONTRACT-BANKING-INPUT"
WORKFLOW_ID = "CWF-BANKING-INPUT"
MISSING_REQUEST_ID = "MDR-BANKING-AMOUNT"
BANKING_REQUEST_ID = "BANKING-REQUEST-INPUT"


def _case() -> EvaluationCase:
    return EvaluationCase(
        evaluation_case_id=CASE_ID,
        dataset_id=DATASET_ID,
        contract_id=CONTRACT_ID,
        customer_id="CUSTOMER-BANKING-INPUT",
        related_order_ids=(),
        related_invoice_ids=(),
        related_service_ids=(),
        related_credit_case_ids=(),
        evaluation_scope=(
            EvaluationScope.FINANCE,
            EvaluationScope.OPERATIONS,
            EvaluationScope.RISK,
        ),
        cashflow_scope=CashflowScope.OPC_GLOBAL,
        warnings=(),
        evidence_refs=(),
    )


def _review() -> DecisionPostBankingReview:
    return DecisionPostBankingReview(
        review_id="DPBR-BANKING-INPUT",
        evaluation_case_id=CASE_ID,
        dataset_id=DATASET_ID,
        contract_id=CONTRACT_ID,
        matrix_id="MATRIX-BANKING-INPUT",
        banking_request_id=BANKING_REQUEST_ID,
        readiness_id="READINESS-BANKING-INPUT",
        outcome=DecisionPostBankingOutcome.BANKING_INPUT_REQUIRED,
        candidate_option_ids=("OPTION-BANKING-INPUT",),
        pending_option_ids=("OPTION-BANKING-INPUT",),
        required_input_fields=("requested_amount",),
        missing_data_requests=(
            MissingDataRequest(
                request_id=MISSING_REQUEST_ID,
                evaluation_case_id=CASE_ID,
                raised_by="DECISION_POST_BANKING_REVIEW",
                requirement_code="BANKING_PRECHECK_AMOUNT_REQUIRED",
                target_record=BANKING_REQUEST_ID,
                field="requested_amount",
                expected_type="positive integer VND amount",
                reason="Banking precheck readiness requires an explicit amount.",
            ),
        ),
        source_artifact_ids=("ART-MATRIX", "ART-READINESS"),
        evidence_ids=("EVD-REVIEW",),
        precheck_executed=False,
    )


def _envelope(
    *,
    artifact_id: str,
    artifact_type: ArtifactType,
    payload: dict[str, object],
    version: int = 1,
) -> ArtifactEnvelope:
    return ArtifactEnvelope(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        evaluation_case_id=CASE_ID,
        producer="UPSTREAM-TEST",
        version=version,
        status=ArtifactStatus.CREATED,
        payload=payload,
        evidence_refs=(),
        input_artifact_ids=(),
        input_hash=f"HASH-{artifact_id}",
        validation_status=ValidationStatus.VALID,
        validation_notes=(),
        created_at=datetime(2026, 7, 18, tzinfo=UTC),
    )


def _submission(
    amount: int = 420_000_000,
    *,
    request_id: str = MISSING_REQUEST_ID,
    workflow_id: str = WORKFLOW_ID,
) -> BankingAmountInputSubmission:
    return BankingAmountInputSubmission(
        workflow_run_id=workflow_id,
        missing_request_id=request_id,
        requested_amount=amount,
        requested_amount_currency=CurrencyCode.VND,
        provided_by=" Founder ",
        evidence_note=" Confirmed performance-bond amount. ",
    )


def _context(
    case_artifact: ArtifactEnvelope,
    review_artifact: ArtifactEnvelope,
    submission: BankingAmountInputSubmission,
    current: ArtifactEnvelope | None = None,
    workflow_id: str = WORKFLOW_ID,
) -> ExecutionContext:
    command = BankingAmountInputCommand(
        submission=submission,
        allowed_pending_request_id=MISSING_REQUEST_ID,
    )
    return ExecutionContext(
        evaluation_case_id=CASE_ID,
        dataset_id=DATASET_ID,
        workflow_run_id=workflow_id,
        input_artifact_ids=(
            case_artifact.artifact_id,
            review_artifact.artifact_id,
            *((current.artifact_id,) if current is not None else ()),
        ),
        requested_scope=(
            EvaluationScope.FINANCE,
            EvaluationScope.OPERATIONS,
            EvaluationScope.RISK,
        ),
        component_input=command.model_dump(mode="json"),
        current_node="BANKING_INPUT_SUPPLEMENT",
    )


async def _setup(
    review: DecisionPostBankingReview | None = None,
) -> tuple[
    InMemoryArtifactRepository,
    ArtifactEnvelope,
    ArtifactEnvelope,
]:
    repository = InMemoryArtifactRepository()
    case_artifact = _envelope(
        artifact_id="ART-EVALUATION-CASE",
        artifact_type=ArtifactType.EVALUATION_CASE,
        payload=_case().model_dump(mode="json"),
    )
    review_artifact = _envelope(
        artifact_id="ART-POST-BANKING-REVIEW",
        artifact_type=ArtifactType.DECISION_POST_BANKING_REVIEW,
        payload=(review or _review()).model_dump(mode="json"),
    )
    await repository.save(case_artifact)
    await repository.save(review_artifact)
    return repository, case_artifact, review_artifact


def test_submission_requires_strict_positive_integer_vnd() -> None:
    with pytest.raises(ValidationError):
        _submission(0)
    with pytest.raises(ValidationError):
        BankingAmountInputSubmission(
            workflow_run_id=WORKFLOW_ID,
            missing_request_id=MISSING_REQUEST_ID,
            requested_amount=420_000_000.5,
            requested_amount_currency="VND",
            provided_by="Founder",
            evidence_note="Confirmed.",
        )


def test_component_returns_only_user_evidenced_supplement_draft() -> None:
    async def scenario() -> None:
        repository, case_artifact, review_artifact = await _setup()
        component = BankingAmountInputIntake(artifacts=repository)

        result = await component.execute(
            _context(case_artifact, review_artifact, _submission())
        )

        assert result.supplement is not None
        assert result.supplement.requested_amount == 420_000_000
        assert result.supplement.banking_request_id == BANKING_REQUEST_ID
        assert result.supplement.provider == "Founder"
        assert result.supplement.note == "Confirmed performance-bond amount."
        assert result.supplement.resolved_request_ids == (MISSING_REQUEST_ID,)
        assert result.supplement.source_artifact_ids == (
            case_artifact.artifact_id,
            review_artifact.artifact_id,
        )
        assert len(result.artifacts) == 1
        assert result.artifacts[0].artifact_type is ArtifactType.BANKING_INPUT_SUPPLEMENT
        assert result.approval_signals == ()
        assert result.action_commands == ()
        assert {
            item.source_type for item in result.artifacts[0].evidence_refs
        } == {SourceType.USER_INPUT}
        validation = await EvidenceValidator().validate(result.artifacts[0])
        assert validation.status is ValidationStatus.VALID
        assert await repository.list_by_case(CASE_ID) == (
            case_artifact,
            review_artifact,
        )

    asyncio.run(scenario())


def test_validator_rejects_supplement_evidence_for_a_different_amount() -> None:
    async def scenario() -> None:
        repository, case_artifact, review_artifact = await _setup()
        result = await BankingAmountInputIntake(artifacts=repository).execute(
            _context(case_artifact, review_artifact, _submission())
        )
        draft = result.artifacts[0]
        changed_evidence = tuple(
            item.model_copy(update={"display_value": 410_000_000})
            if item.field == "requested_amount"
            else item
            for item in draft.evidence_refs
        )
        report = await EvidenceValidator().validate(
            draft.model_copy(update={"evidence_refs": changed_evidence})
        )

        assert report.status is ValidationStatus.BLOCKED
        assert any("exact USER_INPUT" in error for error in report.blocking_errors)

    asyncio.run(scenario())


def test_runtime_workflow_id_does_not_change_business_identity() -> None:
    async def scenario() -> None:
        repository, case_artifact, review_artifact = await _setup()
        component = BankingAmountInputIntake(artifacts=repository)
        first = await component.execute(
            _context(case_artifact, review_artifact, _submission())
        )
        another_workflow_id = "CWF-BANKING-INPUT-RETRY"
        retried = await component.execute(
            _context(
                case_artifact,
                review_artifact,
                _submission(workflow_id=another_workflow_id),
                workflow_id=another_workflow_id,
            )
        )

        assert first.supplement is not None
        assert retried.supplement is not None
        assert retried.supplement.supplement_id == first.supplement.supplement_id
        assert retried.artifacts[0].identity_inputs == first.artifacts[0].identity_inputs

    asyncio.run(scenario())


def test_decision_amount_missing_request_contract_is_accepted_by_intake() -> None:
    async def scenario() -> None:
        code, field, expected_type, reason = (
            DecisionPostBankingReviewer._requirement_contract(
                BankingPrecheckFieldSource.BANKING_INPUT_SUPPLEMENT
            )
        )
        request = MissingDataRequest(
            request_id=MISSING_REQUEST_ID,
            evaluation_case_id=CASE_ID,
            raised_by=DecisionPostBankingReviewer.component_id,
            requirement_code=code,
            target_record=BANKING_REQUEST_ID,
            field=field,
            expected_type=expected_type,
            reason=reason,
        )
        review = _review().model_copy(
            update={
                "required_input_fields": (request.field,),
                "missing_data_requests": (request,),
            }
        )
        repository, case_artifact, review_artifact = await _setup(review)

        result = await BankingAmountInputIntake(artifacts=repository).execute(
            _context(case_artifact, review_artifact, _submission())
        )

        assert result.status.value == "COMPLETED"
        assert result.supplement is not None
        assert result.supplement.resolved_request_ids == (request.request_id,)

    asyncio.run(scenario())


def test_component_rejects_unapproved_request_and_stale_supplement_context() -> None:
    async def scenario() -> None:
        repository, case_artifact, review_artifact = await _setup()
        orchestrator = BankingInputOrchestrator(
            intake=BankingAmountInputIntake(artifacts=repository),
            artifacts=repository,
        )
        first = await orchestrator.run(
            _context(case_artifact, review_artifact, _submission())
        )
        assert first.status is WorkflowStatus.COMPLETED

        wrong_request = await BankingAmountInputIntake(
            artifacts=repository
        ).execute(
            _context(
                case_artifact,
                review_artifact,
                _submission(request_id="MDR-NOT-PENDING"),
                first.generated_artifacts[0],
            )
        )
        omitted_current = await BankingAmountInputIntake(
            artifacts=repository
        ).execute(_context(case_artifact, review_artifact, _submission()))

        assert wrong_request.status.value == "FAILED_SAFE"
        assert wrong_request.artifacts == ()
        assert omitted_current.status.value == "FAILED_SAFE"
        assert omitted_current.artifacts == ()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("request_update", "expected_message"),
    (
        (
            {"status": MissingRequestStatus.RESOLVED},
            "not open",
        ),
        (
            {"requirement_code": "SOME_OTHER_REQUIREMENT"},
            "not the explicit Banking requested-amount request",
        ),
        (
            {"field": "amount"},
            "not the explicit Banking requested-amount request",
        ),
        (
            {"target_record": "ANOTHER-BANKING-REQUEST"},
            "not the explicit Banking requested-amount request",
        ),
    ),
)
def test_component_requires_open_explicit_review_amount_request(
    request_update: dict[str, object],
    expected_message: str,
) -> None:
    async def scenario() -> None:
        review = _review()
        request = review.missing_data_requests[0].model_copy(update=request_update)
        review = review.model_copy(update={"missing_data_requests": (request,)})
        repository, case_artifact, review_artifact = await _setup(review)

        result = await BankingAmountInputIntake(artifacts=repository).execute(
            _context(case_artifact, review_artifact, _submission())
        )

        assert result.status.value == "FAILED_SAFE"
        assert result.artifacts == ()
        assert expected_message in result.runtime_events[0].message

    asyncio.run(scenario())


def test_orchestrator_reuses_current_and_versions_changed_revisions() -> None:
    async def scenario() -> None:
        repository, case_artifact, review_artifact = await _setup()
        orchestrator = BankingInputOrchestrator(
            intake=BankingAmountInputIntake(artifacts=repository),
            artifacts=repository,
        )
        first = await orchestrator.run(
            _context(case_artifact, review_artifact, _submission(420_000_000))
        )
        first_artifact = first.generated_artifacts[0]
        duplicate = await orchestrator.run(
            _context(
                case_artifact,
                review_artifact,
                _submission(420_000_000),
                first_artifact,
            )
        )
        second = await orchestrator.run(
            _context(
                case_artifact,
                review_artifact,
                _submission(430_000_000),
                first_artifact,
            )
        )
        second_artifact = second.generated_artifacts[0]
        reverted = await orchestrator.run(
            _context(
                case_artifact,
                review_artifact,
                _submission(420_000_000),
                second_artifact,
            )
        )
        reverted_artifact = reverted.generated_artifacts[0]

        assert duplicate.generated_artifacts[0].artifact_id == first_artifact.artifact_id
        assert second_artifact.version == 2
        assert first_artifact.artifact_id in second_artifact.input_artifact_ids
        assert BankingInputSupplement.model_validate(
            second_artifact.payload
        ).source_artifact_ids == (
            case_artifact.artifact_id,
            review_artifact.artifact_id,
            first_artifact.artifact_id,
        )
        assert reverted_artifact.version == 3
        assert reverted_artifact.artifact_id != first_artifact.artifact_id
        assert second_artifact.artifact_id in reverted_artifact.input_artifact_ids
        assert BankingInputSupplement.model_validate(
            reverted_artifact.payload
        ).requested_amount == 420_000_000
        supplements = tuple(
            item
            for item in await repository.list_by_case(CASE_ID)
            if item.artifact_type is ArtifactType.BANKING_INPUT_SUPPLEMENT
        )
        assert len(supplements) == 3

    asyncio.run(scenario())


class _BlockingValidator:
    async def validate(self, draft: object) -> ValidationReport:
        return ValidationReport(
            status=ValidationStatus.BLOCKED,
            checks=(),
            blocking_errors=("TEST_VALIDATION_BLOCK",),
            warnings=(),
        )


def test_orchestrator_never_persists_before_evidence_validation() -> None:
    async def scenario() -> None:
        repository, case_artifact, review_artifact = await _setup()
        orchestrator = BankingInputOrchestrator(
            intake=BankingAmountInputIntake(artifacts=repository),
            artifacts=repository,
            evidence_validator=_BlockingValidator(),  # type: ignore[arg-type]
        )

        result = await orchestrator.run(
            _context(case_artifact, review_artifact, _submission())
        )

        assert result.status is WorkflowStatus.FAILED_SAFE
        assert result.validation_errors == ("TEST_VALIDATION_BLOCK",)
        assert not any(
            item.artifact_type is ArtifactType.BANKING_INPUT_SUPPLEMENT
            for item in await repository.list_by_case(CASE_ID)
        )

    asyncio.run(scenario())
