"""Typed data-minimization, masking, and redaction contracts."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from opc_mis.domain.data_classification_models import (
    ClassificationDecision,
    DataClassification,
    DataClassificationRule,
)

MaskableScalar = StrictBool | StrictInt | StrictFloat | StrictStr | None


class MaskingAction(StrEnum):
    """Allowed deterministic handling actions for one selected field."""

    ALLOW_EXACT = "ALLOW_EXACT"
    OMIT = "OMIT"
    TOKENIZE = "TOKENIZE"
    PARTIAL_MASK = "PARTIAL_MASK"
    GENERALIZE = "GENERALIZE"
    REDACT = "REDACT"
    VAULT_REFERENCE = "VAULT_REFERENCE"


class MaskingAlgorithmId(StrEnum):
    """Registered algorithms; arbitrary algorithm names fail validation."""

    EXACT_PASS_THROUGH = "EXACT_PASS_THROUGH"
    DATA_MINIMIZATION_OMIT = "DATA_MINIMIZATION_OMIT"
    HMAC_SHA256_CONTEXTUAL_TOKEN = "HMAC_SHA256_CONTEXTUAL_TOKEN"
    PARTIAL_MASK_DISPLAY = "PARTIAL_MASK_DISPLAY"
    VND_VALUE_BANDING = "VND_VALUE_BANDING"
    FREE_TEXT_IDENTIFIER_REDACTION = "FREE_TEXT_IDENTIFIER_REDACTION"
    VAULT_REFERENCE_ONLY = "VAULT_REFERENCE_ONLY"


class MaskingReasonCode(StrEnum):
    """Machine-readable reason for the final outbound-field decision."""

    POLICY_ACTION = "POLICY_ACTION"
    NOT_REQUIRED_FOR_PURPOSE = "NOT_REQUIRED_FOR_PURPOSE"
    CONTEXT_NOT_ALLOWED = "CONTEXT_NOT_ALLOWED"


class TokenizationContext(BaseModel):
    """Context included in the HMAC namespace for one exact field."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: StrictStr = Field(min_length=1)
    purpose: StrictStr = Field(min_length=1)
    field_type: StrictStr = Field(min_length=1)
    key_version: StrictStr = Field(min_length=1)


class MaskingContext(BaseModel):
    """Outbound trust-boundary context supplied by the calling component."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    recipient: StrictStr = Field(min_length=1)
    purpose: StrictStr = Field(min_length=1)


class VndGeneralizationTier(BaseModel):
    """Magnitude tier selecting a deterministic VND band width."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    upper_bound_exclusive: StrictInt | None = Field(default=None, gt=0)
    unit: StrictInt = Field(gt=0)


class VndGeneralizationConfig(BaseModel):
    """Server-owned numeric banding parameters, never LLM-selected."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    algorithm_id: Literal[MaskingAlgorithmId.VND_VALUE_BANDING] = (
        MaskingAlgorithmId.VND_VALUE_BANDING
    )
    algorithm_version: StrictStr = Field(min_length=1)
    tiers: tuple[VndGeneralizationTier, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_tiers(self) -> VndGeneralizationConfig:
        """Require ascending finite bounds followed by one open-ended tier."""
        bounds = tuple(item.upper_bound_exclusive for item in self.tiers)
        if bounds[-1] is not None or any(bound is None for bound in bounds[:-1]):
            raise ValueError("the final VND tier must be the only open-ended tier")
        finite = tuple(bound for bound in bounds if bound is not None)
        if tuple(sorted(finite)) != finite or len(set(finite)) != len(finite):
            raise ValueError("VND tier upper bounds must be strictly ascending")
        return self


class MaskingRule(BaseModel):
    """One exact field action and its explicitly allowed outbound contexts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id: StrictStr = Field(min_length=1)
    field_name: StrictStr = Field(
        min_length=1,
        pattern=r"^[A-Za-z][A-Za-z0-9_]*$",
    )
    action: MaskingAction
    algorithm_id: MaskingAlgorithmId
    algorithm_version: StrictStr = Field(min_length=1)
    allowed_purposes: tuple[StrictStr, ...] = Field(min_length=1)
    allowed_recipients: tuple[StrictStr, ...] = Field(min_length=1)
    key_version: StrictStr | None = None
    token_bytes: StrictInt = Field(default=16, ge=16, le=32)
    visible_prefix_characters: StrictInt = Field(default=0, ge=0, le=32)
    visible_suffix_characters: StrictInt = Field(default=0, ge=0, le=32)

    @field_validator("allowed_purposes", "allowed_recipients")
    @classmethod
    def require_unique_allowlist(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require explicit, unambiguous context allowlists."""
        if len(set(value)) != len(value):
            raise ValueError("context allowlist values must be unique")
        return value

    @field_validator("allowed_recipients")
    @classmethod
    def reject_recipient_wildcard(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require exact partner or connector identities for every field rule."""
        if "*" in value:
            raise ValueError("allowed_recipients must not contain a wildcard")
        return value

    @model_validator(mode="after")
    def validate_algorithm_for_action(self) -> MaskingRule:
        """Prevent an action label from disguising a weaker algorithm."""
        expected = {
            MaskingAction.ALLOW_EXACT: MaskingAlgorithmId.EXACT_PASS_THROUGH,
            MaskingAction.OMIT: MaskingAlgorithmId.DATA_MINIMIZATION_OMIT,
            MaskingAction.TOKENIZE: MaskingAlgorithmId.HMAC_SHA256_CONTEXTUAL_TOKEN,
            MaskingAction.PARTIAL_MASK: MaskingAlgorithmId.PARTIAL_MASK_DISPLAY,
            MaskingAction.GENERALIZE: MaskingAlgorithmId.VND_VALUE_BANDING,
            MaskingAction.REDACT: MaskingAlgorithmId.FREE_TEXT_IDENTIFIER_REDACTION,
            MaskingAction.VAULT_REFERENCE: MaskingAlgorithmId.VAULT_REFERENCE_ONLY,
        }[self.action]
        if self.algorithm_id is not expected:
            raise ValueError(
                f"{self.action.value} requires algorithm {expected.value}"
            )
        if self.action is MaskingAction.TOKENIZE and self.key_version is None:
            raise ValueError("TOKENIZE requires an explicit key_version")
        if self.action is not MaskingAction.TOKENIZE and self.key_version is not None:
            raise ValueError("key_version is only valid for TOKENIZE")
        return self


class MaskingPolicyDocument(BaseModel):
    """Complete server-owned policy without any cryptographic secret material."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_id: StrictStr = Field(min_length=1)
    policy_version: StrictStr = Field(min_length=1)
    fail_closed: Literal[True] = True
    allowed_recipients: tuple[StrictStr, ...] = Field(min_length=1)
    classification_rules: tuple[DataClassificationRule, ...] = Field(min_length=1)
    masking_rules: tuple[MaskingRule, ...] = Field(min_length=1)
    vnd_generalization: VndGeneralizationConfig

    @field_validator("allowed_recipients")
    @classmethod
    def require_explicit_unique_recipients(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Forbid a global wildcard at the external trust boundary."""
        if "*" in value:
            raise ValueError("global allowed_recipients must not contain a wildcard")
        if len(set(value)) != len(value):
            raise ValueError("global allowed_recipients values must be unique")
        return value

    @model_validator(mode="after")
    def validate_rule_coverage(self) -> MaskingPolicyDocument:
        """Require exactly one masking rule for every classified field."""
        classification_fields = tuple(
            item.field_name for item in self.classification_rules
        )
        masking_fields = tuple(item.field_name for item in self.masking_rules)
        for name, values in (
            ("classification", classification_fields),
            ("masking", masking_fields),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"{name} field rules must be unique")
        if set(classification_fields) != set(masking_fields):
            raise ValueError(
                "classification and masking rules must cover the same exact fields"
            )
        classifications = {
            item.field_name: item.classification for item in self.classification_rules
        }
        actions = {item.field_name: item.action for item in self.masking_rules}
        unknown_recipients = {
            recipient
            for rule in self.masking_rules
            for recipient in rule.allowed_recipients
            if recipient not in self.allowed_recipients
        }
        if unknown_recipients:
            raise ValueError(
                "masking rules contain recipients outside the global allowlist"
            )
        for field_name, classification in classifications.items():
            if classification is DataClassification.RESTRICTED_SECRET and actions[
                field_name
            ] not in {MaskingAction.OMIT, MaskingAction.VAULT_REFERENCE}:
                raise ValueError(
                    f"restricted-secret field {field_name} must be omitted or use a vault reference"
                )
            if classification is DataClassification.RESTRICTED and actions[
                field_name
            ] is MaskingAction.ALLOW_EXACT:
                raise ValueError(
                    f"restricted field {field_name} cannot be allowed as an exact value"
                )
        return self


def masking_policy_document_sha256(document: MaskingPolicyDocument) -> str:
    """Return the canonical SHA-256 commitment for one typed policy version."""
    canonical = json.dumps(
        document.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class MaskingManifestItem(BaseModel):
    """Safe audit record for one input field; raw input is deliberately absent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    field_name: StrictStr = Field(min_length=1)
    classification_decision_id: StrictStr = Field(min_length=1)
    classification: DataClassification
    purpose: StrictStr = Field(min_length=1)
    recipient: StrictStr = Field(min_length=1)
    action: MaskingAction
    reason_code: MaskingReasonCode
    algorithm_id: MaskingAlgorithmId
    algorithm_version: StrictStr = Field(min_length=1)
    key_version: StrictStr | None = None
    included_in_payload: StrictBool
    raw_value_persisted: Literal[False] = False
    output_reference: StrictStr | None = None
    output_digest: StrictStr = Field(min_length=64, max_length=64)
    policy_reference: StrictStr = Field(min_length=1)
    policy_evidence_ids: tuple[StrictStr, ...] = ()
    source_evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)

    @field_validator("policy_evidence_ids", "source_evidence_ids")
    @classmethod
    def require_unique_evidence_ids(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Keep policy provenance separate from exact value lineage."""
        if len(set(value)) != len(value):
            raise ValueError("masking evidence IDs must be unique")
        return value


class MaskingManifest(BaseModel):
    """Artifact-safe masking proof for one minimized outbound payload."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    manifest_id: StrictStr = Field(min_length=1)
    policy_id: StrictStr = Field(min_length=1)
    policy_version: StrictStr = Field(min_length=1)
    policy_document_sha256: StrictStr = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    purpose: StrictStr = Field(min_length=1)
    recipient: StrictStr = Field(min_length=1)
    fail_closed: Literal[True] = True
    items: tuple[MaskingManifestItem, ...] = Field(min_length=1)

    @field_validator("items")
    @classmethod
    def require_unique_fields(
        cls,
        value: tuple[MaskingManifestItem, ...],
    ) -> tuple[MaskingManifestItem, ...]:
        """One field must have exactly one auditable decision."""
        fields = tuple(item.field_name for item in value)
        if len(set(fields)) != len(fields):
            raise ValueError("masking manifest fields must be unique")
        return value


class MaskedPayload(BaseModel):
    """Minimized values plus decisions and a safe manifest for persistence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    values: dict[StrictStr, MaskableScalar]
    classification_decisions: tuple[ClassificationDecision, ...] = Field(min_length=1)
    manifest: MaskingManifest

    @model_validator(mode="after")
    def validate_manifest_alignment(self) -> MaskedPayload:
        """Require exact alignment between decisions, manifest, and output keys."""
        decision_fields = tuple(item.field_name for item in self.classification_decisions)
        manifest_fields = tuple(item.field_name for item in self.manifest.items)
        if decision_fields != manifest_fields:
            raise ValueError(
                "classification decisions must match masking manifest item order"
            )
        included_fields = {
            item.field_name
            for item in self.manifest.items
            if item.included_in_payload
        }
        if set(self.values) != included_fields:
            raise ValueError("masked values must match included manifest fields")
        return self


class RedactionFinding(BaseModel):
    """Count-only redaction evidence that never contains a matched raw value."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    category: StrictStr = Field(min_length=1)
    count: StrictInt = Field(gt=0)


class RedactionResult(BaseModel):
    """Sanitized text and aggregate redaction counts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: StrictStr
    findings: tuple[RedactionFinding, ...] = ()
    algorithm_id: Literal[
        MaskingAlgorithmId.FREE_TEXT_IDENTIFIER_REDACTION
    ] = MaskingAlgorithmId.FREE_TEXT_IDENTIFIER_REDACTION
    algorithm_version: StrictStr = Field(min_length=1)
