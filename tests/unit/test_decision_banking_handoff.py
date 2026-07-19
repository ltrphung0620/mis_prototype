"""Unit tests for Decision-managed Banking discovery handoff."""

import asyncio
from datetime import UTC, datetime

from opc_mis.business.agents.decision.banking_handoff_component import (
    DecisionBankingHandoff,
)
from opc_mis.business.agents.decision.banking_handoff_context import (
    BankingHandoffContextLoader,
)
from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.decision_route_models import (
    DecisionRoutePlan,
    DecisionRoutingReason,
)
from opc_mis.domain.enums import (
    ArtifactStatus,
    ArtifactType,
    BankingDiscoveryHandoffStatus,
    BankingNeedType,
    ComponentStatus,
    CurrencyCode,
    DecisionCapability,
    DecisionRouteMode,
    DecisionRouteOutcome,
    DecisionRoutingReasonCode,
    EvaluationScope,
    SourceType,
    ValidationStatus,
)
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.infrastructure.persistence.memory_artifact_repository import (
    InMemoryArtifactRepository,
)

CASE_ID = "CASE-BANKING-HANDOFF"
DATASET_ID = "BANKING-HANDOFF-TEST"
CONTRACT_ID = "CON-TEST"


def route_artifact(*, banking: bool) -> ArtifactEnvelope:
    evidence = EvidenceRef(
        evidence_id="EVD-BOND-TERM",
        source_type=SourceType.TEAM_PACK,
        sheet="04_CONTRACTS",
        row_number=2,
        record_id=CONTRACT_ID,
        field="payment_terms",
        display_value="Performance bond required",
    )
    reasons = (
        DecisionRoutingReason(
            reason_id="DRR-BOND",
            code=DecisionRoutingReasonCode.PERFORMANCE_BOND_REQUIREMENT,
            banking_need_type=BankingNeedType.PERFORMANCE_BOND,
            source_artifact_id="ART-FINANCE",
            source_reference_ids=("FOB-BOND",),
            evidence_ids=(evidence.evidence_id,),
        ),
    ) if banking else ()
    plan = DecisionRoutePlan(
        route_plan_id="DRP-TEST",
        evaluation_case_id=CASE_ID,
        dataset_id=DATASET_ID,
        contract_id=CONTRACT_ID,
        execution_mode=DecisionRouteMode.INITIAL_ROUTE,
        route_outcome=(
            DecisionRouteOutcome.BANKING_DISCOVERY_REQUIRED
            if banking
            else DecisionRouteOutcome.DIRECT_INTERNAL_DECISION
        ),
        required_capabilities=(
            (DecisionCapability.BANKING_INTERNAL_DISCOVERY,)
            if banking
            else (DecisionCapability.INTERNAL_DECISION_PACKAGE,)
        ),
        banking_need_types=(BankingNeedType.PERFORMANCE_BOND,) if banking else (),
        routing_reasons=reasons,
        source_artifact_ids=("ART-EVALUATION-CASE", "ART-FINANCE"),
    )
    return ArtifactEnvelope(
        artifact_id="ART-DECISION-ROUTE",
        artifact_type=ArtifactType.DECISION_ROUTE_PLAN,
        evaluation_case_id=CASE_ID,
        producer="DECISION_INITIAL_ROUTE",
        version=1,
        status=ArtifactStatus.CREATED,
        payload=plan.model_dump(mode="json"),
        evidence_refs=(evidence,) if banking else (),
        input_artifact_ids=("ART-EVALUATION-CASE", "ART-FINANCE"),
        input_hash="ROUTE-HASH",
        validation_status=ValidationStatus.VALID,
        validation_notes=(),
        created_at=datetime.now(UTC),
    )


async def execute_handoff(*, banking: bool, include_route: bool = True) -> object:
    repository = InMemoryArtifactRepository()
    route = route_artifact(banking=banking)
    if include_route:
        await repository.save(route)
    component = DecisionBankingHandoff(
        context_loader=BankingHandoffContextLoader(artifacts=repository)
    )
    context = ExecutionContext(
        evaluation_case_id=CASE_ID,
        dataset_id=DATASET_ID,
        workflow_run_id="RUN-HANDOFF",
        input_artifact_ids=(route.artifact_id,) if include_route else (),
        requested_scope=(
            EvaluationScope.FINANCE,
            EvaluationScope.OPERATIONS,
            EvaluationScope.RISK,
        ),
        component_input={"execution_mode": "BANKING_DISCOVERY"},
        current_node="BANKING_DISCOVERY_HANDOFF",
    )
    return await component.execute(context)


def test_banking_route_creates_evidence_backed_internal_request() -> None:
    result = asyncio.run(execute_handoff(banking=True))

    request = result.banking_discovery_request
    assert result.status is ComponentStatus.COMPLETED
    assert result.handoff_status is BankingDiscoveryHandoffStatus.REQUEST_CREATED
    assert request is not None
    assert request.requested_capability is DecisionCapability.BANKING_INTERNAL_DISCOVERY
    assert request.need_types == (BankingNeedType.PERFORMANCE_BOND,)
    assert request.requested_amount is None
    assert request.requested_amount_currency is CurrencyCode.VND
    assert request.constraints == ()
    assert request.evidence_ids == ("EVD-BOND-TERM",)
    assert request.source_route_artifact_id == "ART-DECISION-ROUTE"
    assert len(result.artifacts) == 1
    assert result.artifacts[0].artifact_type is ArtifactType.BANKING_DISCOVERY_REQUEST
    assert result.artifacts[0].evidence_refs[0].evidence_id == "EVD-BOND-TERM"
    assert result.approval_signals == ()
    assert result.action_commands == ()


def test_direct_route_does_not_create_a_banking_request() -> None:
    result = asyncio.run(execute_handoff(banking=False))

    assert result.status is ComponentStatus.COMPLETED
    assert result.handoff_status is BankingDiscoveryHandoffStatus.NOT_APPLICABLE
    assert result.banking_discovery_request is None
    assert result.artifacts == ()


def test_missing_route_waits_without_creating_an_artifact() -> None:
    result = asyncio.run(execute_handoff(banking=True, include_route=False))

    assert result.status is ComponentStatus.WAITING_FOR_INPUT
    assert result.handoff_status is BankingDiscoveryHandoffStatus.WAITING_FOR_ROUTE
    assert result.artifacts == ()
    assert result.missing_data_requests[0].field == "DECISION_ROUTE_PLAN"
