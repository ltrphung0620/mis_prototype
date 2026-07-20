"""Typed contracts for the single governed conditional-negotiation round."""

from enum import StrEnum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictStr,
    model_validator,
)

from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.decision_models import ExactDecisionArtifactRef
from opc_mis.domain.enums import ComponentStatus, WorkflowStatus
from opc_mis.domain.lineage import deterministic_id
from opc_mis.domain.validation_reports import ValidationReport


class NegotiationOutcomeStatus(StrEnum):
    """Stable serialized outcome values without adding routing ambiguity."""

    ALL_CONDITIONS_ACCEPTED = "ALL_CONDITIONS_ACCEPTED"
    ONE_OR_MORE_CONDITIONS_REJECTED = "ONE_OR_MORE_CONDITIONS_REJECTED"


class NegotiationConditionOutcomeInput(BaseModel):
    """Founder-recorded customer response for one exact Decision Card condition."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    condition_id: StrictStr = Field(min_length=1)
    customer_accepted: StrictBool
    founder_note: StrictStr | None = Field(default=None, min_length=1, max_length=500)


class NegotiationOutcomeInput(BaseModel):
    """One complete response set for the prototype's single negotiation round."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    workflow_run_id: StrictStr = Field(min_length=1)
    decision_card_artifact_id: StrictStr = Field(min_length=1)
    condition_outcomes: tuple[NegotiationConditionOutcomeInput, ...] = Field(
        min_length=1
    )
    founder_summary: StrictStr | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode="after")
    def require_unique_conditions(self) -> "NegotiationOutcomeInput":
        condition_ids = tuple(item.condition_id for item in self.condition_outcomes)
        if len(set(condition_ids)) != len(condition_ids):
            raise ValueError("condition_outcomes must contain each condition exactly once")
        return self


class NegotiationTermsSentInput(BaseModel):
    """Manual confirmation that terms were sent outside this prototype."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    workflow_run_id: StrictStr = Field(min_length=1)
    decision_card_artifact_id: StrictStr = Field(min_length=1)


class NegotiationConditionOutcome(BaseModel):
    """Canonical condition snapshot paired with the recorded customer response."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    condition_id: StrictStr = Field(min_length=1)
    condition_code: StrictStr = Field(min_length=1)
    condition_title: StrictStr = Field(min_length=1)
    customer_accepted: StrictBool
    founder_note: StrictStr | None = None
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)


class NegotiationOutcome(BaseModel):
    """Validated approval subject for the final negotiation confirmation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    negotiation_outcome_id: StrictStr = Field(min_length=1)
    evaluation_case_id: StrictStr = Field(min_length=1)
    dataset_id: StrictStr = Field(min_length=1)
    contract_id: StrictStr = Field(min_length=1)
    decision_card_artifact: ExactDecisionArtifactRef
    condition_outcomes: tuple[NegotiationConditionOutcome, ...] = Field(min_length=1)
    all_conditions_accepted: StrictBool
    outcome_status: NegotiationOutcomeStatus
    founder_summary: StrictStr | None = None
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)
    confirmation_requested: StrictBool = False

    @model_validator(mode="after")
    def validate_outcome(self) -> "NegotiationOutcome":
        condition_ids = tuple(item.condition_id for item in self.condition_outcomes)
        if len(set(condition_ids)) != len(condition_ids):
            raise ValueError("Negotiation outcome condition IDs must be unique")
        derived_all_accepted = all(
            item.customer_accepted for item in self.condition_outcomes
        )
        expected_status = (
            NegotiationOutcomeStatus.ALL_CONDITIONS_ACCEPTED
            if derived_all_accepted
            else NegotiationOutcomeStatus.ONE_OR_MORE_CONDITIONS_REJECTED
        )
        if self.all_conditions_accepted is not derived_all_accepted:
            raise ValueError("all_conditions_accepted must be derived from every condition")
        if self.outcome_status != expected_status:
            raise ValueError("outcome_status does not match condition responses")
        expected_id = deterministic_id(
            "NGO",
            self.evaluation_case_id,
            self.dataset_id,
            self.contract_id,
            self.decision_card_artifact.model_dump(mode="json"),
            tuple(item.model_dump(mode="json") for item in self.condition_outcomes),
            self.founder_summary,
        )
        if self.negotiation_outcome_id != expected_id:
            raise ValueError("negotiation_outcome_id is unstable")
        return self


class NegotiationOutcomeExecutionResult(BaseModel):
    """Application result returned after persisting negotiation input."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: StrictStr = Field(min_length=1)
    outcome: NegotiationOutcome | None = None
    generated_artifacts: tuple[ArtifactEnvelope, ...] = ()
    validation_reports: tuple[ValidationReport, ...] = ()
    validation_errors: tuple[StrictStr, ...] = ()
    runtime_events: tuple[dict[str, Any], ...] = ()


def negotiation_outcome_action_payload(
    outcome: NegotiationOutcome,
) -> dict[str, object]:
    """Return the exact immutable scope Founder confirms."""

    return {
        "negotiation_outcome_confirmation_requested": True,
        "negotiation_outcome_id": outcome.negotiation_outcome_id,
        "decision_card_artifact_id": outcome.decision_card_artifact.artifact_id,
        "all_conditions_accepted": outcome.all_conditions_accepted,
        "condition_outcomes": [
            {
                "condition_id": item.condition_id,
                "customer_accepted": item.customer_accepted,
            }
            for item in outcome.condition_outcomes
        ],
    }
