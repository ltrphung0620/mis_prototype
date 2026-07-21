"""Resolve typed contract requirements from exact, case-selected source fields."""

from __future__ import annotations

import math
from dataclasses import dataclass

from opc_mis.business.skills.planner.requirement_registry import RequirementFailure
from opc_mis.domain.dataset import DatasetRecord, DatasetSnapshot
from opc_mis.domain.enums import (
    ContractRequirementType,
    CurrencyCode,
    RequirementAmountSemantics,
    RequirementCertainty,
)
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.lineage import LineageFactory, deterministic_id
from opc_mis.domain.planner_models import ContractRequirement, PlannerWarning
from opc_mis.domain.team_pack import SheetRegistry
from opc_mis.domain.validation import valid_identifier


@dataclass(frozen=True)
class ContractRequirementResolution:
    """Requirements, exact credit links, warnings, and their evidence closure."""

    requirements: tuple[ContractRequirement, ...]
    credit_profiles: tuple[DatasetRecord, ...]
    failures: tuple[RequirementFailure, ...]
    warnings: tuple[PlannerWarning, ...]
    evidence_refs: tuple[EvidenceRef, ...]


@dataclass(frozen=True)
class _RequirementSource:
    requirement_type: ContractRequirementType
    certainty: RequirementCertainty
    record: DatasetRecord
    field: str
    evidence: EvidenceRef


@dataclass(frozen=True)
class _CreditCandidate:
    profile: DatasetRecord
    requested_amount: int | None
    evidence_refs: tuple[EvidenceRef, ...]


_REQUIREMENT_PHRASES = {
    "performance bond required": (
        ContractRequirementType.PERFORMANCE_BOND,
        RequirementCertainty.REQUIRED,
    ),
    "requires performance bond": (
        ContractRequirementType.PERFORMANCE_BOND,
        RequirementCertainty.REQUIRED,
    ),
    "requires working capital": (
        ContractRequirementType.WORKING_CAPITAL,
        RequirementCertainty.REQUIRED,
    ),
    "possible lc/trade finance": (
        ContractRequirementType.TRADE_FINANCE_LC,
        RequirementCertainty.POSSIBLE,
    ),
    "may require lc support": (
        ContractRequirementType.TRADE_FINANCE_LC,
        RequirementCertainty.POSSIBLE,
    ),
}

_CREDIT_REQUEST_TYPES = {
    "performance bond": ContractRequirementType.PERFORMANCE_BOND,
    "working capital line": ContractRequirementType.WORKING_CAPITAL,
    "micro working capital for local rollout": ContractRequirementType.WORKING_CAPITAL,
    "trade finance/lc support": ContractRequirementType.TRADE_FINANCE_LC,
}

def _normalize_phrase(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.casefold().split())
    return normalized or None


def _positive_integral_amount(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    amount = int(value)
    if amount <= 0 or amount != value:
        return None
    return amount


def _unique_evidence(items: tuple[EvidenceRef, ...]) -> tuple[EvidenceRef, ...]:
    by_id = {item.evidence_id: item for item in items}
    return tuple(by_id[evidence_id] for evidence_id in sorted(by_id))


class ContractRequirementResolver:
    """Use exact phrases and exact canonical IDs; never use fuzzy or name matching."""

    def resolve(
        self,
        *,
        dataset: DatasetSnapshot,
        contract: DatasetRecord,
        orders: tuple[DatasetRecord, ...],
        evaluation_case_id: str,
        lineage: LineageFactory,
    ) -> ContractRequirementResolution:
        sources = self._requirement_sources(contract, orders, lineage)
        grouped: dict[
            tuple[ContractRequirementType, RequirementCertainty],
            list[_RequirementSource],
        ] = {}
        for source in sources:
            grouped.setdefault((source.requirement_type, source.certainty), []).append(source)

        opc_company = self._opc_company_record(dataset)
        requirements: list[ContractRequirement] = []
        linked_profiles: dict[str, DatasetRecord] = {}
        failures: list[RequirementFailure] = []
        warnings: list[PlannerWarning] = []
        all_evidence: list[EvidenceRef] = [source.evidence for source in sources]

        for key in sorted(grouped, key=lambda item: (item[0].value, item[1].value)):
            requirement_type, certainty = key
            requirement_sources = tuple(
                sorted(
                    grouped[key],
                    key=lambda item: (item.record.sheet, item.record.record_id, item.field),
                )
            )
            source_evidence = tuple(item.evidence for item in requirement_sources)
            candidates = self._credit_candidates(
                dataset=dataset,
                contract=contract,
                requirement_type=requirement_type,
                opc_company=opc_company,
                lineage=lineage,
            )
            for candidate in candidates:
                all_evidence.extend(candidate.evidence_refs)

            selected_candidate = candidates[0] if len(candidates) == 1 else None
            credit_case_id = (
                selected_candidate.profile.record_id
                if selected_candidate is not None
                else None
            )
            requested_amount = (
                selected_candidate.requested_amount
                if selected_candidate is not None
                else None
            )
            requirement_evidence = _unique_evidence(
                source_evidence
                + tuple(
                    evidence
                    for credit_candidate in candidates
                    for evidence in credit_candidate.evidence_refs
                )
            )
            requirement_id = deterministic_id(
                "CREQ",
                evaluation_case_id,
                requirement_type,
                certainty,
                tuple(item.evidence_id for item in source_evidence),
                tuple(
                    (item.profile.record_id, item.requested_amount)
                    for item in candidates
                ),
            )
            requirement = ContractRequirement(
                requirement_id=requirement_id,
                requirement_type=requirement_type,
                certainty=certainty,
                requested_amount=requested_amount,
                requested_amount_currency=CurrencyCode.VND,
                amount_semantics=(
                    RequirementAmountSemantics.CREDIT_PROFILE_REQUESTED_AMOUNT
                    if requested_amount is not None
                    else None
                ),
                credit_case_id=credit_case_id,
                source_record_ids=tuple(
                    item.record.record_id for item in requirement_sources
                ),
                source_fields=tuple(item.field for item in requirement_sources),
                evidence_ids=tuple(item.evidence_id for item in requirement_evidence),
            )
            requirements.append(requirement)

            for credit_candidate in candidates:
                linked_profiles[credit_candidate.profile.record_id] = (
                    credit_candidate.profile
                )
            if requested_amount is not None:
                continue
            warning_evidence = _unique_evidence(
                source_evidence
                + tuple(
                    evidence
                    for credit_candidate in candidates
                    for evidence in credit_candidate.evidence_refs
                )
            )
            warning_code, warning_reason = self._unresolved_reason(candidates)
            if (
                requirement_type is ContractRequirementType.PERFORMANCE_BOND
                and certainty is RequirementCertainty.REQUIRED
            ):
                failure_code = {
                    "CONTRACT_REQUIREMENT_CREDIT_PROFILE_UNLINKED": (
                        "PERFORMANCE_BOND_CREDIT_PROFILE_REQUIRED"
                    ),
                    "CONTRACT_REQUIREMENT_CREDIT_PROFILE_AMBIGUOUS": (
                        "PERFORMANCE_BOND_CREDIT_PROFILE_AMBIGUOUS"
                    ),
                    "CONTRACT_REQUIREMENT_CREDIT_AMOUNT_INVALID": (
                        "PERFORMANCE_BOND_REQUESTED_AMOUNT_REQUIRED"
                    ),
                }[warning_code]
                failures.append(
                    RequirementFailure(
                        code=failure_code,
                        target_record=contract.record_id,
                        field="requested_amount",
                        expected_type=(
                            "one exact linked performance-bond credit profile with a "
                            "positive integral requested_amount"
                        ),
                        reason=warning_reason,
                        evidence_refs=warning_evidence,
                    )
                )
                continue
            warnings.append(
                PlannerWarning(
                    warning_code=warning_code,
                    target_record=contract.record_id,
                    field="contract_requirements",
                    reason=warning_reason,
                    evidence_refs=warning_evidence,
                    details={
                        "requirement_id": requirement_id,
                        "requirement_type": requirement_type.value,
                        "certainty": certainty.value,
                    },
                )
            )

        for warning in warnings:
            all_evidence.extend(warning.evidence_refs)
        return ContractRequirementResolution(
            requirements=tuple(requirements),
            credit_profiles=tuple(
                linked_profiles[credit_case_id]
                for credit_case_id in sorted(linked_profiles)
            ),
            failures=tuple(failures),
            warnings=tuple(warnings),
            evidence_refs=_unique_evidence(tuple(all_evidence)),
        )

    @staticmethod
    def _requirement_sources(
        contract: DatasetRecord,
        orders: tuple[DatasetRecord, ...],
        lineage: LineageFactory,
    ) -> tuple[_RequirementSource, ...]:
        sources: list[_RequirementSource] = []
        for record, field in ((contract, "payment_terms"), *(
            (order, "delivery_note") for order in orders
        )):
            phrase = _normalize_phrase(record.values.get(field))
            classification = _REQUIREMENT_PHRASES.get(phrase) if phrase is not None else None
            if classification is None:
                continue
            requirement_type, certainty = classification
            sources.append(
                _RequirementSource(
                    requirement_type=requirement_type,
                    certainty=certainty,
                    record=record,
                    field=field,
                    evidence=lineage.record_field(record, field),
                )
            )
        return tuple(sources)

    @staticmethod
    def _opc_company_record(dataset: DatasetSnapshot) -> DatasetRecord | None:
        matches = tuple(
            record
            for record in dataset.records(SheetRegistry.OPC_PROFILE)
            if record.values.get("field") == "company_id"
            and valid_identifier(record.values.get("value"))
        )
        return matches[0] if len(matches) == 1 else None

    @classmethod
    def _credit_candidates(
        cls,
        *,
        dataset: DatasetSnapshot,
        contract: DatasetRecord,
        requirement_type: ContractRequirementType,
        opc_company: DatasetRecord | None,
        lineage: LineageFactory,
    ) -> tuple[_CreditCandidate, ...]:
        if opc_company is None:
            return ()
        company_id = opc_company.values.get("value")
        company_evidence = lineage.record_field(opc_company, "value")
        contract_evidence = lineage.record_field(contract, "contract_id")
        contract_ids = tuple(
            record.record_id
            for record in dataset.records(SheetRegistry.CONTRACTS)
            if valid_identifier(record.record_id)
        )
        candidates: list[_CreditCandidate] = []
        for profile in dataset.records(SheetRegistry.CREDIT_PROFILES):
            if profile.values.get("company_id") != company_id:
                continue
            request_type = _normalize_phrase(profile.values.get("request_type"))
            if _CREDIT_REQUEST_TYPES.get(request_type) is not requirement_type:
                continue
            tokens = cls._contract_tokens(
                profile.values.get("collateral_or_basis"), contract_ids
            )
            if tokens != (contract.record_id,):
                continue
            if len(dataset.lookup(SheetRegistry.CONTRACTS, tokens[0])) != 1:
                continue
            requested_amount = _positive_integral_amount(
                profile.values.get("requested_amount")
            )
            collateral_evidence = lineage.record_field(profile, "collateral_or_basis")
            relationship_evidence = lineage.derived(
                sheet=SheetRegistry.CREDIT_PROFILES.sheet_name,
                record_id=profile.record_id,
                field="contract_requirement_relationship",
                display={
                    "contract_id": contract.record_id,
                    "credit_case_id": profile.record_id,
                },
                sources=(contract_evidence, collateral_evidence),
            )
            evidence = _unique_evidence(
                (
                    company_evidence,
                    contract_evidence,
                    lineage.record_field(profile, "credit_case_id"),
                    lineage.record_field(profile, "company_id"),
                    lineage.record_field(profile, "request_type"),
                    lineage.record_field(profile, "requested_amount"),
                    collateral_evidence,
                    relationship_evidence,
                )
            )
            candidates.append(
                _CreditCandidate(
                    profile=profile,
                    requested_amount=requested_amount,
                    evidence_refs=evidence,
                )
            )
        return tuple(sorted(candidates, key=lambda item: item.profile.record_id))

    @staticmethod
    def _unresolved_reason(
        candidates: tuple[_CreditCandidate, ...],
    ) -> tuple[str, str]:
        if not candidates:
            return (
                "CONTRACT_REQUIREMENT_CREDIT_PROFILE_UNLINKED",
                "No credit profile satisfies the exact contract-ID token, OPC company, "
                "and request-type relationship rules.",
            )
        if len(candidates) > 1:
            return (
                "CONTRACT_REQUIREMENT_CREDIT_PROFILE_AMBIGUOUS",
                "Multiple credit profiles satisfy the exact contract, company, and type "
                "rules; Planner did not choose between them.",
            )
        return (
            "CONTRACT_REQUIREMENT_CREDIT_AMOUNT_INVALID",
            "The exact linked credit profile does not contain a positive integral "
            "requested_amount.",
        )

    @staticmethod
    def _contract_tokens(
        value: object,
        contract_ids: tuple[str, ...],
    ) -> tuple[str, ...]:
        if not isinstance(value, str):
            return ()
        known_ids = set(contract_ids)
        tokens = {token for token in value.split() if token in known_ids}
        return tuple(sorted(tokens))
