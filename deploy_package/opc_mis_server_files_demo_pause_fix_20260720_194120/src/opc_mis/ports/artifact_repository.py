"""Artifact persistence port owned by workflow orchestration."""

from typing import Protocol

from opc_mis.domain.artifacts import ArtifactEnvelope


class ArtifactRepository(Protocol):
    """Persist and retrieve immutable artifact versions."""

    async def save(self, artifact: ArtifactEnvelope) -> None:
        """Persist one validated envelope."""
        ...

    async def get(self, artifact_id: str) -> ArtifactEnvelope | None:
        """Return one immutable artifact by stable ID, if present."""
        ...

    async def list_by_case(self, evaluation_case_id: str) -> tuple[ArtifactEnvelope, ...]:
        """Return artifacts for one evaluation case."""
        ...
