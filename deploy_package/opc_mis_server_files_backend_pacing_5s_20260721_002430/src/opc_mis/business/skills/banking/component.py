"""Deterministic, side-effect-free Banking Phase A catalog discovery."""

from collections.abc import Iterable
from typing import Any

from opc_mis.business.skills.banking.context_loader import (
    BankingDiscoveryContext,
    BankingDiscoveryContextError,
    BankingDiscoveryContextLoader,
    BankingDiscoveryRequestMissing,
)
from opc_mis.domain.artifacts import ArtifactDraft
from opc_mis.domain.banking_models import (
    BankingCatalogNumber,
    BankingCatalogPolicy,
    BankingCriterion,
    BankingDataGap,
    BankingDiscoveryComponentResult,
    BankingDiscoveryResult,
    BankingHandlingGuidance,
    BankingNeedBinding,
    BankingOptionCandidate,
    BankingOptionMatrix,
    BankingPrecheckReference,
)
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.dataset import DatasetRecord, DatasetSnapshot
from opc_mis.domain.enums import (
    ArtifactType,
    BankingCriterionCode,
    BankingCriterionStatus,
    BankingDataGapCode,
    BankingDiscoveryStatus,
    BankingHandlingPolicyEffect,
    BankingNeedType,
    BankingPrecheckStatus,
    ComponentStatus,
    CurrencyCode,
    SourceType,
)
from opc_mis.domain.events import RuntimeEvent
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.lineage import LineageFactory, deterministic_id
from opc_mis.domain.missing_data import MissingDataRequest
from opc_mis.domain.serialization import json_safe
from opc_mis.domain.team_pack import SheetDefinition, SheetRegistry

_PRODUCT_FIELDS = (
    "bank_product_id",
    "bank",
    "product_name",
    "target_segment",
    "description",
    "annual_rate_or_fee",
    "processing_fee_rate",
    "collateral_ratio",
    "minimum_amount",
    "automation_level",
    "fit_note",
)
_API_FIELDS = (
    "api_id",
    "provider",
    "method",
    "endpoint",
    "description",
    "required_fields",
    "catalog_status",
    "extension_rule",
)
_HANDLING_FIELDS = (
    "rule_id",
    "applies_to",
    "possible_issue",
    "team_visible_meaning",
    "required_handling",
    "requires_human_approval",
    "sensitive_fields",
    "note",
)


class BankingDiscoveryBuildError(RuntimeError):
    """Raised for a configured catalog reference that cannot be represented safely."""


class BankingDiscoverySkill:
    """Build an internal option matrix without calling a bank or choosing an option."""

    component_id = "BANKING_DISCOVERY_SKILL"

    def __init__(
        self,
        *,
        context_loader: BankingDiscoveryContextLoader,
        policy: BankingCatalogPolicy,
    ) -> None:
        self._context_loader = context_loader
        self._policy = policy

    async def execute(
        self, context: ExecutionContext
    ) -> BankingDiscoveryComponentResult:
        """Return deterministic matrix and compact result drafts only."""
        try:
            discovery_context = await self._context_loader.load(context)
            matrix, evidence_refs = self._build_matrix(discovery_context)
        except BankingDiscoveryRequestMissing as exc:
            case_id = context.evaluation_case_id or "UNKNOWN"
            missing = MissingDataRequest(
                request_id=deterministic_id(
                    "MDR",
                    case_id,
                    self.component_id,
                    ArtifactType.BANKING_DISCOVERY_REQUEST,
                ),
                evaluation_case_id=case_id,
                raised_by=self.component_id,
                requirement_code="BANKING_DISCOVERY_REQUEST_REQUIRED",
                target_record=case_id,
                field=ArtifactType.BANKING_DISCOVERY_REQUEST.value,
                expected_type="validated artifact envelope",
                reason=str(exc),
            )
            return BankingDiscoveryComponentResult(
                status=ComponentStatus.WAITING_FOR_INPUT,
                discovery_status=BankingDiscoveryStatus.WAITING_FOR_REQUEST,
                missing_data_requests=(missing,),
                runtime_events=(
                    RuntimeEvent(
                        event_type="BANKING_DISCOVERY_WAITING_FOR_REQUEST",
                        message=str(exc),
                    ),
                ),
            )
        except (BankingDiscoveryContextError, BankingDiscoveryBuildError) as exc:
            return self._failed_safe(str(exc))

        result = BankingDiscoveryResult(
            result_id=deterministic_id(
                "BDRES",
                matrix.matrix_id,
                matrix.discovery_status,
                tuple(item.option_id for item in matrix.candidates),
                tuple(item.gap_id for item in matrix.data_gaps),
            ),
            evaluation_case_id=matrix.evaluation_case_id,
            dataset_id=matrix.dataset_id,
            contract_id=matrix.contract_id,
            request_id=matrix.request_id,
            matrix_id=matrix.matrix_id,
            discovery_status=matrix.discovery_status,
            candidate_option_ids=tuple(item.option_id for item in matrix.candidates),
            data_gap_ids=tuple(item.gap_id for item in matrix.data_gaps),
            mapping_version=matrix.mapping_version,
            mapping_hash=matrix.mapping_hash,
        )
        common_identity = {
            "source_artifact_ids": matrix.source_artifact_ids,
            "request_id": matrix.request_id,
            "requested_amount": matrix.requested_amount,
            "requested_amount_currency": matrix.requested_amount_currency,
            "request_amount_evidence_ids": (
                discovery_context.request.amount_evidence_ids
            ),
            "supplement_id": (
                discovery_context.supplement.supplement_id
                if discovery_context.supplement is not None
                else None
            ),
            "dataset_snapshot_hash": discovery_context.dataset.snapshot_hash,
            "mapping_policy_id": matrix.mapping_policy_id,
            "mapping_version": matrix.mapping_version,
            "mapping_hash": matrix.mapping_hash,
        }
        drafts = (
            ArtifactDraft(
                artifact_type=ArtifactType.BANKING_OPTION_MATRIX,
                evaluation_case_id=matrix.evaluation_case_id,
                producer=self.component_id,
                payload=matrix.model_dump(mode="json"),
                evidence_refs=evidence_refs,
                identity_inputs=common_identity,
            ),
            ArtifactDraft(
                artifact_type=ArtifactType.BANKING_DISCOVERY_RESULT,
                evaluation_case_id=result.evaluation_case_id,
                producer=self.component_id,
                payload=result.model_dump(mode="json"),
                evidence_refs=evidence_refs,
                identity_inputs={
                    **common_identity,
                    "matrix_id": matrix.matrix_id,
                },
            ),
        )
        warnings = tuple(item.code.value for item in matrix.data_gaps)
        if not matrix.candidates:
            warnings = (*warnings, "BANKING_NO_CONFIGURED_OPTIONS")
        status = (
            ComponentStatus.COMPLETED_WITH_WARNINGS
            if warnings
            else ComponentStatus.COMPLETED
        )
        return BankingDiscoveryComponentResult(
            status=status,
            discovery_status=matrix.discovery_status,
            option_matrix=matrix,
            discovery_result=result,
            artifacts=drafts,
            warnings=warnings,
            runtime_events=(
                RuntimeEvent(
                    event_type="BANKING_INTERNAL_OPTIONS_DISCOVERED",
                    message=(
                        "Banking completed internal catalog discovery without "
                        "executing an external precheck."
                    ),
                    metadata={
                        "discovery_status": matrix.discovery_status.value,
                        "candidate_count": len(matrix.candidates),
                        "data_gap_count": len(matrix.data_gaps),
                    },
                ),
            ),
        )

    def _build_matrix(
        self,
        context: BankingDiscoveryContext,
    ) -> tuple[BankingOptionMatrix, tuple[EvidenceRef, ...]]:
        lineage = LineageFactory(context.dataset.dataset_id, context.dataset.source_hash)
        evidence: dict[str, EvidenceRef] = {
            item.evidence_id: item
            for artifact in (
                context.evaluation_case_artifact,
                context.request_artifact,
                *(
                    (context.supplement_artifact,)
                    if context.supplement_artifact is not None
                    else ()
                ),
            )
            for item in artifact.evidence_refs
        }
        request_sources = self._request_sources(context)
        data_gaps = self._data_gaps(
            context=context,
            lineage=lineage,
            request_sources=request_sources,
            evidence=evidence,
        )

        bindings = {item.need_type: item for item in self._policy.bindings}
        candidates: list[BankingOptionCandidate] = []
        option_ids_by_need_and_product: dict[tuple[BankingNeedType, str], str] = {}
        selected_bindings: list[BankingNeedBinding] = []
        for need_type in context.request.need_types:
            binding = bindings.get(need_type)
            if binding is None:
                missing_mapping = self._policy_evidence(
                    record_id=self._policy.policy_id,
                    field=f"binding:{need_type.value}",
                    display_value=None,
                )
                evidence[missing_mapping.evidence_id] = missing_mapping
                continue
            selected_bindings.append(binding)
            binding_evidence = self._binding_evidence(binding)
            evidence[binding_evidence.evidence_id] = binding_evidence
            guidance, guidance_evidence = self._handling_guidance(
                context.dataset,
                binding,
                lineage,
            )
            self._merge_evidence(evidence, guidance_evidence)
            for product_id in binding.bank_product_ids:
                candidate, candidate_evidence = self._candidate(
                    context=context,
                    binding=binding,
                    binding_evidence=binding_evidence,
                    need_type=need_type,
                    product_id=product_id,
                    handling_guidance=guidance,
                    lineage=lineage,
                    data_gaps=data_gaps,
                )
                candidates.append(candidate)
                option_ids_by_need_and_product[(need_type, product_id)] = (
                    candidate.option_id
                )
                self._merge_evidence(evidence, candidate_evidence)

        allowed_combinations = self._allowed_combinations(
            selected_bindings,
            option_ids_by_need_and_product,
        )
        discovery_status = (
            BankingDiscoveryStatus.NO_CONFIGURED_OPTIONS
            if not candidates
            else BankingDiscoveryStatus.OPTIONS_READY_WITH_GAPS
            if data_gaps
            else BankingDiscoveryStatus.OPTIONS_READY
        )
        evidence_refs = tuple(evidence[key] for key in sorted(evidence))
        matrix_id = deterministic_id(
            "BOM",
            context.evaluation_case.evaluation_case_id,
            context.request.request_id,
            context.request_artifact.artifact_id,
            context.requested_amount,
            context.requested_amount_currency,
            context.request.amount_evidence_ids,
            (
                context.supplement.supplement_id
                if context.request.requested_amount is None
                and context.supplement is not None
                else None
            ),
            context.dataset.snapshot_hash,
            self._policy.policy_id,
            self._policy.mapping_version,
            self._policy.policy_hash,
            tuple(item.option_id for item in candidates),
            tuple(item.gap_id for item in data_gaps),
            allowed_combinations,
        )
        matrix = BankingOptionMatrix(
            matrix_id=matrix_id,
            evaluation_case_id=context.evaluation_case.evaluation_case_id,
            dataset_id=context.dataset.dataset_id,
            contract_id=context.evaluation_case.contract_id,
            request_id=context.request.request_id,
            mapping_policy_id=self._policy.policy_id,
            mapping_version=self._policy.mapping_version,
            mapping_hash=self._policy.policy_hash,
            discovery_status=discovery_status,
            requested_need_types=context.request.need_types,
            requested_amount=context.requested_amount,
            requested_amount_currency=context.requested_amount_currency,
            explicit_credit_case_ids=context.evaluation_case.related_credit_case_ids,
            candidates=tuple(candidates),
            data_gaps=data_gaps,
            allowed_option_combinations=allowed_combinations,
            precheck_executed=False,
            source_artifact_ids=context.source_artifact_ids,
            evidence_ids=tuple(item.evidence_id for item in evidence_refs),
        )
        return matrix, evidence_refs

    def _candidate(
        self,
        *,
        context: BankingDiscoveryContext,
        binding: BankingNeedBinding,
        binding_evidence: EvidenceRef,
        need_type: BankingNeedType,
        product_id: str,
        handling_guidance: tuple[BankingHandlingGuidance, ...],
        lineage: LineageFactory,
        data_gaps: tuple[BankingDataGap, ...],
    ) -> tuple[BankingOptionCandidate, tuple[EvidenceRef, ...]]:
        product = self._exact(
            context.dataset,
            SheetRegistry.BANK_PRODUCTS,
            product_id,
        )
        product_evidence = tuple(
            lineage.record_field(product, field) for field in _PRODUCT_FIELDS
        )
        precheck, precheck_evidence = self._precheck(
            context.dataset,
            binding.precheck_api_by_product.get(product_id),
            lineage,
        )
        credit_evidence = tuple(
            lineage.record_field(record, "credit_case_id")
            for record in context.explicit_credit_profiles
        )
        case_evidence_ids = tuple(
            item.evidence_id for item in context.evaluation_case_artifact.evidence_refs
        )
        amount_gap_evidence = tuple(
            evidence_id
            for gap in data_gaps
            if gap.code is BankingDataGapCode.REQUESTED_AMOUNT_UNAVAILABLE
            for evidence_id in gap.evidence_ids
        )
        amount_evidence = self._amount_evidence(context)
        minimum_amount = self._number(product, "minimum_amount")
        minimum_status = BankingCriterionStatus.NOT_EVALUABLE
        minimum_detail = (
            "Minimum amount cannot be evaluated until an evidence-backed amount exists."
        )
        if context.requested_amount is not None:
            if minimum_amount is None:
                minimum_status = BankingCriterionStatus.NOT_APPLICABLE
                minimum_detail = "The configured option does not publish a minimum amount."
            elif context.requested_amount >= minimum_amount:
                minimum_status = BankingCriterionStatus.PASS
                minimum_detail = "The requested amount meets the catalog minimum."
            else:
                minimum_status = BankingCriterionStatus.FAIL
                minimum_detail = "The requested amount is below the catalog minimum."
        criteria = (
            BankingCriterion(
                criterion_id=deterministic_id(
                    "BCRIT", context.request.request_id, need_type, product_id, "NEED"
                ),
                code=BankingCriterionCode.NEED_TYPE_CONFIGURED,
                status=BankingCriterionStatus.PASS,
                detail=(
                    "The typed Banking need is explicitly mapped to this catalog product."
                ),
                evidence_ids=(binding_evidence.evidence_id,),
            ),
            BankingCriterion(
                criterion_id=deterministic_id(
                    "BCRIT", context.request.request_id, need_type, product_id, "AMOUNT"
                ),
                code=BankingCriterionCode.MINIMUM_AMOUNT,
                status=minimum_status,
                detail=minimum_detail,
                evidence_ids=tuple(
                    dict.fromkeys(
                        (
                            self._field_evidence_id(product_evidence, "minimum_amount"),
                            *amount_gap_evidence,
                            *(item.evidence_id for item in amount_evidence),
                        )
                    )
                ),
            ),
            BankingCriterion(
                criterion_id=deterministic_id(
                    "BCRIT", context.request.request_id, need_type, product_id, "CREDIT"
                ),
                code=BankingCriterionCode.EXPLICIT_CREDIT_PROFILE_RELATIONSHIP,
                status=(
                    BankingCriterionStatus.PASS
                    if context.explicit_credit_profiles
                    else BankingCriterionStatus.NOT_EVALUABLE
                ),
                detail=(
                    "Planner supplied an explicit credit-profile relationship."
                    if context.explicit_credit_profiles
                    else "No explicit case-to-credit-profile relationship is available."
                ),
                evidence_ids=(
                    tuple(item.evidence_id for item in credit_evidence)
                    if credit_evidence
                    else case_evidence_ids
                ),
            ),
            BankingCriterion(
                criterion_id=deterministic_id(
                    "BCRIT", context.request.request_id, need_type, product_id, "PRECHECK"
                ),
                code=BankingCriterionCode.MOCK_PRECHECK_METADATA,
                status=(
                    BankingCriterionStatus.PASS
                    if precheck is not None
                    else BankingCriterionStatus.NOT_APPLICABLE
                ),
                detail=(
                    "Mock precheck metadata is configured but was not executed."
                    if precheck is not None
                    else "No mock precheck metadata is configured for this product."
                ),
                evidence_ids=(
                    precheck.evidence_ids
                    if precheck is not None
                    else (binding_evidence.evidence_id,)
                ),
            ),
        )
        guidance_evidence_ids = tuple(
            evidence_id
            for item in handling_guidance
            for evidence_id in item.evidence_ids
        )
        candidate_evidence = self._unique_evidence(
            (binding_evidence,),
            product_evidence,
            precheck_evidence,
            credit_evidence,
            amount_evidence,
        )
        candidate_evidence_ids = tuple(
            dict.fromkeys(
                (
                    *(item.evidence_id for item in candidate_evidence),
                    *guidance_evidence_ids,
                    *(evidence_id for item in criteria for evidence_id in item.evidence_ids),
                )
            )
        )
        option_id = deterministic_id(
            "BOPT",
            context.evaluation_case.evaluation_case_id,
            context.request.request_id,
            need_type,
            product_id,
            self._policy.policy_hash,
        )
        candidate = BankingOptionCandidate(
            option_id=option_id,
            need_type=need_type,
            bank_product_id=self._text(product, "bank_product_id"),
            provider=self._text(product, "bank"),
            product_name=self._text(product, "product_name"),
            target_segment=self._text(product, "target_segment"),
            description=self._text(product, "description"),
            annual_rate_or_fee=self._number(product, "annual_rate_or_fee"),
            processing_fee_rate=self._number(product, "processing_fee_rate"),
            collateral_ratio=self._number(product, "collateral_ratio"),
            minimum_amount=minimum_amount,
            minimum_amount_currency=CurrencyCode.VND,
            automation_level=self._text(product, "automation_level"),
            fit_note=self._text(product, "fit_note"),
            criteria=criteria,
            precheck=precheck,
            handling_guidance=handling_guidance,
            evidence_ids=candidate_evidence_ids,
        )
        return candidate, candidate_evidence

    def _precheck(
        self,
        dataset: DatasetSnapshot,
        api_id: str | None,
        lineage: LineageFactory,
    ) -> tuple[BankingPrecheckReference | None, tuple[EvidenceRef, ...]]:
        if api_id is None:
            return None, ()
        record = self._exact(dataset, SheetRegistry.API_CATALOG, api_id)
        evidence = tuple(lineage.record_field(record, field) for field in _API_FIELDS)
        required_fields_value = self._text(record, "required_fields")
        required_fields = tuple(
            field.strip()
            for field in required_fields_value.split(",")
            if field.strip()
        )
        return (
            BankingPrecheckReference(
                api_id=self._text(record, "api_id"),
                provider=self._text(record, "provider"),
                method=self._text(record, "method"),
                endpoint=self._text(record, "endpoint"),
                description=self._text(record, "description"),
                required_fields=required_fields,
                catalog_status=self._text(record, "catalog_status"),
                extension_rule=self._text(record, "extension_rule"),
                status=BankingPrecheckStatus.MOCK_AVAILABLE_NOT_EXECUTED,
                precheck_executed=False,
                evidence_ids=tuple(item.evidence_id for item in evidence),
            ),
            evidence,
        )

    def _handling_guidance(
        self,
        dataset: DatasetSnapshot,
        binding: BankingNeedBinding,
        lineage: LineageFactory,
    ) -> tuple[tuple[BankingHandlingGuidance, ...], tuple[EvidenceRef, ...]]:
        guidance: list[BankingHandlingGuidance] = []
        evidence: list[EvidenceRef] = []
        for rule_id in binding.handling_rule_ids:
            record = self._exact(dataset, SheetRegistry.API_HANDLING_RULES, rule_id)
            rule_evidence = tuple(
                lineage.record_field(record, field) for field in _HANDLING_FIELDS
            )
            evidence.extend(rule_evidence)
            guidance.append(
                BankingHandlingGuidance(
                    rule_id=self._text(record, "rule_id"),
                    applies_to=self._text(record, "applies_to"),
                    possible_issue=self._text(record, "possible_issue"),
                    team_visible_meaning=self._text(record, "team_visible_meaning"),
                    required_handling=self._text(record, "required_handling"),
                    source_requires_human_approval_text=self._text(
                        record, "requires_human_approval"
                    ),
                    sensitive_fields=self._text(record, "sensitive_fields"),
                    note=self._text(record, "note"),
                    policy_effect=BankingHandlingPolicyEffect.SOURCE_GUIDANCE_ONLY,
                    evidence_ids=tuple(item.evidence_id for item in rule_evidence),
                )
            )
        return tuple(guidance), self._unique_evidence(tuple(evidence))

    def _data_gaps(
        self,
        *,
        context: BankingDiscoveryContext,
        lineage: LineageFactory,
        request_sources: tuple[EvidenceRef, ...],
        evidence: dict[str, EvidenceRef],
    ) -> tuple[BankingDataGap, ...]:
        specifications: list[
            tuple[BankingDataGapCode, str, str, tuple[EvidenceRef, ...]]
        ] = []
        if context.requested_amount is None:
            specifications.append(
                (
                    BankingDataGapCode.REQUESTED_AMOUNT_UNAVAILABLE,
                    "requested_amount",
                    "The Banking request does not include a requested amount.",
                    request_sources,
                )
            )
        gaps: list[BankingDataGap] = []
        for code, field, detail, sources in specifications:
            gap_evidence = lineage.derived(
                sheet="BANKING_OPTION_MATRIX",
                record_id=context.request.request_id,
                field=field,
                display={"status": "UNAVAILABLE", "code": code.value},
                sources=sources,
            )
            evidence[gap_evidence.evidence_id] = gap_evidence
            gaps.append(
                BankingDataGap(
                    gap_id=deterministic_id(
                        "BDGAP",
                        context.evaluation_case.evaluation_case_id,
                        context.request.request_id,
                        code,
                    ),
                    code=code,
                    detail=detail,
                    blocking_for_precheck=True,
                    evidence_ids=(gap_evidence.evidence_id,),
                )
            )
        return tuple(gaps)

    def _request_sources(
        self, context: BankingDiscoveryContext
    ) -> tuple[EvidenceRef, ...]:
        by_id = {
            item.evidence_id: item for item in context.request_artifact.evidence_refs
        }
        return tuple(by_id[item] for item in context.request.evidence_ids)

    @staticmethod
    def _amount_evidence(
        context: BankingDiscoveryContext,
    ) -> tuple[EvidenceRef, ...]:
        if context.request.requested_amount is not None:
            by_id = {
                item.evidence_id: item
                for item in context.request_artifact.evidence_refs
            }
            return tuple(by_id[item] for item in context.request.amount_evidence_ids)
        if context.supplement is not None and context.supplement_artifact is not None:
            by_id = {
                item.evidence_id: item
                for item in context.supplement_artifact.evidence_refs
            }
            return tuple(by_id[item] for item in context.supplement.evidence_ids)
        return ()

    def _binding_evidence(self, binding: BankingNeedBinding) -> EvidenceRef:
        return self._policy_evidence(
            record_id=binding.binding_id,
            field="explicit_catalog_binding",
            display_value={
                "need_type": binding.need_type.value,
                "bank_product_ids": binding.bank_product_ids,
                "precheck_api_by_product": binding.precheck_api_by_product,
                "precheck_field_sources_by_api": (
                    binding.precheck_field_sources_by_api
                ),
                "handling_rule_ids": binding.handling_rule_ids,
                "allowed_product_combinations": binding.allowed_product_combinations,
            },
        )

    def _policy_evidence(
        self,
        *,
        record_id: str,
        field: str,
        display_value: Any,
    ) -> EvidenceRef:
        safe_display = json_safe(display_value)
        return EvidenceRef(
            evidence_id=deterministic_id(
                "EVD",
                SourceType.POLICY_CONFIG,
                self._policy.policy_id,
                self._policy.mapping_version,
                self._policy.policy_hash,
                record_id,
                field,
                safe_display,
            ),
            source_type=SourceType.POLICY_CONFIG,
            sheet="BANKING_CATALOG_POLICY",
            row_number=0,
            record_id=record_id,
            field=field,
            display_value=safe_display,
        )

    @staticmethod
    def _allowed_combinations(
        bindings: Iterable[BankingNeedBinding],
        option_ids: dict[tuple[BankingNeedType, str], str],
    ) -> tuple[tuple[str, ...], ...]:
        combinations: set[tuple[str, ...]] = set()
        for binding in bindings:
            for products in binding.allowed_product_combinations:
                combination = tuple(
                    sorted(option_ids[(binding.need_type, product_id)] for product_id in products)
                )
                combinations.add(combination)
        return tuple(sorted(combinations))

    @staticmethod
    def _exact(
        dataset: DatasetSnapshot,
        definition: SheetDefinition,
        record_id: str,
    ) -> DatasetRecord:
        matches = dataset.lookup(definition, record_id)
        if len(matches) != 1:
            raise BankingDiscoveryBuildError(
                f"Configured Banking catalog ID {record_id} must resolve exactly once "
                f"in {definition.sheet_name}; found {len(matches)}."
            )
        return matches[0]

    @staticmethod
    def _text(record: DatasetRecord, field: str) -> str:
        value = record.values.get(field)
        if not isinstance(value, str) or not value.strip():
            raise BankingDiscoveryBuildError(
                f"Banking catalog field {record.record_id}.{field} must be non-empty text."
            )
        return value

    @staticmethod
    def _number(record: DatasetRecord, field: str) -> BankingCatalogNumber:
        value = record.values.get(field)
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise BankingDiscoveryBuildError(
                f"Banking catalog field {record.record_id}.{field} must be numeric or null."
            )
        return value

    @staticmethod
    def _field_evidence_id(
        evidence: tuple[EvidenceRef, ...], field: str
    ) -> str:
        matches = tuple(item.evidence_id for item in evidence if item.field == field)
        if len(matches) != 1:  # pragma: no cover - fixed local field construction
            raise BankingDiscoveryBuildError(
                f"Expected one evidence reference for Banking field {field}."
            )
        return matches[0]

    @staticmethod
    def _merge_evidence(
        target: dict[str, EvidenceRef],
        source: tuple[EvidenceRef, ...],
    ) -> None:
        target.update((item.evidence_id, item) for item in source)

    @staticmethod
    def _unique_evidence(
        *groups: tuple[EvidenceRef, ...],
    ) -> tuple[EvidenceRef, ...]:
        by_id = {item.evidence_id: item for group in groups for item in group}
        return tuple(by_id[key] for key in sorted(by_id))

    @classmethod
    def _failed_safe(cls, message: str) -> BankingDiscoveryComponentResult:
        return BankingDiscoveryComponentResult(
            status=ComponentStatus.FAILED_SAFE,
            discovery_status=BankingDiscoveryStatus.FAILED_SAFE,
            runtime_events=(
                RuntimeEvent(
                    event_type="BANKING_DISCOVERY_FAILED_SAFE",
                    message=message,
                ),
            ),
        )
