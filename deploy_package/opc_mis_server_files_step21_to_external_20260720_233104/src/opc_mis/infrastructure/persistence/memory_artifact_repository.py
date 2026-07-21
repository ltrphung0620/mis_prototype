"""Process-local artifact repository used by the prototype Orchestrator."""

from opc_mis.domain.artifacts import ArtifactEnvelope


class InMemoryArtifactRepository:
    """Store immutable artifact versions by stable artifact ID."""

    def __init__(self) -> None:
        self._artifacts: dict[str, ArtifactEnvelope] = {}

    async def save(self, artifact: ArtifactEnvelope) -> None:
        """Persist one envelope idempotently by artifact ID."""
        self._artifacts[artifact.artifact_id] = artifact

    async def get(self, artifact_id: str) -> ArtifactEnvelope | None:
        """Return an artifact by stable ID without exposing mutable storage."""
        return self._artifacts.get(artifact_id)

    async def list_by_case(self, evaluation_case_id: str) -> tuple[ArtifactEnvelope, ...]:
        """Return case artifacts ordered by stable ID."""
        return tuple(
            self._artifacts[key]
            for key in sorted(self._artifacts)
            if self._artifacts[key].evaluation_case_id == evaluation_case_id
        )
