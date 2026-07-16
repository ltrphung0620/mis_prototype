"""Protected-action command contracts."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ActionCommand(BaseModel):
    """A request for the Orchestrator to route a protected action through governance."""

    model_config = ConfigDict(frozen=True)

    action_type: str
    evaluation_case_id: str
    payload_artifact_id: str
    requested_by: str
    payload: dict[str, Any] = Field(default_factory=dict)
