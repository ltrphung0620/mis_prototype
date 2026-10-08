"""Append-only business runtime event contract."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RuntimeEvent(BaseModel):
    """A redaction-safe event proposed by a component or emitted by orchestration."""

    model_config = ConfigDict(frozen=True)

    event_type: str
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)
