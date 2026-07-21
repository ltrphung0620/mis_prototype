"""Domain contracts for a governed Banking precheck submission proposal."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.banking_models import BankingCatalogNumber
from opc_mis.domain.components import ComponentResult
from opc_mis.domain.enums import (
    BankingNeedType,
    BankingPrecheckFieldSource,
    ComponentStatus,
    CurrencyCode,
    ProtectedAction,
    WorkflowStatus,
)
from opc_mis.domain.missing_data import MissingDataRequest
from opc_mis.domain.validation_reports import ValidationReport


class BankingPrecheckFieldBindingReference(BaseModel):
    """Reference one resolved API field without constructing an API request body."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    required_field: StrictStr = Field(min_length=1)
    source: BankingPrecheckFieldSource
    source_reference: StrictStr = Field(min_length=1)
    source_artifact_id: StrictStr | None = None
    source_record_ids: tuple[StrictStr, ...] = Field(min_length=1)
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_references(self) -> "BankingPrecheckFieldBindingReference":
        """Reject ambiguous reference or evidence indexes."""
        if len(set(self.source_record_ids)) != len(self.source_record_ids):
            raise ValueError("source_record_ids must be unique")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("binding evidence_ids must be unique")
        return self


class BankingPrecheckCatalogTerms(BaseModel):
    """Exact catalog terms retained for Governance and later external execution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    annual_rate_or_fee: BankingCatalogNumber
    processing_fee_rate: BankingCatalogNumber
    collateral_ratio: BankingCatalogNumber
    minimum_amount: BankingCatalogNumber
    minimum_amount_currency: CurrencyCode
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_evidence(self) -> "BankingPrecheckCatalogTerms":
        """Keep catalog-term evidence unambiguous."""
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("catalog-term evidence_ids must be unique")
        return self


class BankingPrecheckHandlingPolicyReference(BaseModel):
    """Exact TeamPack handling-rule facts carried for Governance evaluation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id: StrictStr = Field(min_length=1)
    applies_to: StrictStr = Field(min_length=1)
    requires_human_approval_text: StrictStr = Field(min_length=1)
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_evidence_index(self) -> "BankingPrecheckHandlingPolicyReference":
        """Reject ambiguous source-policy evidence references."""
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("handling-policy evidence_ids must be unique")
        return self


class BankingPrecheckGovernanceSourceFacts(BaseModel):
    """Source policy text only; Banking does not interpret an approval outcome."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    api_extension_rule: StrictStr = Field(min_length=1)
    api_extension_rule_evidence_id: StrictStr = Field(min_length=1)
    handling_rules: tuple[BankingPrecheckHandlingPolicyReference, ...] = ()

    @model_validator(mode="after")
    def validate_rules(self) -> "BankingPrecheckGovernanceSourceFacts":
        """Require each explicitly mapped handling rule at most once."""
        rule_ids = tuple(item.rule_id for item in self.handling_rules)
        if len(set(rule_ids)) != len(rule_ids):
            raise ValueError("governance handling-rule IDs must be unique")
        return self


class BankingPrecheckSubmissionCandidate(BaseModel):
    """One READY option included in the batch without selecting or ranking it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    proposal_item_id: StrictStr = Field(min_length=1)
    option_id: StrictStr = Field(min_length=1)
    bank_product_id: StrictStr = Field(min_length=1)
    need_type: BankingNeedType
    provider: StrictStr = Field(min_length=1)
    product_name: StrictStr = Field(min_length=1)
    api_id: StrictStr = Field(min_length=1)
    api_provider: StrictStr = Field(min_length=1)
    api_method: StrictStr = Field(min_length=1)
    api_endpoint: StrictStr = Field(min_length=1)
    governance_source_facts: BankingPrecheckGovernanceSourceFacts
    catalog_terms: BankingPrecheckCatalogTerms
    field_bindings: tuple[BankingPrecheckFieldBindingReference, ...] = Field(
        min_length=1
    )
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_candidate_indexes(self) -> "BankingPrecheckSubmissionCandidate":
        """Require one exact binding per API field and unique evidence."""
        fields = tuple(item.required_field for item in self.field_bindings)
        if len(set(fields)) != len(fields):
            raise ValueError("candidate field bindings must be unique")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("candidate evidence_ids must be unique")
        return self


class BankingPrecheckSubmissionProposal(BaseModel):
    """A batched proposal awaiting Governance before any external submission."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    proposal_id: StrictStr = Field(min_length=1)
    evaluation_case_id: StrictStr = Field(min_length=1)
    dataset_id: StrictStr = Field(min_length=1)
    contract_id: StrictStr = Field(min_length=1)
    banking_request_id: StrictStr = Field(min_length=1)
    matrix_id: StrictStr = Field(min_length=1)
    readiness_id: StrictStr = Field(min_length=1)
    review_id: StrictStr = Field(min_length=1)
    mapping_policy_id: StrictStr = Field(min_length=1)
    mapping_version: StrictStr = Field(min_length=1)
    mapping_hash: StrictStr = Field(min_length=1)
    requested_amount: StrictInt = Field(gt=0)
    requested_amount_currency: CurrencyCode
    proposal_mode: Literal["BATCH_ALL_READY_OPTIONS"] = "BATCH_ALL_READY_OPTIONS"
    proposed_action: ProtectedAction = ProtectedAction.SUBMIT_BANKING_PRECHECK
    candidate_option_ids: tuple[StrictStr, ...] = Field(min_length=1)
    non_ready_option_ids: tuple[StrictStr, ...] = ()
    candidates: tuple[BankingPrecheckSubmissionCandidate, ...] = Field(min_length=1)
    source_artifact_ids: tuple[StrictStr, ...] = Field(min_length=3)
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)
    precheck_executed: Literal[False] = False
    submission_executed: Literal[False] = False

    @model_validator(mode="after")
    def validate_batch_contract(self) -> "BankingPrecheckSubmissionProposal":
        """Guarantee a complete all-ready batch rather than an implicit selection."""
        candidate_ids = tuple(item.option_id for item in self.candidates)
        if candidate_ids != self.candidate_option_ids:
            raise ValueError(
                "candidate_option_ids must exactly preserve the candidate batch order"
            )
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("candidate option IDs must be unique")
        if len(set(self.non_ready_option_ids)) != len(self.non_ready_option_ids):
            raise ValueError("non_ready_option_ids must be unique")
        if set(candidate_ids) & set(self.non_ready_option_ids):
            raise ValueError("ready and non-ready option indexes must be disjoint")
        proposal_item_ids = tuple(item.proposal_item_id for item in self.candidates)
        if len(set(proposal_item_ids)) != len(proposal_item_ids):
            raise ValueError("proposal item IDs must be unique")
        if len(set(self.source_artifact_ids)) != len(self.source_artifact_ids):
            raise ValueError("source_artifact_ids must be unique")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("proposal evidence_ids must be unique")
        if self.proposed_action is not ProtectedAction.SUBMIT_BANKING_PRECHECK:
            raise ValueError("proposal action must be SUBMIT_BANKING_PRECHECK")
        return self


def banking_precheck_action_payload(
    proposal: BankingPrecheckSubmissionProposal,
) -> dict[str, object]:
    """Return the exact JSON-safe policy inputs for this protected proposal."""
    return {
        "precheck_submission_requested": True,
        "api_ids": list(dict.fromkeys(item.api_id for item in proposal.candidates)),
        "requested_amount": proposal.requested_amount,
        "requested_amount_currency": proposal.requested_amount_currency.value,
    }


class BankingPrecheckSubmissionProposalComponentResult(ComponentResult):
    """Side-effect-free proposal result; Governance owns any protected action."""

    proposal: BankingPrecheckSubmissionProposal | None = None


class BankingPrecheckSubmissionProposalExecutionResult(BaseModel):
    """Validated and persisted proposal result for a future workflow boundary."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: str
    proposal: BankingPrecheckSubmissionProposal | None = None
    generated_artifacts: tuple[ArtifactEnvelope, ...] = ()
    validation_reports: tuple[ValidationReport, ...] = ()
    validation_errors: tuple[str, ...] = ()
    missing_data_requests: tuple[MissingDataRequest, ...] = ()
    warnings: tuple[str, ...] = ()
    runtime_events: tuple[dict[str, Any], ...] = ()
