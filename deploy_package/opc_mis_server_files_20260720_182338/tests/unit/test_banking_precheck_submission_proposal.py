"""Unit tests for side-effect-free Banking precheck submission proposals."""

import asyncio
import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from opc_mis.business.skills.banking.precheck_submission_component import (
    BankingPrecheckSubmissionProposalSkill,
)
from opc_mis.business.skills.banking.precheck_submission_context import (
    BankingPrecheckSubmissionProposalContextLoader,
)
from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.banking_models import (
    BankingCatalogPolicy,
    BankingCriterion,
    BankingHandlingGuidance,
    BankingNeedBinding,
    BankingOptionCandidate,
    BankingOptionMatrix,
    BankingOptionPrecheckReadiness,
    BankingPrecheckFieldResolution,
    BankingPrecheckReadiness,
    BankingPrecheckReference,
)
from opc_mis.domain.banking_precheck_submission_models import (
    BankingPrecheckSubmissionProposal,
)
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.decision_post_banking_models import DecisionPostBankingReview
from opc_mis.domain.enums import (
    ArtifactStatus,
    ArtifactType,
    BankingCriterionCode,
    BankingCriterionStatus,
    BankingDiscoveryStatus,
    BankingHandlingPolicyEffect,
    BankingNeedType,
    BankingPrecheckFieldSource,
    BankingPrecheckFieldStatus,
    BankingPrecheckReadinessStatus,
    BankingPrecheckStatus,
    ComponentStatus,
    CurrencyCode,
    DecisionPostBankingOutcome,
    EvaluationScope,
    ProtectedAction,
    SourceType,
    ValidationStatus,
)
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.team_pack import SheetRegistry
from opc_mis.infrastructure.persistence.memory_artifact_repository import (
    InMemoryArtifactRepository,
)

CASE_ID = "CASE-PRECHECK-PROPOSAL"
DATASET_ID = "DATASET-PRECHECK-PROPOSAL"
CONTRACT_ID = "CONTRACT-PRECHECK-PROPOSAL"
REQUEST_ID = "BANKING-REQUEST-PRECHECK-PROPOSAL"
MATRIX_ARTIFACT_ID = "ART-MATRIX-PRECHECK-PROPOSAL"
READINESS_ARTIFACT_ID = "ART-READINESS-PRECHECK-PROPOSAL"
REVIEW_ARTIFACT_ID = "ART-REVIEW-PRECHECK-PROPOSAL"
CASE_ARTIFACT_ID = "ART-CASE-PRECHECK-PROPOSAL"
REQUEST_ARTIFACT_ID = "ART-REQUEST-PRECHECK-PROPOSAL"
SUPPLEMENT_ARTIFACT_ID = "ART-SUPPLEMENT-PRECHECK-PROPOSAL"
SOURCE_ARTIFACT_IDS = (
    MATRIX_ARTIFACT_ID,
    READINESS_ARTIFACT_ID,
    REVIEW_ARTIFACT_ID,
    CASE_ARTIFACT_ID,
    REQUEST_ARTIFACT_ID,
    SUPPLEMENT_ARTIFACT_ID,
)
AMOUNT = 350_000_000


def _proposal_policy(option_count: int = 1) -> BankingCatalogPolicy:
    """Return a server-policy fixture aligned with the synthetic proposal options."""
    product_ids = tuple(f"BANK-PRODUCT-{index}" for index in range(1, option_count + 1))
    return BankingCatalogPolicy(
        policy_id="BANKING-POLICY",
        mapping_version="1",
        policy_hash="POLICY-HASH",
        bindings=(
            BankingNeedBinding(
                binding_id="BINDING-PRECHECK-PROPOSAL",
                need_type=BankingNeedType.PERFORMANCE_BOND,
                bank_product_ids=product_ids,
                precheck_api_by_product={
                    product_id: f"API-{index}"
                    for index, product_id in enumerate(product_ids, start=1)
                },
                precheck_field_sources_by_api={
                    f"API-{index}": {
                        "contract_id": BankingPrecheckFieldSource.EVALUATION_CASE,
                        "amount": (
                            BankingPrecheckFieldSource.BANKING_INPUT_SUPPLEMENT
                        ),
                        "company_profile": BankingPrecheckFieldSource.OPC_PROFILE,
                    }
                    for index in range(1, option_count + 1)
                },
                handling_rule_ids=("API-H-TEST",),
            ),
        ),
    )


def _evidence(
    evidence_id: str,
    *,
    sheet: str,
    record_id: str,
    field: str,
    display_value: object,
    source_type: SourceType = SourceType.TEAM_PACK,
    source_evidence_ids: tuple[str, ...] = (),
) -> EvidenceRef:
    return EvidenceRef(
        evidence_id=evidence_id,
        source_type=source_type,
        sheet=sheet,
        row_number=0 if source_type is not SourceType.TEAM_PACK else 2,
        record_id=record_id,
        field=field,
        display_value=display_value,
        source_evidence_ids=source_evidence_ids,
    )


def _option_evidence(index: int) -> tuple[EvidenceRef, ...]:
    product_id = f"BANK-PRODUCT-{index}"
    values = {
        "bank": f"BANK-{index}",
        "product_name": f"Performance Bond {index}",
        "annual_rate_or_fee": 0.02 + index / 1000,
        "processing_fee_rate": 0.005,
        "collateral_ratio": 0.1,
        "minimum_amount": 300_000_000,
    }
    product = tuple(
        _evidence(
            f"EVD-PRODUCT-{index}-{field}",
            sheet=SheetRegistry.BANK_PRODUCTS.sheet_name,
            record_id=product_id,
            field=field,
            display_value=value,
        )
        for field, value in values.items()
    )
    api_values = {
        "provider": f"BANK-{index}",
        "method": "POST",
        "endpoint": f"/mock/bank-{index}/precheck",
        "required_fields": "contract_id, amount, company_profile",
        "extension_rule": "Human approval before submission",
    }
    api = tuple(
        _evidence(
            f"EVD-API-{index}-{field}",
            sheet=SheetRegistry.API_CATALOG.sheet_name,
            record_id=f"API-{index}",
            field=field,
            display_value=value,
        )
        for field, value in api_values.items()
    )
    handling_values = {
        "rule_id": "API-H-TEST",
        "applies_to": "Financial partner recommendation",
        "requires_human_approval": "Yes before submission",
    }
    handling = tuple(
        _evidence(
            f"EVD-HANDLING-TEST-{field}",
            sheet=SheetRegistry.API_HANDLING_RULES.sheet_name,
            record_id="API-H-TEST",
            field=field,
            display_value=value,
        )
        for field, value in handling_values.items()
    )
    case_source = _evidence(
        "EVD-CASE-SOURCE",
        sheet="EVALUATION_CASE",
        record_id=CONTRACT_ID,
        field="contract_id",
        display_value=CONTRACT_ID,
        source_type=SourceType.DERIVED,
    )
    amount_source = _evidence(
        "EVD-SUPPLEMENT-AMOUNT",
        sheet="BANKING_INPUT_SUPPLEMENT",
        record_id="SUPPLEMENT-PRECHECK-PROPOSAL",
        field="requested_amount",
        display_value=AMOUNT,
        source_type=SourceType.USER_INPUT,
    )
    profile_sources = tuple(
        _evidence(
            f"EVD-PROFILE-{record_id}-{field}",
            sheet=SheetRegistry.OPC_PROFILE.sheet_name,
            record_id=record_id,
            field=field,
            display_value=record_id if field == "field" else value,
        )
        for record_id, value in (
            ("company_id", "OPC-PRECHECK-PROPOSAL"),
            ("business_model", "B2B"),
        )
        for field in ("field", "value")
    )
    api_required_id = f"EVD-API-{index}-required_fields"
    binding_sources = {
        "contract_id": (api_required_id, case_source.evidence_id),
        "amount": (api_required_id, amount_source.evidence_id),
        "company_profile": (
            api_required_id,
            *(item.evidence_id for item in profile_sources),
        ),
    }
    binding_source_types = {
        "contract_id": BankingPrecheckFieldSource.EVALUATION_CASE,
        "amount": BankingPrecheckFieldSource.BANKING_INPUT_SUPPLEMENT,
        "company_profile": BankingPrecheckFieldSource.OPC_PROFILE,
    }
    binding_source_references = {
        "contract_id": "EvaluationCase.contract_id",
        "amount": "BankingInputSupplement.requested_amount",
        "company_profile": "02_OPC_PROFILE[field,value]",
    }
    bindings = tuple(
        _evidence(
            f"EVD-BINDING-{index}-{field}",
            sheet="BANKING_PRECHECK_READINESS",
            record_id="MATRIX-PRECHECK-PROPOSAL",
            field=field,
            display_value={
                "status": "RESOLVED",
                "source": binding_source_types[field].value,
                "source_reference": binding_source_references[field],
            },
            source_type=SourceType.DERIVED,
            source_evidence_ids=binding_sources[field],
        )
        for field in ("contract_id", "amount", "company_profile")
    )
    return (
        *product,
        *api,
        *handling,
        case_source,
        amount_source,
        *profile_sources,
        *bindings,
    )


def _candidate(
    index: int,
    *,
    minimum_status: BankingCriterionStatus = BankingCriterionStatus.PASS,
) -> BankingOptionCandidate:
    evidence = _option_evidence(index)
    by_field = {item.field: item for item in evidence}
    minimum = BankingCriterion(
        criterion_id=f"CRITERION-MINIMUM-{index}",
        code=BankingCriterionCode.MINIMUM_AMOUNT,
        status=minimum_status,
        detail="Exact catalog minimum comparison from the matrix.",
        evidence_ids=(by_field["minimum_amount"].evidence_id,),
    )
    return BankingOptionCandidate(
        option_id=f"OPTION-{index}",
        need_type=BankingNeedType.PERFORMANCE_BOND,
        bank_product_id=f"BANK-PRODUCT-{index}",
        provider=f"BANK-{index}",
        product_name=f"Performance Bond {index}",
        target_segment="SME",
        description="Configured performance-bond option.",
        annual_rate_or_fee=0.02 + index / 1000,
        processing_fee_rate=0.005,
        collateral_ratio=0.1,
        minimum_amount=300_000_000,
        minimum_amount_currency=CurrencyCode.VND,
        automation_level="MOCK",
        fit_note="Catalog fact only; not a recommendation.",
        criteria=(minimum,),
        precheck=BankingPrecheckReference(
            api_id=f"API-{index}",
            provider=f"BANK-{index}",
            method="POST",
            endpoint=f"/mock/bank-{index}/precheck",
            description="Mock precheck metadata.",
            required_fields=("contract_id", "amount", "company_profile"),
            catalog_status="MOCK",
            extension_rule="Human approval before submission",
            status=BankingPrecheckStatus.MOCK_AVAILABLE_NOT_EXECUTED,
            precheck_executed=False,
            evidence_ids=tuple(
                item.evidence_id
                for item in evidence
                if item.sheet == SheetRegistry.API_CATALOG.sheet_name
            ),
        ),
        handling_guidance=(
            BankingHandlingGuidance(
                rule_id="API-H-TEST",
                applies_to="Financial partner recommendation",
                possible_issue="Evidence incomplete",
                team_visible_meaning="Recommendation confidence is low",
                required_handling="Request missing evidence",
                source_requires_human_approval_text="Yes before submission",
                sensitive_fields="company_profile, contract_id",
                note="No fabricated approval",
                policy_effect=BankingHandlingPolicyEffect.SOURCE_GUIDANCE_ONLY,
                evidence_ids=tuple(
                    item.evidence_id
                    for item in evidence
                    if item.sheet == SheetRegistry.API_HANDLING_RULES.sheet_name
                ),
            ),
        ),
        evidence_ids=tuple(item.evidence_id for item in evidence),
    )


def _option_readiness(
    index: int,
    *,
    status: BankingPrecheckReadinessStatus = BankingPrecheckReadinessStatus.READY,
) -> BankingOptionPrecheckReadiness:
    evidence = {item.field: item for item in _option_evidence(index)}
    resolutions = (
        BankingPrecheckFieldResolution(
            required_field="contract_id",
            status=BankingPrecheckFieldStatus.RESOLVED,
            source=BankingPrecheckFieldSource.EVALUATION_CASE,
            source_reference="EvaluationCase.contract_id",
            source_artifact_id=CASE_ARTIFACT_ID,
            source_record_ids=(CONTRACT_ID,),
            evidence_ids=(evidence["contract_id"].evidence_id,),
        ),
        BankingPrecheckFieldResolution(
            required_field="amount",
            status=BankingPrecheckFieldStatus.RESOLVED,
            source=BankingPrecheckFieldSource.BANKING_INPUT_SUPPLEMENT,
            source_reference="BankingInputSupplement.requested_amount",
            source_artifact_id=SUPPLEMENT_ARTIFACT_ID,
            source_record_ids=("SUPPLEMENT-PRECHECK-PROPOSAL",),
            evidence_ids=(evidence["amount"].evidence_id,),
        ),
        BankingPrecheckFieldResolution(
            required_field="company_profile",
            status=BankingPrecheckFieldStatus.RESOLVED,
            source=BankingPrecheckFieldSource.OPC_PROFILE,
            source_reference="02_OPC_PROFILE[field,value]",
            source_artifact_id=None,
            source_record_ids=("company_id", "business_model"),
            evidence_ids=(evidence["company_profile"].evidence_id,),
        ),
    )
    failed = status is BankingPrecheckReadinessStatus.OPTION_REQUIREMENTS_NOT_MET
    minimum = BankingCriterion(
        criterion_id=f"CRITERION-MINIMUM-{index}",
        code=BankingCriterionCode.MINIMUM_AMOUNT,
        status=(
            BankingCriterionStatus.FAIL if failed else BankingCriterionStatus.PASS
        ),
        detail="Exact catalog minimum comparison from the matrix.",
        evidence_ids=(evidence["minimum_amount"].evidence_id,),
    )
    return BankingOptionPrecheckReadiness(
        option_readiness_id=f"OPTION-READINESS-{index}",
        option_id=f"OPTION-{index}",
        bank_product_id=f"BANK-PRODUCT-{index}",
        api_id=f"API-{index}",
        status=status,
        required_fields=("contract_id", "amount", "company_profile"),
        field_resolutions=resolutions,
        requirement_checks=(minimum,),
        failed_requirement_codes=(
            (BankingCriterionCode.MINIMUM_AMOUNT,) if failed else ()
        ),
        evidence_ids=tuple(item.evidence_id for item in _option_evidence(index)),
    )


def _envelope(
    *,
    artifact_id: str,
    artifact_type: ArtifactType,
    payload: dict[str, object],
    evidence_refs: tuple[EvidenceRef, ...],
    validation_status: ValidationStatus = ValidationStatus.VALID,
) -> ArtifactEnvelope:
    return ArtifactEnvelope(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        evaluation_case_id=CASE_ID,
        producer="UPSTREAM-TEST",
        version=1,
        status=ArtifactStatus.CREATED,
        payload=payload,
        evidence_refs=evidence_refs,
        input_artifact_ids=(),
        input_hash=f"HASH-{artifact_id}",
        validation_status=validation_status,
        validation_notes=(),
        created_at=datetime(2026, 7, 18, tzinfo=UTC),
    )


async def _setup(
    *,
    ready_count: int = 1,
    pending_count: int = 0,
) -> tuple[
    InMemoryArtifactRepository,
    BankingPrecheckSubmissionProposalSkill,
    ExecutionContext,
]:
    candidates = tuple(
        _candidate(index)
        for index in range(1, ready_count + 1)
    ) + tuple(
        _candidate(index, minimum_status=BankingCriterionStatus.FAIL)
        for index in range(ready_count + 1, ready_count + pending_count + 1)
    )
    option_readiness = tuple(
        _option_readiness(index)
        for index in range(1, ready_count + 1)
    ) + tuple(
        _option_readiness(
            index,
            status=BankingPrecheckReadinessStatus.OPTION_REQUIREMENTS_NOT_MET,
        )
        for index in range(ready_count + 1, ready_count + pending_count + 1)
    )
    ready_ids = tuple(item.option_id for item in option_readiness[:ready_count])
    pending_ids = tuple(item.option_id for item in option_readiness[ready_count:])
    all_evidence = tuple(
        item
        for index in range(1, ready_count + pending_count + 1)
        for item in _option_evidence(index)
    )
    matrix = BankingOptionMatrix(
        matrix_id="MATRIX-PRECHECK-PROPOSAL",
        evaluation_case_id=CASE_ID,
        dataset_id=DATASET_ID,
        contract_id=CONTRACT_ID,
        request_id=REQUEST_ID,
        mapping_policy_id="BANKING-POLICY",
        mapping_version="1",
        mapping_hash="POLICY-HASH",
        discovery_status=BankingDiscoveryStatus.OPTIONS_READY,
        requested_need_types=(BankingNeedType.PERFORMANCE_BOND,),
        requested_amount=AMOUNT,
        requested_amount_currency=CurrencyCode.VND,
        candidates=candidates,
        source_artifact_ids=(
            CASE_ARTIFACT_ID,
            REQUEST_ARTIFACT_ID,
            SUPPLEMENT_ARTIFACT_ID,
        ),
        evidence_ids=tuple(item.evidence_id for item in all_evidence),
    )
    readiness = BankingPrecheckReadiness(
        readiness_id="READINESS-PRECHECK-PROPOSAL",
        evaluation_case_id=CASE_ID,
        dataset_id=DATASET_ID,
        contract_id=CONTRACT_ID,
        matrix_id=matrix.matrix_id,
        supplement_id="SUPPLEMENT-PRECHECK-PROPOSAL",
        requested_amount_currency=CurrencyCode.VND,
        status=(
            BankingPrecheckReadinessStatus.READY
            if not pending_count
            else BankingPrecheckReadinessStatus.PARTIALLY_READY
        ),
        option_readiness=option_readiness,
        ready_option_ids=ready_ids,
        pending_option_ids=pending_ids,
        source_artifact_ids=(
            CASE_ARTIFACT_ID,
            MATRIX_ARTIFACT_ID,
            SUPPLEMENT_ARTIFACT_ID,
        ),
        evidence_ids=tuple(item.evidence_id for item in all_evidence),
        precheck_executed=False,
    )
    review = DecisionPostBankingReview(
        review_id="REVIEW-PRECHECK-PROPOSAL",
        evaluation_case_id=CASE_ID,
        dataset_id=DATASET_ID,
        contract_id=CONTRACT_ID,
        matrix_id=matrix.matrix_id,
        banking_request_id=matrix.request_id,
        readiness_id=readiness.readiness_id,
        outcome=DecisionPostBankingOutcome.BANKING_PRECHECK_READY,
        candidate_option_ids=tuple(item.option_id for item in candidates),
        precheck_ready_option_ids=ready_ids,
        pending_option_ids=pending_ids,
        source_artifact_ids=(MATRIX_ARTIFACT_ID, READINESS_ARTIFACT_ID),
        evidence_ids=tuple(item.evidence_id for item in all_evidence),
        precheck_executed=False,
    )
    upstream_evidence = (
        _evidence(
            "EVD-CASE-SOURCE",
            sheet="EVALUATION_CASE",
            record_id=CONTRACT_ID,
            field="contract_id",
            display_value=CONTRACT_ID,
            source_type=SourceType.DERIVED,
        ),
        _evidence(
            "EVD-REQUEST",
            sheet="BANKING_DISCOVERY_REQUEST",
            record_id=REQUEST_ID,
            field="request_id",
            display_value=REQUEST_ID,
            source_type=SourceType.DERIVED,
        ),
        _evidence(
            "EVD-SUPPLEMENT-AMOUNT",
            sheet="BANKING_INPUT_SUPPLEMENT",
            record_id="SUPPLEMENT-PRECHECK-PROPOSAL",
            field="requested_amount",
            display_value=AMOUNT,
            source_type=SourceType.USER_INPUT,
        ),
    )
    envelopes = (
        _envelope(
            artifact_id=MATRIX_ARTIFACT_ID,
            artifact_type=ArtifactType.BANKING_OPTION_MATRIX,
            payload=matrix.model_dump(mode="json"),
            evidence_refs=all_evidence,
        ),
        _envelope(
            artifact_id=READINESS_ARTIFACT_ID,
            artifact_type=ArtifactType.BANKING_PRECHECK_READINESS,
            payload=readiness.model_dump(mode="json"),
            evidence_refs=all_evidence,
        ),
        _envelope(
            artifact_id=REVIEW_ARTIFACT_ID,
            artifact_type=ArtifactType.DECISION_POST_BANKING_REVIEW,
            payload=review.model_dump(mode="json"),
            evidence_refs=all_evidence,
        ),
        _envelope(
            artifact_id=CASE_ARTIFACT_ID,
            artifact_type=ArtifactType.EVALUATION_CASE,
            payload={"placeholder": "validated upstream"},
            evidence_refs=(upstream_evidence[0],),
        ),
        _envelope(
            artifact_id=REQUEST_ARTIFACT_ID,
            artifact_type=ArtifactType.BANKING_DISCOVERY_REQUEST,
            payload={"placeholder": "validated upstream"},
            evidence_refs=(upstream_evidence[1],),
        ),
        _envelope(
            artifact_id=SUPPLEMENT_ARTIFACT_ID,
            artifact_type=ArtifactType.BANKING_INPUT_SUPPLEMENT,
            payload={"placeholder": "validated upstream"},
            evidence_refs=(upstream_evidence[2],),
        ),
    )
    repository = InMemoryArtifactRepository()
    for envelope in envelopes:
        await repository.save(envelope)
    skill = BankingPrecheckSubmissionProposalSkill(
        context_loader=BankingPrecheckSubmissionProposalContextLoader(
            artifacts=repository
        )
    )
    execution = ExecutionContext(
        evaluation_case_id=CASE_ID,
        dataset_id=DATASET_ID,
        workflow_run_id="WORKFLOW-PRECHECK-PROPOSAL",
        input_artifact_ids=SOURCE_ARTIFACT_IDS,
        requested_scope=(
            EvaluationScope.FINANCE,
            EvaluationScope.OPERATIONS,
            EvaluationScope.RISK,
        ),
        current_node="BANKING_PRECHECK_SUBMISSION_PROPOSAL",
    )
    return repository, skill, execution


def test_proposal_batches_all_ready_options_and_retains_reference_only_inputs() -> None:
    async def scenario() -> None:
        repository, skill, execution = await _setup(ready_count=2)
        before = await repository.list_by_case(CASE_ID)

        result = await skill.execute(execution)

        assert result.status is ComponentStatus.COMPLETED
        assert result.proposal is not None
        proposal = result.proposal
        assert proposal.proposal_mode == "BATCH_ALL_READY_OPTIONS"
        assert proposal.proposed_action is ProtectedAction.SUBMIT_BANKING_PRECHECK
        assert "approval_required" not in BankingPrecheckSubmissionProposal.model_fields
        assert proposal.requested_amount == AMOUNT
        assert proposal.candidate_option_ids == ("OPTION-1", "OPTION-2")
        assert tuple(item.option_id for item in proposal.candidates) == (
            "OPTION-1",
            "OPTION-2",
        )
        assert proposal.non_ready_option_ids == ()
        assert proposal.source_artifact_ids == SOURCE_ARTIFACT_IDS
        first = proposal.candidates[0]
        assert first.governance_source_facts.api_extension_rule == (
            "Human approval before submission"
        )
        assert first.governance_source_facts.handling_rules[0].rule_id == "API-H-TEST"
        assert first.catalog_terms.minimum_amount == 300_000_000
        assert first.catalog_terms.annual_rate_or_fee == pytest.approx(0.021)
        assert first.catalog_terms.processing_fee_rate == pytest.approx(0.005)
        assert first.catalog_terms.collateral_ratio == pytest.approx(0.1)
        assert tuple(item.required_field for item in first.field_bindings) == (
            "contract_id",
            "amount",
            "company_profile",
        )
        assert all(item.source_record_ids for item in first.field_bindings)
        assert not any(hasattr(item, "value") for item in first.field_bindings)
        assert proposal.precheck_executed is False
        assert proposal.submission_executed is False
        assert len(result.artifacts) == 1
        assert result.artifacts[0].artifact_type is (
            ArtifactType.BANKING_PRECHECK_SUBMISSION_PROPOSAL
        )
        serialized = json.dumps(result.artifacts[0].payload, sort_keys=True)
        assert "external_response" not in serialized
        assert "request_body" not in serialized
        assert result.approval_signals == ()
        assert result.action_commands == ()
        assert result.missing_data_requests == ()
        assert await repository.list_by_case(CASE_ID) == before

    asyncio.run(scenario())


def test_partial_readiness_batches_every_ready_option_without_selecting_pending() -> None:
    async def scenario() -> None:
        _, skill, execution = await _setup(ready_count=2, pending_count=1)

        result = await skill.execute(execution)

        assert result.proposal is not None
        assert result.proposal.candidate_option_ids == ("OPTION-1", "OPTION-2")
        assert result.proposal.non_ready_option_ids == ("OPTION-3",)
        assert len(result.proposal.candidates) == 2

    asyncio.run(scenario())


def test_proposal_identity_ignores_runtime_id_and_is_evidence_stable() -> None:
    async def scenario() -> None:
        _, skill, execution = await _setup()

        first = await skill.execute(execution)
        retried = await skill.execute(
            execution.model_copy(update={"workflow_run_id": "ANOTHER-RUNTIME-ID"})
        )

        assert first.proposal is not None
        assert retried.proposal is not None
        assert first.proposal.proposal_id == retried.proposal.proposal_id
        assert first.proposal.candidates[0].proposal_item_id == (
            retried.proposal.candidates[0].proposal_item_id
        )
        assert first.artifacts[0].identity_inputs == retried.artifacts[0].identity_inputs
        assert first.artifacts[0].evidence_refs == retried.artifacts[0].evidence_refs

    asyncio.run(scenario())


def test_proposal_fails_safe_for_non_exact_artifact_order() -> None:
    async def scenario() -> None:
        _, skill, execution = await _setup()
        wrong_order = execution.model_copy(
            update={
                "input_artifact_ids": (
                    READINESS_ARTIFACT_ID,
                    MATRIX_ARTIFACT_ID,
                    *SOURCE_ARTIFACT_IDS[2:],
                )
            }
        )

        result = await skill.execute(wrong_order)

        assert result.status is ComponentStatus.FAILED_SAFE
        assert result.proposal is None
        assert result.artifacts == ()
        assert "stable matrix/readiness/review/upstream order" in (
            result.runtime_events[0].message
        )

    asyncio.run(scenario())


def test_proposal_fails_safe_when_review_is_not_ready() -> None:
    async def scenario() -> None:
        repository, skill, execution = await _setup()
        artifact = await repository.get(REVIEW_ARTIFACT_ID)
        assert artifact is not None
        review = DecisionPostBankingReview.model_validate(artifact.payload)
        stale = review.model_copy(
            update={"outcome": DecisionPostBankingOutcome.NO_VIABLE_OPTION}
        )
        await repository.save(
            artifact.model_copy(update={"payload": stale.model_dump(mode="json")})
        )

        result = await skill.execute(execution)

        assert result.status is ComponentStatus.FAILED_SAFE
        assert result.proposal is None
        assert result.approval_signals == ()
        assert result.action_commands == ()

    asyncio.run(scenario())


def test_proposal_rejects_an_index_that_omits_a_ready_option() -> None:
    async def scenario() -> None:
        repository, skill, execution = await _setup(ready_count=2)
        readiness_artifact = await repository.get(READINESS_ARTIFACT_ID)
        review_artifact = await repository.get(REVIEW_ARTIFACT_ID)
        assert readiness_artifact is not None
        assert review_artifact is not None
        readiness = BankingPrecheckReadiness.model_validate(
            readiness_artifact.payload
        ).model_copy(
            update={
                "ready_option_ids": ("OPTION-1",),
                "pending_option_ids": ("OPTION-2",),
            }
        )
        review = DecisionPostBankingReview.model_validate(
            review_artifact.payload
        ).model_copy(
            update={
                "precheck_ready_option_ids": ("OPTION-1",),
                "pending_option_ids": ("OPTION-2",),
            }
        )
        await repository.save(
            readiness_artifact.model_copy(
                update={"payload": readiness.model_dump(mode="json")}
            )
        )
        await repository.save(
            review_artifact.model_copy(
                update={"payload": review.model_dump(mode="json")}
            )
        )

        result = await skill.execute(execution)

        assert result.status is ComponentStatus.FAILED_SAFE
        assert result.proposal is None
        assert "include every READY option" in result.runtime_events[0].message

    asyncio.run(scenario())


def test_domain_rejects_an_unrelated_protected_action() -> None:
    async def scenario() -> None:
        _, skill, execution = await _setup()
        result = await skill.execute(execution)
        assert result.proposal is not None
        payload = result.proposal.model_dump(mode="json")
        payload["proposed_action"] = "SEND_DOCUMENT_TO_EXTERNAL_PARTNER"

        with pytest.raises(ValidationError):
            BankingPrecheckSubmissionProposal.model_validate(payload)

    asyncio.run(scenario())
