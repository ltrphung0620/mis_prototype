"""Contracts for resolving a post-precheck evidence-input handoff.

The supplement records only a staff-provided reference to evidence.  It never
changes the provider result, grants approval, or authorizes another protected
precheck call.  Workflow must create a fresh governed precheck after accepting
the handoff.
"""

from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    field_validator,
    model_validator,
)

from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.components import ComponentResult
from opc_mis.domain.enums import (
    BankingPrecheckOutcome,
    ComponentStatus,
    WorkflowStatus,
)
from opc_mis.domain.missing_data import MissingDataRequest
from opc_mis.domain.validation_reports import ValidationReport


def _normalized_text(value: str) -> str:
    normalized = " ".join(value.split())
    if not normalized:
        raise ValueError("value must not be blank")
    return normalized


class BankingPrecheckEvidenceSubmission(BaseModel):
    """Typed staff input for one exact post-precheck missing-data request."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    workflow_run_id: StrictStr = Field(min_length=1)
    missing_request_id: StrictStr = Field(min_length=1)
    evidence_reference_id: StrictStr = Field(min_length=1)
    provided_by: StrictStr = Field(min_length=1)
    evidence_note: StrictStr = Field(min_length=1)

    @field_validator(
        "workflow_run_id",
        "missing_request_id",
        "evidence_reference_id",
        "provided_by",
        "evidence_note",
    )
    @classmethod
    def normalize_text(cls, value: str) -> str:
        """Normalize semantic input before stable identity is calculated."""
        return _normalized_text(value)


class BankingPrecheckEvidenceCommand(BaseModel):
    """Workflow-enriched input containing the authoritative pending request."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    submission: BankingPrecheckEvidenceSubmission
    allowed_pending_request_id: StrictStr = Field(min_length=1)

    @field_validator("allowed_pending_request_id")
    @classmethod
    def normalize_allowed_request(cls, value: str) -> str:
        return _normalized_text(value)


class BankingPrecheckEvidenceSupplement(BaseModel):
    """Immutable reference handoff that requires a new governed precheck."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    supplement_id: StrictStr = Field(min_length=1)
    evaluation_case_id: StrictStr = Field(min_length=1)
    dataset_id: StrictStr = Field(min_length=1)
    contract_id: StrictStr = Field(min_length=1)
    source_review_artifact_id: StrictStr = Field(min_length=1)
    source_review_id: StrictStr = Field(min_length=1)
    source_result_set_artifact_id: StrictStr = Field(min_length=1)
    source_result_set_id: StrictStr = Field(min_length=1)
    normalized_result_id: StrictStr = Field(min_length=1)
    option_id: StrictStr = Field(min_length=1)
    bank_product_id: StrictStr = Field(min_length=1)
    required_field: StrictStr = Field(min_length=1)
    missing_request_id: StrictStr = Field(min_length=1)
    evidence_reference_id: StrictStr = Field(min_length=1)
    provided_by: StrictStr = Field(min_length=1)
    evidence_note: StrictStr = Field(min_length=1)
    source_outcome: BankingPrecheckOutcome = BankingPrecheckOutcome.MISSING_EVIDENCE
    previous_supplement_artifact_id: StrictStr | None = None
    source_artifact_ids: tuple[StrictStr, ...] = Field(min_length=1, max_length=2)
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)
    evidence_reference_only: Literal[True] = True
    input_handoff_resolved: Literal[True] = True
    fresh_governed_precheck_required: Literal[True] = True
    source_precheck_result_unchanged: Literal[True] = True
    bank_approval_obtained: Literal[False] = False
    protected_action_authorized: Literal[False] = False

    @model_validator(mode="after")
    def validate_boundary_and_lineage(self) -> "BankingPrecheckEvidenceSupplement":
        """Reject ambiguous provenance or any claim beyond evidence intake."""
        if self.source_outcome is not BankingPrecheckOutcome.MISSING_EVIDENCE:
            raise ValueError("evidence supplements require a MISSING_EVIDENCE result")
        for value in (
            self.supplement_id,
            self.evaluation_case_id,
            self.dataset_id,
            self.contract_id,
            self.source_review_artifact_id,
            self.source_review_id,
            self.source_result_set_artifact_id,
            self.source_result_set_id,
            self.normalized_result_id,
            self.option_id,
            self.bank_product_id,
            self.required_field,
            self.missing_request_id,
            self.evidence_reference_id,
            self.provided_by,
            self.evidence_note,
        ):
            if not value.strip():
                raise ValueError("supplement text values must not be blank")
        for value in (
            self.evidence_reference_id,
            self.provided_by,
            self.evidence_note,
        ):
            if value != _normalized_text(value):
                raise ValueError("staff-provided supplement values must be normalized")
        if len(set(self.source_artifact_ids)) != len(self.source_artifact_ids):
            raise ValueError("source_artifact_ids must be unique")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("evidence_ids must be unique")
        expected_sources = (
            self.source_review_artifact_id,
            *(
                (self.previous_supplement_artifact_id,)
                if self.previous_supplement_artifact_id
                else ()
            ),
        )
        if self.source_artifact_ids != expected_sources:
            raise ValueError(
                "source_artifact_ids must contain the review then optional prior supplement"
            )
        return self


class BankingPrecheckEvidenceComponentResult(ComponentResult):
    """Side-effect-free evidence-reference intake result."""

    supplement: BankingPrecheckEvidenceSupplement | None = None


class BankingPrecheckEvidenceExecutionResult(BaseModel):
    """Validated and persisted evidence-reference handoff."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: str
    supplement: BankingPrecheckEvidenceSupplement | None = None
    generated_artifacts: tuple[ArtifactEnvelope, ...] = ()
    validation_reports: tuple[ValidationReport, ...] = ()
    validation_errors: tuple[str, ...] = ()
    missing_data_requests: tuple[MissingDataRequest, ...] = ()
    warnings: tuple[str, ...] = ()
    runtime_events: tuple[dict[str, Any], ...] = ()
