"""Unit tests for Decision-managed Banking discovery handoff."""

import asyncio
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from opc_mis.business.agents.decision.banking_handoff_component import (
    DecisionBankingHandoff,
)
from opc_mis.business.agents.decision.banking_handoff_context import (
    BankingHandoffContextLoader,
)
from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.banking_models import BankingDiscoveryRequest
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
    CashflowScope,
    ComponentStatus,
    ContractRequirementType,
    CurrencyCode,
    DecisionCapability,
    DecisionHandoffMode,
    DecisionRouteMode,
    DecisionRouteOutcome,
    DecisionRoutingReasonCode,
    EvaluationScope,
    RequirementAmountSemantics,
    RequirementCertainty,
    SourceType,
    ValidationStatus,
)
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.planner_models import ContractRequirement, EvaluationCase
from opc_mis.infrastructure.persistence.memory_artifact_repository import (
    InMemoryArtifactRepository,
)

CASE_ID = "CASE-BANKING-HANDOFF"
DATASET_ID = "BANKING-HANDOFF-TEST"
CONTRACT_ID = "CON-TEST"
REQUIREMENT_ID = "CREQ-BOND"
CREDIT_CASE_ID = "CR-BOND"
REQUESTED_AMOUNT = 420_000_000


def requirement_evidence() -> tuple[EvidenceRef, EvidenceRef]:
    return (
        EvidenceRef(
            evidence_id="EVD-BOND-TERM",
            source_type=SourceType.TEAM_PACK,
            sheet="04_CONTRACTS",
            row_number=2,
            record_id=CONTRACT_ID,
            field="payment_terms",
            display_value="Performance bond required",
        ),
        EvidenceRef(
            evidence_id="EVD-BOND-AMOUNT",
            source_type=SourceType.TEAM_PACK,
            sheet="10_CREDIT_PROFILE",
            row_number=3,
            record_id=CREDIT_CASE_ID,
            field="requested_amount",
            display_value=REQUESTED_AMOUNT,
        ),
    )


def evaluation_case_artifact(*, banking: bool) -> ArtifactEnvelope:
    evidence = requirement_evidence() if banking else ()
    requirement = (
        ContractRequirement(
            requirement_id=REQUIREMENT_ID,
            requirement_type=ContractRequirementType.PERFORMANCE_BOND,
            certainty=RequirementCertainty.REQUIRED,
            requested_amount=REQUESTED_AMOUNT,
            requested_amount_currency=CurrencyCode.VND,
            amount_semantics=(
                RequirementAmountSemantics.CREDIT_PROFILE_REQUESTED_AMOUNT
            ),
            credit_case_id=CREDIT_CASE_ID,
            source_record_ids=(CONTRACT_ID, CREDIT_CASE_ID),
            source_fields=("payment_terms", "requested_amount"),
            evidence_ids=tuple(item.evidence_id for item in evidence),
        )
        if banking
        else None
    )
    case = EvaluationCase(
        evaluation_case_id=CASE_ID,
        dataset_id=DATASET_ID,
        contract_id=CONTRACT_ID,
        customer_id="CUS-TEST",
        related_order_ids=(),
        related_invoice_ids=(),
        related_service_ids=(),
        related_credit_case_ids=(CREDIT_CASE_ID,) if banking else (),
        evaluation_scope=(
            EvaluationScope.FINANCE,
            EvaluationScope.OPERATIONS,
            EvaluationScope.RISK,
        ),
        cashflow_scope=CashflowScope.OPC_GLOBAL,
        warnings=(),
        evidence_refs=evidence,
        contract_requirements=(requirement,) if requirement is not None else (),
    )
    return ArtifactEnvelope(
        artifact_id="ART-EVALUATION-CASE",
        artifact_type=ArtifactType.EVALUATION_CASE,
        evaluation_case_id=CASE_ID,
        producer="PLANNER_SKILL",
        version=1,
        status=ArtifactStatus.CREATED,
        payload=case.model_dump(mode="json"),
        evidence_refs=evidence,
        input_artifact_ids=("UPSTREAM",),
        input_hash="CASE-HASH",
        validation_status=ValidationStatus.VALID,
        validation_notes=(),
        created_at=datetime.now(UTC),
    )


def route_artifact(*, banking: bool) -> ArtifactEnvelope:
    evidence = requirement_evidence()
    reasons = (
        DecisionRoutingReason(
            reason_id="DRR-BOND",
            code=DecisionRoutingReasonCode.PERFORMANCE_BOND_REQUIREMENT,
            banking_need_type=BankingNeedType.PERFORMANCE_BOND,
            requirement_id=REQUIREMENT_ID,
            requirement_certainty=RequirementCertainty.REQUIRED,
            credit_case_id=CREDIT_CASE_ID,
            requested_amount=REQUESTED_AMOUNT,
            requested_amount_currency=CurrencyCode.VND,
            amount_semantics=(
                RequirementAmountSemantics.CREDIT_PROFILE_REQUESTED_AMOUNT
            ),
            amount_evidence_ids=("EVD-BOND-AMOUNT",),
            source_artifact_id="ART-EVALUATION-CASE",
            source_reference_ids=(REQUIREMENT_ID,),
            evidence_ids=tuple(item.evidence_id for item in evidence),
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
        evidence_refs=evidence if banking else (),
        input_artifact_ids=("ART-EVALUATION-CASE", "ART-FINANCE"),
        input_hash="ROUTE-HASH",
        validation_status=ValidationStatus.VALID,
        validation_notes=(),
        created_at=datetime.now(UTC),
    )


async def execute_handoff(*, banking: bool, include_route: bool = True) -> object:
    repository = InMemoryArtifactRepository()
    case = evaluation_case_artifact(banking=banking)
    route = route_artifact(banking=banking)
    await repository.save(case)
    if include_route:
        await repository.save(route)
    component = DecisionBankingHandoff(
        context_loader=BankingHandoffContextLoader(artifacts=repository)
    )
    context = ExecutionContext(
        evaluation_case_id=CASE_ID,
        dataset_id=DATASET_ID,
        workflow_run_id="RUN-HANDOFF",
        input_artifact_ids=(
            (case.artifact_id, route.artifact_id)
            if include_route
            else (case.artifact_id,)
        ),
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
    assert request.requirement_id == REQUIREMENT_ID
    assert request.credit_case_id == CREDIT_CASE_ID
    assert request.requested_amount == REQUESTED_AMOUNT
    assert request.requested_amount_currency is CurrencyCode.VND
    assert (
        request.amount_semantics
        is RequirementAmountSemantics.CREDIT_PROFILE_REQUESTED_AMOUNT
    )
    assert request.amount_evidence_ids == ("EVD-BOND-AMOUNT",)
    assert request.constraints == ()
    assert request.evidence_ids == ("EVD-BOND-AMOUNT", "EVD-BOND-TERM")
    assert request.source_route_artifact_id == "ART-DECISION-ROUTE"
    assert len(result.artifacts) == 1
    assert result.artifacts[0].artifact_type is ArtifactType.BANKING_DISCOVERY_REQUEST
    assert {item.evidence_id for item in result.artifacts[0].evidence_refs} == {
        "EVD-BOND-TERM",
        "EVD-BOND-AMOUNT",
    }
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


def test_handoff_fails_safe_when_route_amount_drifts_from_evaluation_case() -> None:
    async def run() -> object:
        repository = InMemoryArtifactRepository()
        case = evaluation_case_artifact(banking=True)
        route = route_artifact(banking=True)
        payload = dict(route.payload)
        reasons = [dict(item) for item in payload["routing_reasons"]]
        reasons[0]["requested_amount"] = REQUESTED_AMOUNT - 1
        route = route.model_copy(update={"payload": {**payload, "routing_reasons": reasons}})
        await repository.save(case)
        await repository.save(route)
        component = DecisionBankingHandoff(
            context_loader=BankingHandoffContextLoader(artifacts=repository)
        )
        context = ExecutionContext(
            evaluation_case_id=CASE_ID,
            dataset_id=DATASET_ID,
            workflow_run_id="RUN-HANDOFF-DRIFT",
            input_artifact_ids=(case.artifact_id, route.artifact_id),
            requested_scope=(EvaluationScope.RISK,),
            component_input={"execution_mode": "BANKING_DISCOVERY"},
            current_node="BANKING_DISCOVERY_HANDOFF",
        )
        return await component.execute(context)

    result = asyncio.run(run())

    assert result.status is ComponentStatus.FAILED_SAFE
    assert result.handoff_status is BankingDiscoveryHandoffStatus.FAILED_SAFE
    assert result.artifacts == ()
    assert "does not match EvaluationCase" in result.runtime_events[0].message


def test_banking_request_rejects_amount_without_source_metadata() -> None:
    with pytest.raises(ValidationError, match="must be present together"):
        BankingDiscoveryRequest(
            request_id="BDR-INCOMPLETE",
            evaluation_case_id=CASE_ID,
            dataset_id=DATASET_ID,
            contract_id=CONTRACT_ID,
            execution_mode=DecisionHandoffMode.BANKING_DISCOVERY,
            requested_capability=DecisionCapability.BANKING_INTERNAL_DISCOVERY,
            need_types=(BankingNeedType.PERFORMANCE_BOND,),
            requested_amount=REQUESTED_AMOUNT,
            requested_amount_currency=CurrencyCode.VND,
            source_route_artifact_id="ART-DECISION-ROUTE",
            source_route_plan_id="DRP-INCOMPLETE",
            source_artifact_ids=("ART-DECISION-ROUTE",),
            evidence_ids=("EVD-BOND-AMOUNT",),
        )
