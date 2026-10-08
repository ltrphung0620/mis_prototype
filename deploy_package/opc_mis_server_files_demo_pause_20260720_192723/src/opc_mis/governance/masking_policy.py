"""Deterministic data minimization and masking policy execution."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Collection, Mapping
from decimal import Decimal, InvalidOperation
from math import isfinite
from types import MappingProxyType
from typing import Final

from opc_mis.domain.data_classification_models import DataClassification
from opc_mis.domain.lineage import deterministic_id
from opc_mis.domain.masking_models import (
    MaskableScalar,
    MaskedPayload,
    MaskingAction,
    MaskingAlgorithmId,
    MaskingContext,
    MaskingManifest,
    MaskingManifestItem,
    MaskingPolicyDocument,
    MaskingReasonCode,
    MaskingRule,
    TokenizationContext,
    VndGeneralizationConfig,
    masking_policy_document_sha256,
)
from opc_mis.governance.data_classification_policy import DataClassificationPolicy
from opc_mis.ports.text_redaction_service import TextRedactionService
from opc_mis.ports.tokenization_service import TokenizationService

_OMITTED: Final = object()


class MaskingPolicyError(ValueError):
    """Base class for safe masking failures that never echo raw values."""


class DataMinimizationError(MaskingPolicyError):
    """Raised when the caller does not declare a minimum required field set."""


class UnsafeMaskingInputError(MaskingPolicyError):
    """Raised when a configured algorithm cannot safely handle a field value."""


class MaskingPolicy:
    """Classify, minimize, mask, and manifest a flat partner payload."""

    __slots__ = (
        "_classification_policy",
        "_document",
        "_redactor",
        "_rules",
        "_tokenizer",
    )

    def __init__(
        self,
        *,
        document: MaskingPolicyDocument,
        tokenizer: TokenizationService,
        redactor: TextRedactionService,
    ) -> None:
        self._document = document
        self._classification_policy = DataClassificationPolicy(
            policy_id=document.policy_id,
            policy_version=document.policy_version,
            rules=document.classification_rules,
        )
        self._rules = MappingProxyType(
            {item.field_name: item for item in document.masking_rules}
        )
        self._tokenizer = tokenizer
        self._redactor = redactor

    def mask_payload(
        self,
        payload: Mapping[str, MaskableScalar],
        *,
        recipient: str,
        purpose: str,
        required_fields: Collection[str],
        source_evidence_ids_by_field: Mapping[str, Collection[str]],
    ) -> MaskedPayload:
        """Return only required, context-authorized, safely transformed fields."""
        if not payload:
            raise DataMinimizationError("payload must contain at least one field")
        if not recipient or not purpose:
            raise DataMinimizationError("recipient and purpose must be explicit")
        required = frozenset(required_fields)
        if not required:
            raise DataMinimizationError("required_fields must be explicitly declared")
        if any(not isinstance(field, str) or not field for field in required):
            raise DataMinimizationError("required_fields must contain non-empty field names")
        missing_required = required.difference(payload)
        if missing_required:
            raise DataMinimizationError(
                "payload is missing declared required_fields: "
                + ", ".join(sorted(missing_required))
            )
        if set(source_evidence_ids_by_field) != set(payload):
            raise DataMinimizationError(
                "source evidence must cover every exact masking input field"
            )
        normalized_sources: dict[str, tuple[str, ...]] = {}
        for field_name in payload:
            source_ids = tuple(source_evidence_ids_by_field[field_name])
            if (
                not source_ids
                or any(not isinstance(item, str) or not item for item in source_ids)
                or len(set(source_ids)) != len(source_ids)
            ):
                raise DataMinimizationError(
                    "each masking input field requires unique non-empty source evidence"
                )
            normalized_sources[field_name] = source_ids
        if recipient not in self._document.allowed_recipients:
            raise DataMinimizationError(
                "recipient is not authorized by the masking policy"
            )

        context = MaskingContext(recipient=recipient, purpose=purpose)
        decisions = tuple(
            self._classification_policy.classify(field_name)
            for field_name in payload
        )
        exact_identifiers = {
            decision.field_name: value
            for decision in decisions
            if decision.classification
            in {DataClassification.INTERNAL, DataClassification.RESTRICTED}
            and isinstance((value := payload[decision.field_name]), str)
            and value
        }

        values: dict[str, MaskableScalar] = {}
        items: list[MaskingManifestItem] = []
        for decision in decisions:
            field_name = decision.field_name
            value = payload[field_name]
            self._require_json_scalar(field_name, value)
            configured_rule = self._rules[field_name]
            rule, reason = self._effective_rule(
                configured_rule,
                field_name=field_name,
                context=context,
                required=required,
            )
            output = self._apply(
                rule,
                field_name=field_name,
                value=value,
                context=context,
                exact_identifiers=exact_identifiers,
            )
            included = output is not _OMITTED
            if included:
                values[field_name] = output  # type: ignore[assignment]
            digest = self._output_digest(None if output is _OMITTED else output)
            items.append(
                MaskingManifestItem(
                    field_name=field_name,
                    classification_decision_id=decision.decision_id,
                    classification=decision.classification,
                    purpose=purpose,
                    recipient=recipient,
                    action=rule.action,
                    reason_code=reason,
                    algorithm_id=rule.algorithm_id,
                    algorithm_version=rule.algorithm_version,
                    key_version=rule.key_version,
                    included_in_payload=included,
                    output_reference=self._safe_output_reference(rule.action, output),
                    output_digest=digest,
                    policy_reference=decision.policy_reference,
                    policy_evidence_ids=decision.source_evidence_ids,
                    source_evidence_ids=normalized_sources[field_name],
                )
            )

        manifest_items = tuple(items)
        policy_document_sha256 = masking_policy_document_sha256(self._document)
        manifest_id = deterministic_id(
            "MASK",
            self._document.policy_id,
            self._document.policy_version,
            policy_document_sha256,
            purpose,
            recipient,
            tuple(item.model_dump(mode="json") for item in manifest_items),
        )
        manifest = MaskingManifest(
            manifest_id=manifest_id,
            policy_id=self._document.policy_id,
            policy_version=self._document.policy_version,
            policy_document_sha256=policy_document_sha256,
            purpose=purpose,
            recipient=recipient,
            items=manifest_items,
        )
        return MaskedPayload(
            values=values,
            classification_decisions=decisions,
            manifest=manifest,
        )

    @staticmethod
    def _require_json_scalar(field_name: str, value: object) -> None:
        if value is None or isinstance(value, (str, bool, int)):
            return
        if isinstance(value, float) and isfinite(value):
            return
        raise UnsafeMaskingInputError(
            f"Field {field_name!r} must be a finite JSON scalar before masking."
        )

    @staticmethod
    def _context_allowed(value: str, allowed: tuple[str, ...]) -> bool:
        return "*" in allowed or value in allowed

    def _effective_rule(
        self,
        configured: MaskingRule,
        *,
        field_name: str,
        context: MaskingContext,
        required: frozenset[str],
    ) -> tuple[MaskingRule, MaskingReasonCode]:
        if field_name not in required:
            return self._omission_rule(configured), MaskingReasonCode.NOT_REQUIRED_FOR_PURPOSE
        if not self._context_allowed(
            context.purpose, configured.allowed_purposes
        ) or not self._context_allowed(
            context.recipient, configured.allowed_recipients
        ):
            return self._omission_rule(configured), MaskingReasonCode.CONTEXT_NOT_ALLOWED
        return configured, MaskingReasonCode.POLICY_ACTION

    @staticmethod
    def _omission_rule(configured: MaskingRule) -> MaskingRule:
        return MaskingRule(
            rule_id=f"{configured.rule_id}:MINIMIZED",
            field_name=configured.field_name,
            action=MaskingAction.OMIT,
            algorithm_id=MaskingAlgorithmId.DATA_MINIMIZATION_OMIT,
            algorithm_version="v1",
            allowed_purposes=configured.allowed_purposes,
            allowed_recipients=configured.allowed_recipients,
        )

    def _apply(
        self,
        rule: MaskingRule,
        *,
        field_name: str,
        value: MaskableScalar,
        context: MaskingContext,
        exact_identifiers: Mapping[str, str],
    ) -> object:
        if rule.action is MaskingAction.OMIT:
            return _OMITTED
        if rule.action is MaskingAction.ALLOW_EXACT:
            return value
        if rule.action is MaskingAction.TOKENIZE:
            if not isinstance(value, str) or not value:
                raise UnsafeMaskingInputError(
                    f"Field {field_name!r} must be non-empty text for tokenization."
                )
            if rule.key_version is None:  # pragma: no cover - model invariant
                raise MaskingPolicyError("tokenization rule has no key version")
            return self._tokenizer.tokenize(
                value,
                TokenizationContext(
                    provider=context.recipient,
                    purpose=context.purpose,
                    field_type=field_name,
                    key_version=rule.key_version,
                ),
            )
        if rule.action is MaskingAction.PARTIAL_MASK:
            return self._partial_mask(rule, field_name, value)
        if rule.action is MaskingAction.GENERALIZE:
            return self._generalize_vnd(
                field_name,
                value,
                self._document.vnd_generalization,
            )
        if rule.action is MaskingAction.REDACT:
            if not isinstance(value, str):
                raise UnsafeMaskingInputError(
                    f"Field {field_name!r} must be text for redaction."
                )
            return self._redactor.redact(
                value,
                exact_identifiers=exact_identifiers,
            ).text
        if rule.action is MaskingAction.VAULT_REFERENCE:
            if not isinstance(value, str) or not value.startswith("vault://"):
                raise UnsafeMaskingInputError(
                    f"Field {field_name!r} requires a pre-existing vault:// reference."
                )
            return value
        raise MaskingPolicyError(f"Unsupported masking action for field {field_name!r}.")

    @staticmethod
    def _partial_mask(
        rule: MaskingRule,
        field_name: str,
        value: MaskableScalar,
    ) -> str:
        if not isinstance(value, str) or not value:
            raise UnsafeMaskingInputError(
                f"Field {field_name!r} must be non-empty text for partial masking."
            )
        prefix = rule.visible_prefix_characters
        suffix = rule.visible_suffix_characters
        if len(value) <= prefix + suffix:
            return "[MASKED]"
        left = value[:prefix] if prefix else ""
        right = value[-suffix:] if suffix else ""
        return f"{left}***{right}"

    @staticmethod
    def _generalize_vnd(
        field_name: str,
        value: MaskableScalar,
        config: VndGeneralizationConfig,
    ) -> str:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise UnsafeMaskingInputError(
                f"Field {field_name!r} must be numeric for VND generalization."
            )
        if isinstance(value, float) and not isfinite(value):
            raise UnsafeMaskingInputError(
                f"Field {field_name!r} must be finite for VND generalization."
            )
        try:
            amount = Decimal(str(value))
        except InvalidOperation as exc:  # pragma: no cover - guarded above
            raise UnsafeMaskingInputError(
                f"Field {field_name!r} cannot be generalized."
            ) from exc
        if amount < 0 or amount != amount.to_integral_value():
            raise UnsafeMaskingInputError(
                f"Field {field_name!r} must be a non-negative whole VND amount."
            )
        tier = next(
            item
            for item in config.tiers
            if item.upper_bound_exclusive is None
            or amount < item.upper_bound_exclusive
        )
        unit = Decimal(tier.unit)
        lower = int((amount // unit) * unit)
        upper = lower + tier.unit
        return f"{MaskingPolicy._vnd_label(lower)}-{MaskingPolicy._vnd_label(upper)} VND"

    @staticmethod
    def _vnd_label(value: int) -> str:
        if value and value % 1_000_000_000 == 0:
            return f"{value // 1_000_000_000}B"
        if value and value % 1_000_000 == 0:
            return f"{value // 1_000_000}M"
        if value and value % 1_000 == 0:
            return f"{value // 1_000}K"
        return str(value)

    @staticmethod
    def _output_digest(value: object) -> str:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _safe_output_reference(action: MaskingAction, output: object) -> str | None:
        if output is _OMITTED:
            return None
        if action in {
            MaskingAction.TOKENIZE,
            MaskingAction.PARTIAL_MASK,
            MaskingAction.GENERALIZE,
            MaskingAction.VAULT_REFERENCE,
        }:
            return str(output)
        return None
