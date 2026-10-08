"""Boundary, pause, governance, and identity tests for Operations."""

import asyncio
from types import SimpleNamespace

from opc_mis.business.skills.operations.component import OperationsSkill
from opc_mis.business.skills.operations.requirements import OperationsRequirementFailure
from opc_mis.domain.artifacts import ArtifactDraft
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import (
    ArtifactType,
    ComponentStatus,
    EvaluationScope,
    OperationsAssessmentStatus,
    ValidationStatus,
)
from opc_mis.domain.operations_models import OperationsAssessment
from opc_mis.governance.evidence_validator import EvidenceValidator


def execution_context() -> ExecutionContext:
    return ExecutionContext(
        evaluation_case_id="CASE-X",
        dataset_id="DATASET-X",
        workflow_run_id="RUN-X",
        input_artifact_ids=(),
        requested_scope=(EvaluationScope.OPERATIONS,),
        component_input={},
        current_node="OPERATIONS_ASSESSMENT",
    )


def test_actual_operations_blocker_pauses_without_artifacts_or_signals() -> None:
    failure = OperationsRequirementFailure(
        code="OPERATIONS_ORDER_DUE_DATE_INVALID",
        target_record="ORDER-X",
        field="due_date",
        expected_type="date",
        reason="Required deterministic input is missing.",
    )
    loader = SimpleNamespace()

    async def load(context: ExecutionContext) -> object:
        del context
        return SimpleNamespace(failures=(failure,))

    loader.load = load
    skill = OperationsSkill(context_loader=loader)  # type: ignore[arg-type]

    result = asyncio.run(skill.execute(execution_context()))

    assert result.status is ComponentStatus.WAITING_FOR_INPUT
    assert len(result.missing_data_requests) == 1
    assert result.artifacts == ()
    assert result.approval_signals == ()
    assert result.action_commands == ()


def test_operations_validator_rejects_injected_downstream_fields() -> None:
    assessment = OperationsAssessment(
        evaluation_case_id="CASE-X",
        dataset_id="DATASET-X",
        contract_id="CONTRACT-X",
        assessment_status=OperationsAssessmentStatus.COMPLETE,
        facts_input_hash="HASH-X",
        fact_ids=("FACT-X",),
        observations=(),
        limitations=(),
        summary=(),
    )
    payload = assessment.model_dump(mode="json")
    payload["approval_required"] = True
    draft = ArtifactDraft(
        artifact_type=ArtifactType.OPERATIONS_ASSESSMENT,
        evaluation_case_id="CASE-X",
        producer="OPERATIONS_SKILL",
        payload=payload,
    )

    report = asyncio.run(EvidenceValidator().validate(draft))

    assert report.status is ValidationStatus.BLOCKED


def test_invalid_as_of_date_fails_safe_instead_of_being_swallowed() -> None:
    context = execution_context().model_copy(
        update={"component_input": {"as_of_date": "not-a-date"}}
    )
    skill = OperationsSkill(context_loader=SimpleNamespace())  # type: ignore[arg-type]

    result = asyncio.run(skill.execute(context))

    assert result.status is ComponentStatus.FAILED_SAFE
    assert result.runtime_events
    assert "Invalid Operations request" in result.runtime_events[0].message
