"""Exact, fail-closed data-classification policy execution."""

from __future__ import annotations

from types import MappingProxyType

from opc_mis.domain.data_classification_models import (
    ClassificationDecision,
    DataClassificationRule,
)
from opc_mis.domain.lineage import deterministic_id


class DataClassificationPolicyError(ValueError):
    """Base class for safe classification-policy failures."""


class UnclassifiedFieldError(DataClassificationPolicyError):
    """Raised when no exact field rule exists; values are never included."""


class DataClassificationPolicy:
    """Resolve exact field names without fuzzy, substring, or semantic matching."""

    __slots__ = ("_policy_id", "_policy_version", "_rules")

    def __init__(
        self,
        *,
        policy_id: str,
        policy_version: str,
        rules: tuple[DataClassificationRule, ...],
    ) -> None:
        if not policy_id or not policy_version:
            raise DataClassificationPolicyError(
                "classification policy identity must be non-empty"
            )
        by_field = {item.field_name: item for item in rules}
        if not rules or len(by_field) != len(rules):
            raise DataClassificationPolicyError(
                "classification rules must be non-empty and unique by field_name"
            )
        self._policy_id = policy_id
        self._policy_version = policy_version
        self._rules = MappingProxyType(by_field)

    def classify(self, field_name: str) -> ClassificationDecision:
        """Return one stable decision or fail closed for an unknown exact field."""
        rule = self._rules.get(field_name)
        if rule is None:
            raise UnclassifiedFieldError(
                f"No exact data-classification rule exists for field {field_name!r}."
            )
        return ClassificationDecision(
            decision_id=deterministic_id(
                "CLASS",
                self._policy_id,
                self._policy_version,
                rule.rule_id,
                rule.field_name,
                rule.classification,
                rule.policy_reference,
                rule.source_evidence_ids,
            ),
            field_name=rule.field_name,
            classification=rule.classification,
            rule_id=rule.rule_id,
            policy_reference=rule.policy_reference,
            source_evidence_ids=rule.source_evidence_ids,
        )

