"""Deterministic Banking readiness and Decision post-Banking review tests."""

import asyncio
from types import SimpleNamespace

from opc_mis.business.agents.decision.post_banking_component import (
    DecisionPostBankingReviewer,
)
from opc_mis.business.agents.decision.post_banking_context import (
    DecisionPostBankingContextLoader,
)
from opc_mis.business.skills.banking.component import BankingDiscoverySkill
from opc_mis.business.skills.banking.context_loader import (
    BankingDiscoveryContextLoader,
)
from opc_mis.business.skills.banking.precheck_readiness_component import (
    BankingPrecheckReadinessSkill,
)
from opc_mis.business.skills.banking.precheck_readiness_context import (
    BankingPrecheckReadinessContextLoader,
)
from opc_mis.domain.artifacts import ArtifactDraft
from opc_mis.domain.banking_models import BankingInputSupplement
from opc_mis.domain.enums import (
    ArtifactType,
    BankingCriterionCode,
    BankingCriterionStatus,
    BankingDataGapCode,
    BankingPrecheckFieldSource,
    BankingPrecheckFieldStatus,
    BankingPrecheckReadinessStatus,
    ComponentStatus,
    CurrencyCode,
    DecisionPostBankingOutcome,
    SourceType,
    ValidationStatus,
)
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.team_pack import SheetRegistry
from opc_mis.governance.evidence_validator import EvidenceValidator
from opc_mis.infrastructure.persistence.memory_artifact_repository import (
    InMemoryArtifactRepository,
)
from opc_mis.infrastructure.persistence.memory_dataset_repository import (
    InMemoryDatasetRepository,
)
from tests.unit.test_banking_discovery import (
    BASE_EVIDENCE,
    CASE_ID,
    CONTRACT_ID,
    _case,
    _envelope,
    _execution_context,
    _policy,
    _record,
    _request,
    _snapshot,
)


def _supplement(amount: int) -> tuple[BankingInputSupplement, EvidenceRef]:
    evidence = EvidenceRef(
        evidence_id=f"EVD-SUPPLEMENT-{amount}",
        source_type=SourceType.USER_INPUT,
        sheet="BANKING_INPUT_SUPPLEMENT",
        row_number=0,
        record_id=f"SUPPLEMENT-{amount}",
        field="requested_amount",
        display_value=amount,
    )
    return (
        BankingInputSupplement(
            supplement_id=f"SUPPLEMENT-{amount}",
            evaluation_case_id=CASE_ID,
            dataset_id="DATASET-BANKING-TEST",
            contract_id=CONTRACT_ID,
            banking_request_id="BANKING-REQUEST-TEST",
            requested_amount=amount,
            requested_amount_currency=CurrencyCode.VND,
            provider="FOUNDER",
            note="Amount supplied for deterministic Banking readiness.",
            resolved_request_ids=("MDR-AMOUNT-TEST",),
            source_artifact_ids=(
                "ARTIFACT-EVALUATION-CASE",
                "ARTIFACT-PRIOR-DECISION-REVIEW",
            ),
            evidence_ids=(evidence.evidence_id,),
        ),
        evidence,
    )


async def _scenario(
    *,
    amount: int | None,
    include_profile: bool = True,
    extra_required_field: str | None = None,
) -> SimpleNamespace:
    datasets = InMemoryDatasetRepository()
    artifacts = InMemoryArtifactRepository()
    snapshot = _snapshot(1)
    # Prove that neither readiness nor Decision depends on CREDIT_PROFILE.
    snapshot.sheets.pop(SheetRegistry.CREDIT_PROFILES.sheet_name, None)
    snapshot.indexes.pop(SheetRegistry.CREDIT_PROFILES.sheet_name, None)
    snapshot.headers.pop(SheetRegistry.CREDIT_PROFILES.sheet_name, None)
    if include_profile:
        profile_records = [
            _record(
                SheetRegistry.OPC_PROFILE.sheet_name,
                2,
                "company_id",
                {"field": "company_id", "value": "OPC-TEST"},
            ),
            _record(
                SheetRegistry.OPC_PROFILE.sheet_name,
                3,
                "business_model",
                {"field": "business_model", "value": None},
            ),
        ]
        snapshot.sheets[SheetRegistry.OPC_PROFILE.sheet_name] = profile_records
        snapshot.indexes[SheetRegistry.OPC_PROFILE.sheet_name] = {
            item.record_id: [item] for item in profile_records
        }
        snapshot.headers[SheetRegistry.OPC_PROFILE.sheet_name] = (
            SheetRegistry.OPC_PROFILE.required_headers
        )
    await datasets.register(snapshot)

    case_artifact = _envelope(
        artifact_id="ARTIFACT-EVALUATION-CASE",
        artifact_type=ArtifactType.EVALUATION_CASE,
        payload=_case().model_dump(mode="json"),
    )
    request_artifact = _envelope(
        artifact_id="ARTIFACT-BANKING-REQUEST",
        artifact_type=ArtifactType.BANKING_DISCOVERY_REQUEST,
        payload=_request().model_dump(mode="json"),
    )
    await artifacts.save(case_artifact)
    await artifacts.save(request_artifact)
    supplement = None
    supplement_artifact = None
    if amount is not None:
        supplement, supplement_evidence = _supplement(amount)
        supplement_artifact = _envelope(
            artifact_id=f"ARTIFACT-SUPPLEMENT-{amount}",
            artifact_type=ArtifactType.BANKING_INPUT_SUPPLEMENT,
            payload=supplement.model_dump(mode="json"),
            evidence_refs=(supplement_evidence,),
        )
        await artifacts.save(supplement_artifact)

    policy = _policy(1)
    discovery = BankingDiscoverySkill(
        context_loader=BankingDiscoveryContextLoader(
            datasets=datasets,
            artifacts=artifacts,
        ),
        policy=policy,
    )
    discovery_input_ids = (
        case_artifact.artifact_id,
        request_artifact.artifact_id,
        *((supplement_artifact.artifact_id,) if supplement_artifact else ()),
    )
    discovery_result = await discovery.execute(
        _execution_context(*discovery_input_ids)
    )
    matrix = discovery_result.option_matrix
    assert matrix is not None
    if extra_required_field is not None:
        candidate = matrix.candidates[0]
        assert candidate.precheck is not None
        changed_precheck = candidate.precheck.model_copy(
            update={
                "required_fields": (
                    *candidate.precheck.required_fields,
                    extra_required_field,
                )
            }
        )
        matrix = matrix.model_copy(
            update={
                "candidates": (
                    candidate.model_copy(update={"precheck": changed_precheck}),
                )
            }
        )
    matrix_draft = discovery_result.artifacts[0]
    matrix_artifact = _envelope(
        artifact_id=f"ARTIFACT-MATRIX-{amount or 'NONE'}",
        artifact_type=ArtifactType.BANKING_OPTION_MATRIX,
        payload=matrix.model_dump(mode="json"),
        evidence_refs=matrix_draft.evidence_refs,
    )
    await artifacts.save(matrix_artifact)

    readiness_skill = BankingPrecheckReadinessSkill(
        context_loader=BankingPrecheckReadinessContextLoader(
            datasets=datasets,
            artifacts=artifacts,
        ),
        policy=policy,
    )
    readiness_input_ids = (
        case_artifact.artifact_id,
        matrix_artifact.artifact_id,
        *((supplement_artifact.artifact_id,) if supplement_artifact else ()),
    )
    readiness_result = await readiness_skill.execute(
        _execution_context(*readiness_input_ids)
    )
    readiness = readiness_result.readiness
    assert readiness is not None
    readiness_artifact = _envelope(
        artifact_id=f"ARTIFACT-READINESS-{amount or 'NONE'}",
        artifact_type=ArtifactType.BANKING_PRECHECK_READINESS,
        payload=readiness.model_dump(mode="json"),
        evidence_refs=readiness_result.artifacts[0].evidence_refs,
    )
    await artifacts.save(readiness_artifact)

    decision = DecisionPostBankingReviewer(
        context_loader=DecisionPostBankingContextLoader(artifacts=artifacts)
    )
    decision_result = await decision.execute(
        _execution_context(matrix_artifact.artifact_id, readiness_artifact.artifact_id)
    )
    return SimpleNamespace(
        supplement=supplement,
        discovery=discovery_result,
        matrix=matrix,
        readiness_result=readiness_result,
        readiness=readiness,
        decision=decision_result,
    )


def test_missing_amount_is_assessed_then_decision_owns_the_durable_pause() -> None:
    scenario = asyncio.run(_scenario(amount=None))
    matrix = scenario.matrix
    readiness = scenario.readiness
    decision = scenario.decision

    assert {item.code for item in matrix.data_gaps} == {
        BankingDataGapCode.REQUESTED_AMOUNT_UNAVAILABLE
    }
    assert BankingDataGapCode.CREDIT_PROFILE_RELATIONSHIP_UNCONFIRMED not in {
        item.code for item in matrix.data_gaps
    }
    assert scenario.readiness_result.status is ComponentStatus.COMPLETED_WITH_WARNINGS
    assert scenario.readiness_result.missing_data_requests == ()
    assert len(scenario.readiness_result.artifacts) == 1
    assert readiness.status is BankingPrecheckReadinessStatus.INPUT_REQUIRED
    fields = {
        item.required_field: item for item in readiness.option_readiness[0].field_resolutions
    }
    assert fields["contract_id"].status is BankingPrecheckFieldStatus.RESOLVED
    assert fields["contract_id"].source is BankingPrecheckFieldSource.EVALUATION_CASE
    assert fields["amount"].status is BankingPrecheckFieldStatus.MISSING_INPUT
    assert fields["amount"].source is BankingPrecheckFieldSource.BANKING_INPUT_SUPPLEMENT
    assert fields["company_profile"].status is BankingPrecheckFieldStatus.RESOLVED
    assert fields["company_profile"].source is BankingPrecheckFieldSource.OPC_PROFILE

    assert decision.status is ComponentStatus.WAITING_FOR_INPUT
    assert decision.review.outcome is DecisionPostBankingOutcome.BANKING_INPUT_REQUIRED
    assert decision.review.banking_request_id == matrix.request_id
    assert len(decision.missing_data_requests) == 1
    request = decision.missing_data_requests[0]
    assert request.requirement_code == "BANKING_PRECHECK_AMOUNT_REQUIRED"
    assert request.target_record == matrix.request_id
    assert request.field == "requested_amount"
    assert decision.review.missing_data_requests == decision.missing_data_requests
    assert decision.artifacts[0].payload["missing_data_requests"] == [
        request.model_dump(mode="json")
    ]
    assert decision.approval_signals == ()
    assert decision.action_commands == ()


def test_valid_supplement_resolves_exact_sources_and_reaches_ready_review() -> None:
    scenario = asyncio.run(_scenario(amount=420_000_000))
    matrix = scenario.matrix
    readiness = scenario.readiness
    decision = scenario.decision

    assert matrix.requested_amount == 420_000_000
    assert matrix.data_gaps == ()
    matrix_check = next(
        item
        for item in matrix.candidates[0].criteria
        if item.code is BankingCriterionCode.MINIMUM_AMOUNT
    )
    assert matrix_check.status is BankingCriterionStatus.PASS
    assert readiness.status is BankingPrecheckReadinessStatus.READY
    readiness_check = readiness.option_readiness[0].requirement_checks[0]
    assert readiness_check == matrix_check
    assert readiness.ready_option_ids == (matrix.candidates[0].option_id,)
    assert readiness.precheck_executed is False
    assert decision.status is ComponentStatus.COMPLETED
    assert decision.review.outcome is DecisionPostBankingOutcome.BANKING_PRECHECK_READY
    assert decision.review.precheck_ready_option_ids == readiness.ready_option_ids
    assert decision.review.missing_data_requests == ()
    assert decision.review.precheck_executed is False
    assert decision.approval_signals == ()
    assert decision.action_commands == ()


def test_below_minimum_amount_is_not_a_viable_option_and_not_an_input_gap() -> None:
    scenario = asyncio.run(_scenario(amount=200_000_000))
    matrix_check = next(
        item
        for item in scenario.matrix.candidates[0].criteria
        if item.code is BankingCriterionCode.MINIMUM_AMOUNT
    )

    assert matrix_check.status is BankingCriterionStatus.FAIL
    assert (
        scenario.readiness.status
        is BankingPrecheckReadinessStatus.OPTION_REQUIREMENTS_NOT_MET
    )
    assert scenario.readiness.option_readiness[0].failed_requirement_codes == (
        BankingCriterionCode.MINIMUM_AMOUNT,
    )
    assert scenario.decision.review.outcome is DecisionPostBankingOutcome.NO_VIABLE_OPTION
    assert scenario.decision.missing_data_requests == ()
    assert scenario.decision.status is ComponentStatus.COMPLETED_WITH_WARNINGS
    assert scenario.decision.approval_signals == ()
    assert scenario.decision.action_commands == ()


def test_unknown_api_field_is_not_fuzzy_mapped_or_requested_from_founder() -> None:
    scenario = asyncio.run(
        _scenario(amount=420_000_000, extra_required_field="beneficiary_profile")
    )
    option = scenario.readiness.option_readiness[0]

    assert scenario.readiness.status is BankingPrecheckReadinessStatus.UNSUPPORTED_MAPPING
    assert option.unmapped_fields == ("beneficiary_profile",)
    unmapped = option.field_resolutions[-1]
    assert unmapped.status is BankingPrecheckFieldStatus.UNMAPPED
    assert unmapped.source is None
    assert (
        scenario.decision.review.outcome
        is DecisionPostBankingOutcome.UNSUPPORTED_PRECHECK_MAPPING
    )
    assert scenario.decision.missing_data_requests == ()
    assert scenario.decision.approval_signals == ()
    assert scenario.decision.action_commands == ()


def test_missing_opc_profile_is_a_decision_owned_blocker_not_a_credit_fallback() -> None:
    scenario = asyncio.run(_scenario(amount=420_000_000, include_profile=False))

    assert scenario.readiness.status is BankingPrecheckReadinessStatus.INPUT_REQUIRED
    assert scenario.decision.status is ComponentStatus.WAITING_FOR_INPUT
    assert len(scenario.decision.missing_data_requests) == 1
    request = scenario.decision.missing_data_requests[0]
    assert request.requirement_code == "BANKING_COMPANY_PROFILE_REQUIRED"
    assert request.field == "company_profile"
    assert scenario.decision.review.missing_data_requests == (request,)
    assert scenario.decision.approval_signals == ()
    assert scenario.decision.action_commands == ()


def test_validator_accepts_exact_artifacts_and_typed_unsupported_mapping() -> None:
    policy = _policy(1)
    for scenario in (
        asyncio.run(_scenario(amount=None)),
        asyncio.run(_scenario(amount=420_000_000)),
    ):
        drafts = (
            scenario.discovery.artifacts[0],
            scenario.readiness_result.artifacts[0],
            scenario.decision.artifacts[0],
        )
        reports = tuple(
            asyncio.run(EvidenceValidator(banking_policy=policy).validate(draft))
            for draft in drafts
        )
        assert all(report.status is ValidationStatus.VALID for report in reports)

    unsupported = asyncio.run(
        _scenario(amount=420_000_000, extra_required_field="beneficiary_profile")
    )
    report = asyncio.run(
        EvidenceValidator(banking_policy=policy).validate(
            unsupported.readiness_result.artifacts[0]
        )
    )
    assert report.status is ValidationStatus.VALID


def test_validator_blocks_numeric_amount_status_and_lineage_tampering() -> None:
    scenario = asyncio.run(_scenario(amount=420_000_000))
    candidate = scenario.matrix.candidates[0]
    minimum = next(
        item
        for item in candidate.criteria
        if item.code is BankingCriterionCode.MINIMUM_AMOUNT
    )
    tampered_minimum = minimum.model_copy(
        update={
            "status": BankingCriterionStatus.FAIL,
            "evidence_ids": tuple(
                evidence_id
                for evidence_id in minimum.evidence_ids
                if evidence_id not in scenario.supplement.evidence_ids
            ),
        }
    )
    tampered_candidate = candidate.model_copy(
        update={
            "criteria": tuple(
                tampered_minimum
                if item.code is BankingCriterionCode.MINIMUM_AMOUNT
                else item
                for item in candidate.criteria
            )
        }
    )
    tampered_matrix = scenario.matrix.model_copy(
        update={"candidates": (tampered_candidate,)}
    )
    draft = scenario.discovery.artifacts[0].model_copy(
        update={"payload": tampered_matrix.model_dump(mode="json")}
    )

    report = asyncio.run(
        EvidenceValidator(banking_policy=_policy(1)).validate(draft)
    )

    assert report.status is ValidationStatus.BLOCKED
    assert any("numeric inputs" in error for error in report.blocking_errors)
    assert any("exact USER_INPUT" in error for error in report.blocking_errors)


def test_validator_blocks_non_finite_values_and_non_immutable_request() -> None:
    scenario = asyncio.run(_scenario(amount=420_000_000))
    candidate = scenario.matrix.candidates[0].model_copy(
        update={"minimum_amount": float("nan")}
    )
    non_finite = scenario.matrix.model_copy(update={"candidates": (candidate,)})
    non_finite_draft = scenario.discovery.artifacts[0].model_copy(
        update={"payload": non_finite.model_dump(mode="python")}
    )
    non_finite_report = asyncio.run(
        EvidenceValidator(banking_policy=_policy(1)).validate(non_finite_draft)
    )

    request_payload = _request().model_dump(mode="json")
    request_payload["requested_amount"] = 420_000_000
    request_payload["action_command"] = {"action": "SUBMIT_BANKING_PRECHECK"}
    request_report = asyncio.run(
        EvidenceValidator().validate(
            ArtifactDraft(
                artifact_type=ArtifactType.BANKING_DISCOVERY_REQUEST,
                evaluation_case_id=CASE_ID,
                producer="DECISION_BANKING_HANDOFF",
                payload=request_payload,
                evidence_refs=(BASE_EVIDENCE,),
            )
        )
    )

    assert non_finite_report.status is ValidationStatus.BLOCKED
    assert any("non-finite" in error for error in non_finite_report.blocking_errors)
    assert request_report.status is ValidationStatus.BLOCKED
    assert any(
        "Invalid BANKING_DISCOVERY_REQUEST schema" in error
        for error in request_report.blocking_errors
    )


def test_validator_blocks_readiness_field_source_substitution() -> None:
    scenario = asyncio.run(_scenario(amount=420_000_000))
    option = scenario.readiness.option_readiness[0]
    resolutions = tuple(
        field.model_copy(
            update={
                "source": BankingPrecheckFieldSource.EVALUATION_CASE,
                "source_reference": "EvaluationCase.contract_id",
                "source_artifact_id": "ARTIFACT-EVALUATION-CASE",
                "source_record_ids": (CONTRACT_ID,),
            }
        )
        if field.required_field == "amount"
        else field
        for field in option.field_resolutions
    )
    changed_option = option.model_copy(update={"field_resolutions": resolutions})
    changed_readiness = scenario.readiness.model_copy(
        update={"option_readiness": (changed_option,)}
    )
    draft = scenario.readiness_result.artifacts[0].model_copy(
        update={"payload": changed_readiness.model_dump(mode="json")}
    )

    report = asyncio.run(
        EvidenceValidator(banking_policy=_policy(1)).validate(draft)
    )

    assert report.status is ValidationStatus.BLOCKED
    assert any("exact policy source" in error for error in report.blocking_errors)
