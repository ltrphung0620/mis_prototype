"""Domain contracts for deterministic Decision review after Banking precheck."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator

from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.components import ComponentResult
from opc_mis.domain.enums import (
    BankingPrecheckOutcome,
    BankingPrecheckResultAuthority,
    ComponentStatus,
    DecisionPostPrecheckOptionDisposition,
    DecisionPostPrecheckOutcome,
    MissingRequestStatus,
    MissingSeverity,
    SourceType,
    WorkflowStatus,
)
from opc_mis.domain.lineage import deterministic_id
from opc_mis.domain.missing_data import MissingDataRequest
from opc_mis.domain.validation_reports import ValidationReport

_DISPOSITION_BY_OUTCOME = {
    BankingPrecheckOutcome.CONDITIONAL_PRECHECK: (
        DecisionPostPrecheckOptionDisposition.CONDITIONAL_REVIEW
    ),
    BankingPrecheckOutcome.MISSING_EVIDENCE: (
        DecisionPostPrecheckOptionDisposition.FOLLOW_UP_EVIDENCE_REQUIRED
    ),
    BankingPrecheckOutcome.NOT_ELIGIBLE: (
        DecisionPostPrecheckOptionDisposition.NOT_ELIGIBLE
    ),
    BankingPrecheckOutcome.NO_RECOMMENDATION: (
        DecisionPostPrecheckOptionDisposition.NO_PROVIDER_RECOMMENDATION
    ),
    BankingPrecheckOutcome.SERVICE_UNAVAILABLE: (
        DecisionPostPrecheckOptionDisposition.PRECHECK_UNAVAILABLE
    ),
}

if set(_DISPOSITION_BY_OUTCOME) != set(BankingPrecheckOutcome):  # pragma: no cover
    raise RuntimeError("Decision must explicitly map every Banking precheck outcome.")


def decision_post_precheck_disposition(
    outcome: BankingPrecheckOutcome,
) -> DecisionPostPrecheckOptionDisposition:
    """Return the exhaustive deterministic disposition for one typed result."""
    return _DISPOSITION_BY_OUTCOME[outcome]


def decision_post_precheck_outcome(
    outcomes: tuple[BankingPrecheckOutcome, ...],
) -> DecisionPostPrecheckOutcome:
    """Aggregate a complete ordered result batch without selecting an option."""
    if not outcomes:
        raise ValueError("Post-precheck review requires at least one result.")
    if BankingPrecheckOutcome.MISSING_EVIDENCE in outcomes:
        return DecisionPostPrecheckOutcome.FOLLOW_UP_EVIDENCE_REQUIRED
    if BankingPrecheckOutcome.CONDITIONAL_PRECHECK in outcomes:
        return DecisionPostPrecheckOutcome.CONDITIONAL_OPTIONS_AVAILABLE
    if all(item is BankingPrecheckOutcome.NOT_ELIGIBLE for item in outcomes):
        return DecisionPostPrecheckOutcome.ALL_OPTIONS_NOT_ELIGIBLE
    if all(item is BankingPrecheckOutcome.NO_RECOMMENDATION for item in outcomes):
        return DecisionPostPrecheckOutcome.NO_PROVIDER_RECOMMENDATION
    if all(item is BankingPrecheckOutcome.SERVICE_UNAVAILABLE for item in outcomes):
        return DecisionPostPrecheckOutcome.PRECHECK_SERVICE_UNAVAILABLE
    return DecisionPostPrecheckOutcome.MIXED_NON_ACTIONABLE_RESULTS


def decision_post_precheck_item_id(
    *,
    result_set_id: str,
    normalized_result_id: str,
    proposal_item_id: str,
    option_id: str,
    bank_product_id: str,
    source_outcome: BankingPrecheckOutcome,
    disposition: DecisionPostPrecheckOptionDisposition,
    required_follow_up_fields: tuple[str, ...],
) -> str:
    """Build a stable review-item identity from exact provider-result lineage."""
    return deterministic_id(
        "DPPRI",
        result_set_id,
        normalized_result_id,
        proposal_item_id,
        option_id,
        bank_product_id,
        source_outcome,
        disposition,
        required_follow_up_fields,
    )


def decision_post_precheck_review_id(
    *,
    result_set_artifact_id: str,
    result_set_id: str,
    proposal_artifact_id: str,
    item_ids: tuple[str, ...],
    outcome: DecisionPostPrecheckOutcome,
    missing_request_ids: tuple[str, ...],
) -> str:
    """Build stable aggregate identity without runtime-only identifiers."""
    return deterministic_id(
        "DPPR",
        result_set_artifact_id,
        result_set_id,
        proposal_artifact_id,
        item_ids,
        outcome,
        missing_request_ids,
    )


def decision_post_precheck_evidence_id(
    *,
    dataset_id: str,
    review_item_id: str,
    display: dict[str, Any],
    source_evidence_ids: tuple[str, ...],
) -> str:
    """Build exact derived-evidence identity for one classified result."""
    return deterministic_id(
        "EVD",
        dataset_id,
        SourceType.DERIVED,
        "DECISION_POST_PRECHECK_REVIEW",
        review_item_id,
        "precheck_disposition",
        display,
        source_evidence_ids,
    )


class DecisionPostPrecheckOptionReview(BaseModel):
    """One preserved option/product pair and its non-binding disposition."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    review_item_id: StrictStr = Field(min_length=1)
    normalized_result_id: StrictStr = Field(min_length=1)
    proposal_item_id: StrictStr = Field(min_length=1)
    option_id: StrictStr = Field(min_length=1)
    bank_product_id: StrictStr = Field(min_length=1)
    api_id: StrictStr = Field(min_length=1)
    api_provider: StrictStr = Field(min_length=1)
    source_outcome: BankingPrecheckOutcome
    disposition: DecisionPostPrecheckOptionDisposition
    reason_codes: tuple[StrictStr, ...] = ()
    required_follow_up_fields: tuple[StrictStr, ...] = ()
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)
    non_binding: Literal[True] = True

    @model_validator(mode="after")
    def validate_exact_disposition(self) -> "DecisionPostPrecheckOptionReview":
        """Keep classification exhaustive, stable, and evidence-indexed."""
        if self.disposition is not decision_post_precheck_disposition(
            self.source_outcome
        ):
            raise ValueError("precheck disposition does not match source outcome")
        for name, values in (
            ("reason_codes", self.reason_codes),
            ("required_follow_up_fields", self.required_follow_up_fields),
            ("evidence_ids", self.evidence_ids),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"{name} must be unique")
            if any(not value.strip() for value in values):
                raise ValueError(f"{name} values must not be blank")
        return self


class DecisionPostPrecheckReview(BaseModel):
    """Typed result routing without selection, approval, ranking, or documents."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    review_id: StrictStr = Field(min_length=1)
    evaluation_case_id: StrictStr = Field(min_length=1)
    dataset_id: StrictStr = Field(min_length=1)
    contract_id: StrictStr = Field(min_length=1)
    result_set_artifact_id: StrictStr = Field(min_length=1)
    result_set_id: StrictStr = Field(min_length=1)
    proposal_artifact_id: StrictStr = Field(min_length=1)
    proposal_id: StrictStr = Field(min_length=1)
    source_authority: BankingPrecheckResultAuthority
    outcome: DecisionPostPrecheckOutcome
    option_reviews: tuple[DecisionPostPrecheckOptionReview, ...] = Field(
        min_length=1
    )
    candidate_option_ids: tuple[StrictStr, ...] = Field(min_length=1)
    candidate_bank_product_ids: tuple[StrictStr, ...] = Field(min_length=1)
    conditional_option_ids: tuple[StrictStr, ...] = ()
    evidence_required_option_ids: tuple[StrictStr, ...] = ()
    not_eligible_option_ids: tuple[StrictStr, ...] = ()
    no_recommendation_option_ids: tuple[StrictStr, ...] = ()
    unavailable_option_ids: tuple[StrictStr, ...] = ()
    required_input_fields: tuple[StrictStr, ...] = ()
    missing_data_requests: tuple[MissingDataRequest, ...] = ()
    source_artifact_ids: tuple[StrictStr, StrictStr]
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)
    non_binding: Literal[True] = True
    bank_approval_obtained: Literal[False] = False
    selection_performed: Literal[False] = False
    ranking_performed: Literal[False] = False
    documents_prepared: Literal[False] = False

    @model_validator(mode="after")
    def validate_complete_partition(self) -> "DecisionPostPrecheckReview":
        """Require exact ordered classification and blocking-request semantics."""
        option_ids = tuple(item.option_id for item in self.option_reviews)
        if option_ids != self.candidate_option_ids:
            raise ValueError("candidate option order must match option reviews")
        if len(set(option_ids)) != len(option_ids):
            raise ValueError("candidate option IDs must be unique")
        if tuple(item.bank_product_id for item in self.option_reviews) != (
            self.candidate_bank_product_ids
        ):
            raise ValueError("candidate product order must match option reviews")
        for name, values in (
            ("conditional_option_ids", self.conditional_option_ids),
            ("evidence_required_option_ids", self.evidence_required_option_ids),
            ("not_eligible_option_ids", self.not_eligible_option_ids),
            ("no_recommendation_option_ids", self.no_recommendation_option_ids),
            ("unavailable_option_ids", self.unavailable_option_ids),
            ("required_input_fields", self.required_input_fields),
            ("evidence_ids", self.evidence_ids),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"{name} must be unique")
        expected_indexes = {
            DecisionPostPrecheckOptionDisposition.CONDITIONAL_REVIEW: (
                self.conditional_option_ids
            ),
            DecisionPostPrecheckOptionDisposition.FOLLOW_UP_EVIDENCE_REQUIRED: (
                self.evidence_required_option_ids
            ),
            DecisionPostPrecheckOptionDisposition.NOT_ELIGIBLE: (
                self.not_eligible_option_ids
            ),
            DecisionPostPrecheckOptionDisposition.NO_PROVIDER_RECOMMENDATION: (
                self.no_recommendation_option_ids
            ),
            DecisionPostPrecheckOptionDisposition.PRECHECK_UNAVAILABLE: (
                self.unavailable_option_ids
            ),
        }
        for disposition, actual in expected_indexes.items():
            expected = tuple(
                item.option_id
                for item in self.option_reviews
                if item.disposition is disposition
            )
            if actual != expected:
                raise ValueError(
                    f"{disposition.value} option index does not match reviews"
                )
        expected_outcome = decision_post_precheck_outcome(
            tuple(item.source_outcome for item in self.option_reviews)
        )
        if self.outcome is not expected_outcome:
            raise ValueError("aggregate outcome does not match option reviews")
        if len(set(self.source_artifact_ids)) != 2:
            raise ValueError("source_artifact_ids must contain two unique artifacts")
        request_ids = tuple(item.request_id for item in self.missing_data_requests)
        if len(set(request_ids)) != len(request_ids):
            raise ValueError("missing-data request IDs must be unique")
        expected_pairs = {
            (item.normalized_result_id, field)
            for item in self.option_reviews
            if item.source_outcome is BankingPrecheckOutcome.MISSING_EVIDENCE
            for field in item.required_follow_up_fields
        }
        missing_without_fields = tuple(
            item.normalized_result_id
            for item in self.option_reviews
            if item.source_outcome is BankingPrecheckOutcome.MISSING_EVIDENCE
            and not item.required_follow_up_fields
        )
        if missing_without_fields:
            raise ValueError(
                "MISSING_EVIDENCE results require explicit follow-up fields"
            )
        actual_pairs = {
            (item.target_record, item.field) for item in self.missing_data_requests
        }
        if actual_pairs != expected_pairs:
            raise ValueError(
                "missing-data requests must match exact result/follow-up pairs"
            )
        if any(
            item.raised_by != "DECISION_POST_PRECHECK_REVIEW"
            or item.evaluation_case_id != self.evaluation_case_id
            or item.severity is not MissingSeverity.BLOCKING
            or item.status is not MissingRequestStatus.OPEN
            for item in self.missing_data_requests
        ):
            raise ValueError("post-precheck missing-data request contract is invalid")
        expected_fields = tuple(
            dict.fromkeys(item.field for item in self.missing_data_requests)
        )
        if self.required_input_fields != expected_fields:
            raise ValueError("required inputs do not match missing-data requests")
        if self.source_authority is not (
            BankingPrecheckResultAuthority.SIMULATED_NON_BINDING
        ):
            raise ValueError("current post-precheck review must remain non-binding")
        return self


class DecisionPostPrecheckComponentResult(ComponentResult):
    """Side-effect-free Decision output for a precheck result batch."""

    review: DecisionPostPrecheckReview | None = None


class DecisionPostPrecheckExecutionResult(BaseModel):
    """Validated post-precheck review returned through application boundaries."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: str
    review: DecisionPostPrecheckReview | None = None
    generated_artifacts: tuple[ArtifactEnvelope, ...] = ()
    validation_reports: tuple[ValidationReport, ...] = ()
    validation_errors: tuple[str, ...] = ()
    missing_data_requests: tuple[MissingDataRequest, ...] = ()
    warnings: tuple[str, ...] = ()
    runtime_events: tuple[dict[str, Any], ...] = ()
