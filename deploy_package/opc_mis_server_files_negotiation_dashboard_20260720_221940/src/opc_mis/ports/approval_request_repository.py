"""Persistence port for mutable human approval-request state."""

from typing import Protocol

from opc_mis.domain.approvals import ApprovalRequest
from opc_mis.domain.enums import ApprovalRequestStatus


class ApprovalRequestRepository(Protocol):
    """Store and query approval requests independently of immutable artifacts."""

    async def save(self, request: ApprovalRequest) -> None:
        """Persist or replace one request state by stable request ID."""
        ...

    async def compare_and_set(
        self,
        request: ApprovalRequest,
        *,
        expected_status: ApprovalRequestStatus,
    ) -> tuple[ApprovalRequest | None, bool]:
        """Transition only from ``expected_status`` and return stored state/winner."""
        ...

    async def get(self, request_id: str) -> ApprovalRequest | None:
        """Return one request by ID."""
        ...

    async def list_by_case(self, evaluation_case_id: str) -> tuple[ApprovalRequest, ...]:
        """Return all approval requests for one evaluation case."""
        ...
