"""Governance validation result contracts."""

from pydantic import BaseModel, ConfigDict

from opc_mis.domain.enums import ValidationStatus


class ValidationReport(BaseModel):
    """Evidence Validator output used before artifact persistence."""

    model_config = ConfigDict(frozen=True)

    status: ValidationStatus
    checks: tuple[str, ...] = ()
    blocking_errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
