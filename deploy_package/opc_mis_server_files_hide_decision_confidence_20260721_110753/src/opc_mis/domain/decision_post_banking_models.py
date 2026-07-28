"""Domain contracts for deterministic Decision review after Banking discovery."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.components import ComponentResult
from opc_mis.domain.enums import (
    ComponentStatus,
    DecisionPostBankingOutcome,
    WorkflowStatus,
)
from opc_mis.domain.missing_data import MissingDataRequest
from opc_mis.domain.validation_reports import ValidationReport


class DecisionPostBankingReview(BaseModel):
    """Route classification without selecting or executing a Banking option."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    review_id: str
    evaluation_case_id: str
    dataset_id: str
    contract_id: str
    matrix_id: str
    banking_request_id: str
    readiness_id: str
    outcome: DecisionPostBankingOutcome
    candidate_option_ids: tuple[str, ...]
    precheck_ready_option_ids: tuple[str, ...] = ()
    pending_option_ids: tuple[str, ...] = ()
    required_input_fields: tuple[str, ...] = ()
    missing_data_requests: tuple[MissingDataRequest, ...] = ()
    source_artifact_ids: tuple[str, ...] = Field(min_length=2)
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    precheck_executed: Literal[False] = False

    @model_validator(mode="after")
    def validate_option_indexes(self) -> "DecisionPostBankingReview":
        """Prevent an implicit product selection in the review indexes."""
        candidates = set(self.candidate_option_ids)
        ready = set(self.precheck_ready_option_ids)
        pending = set(self.pending_option_ids)
        if len(candidates) != len(self.candidate_option_ids):
            raise ValueError("candidate_option_ids must be unique")
        if not ready.issubset(candidates) or not pending.issubset(candidates):
            raise ValueError("Decision option indexes must reference matrix candidates")
        if ready & pending:
            raise ValueError("ready and pending option indexes must be disjoint")
        if ready | pending != candidates:
            raise ValueError("ready and pending option indexes must cover all candidates")
        if len(set(self.required_input_fields)) != len(self.required_input_fields):
            raise ValueError("required_input_fields must be unique")
        request_ids = tuple(item.request_id for item in self.missing_data_requests)
        if len(set(request_ids)) != len(request_ids):
            raise ValueError("missing_data_requests must use unique request IDs")
        return self


class DecisionPostBankingComponentResult(ComponentResult):
    """Typed side-effect-free output of Decision post-Banking review."""

    review: DecisionPostBankingReview | None = None


class DecisionPostBankingExecutionResult(BaseModel):
    """Validated post-Banking review returned through application boundaries."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: str
    review: DecisionPostBankingReview | None = None
    generated_artifacts: tuple[ArtifactEnvelope, ...] = ()
    validation_reports: tuple[ValidationReport, ...] = ()
    validation_errors: tuple[str, ...] = ()
    missing_data_requests: tuple[MissingDataRequest, ...] = ()
    warnings: tuple[str, ...] = ()
    runtime_events: tuple[dict[str, Any], ...] = ()
