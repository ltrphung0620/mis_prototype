"""Unit coverage for the non-selective Decision-to-Document handoff."""

import asyncio

from opc_mis.business.agents.decision.document_handoff_component import (
    DecisionDocumentHandoff,
)
from opc_mis.business.agents.decision.document_handoff_context import (
    DecisionDocumentHandoffContextLoader,
)
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import (
    ArtifactType,
    BankingPrecheckOutcome,
    ComponentStatus,
    ValidationStatus,
)
from opc_mis.governance.evidence_validator import EvidenceValidator
from tests.unit.test_banking_precheck_result_component import WORKFLOW_RUN_ID
from tests.unit.test_banking_precheck_submission_proposal import (
    CASE_ID,
    DATASET_ID,
    _envelope,
)
from tests.unit.test_decision_post_precheck import (
    RESULT_ARTIFACT_ID,
)
from tests.unit.test_decision_post_precheck import (
    _setup as _review_setup,
)


def test_conditional_result_creates_one_non_selective_document_request() -> None:
    async def scenario() -> None:
        reviewer, review_execution, repository = await _review_setup(
            (BankingPrecheckOutcome.CONDITIONAL_PRECHECK,)
        )
        review_result = await reviewer.execute(review_execution)
        assert review_result.review is not None
        review_artifact = _envelope(
            artifact_id="ART-DOCUMENT-HANDOFF-REVIEW",
            artifact_type=ArtifactType.DECISION_POST_PRECHECK_REVIEW,
            payload=review_result.review.model_dump(mode="json"),
            evidence_refs=review_result.artifacts[0].evidence_refs,
        )
        await repository.save(review_artifact)
        component = DecisionDocumentHandoff(
            context_loader=DecisionDocumentHandoffContextLoader(
                artifacts=repository
            )
        )
        result = await component.execute(
            ExecutionContext(
                evaluation_case_id=CASE_ID,
                dataset_id=DATASET_ID,
                workflow_run_id=WORKFLOW_RUN_ID,
                input_artifact_ids=(review_artifact.artifact_id, RESULT_ARTIFACT_ID),
                requested_scope=review_execution.requested_scope,
                component_input={"execution_mode": "DOCUMENT_PREPARATION"},
                current_node="DECISION_DOCUMENT_HANDOFF",
            )
        )

        assert result.status is ComponentStatus.COMPLETED
        assert len(result.preparation_requests) == 1
        request = result.preparation_requests[0]
        assert request.requested_amount == request.supported_amount
        assert request.selection_performed is False
        assert request.documents_prepared is False
        assert request.required_document_codes
        assert result.artifacts[0].artifact_type is (
            ArtifactType.DOCUMENT_PREPARATION_REQUEST
        )
        assert result.approval_signals == ()
        assert result.action_commands == ()
        report = await EvidenceValidator().validate(result.artifacts[0])
        assert report.status is ValidationStatus.VALID

    asyncio.run(scenario())


def test_no_recommendation_does_not_create_document_work() -> None:
    async def scenario() -> None:
        reviewer, review_execution, repository = await _review_setup(
            (BankingPrecheckOutcome.NO_RECOMMENDATION,)
        )
        review_result = await reviewer.execute(review_execution)
        assert review_result.review is not None
        review_artifact = _envelope(
            artifact_id="ART-NO-DOCUMENT-HANDOFF-REVIEW",
            artifact_type=ArtifactType.DECISION_POST_PRECHECK_REVIEW,
            payload=review_result.review.model_dump(mode="json"),
            evidence_refs=review_result.artifacts[0].evidence_refs,
        )
        await repository.save(review_artifact)
        component = DecisionDocumentHandoff(
            context_loader=DecisionDocumentHandoffContextLoader(
                artifacts=repository
            )
        )
        result = await component.execute(
            ExecutionContext(
                evaluation_case_id=CASE_ID,
                dataset_id=DATASET_ID,
                workflow_run_id=WORKFLOW_RUN_ID,
                input_artifact_ids=(review_artifact.artifact_id, RESULT_ARTIFACT_ID),
                requested_scope=review_execution.requested_scope,
                component_input={"execution_mode": "DOCUMENT_PREPARATION"},
                current_node="DECISION_DOCUMENT_HANDOFF",
            )
        )

        assert result.status is ComponentStatus.COMPLETED_WITH_WARNINGS
        assert result.preparation_requests == ()
        assert result.artifacts == ()

    asyncio.run(scenario())
