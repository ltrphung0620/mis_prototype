"""Missing-data contracts shared by business components and workflow."""

from pydantic import BaseModel, ConfigDict

from opc_mis.domain.enums import MissingRequestStatus, MissingSeverity
from opc_mis.domain.evidence import EvidenceRef


class MissingDataRequest(BaseModel):
    """A precise blocking request that workflow can persist and later resolve."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    evaluation_case_id: str
    raised_by: str
    requirement_code: str
    target_record: str
    field: str
    expected_type: str
    reason: str
    severity: MissingSeverity = MissingSeverity.BLOCKING
    status: MissingRequestStatus = MissingRequestStatus.OPEN
    evidence_refs: tuple[EvidenceRef, ...] = ()
