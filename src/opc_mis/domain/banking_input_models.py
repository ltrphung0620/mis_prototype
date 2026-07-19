"""Domain contracts for immutable Banking amount-input intake."""

from typing import Any

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
from opc_mis.domain.banking_models import BankingInputSupplement
from opc_mis.domain.components import ComponentResult
from opc_mis.domain.enums import ComponentStatus, CurrencyCode, WorkflowStatus
from opc_mis.domain.missing_data import MissingDataRequest
from opc_mis.domain.validation_reports import ValidationReport


def _normalized_text(value: str) -> str:
    normalized = " ".join(value.split())
    if not normalized:
        raise ValueError("value must not be blank")
    return normalized


class BankingAmountInputSubmission(BaseModel):
    """Typed human submission accepted by the Banking amount-input endpoint."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    workflow_run_id: StrictStr = Field(min_length=1)
    missing_request_id: StrictStr = Field(min_length=1)
    requested_amount: StrictInt = Field(gt=0)
    requested_amount_currency: CurrencyCode = CurrencyCode.VND
    provided_by: StrictStr = Field(min_length=1)
    evidence_note: StrictStr = Field(min_length=1)

    @field_validator(
        "workflow_run_id",
        "missing_request_id",
        "provided_by",
        "evidence_note",
    )
    @classmethod
    def normalize_text(cls, value: str) -> str:
        """Normalize user whitespace before stable identity is calculated."""
        return _normalized_text(value)

    @model_validator(mode="after")
    def require_vnd(self) -> "BankingAmountInputSubmission":
        """The current TeamPack and Banking policy use VND only."""
        if self.requested_amount_currency is not CurrencyCode.VND:
            raise ValueError("Banking amount input must use VND")
        return self


class BankingAmountInputCommand(BaseModel):
    """Server-enriched component input with the authoritative pending request ID."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    submission: BankingAmountInputSubmission
    allowed_pending_request_id: StrictStr = Field(min_length=1)

    @field_validator("allowed_pending_request_id")
    @classmethod
    def normalize_allowed_request(cls, value: str) -> str:
        return _normalized_text(value)


class BankingInputComponentResult(ComponentResult):
    """Side-effect-free Banking intake result containing at most one draft."""

    supplement: BankingInputSupplement | None = None


class BankingInputExecutionResult(BaseModel):
    """Validated, persisted Banking input result returned by the workflow layer."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: str
    supplement: BankingInputSupplement | None = None
    generated_artifacts: tuple[ArtifactEnvelope, ...] = ()
    validation_reports: tuple[ValidationReport, ...] = ()
    validation_errors: tuple[str, ...] = ()
    missing_data_requests: tuple[MissingDataRequest, ...] = ()
    warnings: tuple[str, ...] = ()
    runtime_events: tuple[dict[str, Any], ...] = ()
