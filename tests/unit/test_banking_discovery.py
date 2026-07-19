"""Unit tests for deterministic Banking discovery and bounded option advice."""

import asyncio
import json
from datetime import UTC, datetime

from opc_mis.business.skills.banking.advisor_component import (
    BankingOptionAdvisorSkill,
)
from opc_mis.business.skills.banking.advisor_context import (
    BankingAdvisorContextLoader,
)
from opc_mis.business.skills.banking.component import BankingDiscoverySkill
from opc_mis.business.skills.banking.context_loader import (
    BankingDiscoveryContextLoader,
)
from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.banking_models import (
    BankingAdviceComposition,
    BankingCatalogPolicy,
    BankingDiscoveryRequest,
    BankingNeedBinding,
    BankingOptionAdviceDraft,
    BankingOptionSuggestionDraft,
)
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.dataset import DatasetRecord, DatasetSnapshot
from opc_mis.domain.enums import (
    ArtifactStatus,
    ArtifactType,
    BankingAdviceSource,
    BankingAdviceStatus,
    BankingCriterionCode,
    BankingCriterionStatus,
    BankingDataGapCode,
    BankingDiscoveryStatus,
    BankingNeedType,
    BankingPrecheckFieldSource,
    BankingPrecheckStatus,
    CashflowScope,
    ComponentStatus,
    CurrencyCode,
    DecisionCapability,
    DecisionHandoffMode,
    EvaluationScope,
    SourceType,
    ValidationStatus,
)
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.planner_models import EvaluationCase
from opc_mis.domain.team_pack import SheetRegistry
from opc_mis.governance.evidence_validator import EvidenceValidator
from opc_mis.infrastructure.persistence.memory_artifact_repository import (
    InMemoryArtifactRepository,
)
from opc_mis.infrastructure.persistence.memory_dataset_repository import (
    InMemoryDatasetRepository,
)

CASE_ID = "CASE-BANKING-TEST"
DATASET_ID = "DATASET-BANKING-TEST"
CONTRACT_ID = "CONTRACT-TEST"
BASE_EVIDENCE = EvidenceRef(
    evidence_id="EVD-EXPLICIT-BANKING-NEED",
    source_type=SourceType.TEAM_PACK,
    sheet="04_CONTRACTS",
    row_number=2,
    record_id=CONTRACT_ID,
    field="payment_terms",
    display_value="Performance bond requirement",
)


def _record(sheet: str, row: int, record_id: str, values: dict[str, object]) -> DatasetRecord:
    return DatasetRecord(
        sheet=sheet,
        row_number=row,
        record_id=record_id,
        values=values,
        display_values=dict(values),
    )


def _product(product_id: str, row: int) -> DatasetRecord:
    return _record(
        SheetRegistry.BANK_PRODUCTS.sheet_name,
        row,
        product_id,
        {
            "bank_product_id": product_id,
            "bank": f"Provider {product_id}",
            "product_name": f"Product {product_id}",
            "target_segment": "Business",
            "description": "Mock catalog option",
            "annual_rate_or_fee": 0.01,
            "processing_fee_rate": 0.001,
            "collateral_ratio": 0.2,
            "minimum_amount": 300000000.0,
            "automation_level": "Human review text from catalog",
            "fit_note": "Catalog note only",
        },
    )


def _api(api_id: str, row: int) -> DatasetRecord:
    return _record(
        SheetRegistry.API_CATALOG.sheet_name,
        row,
        api_id,
        {
            "api_id": api_id,
            "provider": f"Provider {api_id}",
            "method": "POST",
            "endpoint": f"/mock/{api_id.casefold()}/precheck",
            "description": "Mock precheck metadata",
            "required_fields": "contract_id, amount, company_profile",
            "payload_example": "{}",
            "recommended_core_role": "Banking discovery",
            "catalog_status": "Baseline mock",
            "extension_rule": "Replace with a real adapter only after configuration",
        },
    )


def _handling_rule() -> DatasetRecord:
    return _record(
        SheetRegistry.API_HANDLING_RULES.sheet_name,
        2,
        "HANDLING-ALPHA",
        {
            "rule_id": "HANDLING-ALPHA",
            "applies_to": "Mock precheck",
            "possible_issue": "Partner response unavailable",
            "team_visible_meaning": "No response was received",
            "required_handling": "Keep status visible",
            "requires_human_approval": "Source workbook says yes",
            "sensitive_fields": "company_profile",
            "note": "Source guidance, not executable policy",
        },
    )


def _unrelated_credit_profile() -> DatasetRecord:
    return _record(
        SheetRegistry.CREDIT_PROFILES.sheet_name,
        2,
        "CREDIT-UNRELATED",
        {
            "credit_case_id": "CREDIT-UNRELATED",
            "company_id": "COMPANY-X",
            "request_type": "Guarantee",
            "requested_amount": 420000000.0,
            "tenor": "Twelve months",
            "collateral_or_basis": f"Description mentions {CONTRACT_ID}",
            "eligibility_score": 80.0,
            "precheck_note": "Text only",
            "approval_status": "Mock",
        },
    )


def _snapshot(product_count: int) -> DatasetSnapshot:
    products = tuple(
        _product(product_id, row)
        for row, product_id in enumerate(("PRODUCT-ALPHA", "PRODUCT-BETA")[:product_count], 2)
    )
    apis = tuple(
        _api(api_id, row)
        for row, api_id in enumerate(("API-ALPHA", "API-BETA")[:product_count], 2)
    )
    records = {
        SheetRegistry.BANK_PRODUCTS.sheet_name: list(products),
        SheetRegistry.API_CATALOG.sheet_name: list(apis),
        SheetRegistry.API_HANDLING_RULES.sheet_name: [_handling_rule()],
        SheetRegistry.CREDIT_PROFILES.sheet_name: [_unrelated_credit_profile()],
    }
    indexes = {
        sheet: {record.record_id: [record] for record in sheet_records}
        for sheet, sheet_records in records.items()
    }
    return DatasetSnapshot(
        dataset_id=DATASET_ID,
        source_locator="memory://banking-test",
        source_hash="SOURCE-HASH-BANKING",
        snapshot_hash="SNAPSHOT-HASH-BANKING",
        sheets=records,
        headers={
            definition.sheet_name: definition.required_headers
            for definition in (
                SheetRegistry.BANK_PRODUCTS,
                SheetRegistry.API_CATALOG,
                SheetRegistry.API_HANDLING_RULES,
                SheetRegistry.CREDIT_PROFILES,
            )
        },
        indexes=indexes,
        duplicate_ids={},
        validation_issues=[],
        missing_sheets=(),
        missing_headers={},
    )


def _policy(product_count: int, *, allow_combination: bool = False) -> BankingCatalogPolicy:
    product_ids = ("PRODUCT-ALPHA", "PRODUCT-BETA")[:product_count]
    api_ids = ("API-ALPHA", "API-BETA")[:product_count]
    combinations = (product_ids,) if allow_combination and len(product_ids) > 1 else ()
    return BankingCatalogPolicy(
        policy_id="BANKING-POLICY-TEST",
        mapping_version="banking-test-v1",
        policy_hash="POLICY-HASH-TEST",
        bindings=(
            BankingNeedBinding(
                binding_id="BINDING-PERFORMANCE-BOND",
                need_type=BankingNeedType.PERFORMANCE_BOND,
                bank_product_ids=product_ids,
                precheck_api_by_product=dict(zip(product_ids, api_ids, strict=True)),
                precheck_field_sources_by_api={
                    api_id: {
                        "contract_id": BankingPrecheckFieldSource.EVALUATION_CASE,
                        "amount": (
                            BankingPrecheckFieldSource.BANKING_INPUT_SUPPLEMENT
                        ),
                        "company_profile": BankingPrecheckFieldSource.OPC_PROFILE,
                    }
                    for api_id in api_ids
                },
                handling_rule_ids=("HANDLING-ALPHA",),
                allowed_product_combinations=combinations,
            ),
        ),
    )


def _case(*, related_credit_case_ids: tuple[str, ...] = ()) -> EvaluationCase:
    return EvaluationCase(
        evaluation_case_id=CASE_ID,
        dataset_id=DATASET_ID,
        contract_id=CONTRACT_ID,
        customer_id="CUSTOMER-TEST",
        related_order_ids=(),
        related_invoice_ids=(),
        related_service_ids=(),
        related_credit_case_ids=related_credit_case_ids,
        evaluation_scope=(
            EvaluationScope.FINANCE,
            EvaluationScope.OPERATIONS,
            EvaluationScope.RISK,
        ),
        cashflow_scope=CashflowScope.NOT_AVAILABLE,
        warnings=(),
        evidence_refs=(BASE_EVIDENCE,),
    )


def _request() -> BankingDiscoveryRequest:
    return BankingDiscoveryRequest(
        request_id="BANKING-REQUEST-TEST",
        evaluation_case_id=CASE_ID,
        dataset_id=DATASET_ID,
        contract_id=CONTRACT_ID,
        execution_mode=DecisionHandoffMode.BANKING_DISCOVERY,
        requested_capability=DecisionCapability.BANKING_INTERNAL_DISCOVERY,
        need_types=(BankingNeedType.PERFORMANCE_BOND,),
        requested_amount=None,
        requested_amount_currency=None,
        constraints=(),
        source_route_artifact_id="ARTIFACT-ROUTE",
        source_route_plan_id="ROUTE-PLAN-TEST",
        source_artifact_ids=("ARTIFACT-ROUTE", "ARTIFACT-EVALUATION-CASE"),
        evidence_ids=(BASE_EVIDENCE.evidence_id,),
    )


def _envelope(
    *,
    artifact_id: str,
    artifact_type: ArtifactType,
    payload: dict[str, object],
    evidence_refs: tuple[EvidenceRef, ...] = (BASE_EVIDENCE,),
) -> ArtifactEnvelope:
    return ArtifactEnvelope(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        evaluation_case_id=CASE_ID,
        producer="TEST",
        version=1,
        status=ArtifactStatus.CREATED,
        payload=payload,
        evidence_refs=evidence_refs,
        input_artifact_ids=(),
        input_hash="INPUT-HASH-TEST",
        validation_status=ValidationStatus.VALID,
        validation_notes=(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _execution_context(*artifact_ids: str) -> ExecutionContext:
    return ExecutionContext(
        evaluation_case_id=CASE_ID,
        dataset_id=DATASET_ID,
        workflow_run_id="RUN-BANKING-TEST",
        input_artifact_ids=artifact_ids,
        requested_scope=(
            EvaluationScope.FINANCE,
            EvaluationScope.OPERATIONS,
            EvaluationScope.RISK,
        ),
        component_input={},
        current_node="BANKING_INTERNAL_DISCOVERY",
    )


async def _run_discovery(
    *,
    product_count: int,
    allow_combination: bool = False,
    related_credit_case_ids: tuple[str, ...] = (),
) -> tuple[object, BankingCatalogPolicy]:
    datasets = InMemoryDatasetRepository()
    artifacts = InMemoryArtifactRepository()
    await datasets.register(_snapshot(product_count))
    case_artifact = _envelope(
        artifact_id="ARTIFACT-EVALUATION-CASE",
        artifact_type=ArtifactType.EVALUATION_CASE,
        payload=_case(
            related_credit_case_ids=related_credit_case_ids
        ).model_dump(mode="json"),
    )
    request_artifact = _envelope(
        artifact_id="ARTIFACT-BANKING-REQUEST",
        artifact_type=ArtifactType.BANKING_DISCOVERY_REQUEST,
        payload=_request().model_dump(mode="json"),
    )
    await artifacts.save(case_artifact)
    await artifacts.save(request_artifact)
    policy = _policy(product_count, allow_combination=allow_combination)
    skill = BankingDiscoverySkill(
        context_loader=BankingDiscoveryContextLoader(
            datasets=datasets,
            artifacts=artifacts,
        ),
        policy=policy,
    )
    result = await skill.execute(
        _execution_context(case_artifact.artifact_id, request_artifact.artifact_id)
    )
    return result, policy


def test_discovery_uses_only_explicit_relationships_and_never_executes_precheck() -> None:
    result, policy = asyncio.run(_run_discovery(product_count=1))
    matrix = result.option_matrix

    assert result.status is ComponentStatus.COMPLETED_WITH_WARNINGS
    assert result.discovery_status is BankingDiscoveryStatus.OPTIONS_READY_WITH_GAPS
    assert matrix is not None
    assert matrix.explicit_credit_case_ids == ()
    assert len(matrix.candidates) == 1
    assert {gap.code for gap in matrix.data_gaps} == {
        BankingDataGapCode.REQUESTED_AMOUNT_UNAVAILABLE,
    }
    candidate = matrix.candidates[0]
    amount_check = next(
        item for item in candidate.criteria if item.code is BankingCriterionCode.MINIMUM_AMOUNT
    )
    credit_check = next(
        item
        for item in candidate.criteria
        if item.code is BankingCriterionCode.EXPLICIT_CREDIT_PROFILE_RELATIONSHIP
    )
    assert amount_check.status is BankingCriterionStatus.NOT_EVALUABLE
    assert credit_check.status is BankingCriterionStatus.NOT_EVALUABLE
    assert matrix.requested_amount_currency is CurrencyCode.VND
    assert candidate.minimum_amount_currency is CurrencyCode.VND
    assert candidate.precheck is not None
    assert candidate.precheck.status is BankingPrecheckStatus.MOCK_AVAILABLE_NOT_EXECUTED
    assert candidate.precheck.precheck_executed is False
    assert matrix.precheck_executed is False
    assert result.approval_signals == ()
    assert result.action_commands == ()
    assert tuple(item.artifact_type for item in result.artifacts) == (
        ArtifactType.BANKING_OPTION_MATRIX,
        ArtifactType.BANKING_DISCOVERY_RESULT,
    )
    assert SourceType.POLICY_CONFIG in {
        item.source_type for item in result.artifacts[0].evidence_refs
    }
    assert "12_API_CATALOG" in {
        item.sheet for item in result.artifacts[0].evidence_refs
    }
    reports = tuple(
        asyncio.run(EvidenceValidator(banking_policy=policy).validate(draft))
        for draft in result.artifacts
    )
    assert all(report.status is ValidationStatus.VALID for report in reports)


def test_discovery_uses_a_credit_profile_only_when_planner_selected_its_id() -> None:
    result, _ = asyncio.run(
        _run_discovery(
            product_count=1,
            related_credit_case_ids=("CREDIT-UNRELATED",),
        )
    )
    matrix = result.option_matrix

    assert matrix is not None
    assert matrix.explicit_credit_case_ids == ("CREDIT-UNRELATED",)
    assert BankingDataGapCode.CREDIT_PROFILE_RELATIONSHIP_UNCONFIRMED not in {
        item.code for item in matrix.data_gaps
    }
    credit_check = next(
        item
        for item in matrix.candidates[0].criteria
        if item.code is BankingCriterionCode.EXPLICIT_CREDIT_PROFILE_RELATIONSHIP
    )
    assert credit_check.status is BankingCriterionStatus.PASS
    assert credit_check.evidence_ids


class _MustNotRunAdvisor:
    def __init__(self) -> None:
        self.calls = 0

    async def compose(self, payload: object) -> BankingAdviceComposition:
        del payload
        self.calls += 1
        raise AssertionError("advisor must not run for fewer than two candidates")


class _CapturingAdvisor:
    def __init__(self, *, suggest_combination: bool = True) -> None:
        self.calls = 0
        self.payload: object | None = None
        self._suggest_combination = suggest_combination

    async def compose(self, payload: object) -> BankingAdviceComposition:
        self.calls += 1
        self.payload = payload
        options = payload.options  # type: ignore[attr-defined]
        option_ids = tuple(item.option_id for item in options)
        return BankingAdviceComposition(
            advice=BankingOptionAdviceDraft(
                overview="The configured alternatives can be read side by side.",
                suggestions=(
                    BankingOptionSuggestionDraft(
                        option_ids=(
                            option_ids
                            if self._suggest_combination
                            else (option_ids[0],)
                        ),
                        rationale="This is a non-authoritative comparison for review.",
                    ),
                ),
            ),
            source=BankingAdviceSource.OPENAI,
            model="MODEL-TEST",
            prompt_version="PROMPT-TEST",
        )


async def _run_advisor(
    *,
    discovery_result: object,
    advisor: object,
) -> object:
    matrix_draft = discovery_result.artifacts[0]  # type: ignore[attr-defined]
    matrix_artifact = _envelope(
        artifact_id="ARTIFACT-BANKING-MATRIX",
        artifact_type=ArtifactType.BANKING_OPTION_MATRIX,
        payload=matrix_draft.payload,
        evidence_refs=matrix_draft.evidence_refs,
    )
    artifacts = InMemoryArtifactRepository()
    await artifacts.save(matrix_artifact)
    skill = BankingOptionAdvisorSkill(
        context_loader=BankingAdvisorContextLoader(artifacts=artifacts),
        advisor=advisor,  # type: ignore[arg-type]
    )
    return await skill.execute(_execution_context(matrix_artifact.artifact_id))


def test_advisor_is_not_called_when_only_one_candidate_exists() -> None:
    discovery, _ = asyncio.run(_run_discovery(product_count=1))
    advisor = _MustNotRunAdvisor()

    result = asyncio.run(_run_advisor(discovery_result=discovery, advisor=advisor))

    assert advisor.calls == 0
    assert result.status is ComponentStatus.COMPLETED
    assert result.option_advice.status is BankingAdviceStatus.NOT_INVOKED
    assert result.option_advice.source is BankingAdviceSource.NOT_INVOKED
    assert result.option_advice.suggestions == ()
    assert result.artifacts[0].artifact_type is ArtifactType.BANKING_OPTION_ADVICE
    assert result.approval_signals == ()
    assert result.action_commands == ()


def test_advisor_can_only_reference_an_explicitly_allowed_combination() -> None:
    discovery, _ = asyncio.run(
        _run_discovery(product_count=2, allow_combination=True)
    )
    advisor = _CapturingAdvisor()

    result = asyncio.run(_run_advisor(discovery_result=discovery, advisor=advisor))

    assert advisor.calls == 1
    assert result.status is ComponentStatus.COMPLETED
    assert result.option_advice.status is BankingAdviceStatus.ADVISORY_ONLY
    assert result.option_advice.source is BankingAdviceSource.OPENAI
    assert result.option_advice.suggestions[0].option_ids == tuple(
        sorted(discovery.option_matrix.allowed_option_combinations[0])
    )
    serialized_input = json.dumps(advisor.payload.model_dump(mode="json"))  # type: ignore[union-attr]
    assert CASE_ID not in serialized_input
    assert CONTRACT_ID not in serialized_input
    assert "300000000" not in serialized_input
    assert result.approval_signals == ()
    assert result.action_commands == ()


def test_advisor_rejects_an_unconfigured_multi_option_suggestion() -> None:
    discovery, _ = asyncio.run(_run_discovery(product_count=2))
    advisor = _CapturingAdvisor()

    result = asyncio.run(_run_advisor(discovery_result=discovery, advisor=advisor))

    assert advisor.calls == 1
    assert result.status is ComponentStatus.FAILED_SAFE
    assert result.option_advice is None
    assert result.artifacts == ()
    assert result.approval_signals == ()
    assert result.action_commands == ()
