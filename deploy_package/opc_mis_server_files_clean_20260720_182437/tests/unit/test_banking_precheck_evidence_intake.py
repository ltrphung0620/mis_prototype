"""Post-precheck evidence-reference intake and persistence tests."""

import asyncio
import json

from opc_mis.business.agents.decision.post_precheck_evidence_component import (
    BankingPrecheckEvidenceIntake,
)
from opc_mis.domain.banking_precheck_evidence_models import (
    BankingPrecheckEvidenceCommand,
    BankingPrecheckEvidenceSubmission,
    BankingPrecheckEvidenceSupplement,
)
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import (
    ArtifactType,
    BankingPrecheckOutcome,
    ComponentStatus,
    SourceType,
    ValidationStatus,
    WorkflowStatus,
)
from opc_mis.domain.validation_reports import ValidationReport
from opc_mis.governance.evidence_validator import EvidenceValidator
from opc_mis.workflow.banking_precheck_evidence_orchestrator import (
    BankingPrecheckEvidenceOrchestrator,
)
from opc_mis.workflow.decision_post_precheck_orchestrator import (
    DecisionPostPrecheckOrchestrator,
)
from tests.unit.test_decision_post_precheck import _setup as _review_setup

WORKFLOW_ID = "CWF-POST-PRECHECK-EVIDENCE"


async def _setup() -> tuple[object, object, object, object]:
    reviewer, review_execution, repository = await _review_setup(
        (BankingPrecheckOutcome.MISSING_EVIDENCE,)
    )
    review_result = await DecisionPostPrecheckOrchestrator(
        reviewer=reviewer,
        artifacts=repository,
    ).run(review_execution)
    assert review_result.review is not None
    assert len(review_result.generated_artifacts) == 1
    return (
        repository,
        review_execution,
        review_result.review,
        review_result.generated_artifacts[0],
    )


def _submission(
    request_id: str,
    *,
    workflow_id: str = WORKFLOW_ID,
    reference_id: str = "DOCREF-2026-0042",
    note: str = " Uploaded supplier commitment evidence. ",
) -> BankingPrecheckEvidenceSubmission:
    return BankingPrecheckEvidenceSubmission(
        workflow_run_id=workflow_id,
        missing_request_id=request_id,
        evidence_reference_id=reference_id,
        provided_by=" Operations Staff ",
        evidence_note=note,
    )


def _context(
    *,
    review_execution: object,
    review_artifact: object,
    submission: BankingPrecheckEvidenceSubmission,
    allowed_request_id: str,
    current_artifact: object | None = None,
) -> ExecutionContext:
    command = BankingPrecheckEvidenceCommand(
        submission=submission,
        allowed_pending_request_id=allowed_request_id,
    )
    return ExecutionContext(
        evaluation_case_id=review_artifact.evaluation_case_id,
        dataset_id=review_execution.dataset_id,
        workflow_run_id=submission.workflow_run_id,
        input_artifact_ids=(
            review_artifact.artifact_id,
            *((current_artifact.artifact_id,) if current_artifact is not None else ()),
        ),
        requested_scope=review_execution.requested_scope,
        component_input=command.model_dump(mode="json"),
        current_node="BANKING_PRECHECK_EVIDENCE_INTAKE",
    )


def test_component_accepts_only_reference_handoff_without_changing_result() -> None:
    async def scenario() -> None:
        repository, review_execution, review, review_artifact = await _setup()
        request = review.missing_data_requests[0]
        before = await repository.list_by_case(review.evaluation_case_id)
        component = BankingPrecheckEvidenceIntake(artifacts=repository)

        result = await component.execute(
            _context(
                review_execution=review_execution,
                review_artifact=review_artifact,
                submission=_submission(request.request_id),
                allowed_request_id=request.request_id,
            )
        )

        assert result.status is ComponentStatus.COMPLETED
        assert result.supplement is not None
        supplement = result.supplement
        assert supplement.missing_request_id == request.request_id
        assert supplement.required_field == request.field
        assert supplement.normalized_result_id == request.target_record
        assert supplement.evidence_reference_id == "DOCREF-2026-0042"
        assert supplement.provided_by == "Operations Staff"
        assert supplement.evidence_note == "Uploaded supplier commitment evidence."
        assert supplement.evidence_reference_only is True
        assert supplement.input_handoff_resolved is True
        assert supplement.fresh_governed_precheck_required is True
        assert supplement.source_precheck_result_unchanged is True
        assert supplement.bank_approval_obtained is False
        assert supplement.protected_action_authorized is False
        assert result.approval_signals == ()
        assert result.action_commands == ()
        assert result.missing_data_requests == ()
        assert len(result.artifacts) == 1
        draft = result.artifacts[0]
        assert (
            draft.artifact_type
            is ArtifactType.BANKING_PRECHECK_EVIDENCE_SUPPLEMENT
        )
        assert tuple(item.evidence_id for item in draft.evidence_refs) == (
            supplement.evidence_ids
        )
        assert {item.source_type for item in draft.evidence_refs} >= {
            SourceType.USER_INPUT,
            SourceType.DERIVED,
        }
        derived = tuple(
            item
            for item in draft.evidence_refs
            if item.field == "input_handoff_resolution"
        )
        assert len(derived) == 1
        assert set(derived[0].source_evidence_ids).issubset(
            {item.evidence_id for item in draft.evidence_refs}
        )
        assert await EvidenceValidator().validate(draft) == ValidationReport(
            status=ValidationStatus.VALID,
            checks=(
                "SCHEMA_JSON_SAFE",
                "LINEAGE_IDS_UNIQUE",
                "LINEAGE_DERIVED_SOURCES_EXIST",
            ),
            blocking_errors=(),
            warnings=(),
        )
        json.dumps(draft.model_dump(mode="json"), allow_nan=False)
        assert await repository.list_by_case(review.evaluation_case_id) == before

    asyncio.run(scenario())


def test_runtime_run_id_does_not_change_supplement_identity() -> None:
    async def scenario() -> None:
        repository, review_execution, review, review_artifact = await _setup()
        request_id = review.missing_data_requests[0].request_id
        component = BankingPrecheckEvidenceIntake(artifacts=repository)
        first = await component.execute(
            _context(
                review_execution=review_execution,
                review_artifact=review_artifact,
                submission=_submission(request_id),
                allowed_request_id=request_id,
            )
        )
        second = await component.execute(
            _context(
                review_execution=review_execution,
                review_artifact=review_artifact,
                submission=_submission(request_id, workflow_id="CWF-RETRY"),
                allowed_request_id=request_id,
            )
        )

        assert first.supplement is not None
        assert second.supplement is not None
        assert first.supplement.supplement_id == second.supplement.supplement_id
        assert first.artifacts[0].identity_inputs == second.artifacts[0].identity_inputs
        assert "CWF-" not in json.dumps(first.artifacts[0].identity_inputs)

    asyncio.run(scenario())


def test_component_rejects_nonpending_or_unknown_request() -> None:
    async def scenario() -> None:
        repository, review_execution, review, review_artifact = await _setup()
        request_id = review.missing_data_requests[0].request_id
        component = BankingPrecheckEvidenceIntake(artifacts=repository)
        wrong_pending = await component.execute(
            _context(
                review_execution=review_execution,
                review_artifact=review_artifact,
                submission=_submission(request_id),
                allowed_request_id="MDR-ANOTHER-PENDING-REQUEST",
            )
        )
        unknown = await component.execute(
            _context(
                review_execution=review_execution,
                review_artifact=review_artifact,
                submission=_submission("MDR-NOT-IN-REVIEW"),
                allowed_request_id="MDR-NOT-IN-REVIEW",
            )
        )

        assert wrong_pending.status is ComponentStatus.FAILED_SAFE
        assert "allowed pending request" in wrong_pending.runtime_events[0].message
        assert unknown.status is ComponentStatus.FAILED_SAFE
        assert "not present exactly once" in unknown.runtime_events[0].message
        assert wrong_pending.artifacts == ()
        assert unknown.artifacts == ()

    asyncio.run(scenario())


def test_orchestrator_persists_reuses_and_versions_exact_request_stream() -> None:
    async def scenario() -> None:
        repository, review_execution, review, review_artifact = await _setup()
        request_id = review.missing_data_requests[0].request_id
        orchestrator = BankingPrecheckEvidenceOrchestrator(
            intake=BankingPrecheckEvidenceIntake(artifacts=repository),
            artifacts=repository,
        )
        first = await orchestrator.run(
            _context(
                review_execution=review_execution,
                review_artifact=review_artifact,
                submission=_submission(request_id),
                allowed_request_id=request_id,
            )
        )
        first_artifact = first.generated_artifacts[0]
        duplicate = await orchestrator.run(
            _context(
                review_execution=review_execution,
                review_artifact=review_artifact,
                submission=_submission(request_id),
                allowed_request_id=request_id,
                current_artifact=first_artifact,
            )
        )
        changed = await orchestrator.run(
            _context(
                review_execution=review_execution,
                review_artifact=review_artifact,
                submission=_submission(
                    request_id,
                    reference_id="DOCREF-2026-0043",
                    note="Replaced with signed evidence reference.",
                ),
                allowed_request_id=request_id,
                current_artifact=first_artifact,
            )
        )
        second_artifact = changed.generated_artifacts[0]
        second = BankingPrecheckEvidenceSupplement.model_validate(
            second_artifact.payload
        )

        assert first.status is WorkflowStatus.COMPLETED
        assert duplicate.generated_artifacts[0].artifact_id == first_artifact.artifact_id
        assert second_artifact.version == 2
        assert second.previous_supplement_artifact_id == first_artifact.artifact_id
        assert second.source_artifact_ids == (
            review_artifact.artifact_id,
            first_artifact.artifact_id,
        )
        assert second.fresh_governed_precheck_required is True
        assert second.source_precheck_result_unchanged is True
        assert second.bank_approval_obtained is False
        assert second_artifact.input_artifact_ids == second.source_artifact_ids

    asyncio.run(scenario())


class _BlockingValidator:
    async def validate(self, draft: object) -> ValidationReport:
        return ValidationReport(
            status=ValidationStatus.BLOCKED,
            checks=(),
            blocking_errors=("TEST_EVIDENCE_VALIDATION_BLOCK",),
            warnings=(),
        )


def test_orchestrator_never_persists_before_evidence_validation() -> None:
    async def scenario() -> None:
        repository, review_execution, review, review_artifact = await _setup()
        request_id = review.missing_data_requests[0].request_id
        orchestrator = BankingPrecheckEvidenceOrchestrator(
            intake=BankingPrecheckEvidenceIntake(artifacts=repository),
            artifacts=repository,
            evidence_validator=_BlockingValidator(),  # type: ignore[arg-type]
        )

        result = await orchestrator.run(
            _context(
                review_execution=review_execution,
                review_artifact=review_artifact,
                submission=_submission(request_id),
                allowed_request_id=request_id,
            )
        )

        assert result.status is WorkflowStatus.FAILED_SAFE
        assert result.validation_errors == ("TEST_EVIDENCE_VALIDATION_BLOCK",)
        assert not any(
            item.artifact_type
            is ArtifactType.BANKING_PRECHECK_EVIDENCE_SUPPLEMENT
            for item in await repository.list_by_case(review.evaluation_case_id)
        )

    asyncio.run(scenario())


def test_orchestrator_rejects_lineage_that_disagrees_with_reference() -> None:
    async def scenario() -> None:
        repository, review_execution, review, review_artifact = await _setup()
        request_id = review.missing_data_requests[0].request_id
        context = _context(
            review_execution=review_execution,
            review_artifact=review_artifact,
            submission=_submission(request_id),
            allowed_request_id=request_id,
        )
        valid_result = await BankingPrecheckEvidenceIntake(
            artifacts=repository
        ).execute(context)
        draft = valid_result.artifacts[0]
        tampered_refs = tuple(
            item.model_copy(update={"display_value": "DOCREF-FORGED"})
            if item.field == "evidence_reference_id"
            and item.source_type is SourceType.USER_INPUT
            else item
            for item in draft.evidence_refs
        )
        tampered_result = valid_result.model_copy(
            update={
                "artifacts": (
                    draft.model_copy(update={"evidence_refs": tampered_refs}),
                )
            }
        )

        class _TamperingIntake:
            async def execute(self, execution: ExecutionContext) -> object:
                return tampered_result

        orchestrator = BankingPrecheckEvidenceOrchestrator(
            intake=_TamperingIntake(),  # type: ignore[arg-type]
            artifacts=repository,
        )
        result = await orchestrator.run(context)

        assert result.status is WorkflowStatus.FAILED_SAFE
        assert any("exact USER_INPUT lineage" in item for item in result.validation_errors)
        assert not any(
            item.artifact_type
            is ArtifactType.BANKING_PRECHECK_EVIDENCE_SUPPLEMENT
            for item in await repository.list_by_case(review.evaluation_case_id)
        )

    asyncio.run(scenario())
