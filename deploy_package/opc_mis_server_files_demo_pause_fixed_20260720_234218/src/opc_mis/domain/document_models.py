"""Domain contracts for Decision-managed document preparation.

The models in this module deliberately describe internal drafts and immutable
references only.  They do not authorize an external release and never carry
raw document bytes or client-controlled filesystem paths.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.components import ComponentResult
from opc_mis.domain.data_classification_models import ClassificationDecision
from opc_mis.domain.enums import (
    BankingPrecheckResultAuthority,
    ComponentStatus,
    CurrencyCode,
    MissingRequestStatus,
    MissingSeverity,
    WorkflowStatus,
)
from opc_mis.domain.lineage import deterministic_id
from opc_mis.domain.masking_models import MaskableScalar, MaskingManifest
from opc_mis.domain.missing_data import MissingDataRequest
from opc_mis.domain.validation_reports import ValidationReport

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_REFERENCE_PATTERN = re.compile(
    r"^DOCREF-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    flags=re.IGNORECASE,
)


class DocumentRequirementCode(StrEnum):
    """Provider document requirements implemented by the prototype."""

    SIGNED_CONTRACT = "SIGNED_CONTRACT"
    COMPANY_PROFILE = "COMPANY_PROFILE"
    PERFORMANCE_BOND_REQUEST_FORM = "PERFORMANCE_BOND_REQUEST_FORM"
    CASHFLOW_BUFFER_EVIDENCE = "CASHFLOW_BUFFER_EVIDENCE"


class DocumentRequirementStatus(StrEnum):
    """Deterministic preparation state for one provider requirement."""

    AVAILABLE = "AVAILABLE"
    DRAFTED = "DRAFTED"
    MISSING = "MISSING"
    AVAILABLE_WITH_LIMITATIONS = "AVAILABLE_WITH_LIMITATIONS"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class DocumentEvidenceReasonCode(StrEnum):
    """Controlled audit reason; arbitrary evidence free text is not accepted."""

    REQUESTED_DOCUMENT_REFERENCE_SUPPLIED = (
        "REQUESTED_DOCUMENT_REFERENCE_SUPPLIED"
    )


class DocumentPackageReadiness(StrEnum):
    """Whether an internal draft can proceed to the next internal workflow phase."""

    WAITING_FOR_INPUT = "WAITING_FOR_INPUT"
    READY_FOR_INTERNAL_DECISION = "READY_FOR_INTERNAL_DECISION"
    # Legacy persisted value. New packages must use READY_FOR_INTERNAL_DECISION.
    READY_FOR_RELEASE_REVIEW = "READY_FOR_RELEASE_REVIEW"


def document_preparation_request_id(
    *,
    result_set_artifact_id: str,
    review_artifact_id: str,
    normalized_result_id: str,
    review_item_id: str,
    option_id: str,
    required_document_codes: tuple[DocumentRequirementCode, ...],
    approval_condition_codes: tuple[str, ...],
) -> str:
    """Build stable handoff identity from exact provider-result lineage."""
    return deterministic_id(
        "DPR",
        result_set_artifact_id,
        review_artifact_id,
        normalized_result_id,
        review_item_id,
        option_id,
        required_document_codes,
        approval_condition_codes,
    )


def document_checklist_id(
    *, request_artifact_id: str, request_id: str, item_ids: tuple[str, ...]
) -> str:
    """Build stable checklist identity without runtime identifiers."""
    return deterministic_id("DCL", request_artifact_id, request_id, item_ids)


def document_package_draft_id(
    *,
    request_artifact_id: str,
    request_id: str,
    checklist_id: str,
    supplement_artifact_ids: tuple[str, ...],
    classification_decision_ids: tuple[str, ...],
    masking_manifest_id: str,
) -> str:
    """Build stable package identity from business inputs and protection policy."""
    return deterministic_id(
        "DPD",
        request_artifact_id,
        request_id,
        checklist_id,
        supplement_artifact_ids,
        classification_decision_ids,
        masking_manifest_id,
    )


class DocumentPreparationRequest(BaseModel):
    """Decision handoff for every viable conditional Banking result."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: StrictStr = Field(min_length=1)
    evaluation_case_id: StrictStr = Field(min_length=1)
    dataset_id: StrictStr = Field(min_length=1)
    contract_id: StrictStr = Field(min_length=1)
    normalized_result_id: StrictStr = Field(min_length=1)
    review_item_id: StrictStr = Field(min_length=1)
    option_id: StrictStr = Field(min_length=1)
    bank_product_id: StrictStr = Field(min_length=1)
    api_id: StrictStr = Field(min_length=1)
    provider: StrictStr = Field(min_length=1)
    provider_reference: StrictStr = Field(min_length=1)
    requested_amount: StrictInt = Field(gt=0)
    supported_amount: StrictInt = Field(gt=0)
    currency: CurrencyCode = CurrencyCode.VND
    required_document_codes: tuple[DocumentRequirementCode, ...] = Field(
        min_length=1
    )
    approval_condition_codes: tuple[StrictStr, ...] = Field(min_length=1)
    provider_result_authority: BankingPrecheckResultAuthority
    source_artifact_ids: tuple[StrictStr, StrictStr]
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)
    non_binding: Literal[True] = True
    selection_performed: Literal[False] = False
    bank_approval_obtained: Literal[False] = False
    documents_prepared: Literal[False] = False
    external_release_performed: Literal[False] = False

    @model_validator(mode="after")
    def validate_request(self) -> DocumentPreparationRequest:
        """Keep a full-coverage non-binding handoff exact and non-selective."""
        if self.currency is not CurrencyCode.VND:
            raise ValueError("document preparation currently supports VND only")
        if self.supported_amount != self.requested_amount:
            raise ValueError(
                "partial coverage is outside the current document preparation phase"
            )
        for name, values in (
            ("required_document_codes", self.required_document_codes),
            ("approval_condition_codes", self.approval_condition_codes),
            ("source_artifact_ids", self.source_artifact_ids),
            ("evidence_ids", self.evidence_ids),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"{name} must be unique")
        expected_id = document_preparation_request_id(
            result_set_artifact_id=self.source_artifact_ids[1],
            review_artifact_id=self.source_artifact_ids[0],
            normalized_result_id=self.normalized_result_id,
            review_item_id=self.review_item_id,
            option_id=self.option_id,
            required_document_codes=self.required_document_codes,
            approval_condition_codes=self.approval_condition_codes,
        )
        if self.request_id != expected_id:
            raise ValueError("document preparation request_id is not deterministic")
        return self


class DocumentChecklistItem(BaseModel):
    """Traceable status of one provider-declared document requirement."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: StrictStr = Field(min_length=1)
    document_code: DocumentRequirementCode
    status: DocumentRequirementStatus
    reason: StrictStr = Field(min_length=1)
    limitation_codes: tuple[StrictStr, ...] = ()
    source_reference_ids: tuple[StrictStr, ...] = ()
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)
    missing_request_id: StrictStr | None = None

    @model_validator(mode="after")
    def validate_status(self) -> DocumentChecklistItem:
        """Bind MISSING status to exactly one external missing-data request."""
        if (self.status is DocumentRequirementStatus.MISSING) != (
            self.missing_request_id is not None
        ):
            raise ValueError("only MISSING checklist items carry missing_request_id")
        for name, values in (
            ("limitation_codes", self.limitation_codes),
            ("source_reference_ids", self.source_reference_ids),
            ("evidence_ids", self.evidence_ids),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"{name} must be unique")
        return self


class DocumentChecklist(BaseModel):
    """Complete ordered classification of provider document requirements."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    checklist_id: StrictStr = Field(min_length=1)
    evaluation_case_id: StrictStr = Field(min_length=1)
    dataset_id: StrictStr = Field(min_length=1)
    contract_id: StrictStr = Field(min_length=1)
    preparation_request_id: StrictStr = Field(min_length=1)
    approval_condition_codes: tuple[StrictStr, ...] = Field(min_length=1)
    items: tuple[DocumentChecklistItem, ...] = Field(min_length=1)
    missing_document_codes: tuple[DocumentRequirementCode, ...] = ()
    limitation_codes: tuple[StrictStr, ...] = ()
    source_artifact_ids: tuple[StrictStr, ...] = Field(min_length=1)
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_partition(self) -> DocumentChecklist:
        """Require one item per code and an exact missing-code index."""
        codes = tuple(item.document_code for item in self.items)
        if len(set(codes)) != len(codes):
            raise ValueError("checklist document codes must be unique")
        expected_missing = tuple(
            item.document_code
            for item in self.items
            if item.status is DocumentRequirementStatus.MISSING
        )
        if self.missing_document_codes != expected_missing:
            raise ValueError("missing_document_codes does not match checklist items")
        expected_limitations = tuple(
            dict.fromkeys(
                limitation
                for item in self.items
                for limitation in item.limitation_codes
            )
        )
        if self.limitation_codes != expected_limitations:
            raise ValueError("limitation_codes does not match checklist items")
        if len(set(self.approval_condition_codes)) != len(
            self.approval_condition_codes
        ):
            raise ValueError("approval_condition_codes must be unique")
        if len(set(self.source_artifact_ids)) != len(self.source_artifact_ids):
            raise ValueError("source_artifact_ids must be unique")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("evidence_ids must be unique")
        if len(self.source_artifact_ids) < 2:
            raise ValueError("checklist requires case and preparation request artifacts")
        expected_id = document_checklist_id(
            request_artifact_id=self.source_artifact_ids[1],
            request_id=self.preparation_request_id,
            item_ids=tuple(item.item_id for item in self.items),
        )
        if self.checklist_id != expected_id:
            raise ValueError("document checklist_id is not deterministic")
        return self


class DocumentPackageDraft(BaseModel):
    """Sanitized internal package; never itself authorizes external release."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    package_draft_id: StrictStr = Field(min_length=1)
    evaluation_case_id: StrictStr = Field(min_length=1)
    dataset_id: StrictStr = Field(min_length=1)
    contract_id: StrictStr = Field(min_length=1)
    preparation_request_id: StrictStr = Field(min_length=1)
    checklist_id: StrictStr = Field(min_length=1)
    approval_condition_codes: tuple[StrictStr, ...] = Field(min_length=1)
    limitation_codes: tuple[StrictStr, ...] = ()
    recipient: StrictStr = Field(min_length=1)
    purpose: StrictStr = Field(min_length=1)
    readiness: DocumentPackageReadiness
    sanitized_payload: dict[StrictStr, MaskableScalar]
    classification_decisions: tuple[ClassificationDecision, ...] = Field(
        min_length=1
    )
    masking_manifest: MaskingManifest
    classification_decision_ids: tuple[StrictStr, ...] = Field(min_length=1)
    masking_manifest_id: StrictStr = Field(min_length=1)
    masking_manifest_item_ids: tuple[StrictStr, ...] = Field(min_length=1)
    missing_data_requests: tuple[MissingDataRequest, ...] = ()
    source_artifact_ids: tuple[StrictStr, ...] = Field(min_length=1)
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)
    internal_draft: Literal[True] = True
    release_authorized: Literal[False] = False
    external_release_performed: Literal[False] = False

    @model_validator(mode="after")
    def validate_readiness(self) -> DocumentPackageDraft:
        """Make blocking gaps and package readiness impossible to contradict."""
        has_missing = bool(self.missing_data_requests)
        if has_missing != (self.readiness is DocumentPackageReadiness.WAITING_FOR_INPUT):
            raise ValueError("package readiness does not match missing data requests")
        if any(
            item.evaluation_case_id != self.evaluation_case_id
            or item.severity is not MissingSeverity.BLOCKING
            or item.status is not MissingRequestStatus.OPEN
            for item in self.missing_data_requests
        ):
            raise ValueError("document package contains an invalid missing-data request")
        if self.classification_decision_ids != tuple(
            item.decision_id for item in self.classification_decisions
        ):
            raise ValueError("classification decision references do not match manifest")
        if self.masking_manifest_id != self.masking_manifest.manifest_id:
            raise ValueError("masking manifest reference does not match manifest")
        if self.masking_manifest_item_ids != tuple(
            deterministic_id("MASKI", self.masking_manifest_id, item.field_name)
            for item in self.masking_manifest.items
        ):
            raise ValueError("masking manifest item references do not match manifest")
        for name, values in (
            ("approval_condition_codes", self.approval_condition_codes),
            ("limitation_codes", self.limitation_codes),
            ("classification_decision_ids", self.classification_decision_ids),
            ("masking_manifest_item_ids", self.masking_manifest_item_ids),
            ("source_artifact_ids", self.source_artifact_ids),
            ("evidence_ids", self.evidence_ids),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"{name} must be unique")
        if len(self.source_artifact_ids) < 2:
            raise ValueError("package requires case and preparation request artifacts")
        expected_id = document_package_draft_id(
            request_artifact_id=self.source_artifact_ids[1],
            request_id=self.preparation_request_id,
            checklist_id=self.checklist_id,
            supplement_artifact_ids=self.source_artifact_ids[2:],
            classification_decision_ids=self.classification_decision_ids,
            masking_manifest_id=self.masking_manifest_id,
        )
        if self.package_draft_id != expected_id:
            raise ValueError("document package_draft_id is not deterministic")
        return self


class DocumentReleaseManifestItem(BaseModel):
    """Reference-only dossier entry; it never carries bytes or a filesystem path."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    manifest_item_id: StrictStr = Field(min_length=1)
    checklist_item_id: StrictStr = Field(min_length=1)
    document_code: DocumentRequirementCode
    status: DocumentRequirementStatus
    limitation_codes: tuple[StrictStr, ...] = ()
    source_reference_ids: tuple[StrictStr, ...] = ()
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_reference_only_item(self) -> DocumentReleaseManifestItem:
        if self.status is DocumentRequirementStatus.MISSING:
            raise ValueError("release manifest cannot contain a missing document")
        for name, values in (
            ("limitation_codes", self.limitation_codes),
            ("source_reference_ids", self.source_reference_ids),
            ("evidence_ids", self.evidence_ids),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"{name} must be unique")
        expected_id = deterministic_id(
            "DRMI",
            self.checklist_item_id,
            self.document_code,
            self.status,
            self.limitation_codes,
            self.source_reference_ids,
            self.evidence_ids,
        )
        if self.manifest_item_id != expected_id:
            raise ValueError("document release manifest item identity is unstable")
        return self


class DocumentReleasePackage(BaseModel):
    """Masked package retained for a later internal Decision recommendation.

    Creating this artifact is not a request or authorization to release it to
    an external partner. A later Decision phase must explicitly reference the
    exact persisted package before Governance may evaluate an external action.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    release_package_id: StrictStr = Field(min_length=1)
    package_draft_id: StrictStr = Field(min_length=1)
    evaluation_case_id: StrictStr = Field(min_length=1)
    dataset_id: StrictStr = Field(min_length=1)
    contract_id: StrictStr = Field(min_length=1)
    preparation_request_id: StrictStr = Field(min_length=1)
    checklist_id: StrictStr = Field(min_length=1)
    approval_condition_codes: tuple[StrictStr, ...] = Field(min_length=1)
    limitation_codes: tuple[StrictStr, ...] = ()
    recipient: StrictStr = Field(min_length=1)
    purpose: StrictStr = Field(min_length=1)
    document_codes: tuple[DocumentRequirementCode, ...] = Field(min_length=1)
    document_manifest: tuple[DocumentReleaseManifestItem, ...] = Field(
        min_length=1
    )
    sanitized_payload: dict[StrictStr, MaskableScalar]
    classification_decisions: tuple[ClassificationDecision, ...] = Field(
        min_length=1
    )
    masking_manifest: MaskingManifest
    classification_decision_ids: tuple[StrictStr, ...] = Field(min_length=1)
    masking_manifest_id: StrictStr = Field(min_length=1)
    masking_manifest_item_ids: tuple[StrictStr, ...] = Field(min_length=1)
    source_artifact_ids: tuple[StrictStr, ...] = Field(min_length=1)
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)
    release_authorized: Literal[False] = False
    external_release_performed: Literal[False] = False

    @model_validator(mode="after")
    def validate_protection_references(self) -> DocumentReleasePackage:
        """Keep the release candidate bound to the embedded masking proof."""
        if self.document_codes != tuple(
            item.document_code for item in self.document_manifest
        ):
            raise ValueError("document_codes does not match release manifest")
        if len(set(self.document_codes)) != len(self.document_codes):
            raise ValueError("release manifest document codes must be unique")
        expected_limitations = tuple(
            dict.fromkeys(
                limitation
                for item in self.document_manifest
                for limitation in item.limitation_codes
            )
        )
        if self.limitation_codes != expected_limitations:
            raise ValueError("release limitation_codes does not match document manifest")
        if len(set(self.approval_condition_codes)) != len(
            self.approval_condition_codes
        ):
            raise ValueError("approval_condition_codes must be unique")
        if self.classification_decision_ids != tuple(
            item.decision_id for item in self.classification_decisions
        ):
            raise ValueError("classification decision references do not match manifest")
        if self.masking_manifest_id != self.masking_manifest.manifest_id:
            raise ValueError("masking manifest reference does not match manifest")
        if self.masking_manifest_item_ids != tuple(
            deterministic_id("MASKI", self.masking_manifest_id, item.field_name)
            for item in self.masking_manifest.items
        ):
            raise ValueError("masking manifest item references do not match manifest")
        if set(self.sanitized_payload) != {
            item.field_name
            for item in self.masking_manifest.items
            if item.included_in_payload
        }:
            raise ValueError("sanitized payload differs from the masking manifest")
        expected_id = deterministic_id(
            "DRP",
            self.package_draft_id,
            self.preparation_request_id,
            self.checklist_id,
            self.masking_manifest_id,
        )
        if self.release_package_id != expected_id:
            raise ValueError("document release_package_id is not deterministic")
        return self


class DocumentEvidenceSubmission(BaseModel):
    """Caller-declared reference metadata; raw bytes and paths are forbidden."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    workflow_run_id: StrictStr = Field(min_length=1)
    missing_request_id: StrictStr = Field(min_length=1)
    document_reference_id: StrictStr = Field(min_length=1, max_length=128)
    content_sha256: StrictStr = Field(min_length=64, max_length=64)
    document_type: DocumentRequirementCode
    provided_by: StrictStr = Field(min_length=1)
    evidence_note: DocumentEvidenceReasonCode

    @field_validator(
        "workflow_run_id",
        "missing_request_id",
        "document_reference_id",
        "provided_by",
    )
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized

    @field_validator("document_reference_id")
    @classmethod
    def reject_paths(cls, value: str) -> str:
        """Accept only an opaque identifier, never a path or URL."""
        if not _REFERENCE_PATTERN.fullmatch(value):
            raise ValueError(
                "document_reference_id must use the DOCREF-<UUIDv4> namespace"
            )
        return f"DOCREF-{value[7:].lower()}"

    @field_validator("content_sha256")
    @classmethod
    def normalize_hash(cls, value: str) -> str:
        normalized = value.lower()
        if not _SHA256_PATTERN.fullmatch(normalized):
            raise ValueError("content_sha256 must contain exactly 64 hexadecimal digits")
        return normalized


class DocumentEvidenceCommand(BaseModel):
    """Server-enriched command binding a submission to one pending request."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    submission: DocumentEvidenceSubmission
    allowed_pending_request_id: StrictStr = Field(min_length=1)


class DocumentEvidenceSupplement(BaseModel):
    """Immutable evidence reference used when rebuilding a document package."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    supplement_id: StrictStr = Field(min_length=1)
    evaluation_case_id: StrictStr = Field(min_length=1)
    dataset_id: StrictStr = Field(min_length=1)
    contract_id: StrictStr = Field(min_length=1)
    preparation_request_id: StrictStr = Field(min_length=1)
    missing_request_id: StrictStr = Field(min_length=1)
    document_reference_id: StrictStr = Field(min_length=1, max_length=128)
    content_sha256: StrictStr = Field(min_length=64, max_length=64)
    document_type: DocumentRequirementCode
    provided_by: StrictStr = Field(min_length=1)
    evidence_note: DocumentEvidenceReasonCode
    source_package_artifact_id: StrictStr = Field(min_length=1)
    source_artifact_ids: tuple[StrictStr, ...] = Field(min_length=1)
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)

    @field_validator("document_reference_id")
    @classmethod
    def validate_reference(cls, value: str) -> str:
        if not _REFERENCE_PATTERN.fullmatch(value):
            raise ValueError(
                "document_reference_id must use the DOCREF-<UUIDv4> namespace"
            )
        return f"DOCREF-{value[7:].lower()}"

    @field_validator("content_sha256")
    @classmethod
    def validate_content_hash(cls, value: str) -> str:
        normalized = value.lower()
        if not _SHA256_PATTERN.fullmatch(normalized):
            raise ValueError("content_sha256 must contain exactly 64 hexadecimal digits")
        return normalized

    @model_validator(mode="after")
    def validate_identity(self) -> DocumentEvidenceSupplement:
        if self.source_artifact_ids != (self.source_package_artifact_id,):
            raise ValueError("supplement must reference only its exact package draft")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("supplement evidence_ids must be unique")
        expected_id = deterministic_id(
            "DES",
            self.evaluation_case_id,
            self.preparation_request_id,
            self.source_package_artifact_id,
            self.missing_request_id,
            self.document_reference_id,
            self.content_sha256,
            self.document_type,
            self.provided_by,
            self.evidence_note,
        )
        if self.supplement_id != expected_id:
            raise ValueError("document supplement_id is not deterministic")
        return self


class DecisionDocumentHandoffComponentResult(ComponentResult):
    """Side-effect-free Decision result preserving every viable option."""

    preparation_requests: tuple[DocumentPreparationRequest, ...] = ()


class DocumentSkillComponentResult(ComponentResult):
    """Side-effect-free Document preparation output."""

    checklist: DocumentChecklist | None = None
    package_draft: DocumentPackageDraft | None = None
    release_package: DocumentReleasePackage | None = None


class DocumentEvidenceIntakeComponentResult(ComponentResult):
    """Side-effect-free typed intake output containing at most one supplement."""

    supplement: DocumentEvidenceSupplement | None = None


def document_release_action_payload(
    release_package: DocumentReleasePackage,
) -> dict[str, object]:
    """Build metadata for a future Decision-owned external-release proposal.

    Document preparation must never call this function to trigger Governance.
    It remains available for the later Decision phase, which must bind this
    payload to an exact recommendation before proposing the protected action.
    """
    return {
        "document_sent_to_partner": True,
        "release_package_id": release_package.release_package_id,
        "recipient": release_package.recipient,
        "purpose": release_package.purpose,
        "document_codes": tuple(item.value for item in release_package.document_codes),
        "approval_condition_codes": release_package.approval_condition_codes,
        "limitation_codes": release_package.limitation_codes,
        "document_manifest": tuple(
            {
                "manifest_item_id": item.manifest_item_id,
                "document_code": item.document_code.value,
                "status": item.status.value,
                "limitation_codes": item.limitation_codes,
                "source_reference_ids": item.source_reference_ids,
                "evidence_ids": item.evidence_ids,
            }
            for item in release_package.document_manifest
        ),
        "masking_manifest_id": release_package.masking_manifest_id,
    }


class DecisionDocumentHandoffExecutionResult(BaseModel):
    """Validated Decision handoff result returned through application boundaries."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: StrictStr = Field(min_length=1)
    preparation_requests: tuple[DocumentPreparationRequest, ...] = ()
    generated_artifacts: tuple[ArtifactEnvelope, ...] = ()
    validation_reports: tuple[ValidationReport, ...] = ()
    validation_errors: tuple[StrictStr, ...] = ()
    missing_data_requests: tuple[MissingDataRequest, ...] = ()
    warnings: tuple[StrictStr, ...] = ()
    runtime_events: tuple[dict[str, object], ...] = ()


class DocumentSkillExecutionResult(BaseModel):
    """Validated internal Document preparation result."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: StrictStr = Field(min_length=1)
    checklist: DocumentChecklist | None = None
    package_draft: DocumentPackageDraft | None = None
    release_package: DocumentReleasePackage | None = None
    generated_artifacts: tuple[ArtifactEnvelope, ...] = ()
    validation_reports: tuple[ValidationReport, ...] = ()
    validation_errors: tuple[StrictStr, ...] = ()
    missing_data_requests: tuple[MissingDataRequest, ...] = ()
    warnings: tuple[StrictStr, ...] = ()
    runtime_events: tuple[dict[str, object], ...] = ()


class DocumentEvidenceExecutionResult(BaseModel):
    """Validated reference-only evidence intake result."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: StrictStr = Field(min_length=1)
    supplement: DocumentEvidenceSupplement | None = None
    generated_artifacts: tuple[ArtifactEnvelope, ...] = ()
    validation_reports: tuple[ValidationReport, ...] = ()
    validation_errors: tuple[StrictStr, ...] = ()
    missing_data_requests: tuple[MissingDataRequest, ...] = ()
    warnings: tuple[StrictStr, ...] = ()
    runtime_events: tuple[dict[str, object], ...] = ()
