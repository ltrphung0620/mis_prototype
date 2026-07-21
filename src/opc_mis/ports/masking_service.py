"""Port for fail-closed outbound payload minimization and masking."""

from collections.abc import Collection, Mapping
from typing import Protocol

from opc_mis.domain.masking_models import MaskableScalar, MaskedPayload


class MaskingService(Protocol):
    """Sanitize one flat partner payload behind a business-layer-safe contract."""

    def mask_payload(
        self,
        payload: Mapping[str, MaskableScalar],
        *,
        recipient: str,
        purpose: str,
        required_fields: Collection[str],
        source_evidence_ids_by_field: Mapping[str, Collection[str]],
    ) -> MaskedPayload:
        """Return only required and policy-authorized transformed values."""
        ...
