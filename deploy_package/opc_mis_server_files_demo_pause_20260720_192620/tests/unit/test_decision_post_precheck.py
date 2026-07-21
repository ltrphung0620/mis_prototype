"""Unit coverage for deterministic Decision review after Banking precheck."""

import asyncio
import json

import pytest

from opc_mis.business.agents.decision.post_precheck_component import (
    DecisionPostPrecheckReviewer,
)
from opc_mis.business.agents.decision.post_precheck_context import (
    DecisionPostPrecheckContextLoader,
)
from opc_mis.domain.artifacts import ArtifactDraft
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import (
    ArtifactType,
    BankingPrecheckOutcome,
    ComponentStatus,
    DecisionPostPrecheckOptionDisposition,
    DecisionPostPrecheckOutcome,
    ValidationStatus,
    WorkflowStatus,
)
from opc_mis.governance.evidence_validator import EvidenceValidator
from opc_mis.workflow.decision_post_precheck_orchestrator import (
    DecisionPostPrecheckOrchestrator,
)
from tests.unit.test_banking_precheck_result_component import (
    PROPOSAL_ARTIFACT_ID,
    WORKFLOW_RUN_ID,
    _response,
)
from tests.unit.test_banking_precheck_result_component import (
    _setup as _banking_setup,
)
from tests.unit.test_banking_precheck_submission_proposal import (
    CASE_ID,
    DATASET_ID,
    _envelope,
)

RESULT_ARTIFACT_ID = "ART-RESULT-POST-PRECHECK"


async def _setup(
    outcomes: tuple[BankingPrecheckOutcome, ...],
) -> tuple[
    DecisionPostPrecheckReviewer,
    ExecutionContext,
    object,
]:
    repository, banking_component, banking_execution, component_input = (
        await _banking_setup(candidate_count=len(outcomes))
    )
    responses = tuple(
        _response(request, index=index, outcome=outcome)
        for index, (request, outcome) in enumerate(
            zip(component_input.requests, outcomes, strict=True), start=1
        )
    )
    changed_input = component_input.model_copy(
        update={"raw_responses": responses}
    )
    banking_result = await banking_component.execute(
        banking_execution.model_copy(
            update={"component_input": changed_input.model_dump(mode="json")}
        )
    )
    assert banking_result.result_set is not None
    result_artifact = _envelope(
        artifact_id=RESULT_ARTIFACT_ID,
        artifact_type=ArtifactType.BANKING_PRECHECK_RESULT_SET,
        payload=banking_result.result_set.model_dump(mode="json"),
        evidence_refs=banking_result.artifacts[0].evidence_refs,
    )
    await repository.save(result_artifact)
    execution = ExecutionContext(
        evaluation_case_id=CASE_ID,
        dataset_id=DATASET_ID,
        workflow_run_id=WORKFLOW_RUN_ID,
        input_artifact_ids=(RESULT_ARTIFACT_ID, PROPOSAL_ARTIFACT_ID),
        requested_scope=banking_execution.requested_scope,
        component_input={},
        current_node="DECISION_POST_PRECHECK_REVIEW",
    )
    reviewer = DecisionPostPrecheckReviewer(
        context_loader=DecisionPostPrecheckContextLoader(
            artifacts=repository
        )
    )
    return reviewer, execution, repository


@pytest.mark.parametrize(
    ("source_outcome", "disposition", "aggregate", "status"),
    (
        (
            BankingPrecheckOutcome.CONDITIONAL_PRECHECK,
            DecisionPostPrecheckOptionDisposition.CONDITIONAL_REVIEW,
            DecisionPostPrecheckOutcome.CONDITIONAL_OPTIONS_AVAILABLE,
            ComponentStatus.COMPLETED,
        ),
        (
            BankingPrecheckOutcome.MISSING_EVIDENCE,
            DecisionPostPrecheckOptionDisposition.FOLLOW_UP_EVIDENCE_REQUIRED,
            DecisionPostPrecheckOutcome.FOLLOW_UP_EVIDENCE_REQUIRED,
            ComponentStatus.WAITING_FOR_INPUT,
        ),
        (
            BankingPrecheckOutcome.NOT_ELIGIBLE,
            DecisionPostPrecheckOptionDisposition.NOT_ELIGIBLE,
            DecisionPostPrecheckOutcome.ALL_OPTIONS_NOT_ELIGIBLE,
            ComponentStatus.COMPLETED_WITH_WARNINGS,
        ),
        (
            BankingPrecheckOutcome.NO_RECOMMENDATION,
            DecisionPostPrecheckOptionDisposition.NO_PROVIDER_RECOMMENDATION,
            DecisionPostPrecheckOutcome.NO_PROVIDER_RECOMMENDATION,
            ComponentStatus.COMPLETED_WITH_WARNINGS,
        ),
        (
            BankingPrecheckOutcome.SERVICE_UNAVAILABLE,
            DecisionPostPrecheckOptionDisposition.PRECHECK_UNAVAILABLE,
            DecisionPostPrecheckOutcome.PRECHECK_SERVICE_UNAVAILABLE,
            ComponentStatus.COMPLETED_WITH_WARNINGS,
        ),
    ),
)
def test_all_typed_outcomes_map_exhaustively_without_selection(
    source_outcome: BankingPrecheckOutcome,
    disposition: DecisionPostPrecheckOptionDisposition,
    aggregate: DecisionPostPrecheckOutcome,
    status: ComponentStatus,
) -> None:
    async def scenario() -> None:
        reviewer, execution, repository = await _setup((source_outcome,))
        before = await repository.list_by_case(CASE_ID)

        result = await reviewer.execute(execution)

        assert result.status is status
        assert result.review is not None
        review = result.review
        assert review.outcome is aggregate
        assert review.option_reviews[0].source_outcome is source_outcome
        assert review.option_reviews[0].disposition is disposition
        assert review.selection_performed is False
        assert review.ranking_performed is False
        assert review.documents_prepared is False
        assert review.bank_approval_obtained is False
        assert result.approval_signals == ()
        assert result.action_commands == ()
        assert await repository.list_by_case(CASE_ID) == before

    asyncio.run(scenario())


def test_no_recommendation_preserves_exact_product_and_is_not_a_rejection() -> None:
    async def scenario() -> None:
        reviewer, execution, _ = await _setup(
            (BankingPrecheckOutcome.NO_RECOMMENDATION,)
        )

        result = await reviewer.execute(execution)

        assert result.review is not None
        item = result.review.option_reviews[0]
        assert item.bank_product_id == "BANK-PRODUCT-1"
        assert result.review.candidate_bank_product_ids == ("BANK-PRODUCT-1",)
        assert result.review.no_recommendation_option_ids == (item.option_id,)
        assert result.review.not_eligible_option_ids == ()
        assert result.review.missing_data_requests == ()
        serialized = json.dumps(result.artifacts[0].payload, sort_keys=True)
        for forbidden in (
            "selected_option",
            "recommended_option",
            "approval_request",
            "decision_card",
        ):
            assert forbidden not in serialized

    asyncio.run(scenario())


def test_missing_evidence_creates_only_explicit_stable_requests() -> None:
    async def scenario() -> None:
        reviewer, execution, _ = await _setup(
            (BankingPrecheckOutcome.MISSING_EVIDENCE,)
        )

        first = await reviewer.execute(execution)
        retried = await reviewer.execute(execution)

        assert first.review is not None
        assert retried.review is not None
        assert first.review.review_id == retried.review.review_id
        assert first.review.missing_data_requests == (
            retried.review.missing_data_requests
        )
        request = first.review.missing_data_requests[0]
        item = first.review.option_reviews[0]
        assert request.field == "supporting_document_reference"
        assert request.target_record == item.normalized_result_id
        assert request.evaluation_case_id == CASE_ID
        assert request.raised_by == "DECISION_POST_PRECHECK_REVIEW"
        assert request.evidence_refs[0].record_id == item.review_item_id
        assert first.missing_data_requests == first.review.missing_data_requests

    asyncio.run(scenario())


def test_missing_evidence_without_named_field_fails_safe() -> None:
    async def scenario() -> None:
        reviewer, execution, repository = await _setup(
            (BankingPrecheckOutcome.MISSING_EVIDENCE,)
        )
        artifact = await repository.get(RESULT_ARTIFACT_ID)
        assert artifact is not None
        payload = dict(artifact.payload)
        results = [dict(item) for item in payload["results"]]
        results[0]["required_follow_up_fields"] = []
        payload["results"] = results
        changed = artifact.model_copy(update={"payload": payload})
        await repository.save(changed)

        result = await reviewer.execute(execution)

        assert result.status is ComponentStatus.FAILED_SAFE
        assert result.review is None
        assert result.artifacts == ()
        assert "will not invent" in result.runtime_events[0].message

    asyncio.run(scenario())


def test_mixed_batch_uses_missing_evidence_precedence_and_preserves_all() -> None:
    async def scenario() -> None:
        reviewer, execution, _ = await _setup(
            (
                BankingPrecheckOutcome.NO_RECOMMENDATION,
                BankingPrecheckOutcome.CONDITIONAL_PRECHECK,
                BankingPrecheckOutcome.MISSING_EVIDENCE,
            )
        )

        result = await reviewer.execute(execution)

        assert result.review is not None
        review = result.review
        assert review.outcome is (
            DecisionPostPrecheckOutcome.FOLLOW_UP_EVIDENCE_REQUIRED
        )
        assert result.status is ComponentStatus.WAITING_FOR_INPUT
        assert len(review.option_reviews) == 3
        partition = (
            *review.conditional_option_ids,
            *review.evidence_required_option_ids,
            *review.not_eligible_option_ids,
            *review.no_recommendation_option_ids,
            *review.unavailable_option_ids,
        )
        assert set(partition) == set(review.candidate_option_ids)
        assert len(partition) == len(review.candidate_option_ids)

    asyncio.run(scenario())


def test_context_rejects_relabelled_bank_product() -> None:
    async def scenario() -> None:
        reviewer, execution, repository = await _setup(
            (BankingPrecheckOutcome.NO_RECOMMENDATION,)
        )
        artifact = await repository.get(RESULT_ARTIFACT_ID)
        assert artifact is not None
        payload = dict(artifact.payload)
        results = [dict(item) for item in payload["results"]]
        results[0]["bank_product_id"] = "INVENTED-PRODUCT"
        payload["results"] = results
        await repository.save(artifact.model_copy(update={"payload": payload}))

        result = await reviewer.execute(execution)

        assert result.status is ComponentStatus.FAILED_SAFE
        assert result.review is None
        assert "option/product lineage" in result.runtime_events[0].message

    asyncio.run(scenario())


def test_validator_blocks_tampered_review_identity_and_forbidden_selection() -> None:
    async def scenario() -> None:
        reviewer, execution, _ = await _setup(
            (BankingPrecheckOutcome.NO_RECOMMENDATION,)
        )
        result = await reviewer.execute(execution)
        assert result.review is not None
        draft = result.artifacts[0]

        valid = await EvidenceValidator().validate(draft)
        assert valid.status is ValidationStatus.VALID

        payload = dict(draft.payload)
        payload["review_id"] = "FORGED"
        payload["selected_option_id"] = result.review.candidate_option_ids[0]
        tampered = ArtifactDraft(
            artifact_type=draft.artifact_type,
            evaluation_case_id=draft.evaluation_case_id,
            producer=draft.producer,
            payload=payload,
            evidence_refs=draft.evidence_refs,
            identity_inputs=draft.identity_inputs,
        )
        blocked = await EvidenceValidator().validate(tampered)
        assert blocked.status is ValidationStatus.BLOCKED
        assert any(
            "Invalid DECISION_POST_PRECHECK_REVIEW schema" in error
            for error in blocked.blocking_errors
        )

    asyncio.run(scenario())


def test_orchestrator_validates_persists_and_reuses_exact_review() -> None:
    async def scenario() -> None:
        reviewer, execution, repository = await _setup(
            (BankingPrecheckOutcome.NO_RECOMMENDATION,)
        )
        orchestrator = DecisionPostPrecheckOrchestrator(
            reviewer=reviewer,
            artifacts=repository,
        )

        first = await orchestrator.run(execution)
        retried = await orchestrator.run(execution)

        assert first.status is WorkflowStatus.COMPLETED
        assert first.component_status is ComponentStatus.COMPLETED_WITH_WARNINGS
        assert first.review is not None
        assert retried.review == first.review
        assert retried.generated_artifacts[0].artifact_id == (
            first.generated_artifacts[0].artifact_id
        )
        reviews = tuple(
            item
            for item in await repository.list_by_case(CASE_ID)
            if item.artifact_type is ArtifactType.DECISION_POST_PRECHECK_REVIEW
        )
        assert len(reviews) == 1

    asyncio.run(scenario())
