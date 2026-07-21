"""Declarative base and scope-specific Planner requirements."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from numbers import Real
from typing import TYPE_CHECKING, Any

from opc_mis.domain.enums import EvaluationScope
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.team_pack import SheetRegistry
from opc_mis.domain.validation import valid_date_like, valid_identifier, valid_numeric

if TYPE_CHECKING:
    from opc_mis.business.skills.planner.case_builder import CaseBuildOutcome


@dataclass(frozen=True)
class RequirementDefinition:
    """Declarative field requirement for one resolved entity."""

    code: str
    entity: str
    field: str
    expected_type: str
    reason: str
    scopes: frozenset[EvaluationScope]
    predicate: Callable[[Any], bool]


@dataclass(frozen=True)
class RequirementFailure:
    """Blocking requirement failure later converted to MissingDataRequest."""

    code: str
    target_record: str
    field: str
    expected_type: str
    reason: str
    evidence_refs: tuple[EvidenceRef, ...] = ()


def _non_empty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


class RequirementRegistry:
    """Evaluate base integrity and only the requirements needed by requested scopes."""

    DEFINITIONS = (
        RequirementDefinition(
            code="BASE_CONTRACT_ID_REQUIRED",
            entity="contract",
            field="contract_id",
            expected_type="non-empty identifier",
            reason="The selected contract must have a valid primary identifier.",
            scopes=frozenset(),
            predicate=valid_identifier,
        ),
        RequirementDefinition(
            code="BASE_CUSTOMER_REFERENCE_REQUIRED",
            entity="contract",
            field="customer_id",
            expected_type="non-empty identifier",
            reason="The selected contract must explicitly reference a customer.",
            scopes=frozenset(),
            predicate=valid_identifier,
        ),
        RequirementDefinition(
            code="FINANCE_CONTRACT_VALUE_REQUIRED",
            entity="contract",
            field="contract_value",
            expected_type="number",
            reason="Finance Assessment requires a valid contract value input.",
            scopes=frozenset({EvaluationScope.FINANCE}),
            predicate=valid_numeric,
        ),
        RequirementDefinition(
            code="FINANCE_GROSS_MARGIN_INPUT_REQUIRED",
            entity="contract",
            field="gross_margin",
            expected_type="number",
            reason="Finance Assessment requires a valid source gross-margin input.",
            scopes=frozenset({EvaluationScope.FINANCE}),
            predicate=valid_numeric,
        ),
        RequirementDefinition(
            code="FINANCE_PAYMENT_TERMS_REQUIRED",
            entity="contract",
            field="payment_terms",
            expected_type="non-empty text",
            reason="Finance Assessment requires the source payment terms.",
            scopes=frozenset({EvaluationScope.FINANCE}),
            predicate=_non_empty_text,
        ),
        RequirementDefinition(
            code="OPERATIONS_START_DATE_REQUIRED",
            entity="contract",
            field="start_date",
            expected_type="date or Excel serial number",
            reason="Operations Assessment requires a valid contract start date.",
            scopes=frozenset({EvaluationScope.OPERATIONS}),
            predicate=valid_date_like,
        ),
        RequirementDefinition(
            code="OPERATIONS_END_DATE_REQUIRED",
            entity="contract",
            field="end_date",
            expected_type="date or Excel serial number",
            reason="Operations Assessment requires a valid contract end date.",
            scopes=frozenset({EvaluationScope.OPERATIONS}),
            predicate=valid_date_like,
        ),
    )

    def evaluate(self, outcome: CaseBuildOutcome) -> tuple[RequirementFailure, ...]:
        """Return deterministic blocking failures for the requested case only."""
        failures = list(outcome.failures)
        dataset = outcome.dataset

        for sheet in dataset.missing_sheets:
            failures.append(
                RequirementFailure(
                    code="MANDATORY_BASE_SHEET_MISSING",
                    target_record=sheet,
                    field="sheet",
                    expected_type="TeamPack worksheet",
                    reason=f"Mandatory Planner sheet {sheet} is missing.",
                )
            )
        for sheet, headers in sorted(dataset.missing_headers.items()):
            registry_definition = SheetRegistry.BY_SHEET.get(sheet)
            if registry_definition is None or not registry_definition.mandatory:
                continue
            for header in headers:
                failures.append(
                    RequirementFailure(
                        code="MANDATORY_HEADER_MISSING",
                        target_record=sheet,
                        field=header,
                        expected_type="workbook column",
                        reason=f"Required header {header} is missing from {sheet}.",
                    )
                )

        contract = outcome.contract
        if contract is not None:
            for definition in self.DEFINITIONS:
                if definition.entity != "contract":
                    continue
                if definition.scopes and not definition.scopes.intersection(
                    outcome.request.evaluation_scope
                ):
                    continue
                value = contract.values.get(definition.field)
                if not definition.predicate(value):
                    failures.append(
                        RequirementFailure(
                            code=definition.code,
                            target_record=contract.record_id,
                            field=definition.field,
                            expected_type=definition.expected_type,
                            reason=definition.reason,
                            evidence_refs=(
                                outcome.lineage.record_field(contract, definition.field),
                            ),
                        )
                    )

        selected_sheets = {record.sheet for record in outcome.selected_records}
        selected_keys = {(record.sheet, record.record_id) for record in outcome.selected_records}
        for sheet in sorted(selected_sheets):
            definition = SheetRegistry.BY_SHEET.get(sheet)
            if definition is None or definition.primary_key is None:
                continue
            for duplicate_id in dataset.duplicate_ids.get(sheet, ()):
                if (sheet, duplicate_id) not in selected_keys:
                    continue
                matches = dataset.lookup(definition, duplicate_id)
                failures.append(
                    RequirementFailure(
                        code="DUPLICATE_PRIMARY_KEY",
                        target_record=duplicate_id,
                        field=definition.primary_key,
                        expected_type=f"unique {definition.primary_key}",
                        reason=(
                            f"Selected {definition.primary_key} resolves to multiple rows "
                            f"in {sheet}."
                        ),
                        evidence_refs=tuple(
                            outcome.lineage.record_field(match, definition.primary_key)
                            for match in matches
                        ),
                    )
                )
        for issue in dataset.validation_issues:
            if (issue.sheet, issue.record_id) not in selected_keys:
                continue
            record = next(
                (
                    selected
                    for selected in outcome.selected_records
                    if selected.sheet == issue.sheet and selected.record_id == issue.record_id
                ),
                None,
            )
            evidence = (
                (outcome.lineage.record_field(record, issue.field),) if record is not None else ()
            )
            failures.append(
                RequirementFailure(
                    code=issue.code,
                    target_record=issue.record_id,
                    field=issue.field,
                    expected_type="valid TeamPack value",
                    reason=issue.reason,
                    evidence_refs=evidence,
                )
            )

        unique: dict[tuple[str, str, str], RequirementFailure] = {}
        for failure in failures:
            unique[(failure.code, failure.target_record, failure.field)] = failure
        return tuple(unique[key] for key in sorted(unique))


def is_number(value: Any) -> bool:
    """Retained as a narrow public predicate for unit testing requirement definitions."""
    return isinstance(value, Real) and not isinstance(value, bool)
