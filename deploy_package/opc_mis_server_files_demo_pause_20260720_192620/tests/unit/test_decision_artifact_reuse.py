"""Fail-safe reuse tests for persisted Decision artifacts."""

import asyncio
from collections.abc import Callable
from typing import cast

import pytest

from opc_mis.business.agents.decision.banking_handoff_component import (
    DecisionBankingHandoff,
)
from opc_mis.business.agents.decision.component import DecisionInitialRoutePlanner
from opc_mis.business.agents.decision.post_banking_component import (
    DecisionPostBankingReviewer,
)
from opc_mis.domain.artifacts import ArtifactDraft, ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import (
    ArtifactType,
    EvaluationScope,
    SourceType,
    ValidationStatus,
)
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.validation_reports import ValidationReport
from opc_mis.infrastructure.persistence.memory_artifact_repository import (
    InMemoryArtifactRepository,
)
from opc_mis.workflow.decision_banking_handoff_orchestrator import (
    DecisionBankingHandoffOrchestrator,
    DecisionBankingHandoffPersistenceError,
)
from opc_mis.workflow.decision_post_banking_orchestrator import (
    DecisionPostBankingOrchestrator,
    DecisionPostBankingPersistenceError,
)
from opc_mis.workflow.decision_route_orchestrator import (
    DecisionRouteOrchestrator,
    DecisionRoutePersistenceError,
)

CASE_ID = "CASE-DECISION-REUSE"


def _context() -> ExecutionContext:
    return ExecutionContext(
        evaluation_case_id=CASE_ID,
        dataset_id="DATASET-DECISION-REUSE",
        workflow_run_id="RUN-DECISION-REUSE",
        input_artifact_ids=("ART-UPSTREAM-EXACT",),
        requested_scope=(EvaluationScope.RISK,),
        component_input={},
        current_node="DECISION_TEST",
    )


def _draft() -> ArtifactDraft:
    return ArtifactDraft(
        artifact_type=ArtifactType.DECISION_ROUTE_PLAN,
        evaluation_case_id=CASE_ID,
        producer="DECISION_TEST",
        payload={"deterministic": "payload"},
        evidence_refs=(),
    )


def _orchestrators() -> tuple[
    tuple[object, InMemoryArtifactRepository, type[RuntimeError]], ...
]:
    route_repository = InMemoryArtifactRepository()
    handoff_repository = InMemoryArtifactRepository()
    review_repository = InMemoryArtifactRepository()
    return (
        (
            DecisionRouteOrchestrator(
                planner=cast(DecisionInitialRoutePlanner, object()),
                artifacts=route_repository,
            ),
            route_repository,
            DecisionRoutePersistenceError,
        ),
        (
            DecisionBankingHandoffOrchestrator(
                handoff=cast(DecisionBankingHandoff, object()),
                artifacts=handoff_repository,
            ),
            handoff_repository,
            DecisionBankingHandoffPersistenceError,
        ),
        (
            DecisionPostBankingOrchestrator(
                reviewer=cast(DecisionPostBankingReviewer, object()),
                artifacts=review_repository,
            ),
            review_repository,
            DecisionPostBankingPersistenceError,
        ),
    )


def _invalid_validation(artifact: ArtifactEnvelope) -> ArtifactEnvelope:
    return artifact.model_copy(update={"validation_status": ValidationStatus.BLOCKED})


def _different_payload(artifact: ArtifactEnvelope) -> ArtifactEnvelope:
    return artifact.model_copy(update={"payload": {"tampered": True}})


def _different_evidence(artifact: ArtifactEnvelope) -> ArtifactEnvelope:
    evidence = EvidenceRef(
        evidence_id="EVD-TAMPERED",
        source_type=SourceType.USER_INPUT,
        sheet="USER_INPUT",
        row_number=0,
        record_id=CASE_ID,
        field="unsafe_reuse",
        display_value="unexpected",
    )
    return artifact.model_copy(update={"evidence_refs": (evidence,)})


def _different_inputs(artifact: ArtifactEnvelope) -> ArtifactEnvelope:
    return artifact.model_copy(update={"input_artifact_ids": ("ART-STALE",)})


@pytest.mark.parametrize(
    "mutate",
    (_invalid_validation, _different_payload, _different_evidence, _different_inputs),
)
def test_decision_orchestrators_reject_non_exact_same_hash_reuse(
    mutate: Callable[[ArtifactEnvelope], ArtifactEnvelope],
) -> None:
    async def run() -> None:
        for orchestrator, repository, expected_error in _orchestrators():
            draft = _draft()
            context = _context()
            report = ValidationReport(status=ValidationStatus.VALID)
            original = await orchestrator._persist_or_reuse(draft, context, report)
            await repository.save(mutate(original))

            with pytest.raises(expected_error):
                await orchestrator._persist_or_reuse(draft, context, report)

    asyncio.run(run())
