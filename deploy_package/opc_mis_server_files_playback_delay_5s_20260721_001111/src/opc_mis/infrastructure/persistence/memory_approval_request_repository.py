"""Process-local approval request storage for the prototype runtime."""

from opc_mis.domain.approvals import ApprovalRequest
from opc_mis.domain.enums import ApprovalRequestStatus


class InMemoryApprovalRequestRepository:
    """Store approval request state behind the governance persistence port."""

    def __init__(self) -> None:
        self._requests: dict[str, ApprovalRequest] = {}

    async def save(self, request: ApprovalRequest) -> None:
        """Persist or replace one request state."""
        self._requests[request.request_id] = request

    async def compare_and_set(
        self,
        request: ApprovalRequest,
        *,
        expected_status: ApprovalRequestStatus,
    ) -> tuple[ApprovalRequest | None, bool]:
        """Apply one atomic process-local status transition."""
        current = self._requests.get(request.request_id)
        if current is None or current.status is not expected_status:
            return current, False
        self._requests[request.request_id] = request
        return request, True

    async def get(self, request_id: str) -> ApprovalRequest | None:
        """Return one request without exposing mutable storage."""
        return self._requests.get(request_id)

    async def list_by_case(self, evaluation_case_id: str) -> tuple[ApprovalRequest, ...]:
        """Return case requests ordered by stable ID."""
        return tuple(
            self._requests[key]
            for key in sorted(self._requests)
            if self._requests[key].evaluation_case_id == evaluation_case_id
        )
