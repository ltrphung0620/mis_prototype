"""Approval checkpoint, request, and human-decision domain contracts."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    model_validator,
)

from opc_mis.domain.commands import ActionCommand
from opc_mis.domain.enums import (
    ApprovalCheckpointStatus,
    ApprovalDecision,
    ApprovalGateStatus,
    ApprovalRequestStatus,
    ApprovalSignalStatus,
    ApprovalTriggerEvent,
    ProtectedAction,
    RuleOperator,
    WorkflowStatus,
)
from opc_mis.domain.evidence import EvidenceRef

ApprovalValue = StrictBool | StrictInt | StrictFloat | StrictStr


class ApprovalDecisionReasonCode(StrEnum):
    """Controlled public-API reason code; arbitrary human free text is excluded."""

    HUMAN_REVIEW_COMPLETED = "HUMAN_REVIEW_COMPLETED"


class ApprovalCondition(BaseModel):
    """One safe comparison evaluated only against a protected-action payload."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_field: str
    operator: RuleOperator
    threshold: ApprovalValue


class ApprovalSignal(BaseModel):
    """A non-executing, evidence-bound checkpoint candidate emitted by Risk."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    approval_type: str
    protected_action: ProtectedAction
    trigger_event: ApprovalTriggerEvent
    trigger_rule: str
    condition: ApprovalCondition
    status: ApprovalSignalStatus = ApprovalSignalStatus.CHECKPOINT_CANDIDATE
    evidence_refs: tuple[EvidenceRef, ...] = ()


class ApprovalCheckpoint(BaseModel):
    """Registered future gate; registration never pauses a workflow by itself."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    checkpoint_id: str
    evaluation_case_id: str
    source_rule_id: str
    approval_type: str
    trigger_event: ApprovalTriggerEvent
    protected_action: ProtectedAction
    condition: ApprovalCondition
    status: ApprovalCheckpointStatus = ApprovalCheckpointStatus.REGISTERED
    evidence_ids: tuple[str, ...]
    policy_coverage_ids: tuple[str, ...] = ()
    approver_role: str = "FOUNDER"

    @model_validator(mode="after")
    def validate_policy_links(self) -> "ApprovalCheckpoint":
        """Keep checkpoint policy and approver references deterministic."""
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("checkpoint evidence_ids must be unique")
        if len(set(self.policy_coverage_ids)) != len(self.policy_coverage_ids):
            raise ValueError("checkpoint policy_coverage_ids must be unique")
        if not self.approver_role.strip():
            raise ValueError("checkpoint approver_role must not be blank")
        return self


class ApprovalPolicyCoverage(BaseModel):
    """Evidence-backed proof that Governance evaluated one exact action scope."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    coverage_id: StrictStr = Field(min_length=1)
    evaluation_case_id: StrictStr = Field(min_length=1)
    protected_action: ProtectedAction
    subject_artifact_id: StrictStr = Field(min_length=1)
    api_ids: tuple[StrictStr, ...] = Field(min_length=1)
    source_policy_ids: tuple[StrictStr, ...] = Field(min_length=1)
    requires_human_approval: StrictBool
    approver_role: StrictStr = "FOUNDER"
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_scope(self) -> "ApprovalPolicyCoverage":
        """Require one unambiguous API policy scope and source lineage."""
        for field_name, values in (
            ("api_ids", self.api_ids),
            ("source_policy_ids", self.source_policy_ids),
            ("evidence_ids", self.evidence_ids),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"coverage {field_name} must be unique")
        if not self.approver_role.strip():
            raise ValueError("coverage approver_role must not be blank")
        return self


class ApprovalCheckpointSet(BaseModel):
    """Case-scoped checkpoint registry derived from an Initial Risk pre-scan."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    evaluation_case_id: str
    dataset_id: str
    contract_id: str
    checkpoints: tuple[ApprovalCheckpoint, ...]
    policy_coverages: tuple[ApprovalPolicyCoverage, ...] = ()

    @model_validator(mode="after")
    def validate_registry(self) -> "ApprovalCheckpointSet":
        """Reject duplicate or dangling policy references in one registry."""
        coverage_ids = tuple(item.coverage_id for item in self.policy_coverages)
        if len(set(coverage_ids)) != len(coverage_ids):
            raise ValueError("policy coverage IDs must be unique")
        if any(
            item.evaluation_case_id != self.evaluation_case_id
            for item in self.policy_coverages
        ):
            raise ValueError("policy coverage belongs to another evaluation case")
        known = set(coverage_ids)
        dangling = {
            coverage_id
            for checkpoint in self.checkpoints
            for coverage_id in checkpoint.policy_coverage_ids
            if coverage_id not in known
        }
        if dangling:
            raise ValueError("checkpoint references unknown policy coverage")
        by_id = {item.coverage_id: item for item in self.policy_coverages}
        if any(
            by_id[coverage_id].protected_action is not checkpoint.protected_action
            for checkpoint in self.checkpoints
            for coverage_id in checkpoint.policy_coverage_ids
        ):
            raise ValueError("checkpoint and policy coverage actions must match")
        api_scopes = tuple(
            (item.protected_action, item.subject_artifact_id, api_id)
            for item in self.policy_coverages
            for api_id in item.api_ids
        )
        if len(set(api_scopes)) != len(api_scopes):
            raise ValueError("API policy coverage scopes must be unique")
        return self


class ApprovalDecisionRecord(BaseModel):
    """Auditable human resolution without embedding authentication concerns."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: ApprovalDecision
    decided_by: str
    reason: str = Field(min_length=1, max_length=64)
    decided_at: datetime


class ApprovalRequest(BaseModel):
    """One persisted human request or explicit machine authorization record."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str
    workflow_run_id: str
    evaluation_case_id: str
    dataset_id: str
    subject_artifact_id: str
    subject_artifact_version: int = Field(ge=1)
    subject_input_hash: str
    checkpoint_ids: tuple[str, ...]
    policy_artifact_id: str | None = None
    policy_artifact_version: int | None = Field(default=None, ge=1)
    policy_input_hash: str | None = None
    policy_coverage_ids: tuple[str, ...] = ()
    command: ActionCommand
    resume_stage: str | None = None
    status: ApprovalRequestStatus
    created_at: datetime
    decision_record: ApprovalDecisionRecord | None = None

    @model_validator(mode="after")
    def validate_authorization_lineage(self) -> "ApprovalRequest":
        """Keep human and policy authorization provenance unambiguous."""
        if len(set(self.checkpoint_ids)) != len(self.checkpoint_ids):
            raise ValueError("approval checkpoint_ids must be unique")
        if len(set(self.policy_coverage_ids)) != len(self.policy_coverage_ids):
            raise ValueError("approval policy_coverage_ids must be unique")
        policy_identity = (
            self.policy_artifact_id,
            self.policy_artifact_version,
            self.policy_input_hash,
        )
        if any(item is not None for item in policy_identity) and not all(
            item is not None for item in policy_identity
        ):
            raise ValueError("approval policy artifact identity must be complete")
        if self.status is ApprovalRequestStatus.AUTHORIZED_WITHOUT_HUMAN and (
            self.decision_record is not None
            or not all(item is not None for item in policy_identity)
        ):
            raise ValueError(
                "machine authorization requires exact policy lineage and no human decision"
            )
        if self.status is ApprovalRequestStatus.APPROVED and (
            self.decision_record is None
            or self.decision_record.decision is not ApprovalDecision.APPROVE
        ):
            raise ValueError("approved request requires an APPROVE decision")
        if self.status is ApprovalRequestStatus.REJECTED and (
            self.decision_record is None
            or self.decision_record.decision is not ApprovalDecision.REJECT
        ):
            raise ValueError("rejected request requires a REJECT decision")
        if (
            self.status is ApprovalRequestStatus.PENDING
            and self.decision_record is not None
        ):
            raise ValueError("pending request cannot contain a decision")
        if (
            self.command.action_type is ProtectedAction.SUBMIT_BANKING_PRECHECK
            and self.status is not ApprovalRequestStatus.EXPIRED
            and (
                not all(item is not None for item in policy_identity)
                or not self.policy_coverage_ids
            )
        ):
            raise ValueError("Banking precheck control requires exact policy coverage")
        return self


class ApprovalExecutionResult(BaseModel):
    """Workflow-owned result for gate evaluation or human resolution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    gate_status: ApprovalGateStatus
    current_node: str
    workflow_run_id: str | None = None
    evaluation_case_id: str
    action_authorized: bool
    approval_request: ApprovalRequest | None = None
    missing_fields: tuple[str, ...] = ()
    reason: str
    runtime_events: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
