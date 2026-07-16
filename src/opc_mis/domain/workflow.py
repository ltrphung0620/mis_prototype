"""Workflow node identifiers owned by the application layer."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from opc_mis.domain.enums import WorkflowStatus


class WorkflowNode(StrEnum):
    """Nodes currently implemented by the Planner intake slice."""

    DATASET_INGESTION = "DATASET_INGESTION"
    PLANNER_INTAKE = "PLANNER_INTAKE"
    INITIAL_ASSESSMENT = "INITIAL_ASSESSMENT"
    FINANCE_ASSESSMENT = "FINANCE_ASSESSMENT"
    OPERATIONS_ASSESSMENT = "OPERATIONS_ASSESSMENT"


class WorkflowRunState(BaseModel):
    """Persisted state selected by the Orchestrator after a node attempt."""

    model_config = ConfigDict(frozen=True)

    workflow_run_id: str
    dataset_id: str
    evaluation_case_id: str | None
    status: WorkflowStatus
    current_node: str
    blocked_node: str | None = None
    blocked_reason: str | None = None
    pending_request_ids: tuple[str, ...] = ()
