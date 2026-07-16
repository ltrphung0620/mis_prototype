"""HTTP request and discovery response schemas."""

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from opc_mis.domain.enums import EvaluationScope


class PlannerEvaluationRequest(BaseModel):
    """Swagger request for evaluating one contract through Planner Intake."""

    model_config = ConfigDict(
        frozen=True,
        json_schema_extra={
            "example": {
                "contract_id": "CONTRACT-ID",
                "evaluation_scope": ["FINANCE", "OPERATIONS", "RISK"],
            }
        },
    )

    contract_id: str = Field(description="Exact contract_id from 04_CONTRACTS")
    evaluation_scope: tuple[EvaluationScope, ...] = (
        EvaluationScope.FINANCE,
        EvaluationScope.OPERATIONS,
        EvaluationScope.RISK,
    )

    @field_validator("contract_id")
    @classmethod
    def normalize_contract_id(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized or any(character.isspace() for character in normalized):
            raise ValueError("contract_id must be a non-empty identifier without whitespace")
        return normalized

    @field_validator("evaluation_scope", mode="before")
    @classmethod
    def require_scope(cls, value: Any) -> Any:
        if value is None or value == [] or value == ():
            raise ValueError("evaluation_scope must contain at least one scope")
        return value


class ContractCatalogResponse(BaseModel):
    """Contracts available for Swagger evaluation."""

    model_config = ConfigDict(frozen=True)

    dataset_id: str
    snapshot_hash: str
    contract_ids: tuple[str, ...]


class OperationsAssessmentRequest(BaseModel):
    """Optional point-in-time input for deterministic past-due calculations."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        json_schema_extra={"example": {"as_of_date": "2026-07-16"}},
    )

    as_of_date: date | None = Field(
        default=None,
        description=(
            "Explicit assessment date. If omitted, Operations reports past-due facts "
            "as unavailable rather than using the server clock."
        ),
    )
