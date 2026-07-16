"""Approval signal contract emitted by business components."""

from pydantic import BaseModel, ConfigDict

from opc_mis.domain.evidence import EvidenceRef


class ApprovalSignal(BaseModel):
    """A non-executing signal for the governance policy registry."""

    model_config = ConfigDict(frozen=True)

    approval_type: str
    protected_action: str
    trigger_rule: str
    status: str
    evidence_refs: tuple[EvidenceRef, ...] = ()
