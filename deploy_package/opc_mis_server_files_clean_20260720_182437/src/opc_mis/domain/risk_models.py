"""Domain contracts for the deterministic, pause/resume initial Risk scan."""

from typing import Any

from pydantic import BaseModel, ConfigDict, StrictBool, StrictFloat, StrictInt, StrictStr

from opc_mis.domain.approvals import ApprovalCheckpointSet, ApprovalSignal
from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.components import ComponentResult
from opc_mis.domain.enums import (
    ComponentStatus,
    RiskAssessmentStatus,
    RiskDependency,
    RiskExecutionMode,
    RiskLevel,
    RiskRunStatus,
    RiskScope,
    RiskSeverity,
    RuleEvaluationStatus,
    RuleOperator,
    WorkflowStatus,
)
from opc_mis.domain.validation_reports import ValidationReport

RiskValue = StrictBool | StrictInt | StrictFloat | StrictStr | None


class RiskSourceRule(BaseModel):
    """One rule loaded from the named TeamPack sheet without executing free text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id: str
    risk_type: str
    declared_condition: str
    severity: RiskSeverity
    required_action: str
    owner_agent: str
    evidence_ids: tuple[str, ...]


class RiskSourceAlert(BaseModel):
    """One TeamPack alert resolved only through exact related-record tokens."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    alert_id: str
    alert_type: str
    related_entity_ids: tuple[str, ...]
    relation_scope: RiskScope
    severity: RiskSeverity
    source_risk_score: StrictFloat | StrictInt | None
    description: str
    recommended_action: str
    evidence_ids: tuple[str, ...]


class RiskGlobalSignal(BaseModel):
    """OPC-level context that must never be attributed to a contract."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    signal_id: str
    code: str
    title: str
    detail: str
    source_record_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]


class RiskRuleDependency(BaseModel):
    """Typed upstream facts required to evaluate a source rule."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id: str
    dependencies: tuple[RiskDependency, ...]


class RiskPreScan(BaseModel):
    """Immutable TeamPack scan produced before Finance and Operations are ready."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    evaluation_case_id: str
    dataset_id: str
    contract_id: str
    source_rule_ids: tuple[str, ...]
    source_rules: tuple[RiskSourceRule, ...]
    case_alerts: tuple[RiskSourceAlert, ...]
    global_alerts: tuple[RiskSourceAlert, ...]
    global_signals: tuple[RiskGlobalSignal, ...]
    rule_dependencies: tuple[RiskRuleDependency, ...]
    source_record_counts: dict[str, int]


class RuleEvaluation(BaseModel):
    """Auditable result of one whitelisted comparison or applicability decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    evaluation_id: str
    rule_id: str
    risk_type: str
    declared_condition: str
    applicability_scope: RiskScope
    status: RuleEvaluationStatus
    severity: RiskSeverity | None
    source_field: str | None
    operator: RuleOperator | None
    threshold: RiskValue
    actual_value: RiskValue
    source_fact_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    explanation: str


class RiskFinding(BaseModel):
    """Case-specific finding derived from a triggered rule or explicit source alert."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    finding_id: str
    code: str
    title: str
    detail: str
    severity: RiskSeverity
    source_rule_id: str | None = None
    source_alert_id: str | None = None
    evidence_ids: tuple[str, ...]


class RiskEvidenceLimitation(BaseModel):
    """Non-blocking reason a potentially relevant rule cannot be evaluated."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    limitation_id: str
    code: str
    detail: str
    scope: RiskScope
    rule_id: str | None = None
    evidence_ids: tuple[str, ...] = ()


class HumanConfirmationPoint(BaseModel):
    """A reversible request for human review, not an ApprovalRequest."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    confirmation_id: str
    reason_code: str
    question: str
    severity: RiskSeverity
    evidence_ids: tuple[str, ...]


class RiskRuleEvaluationSet(BaseModel):
    """Authoritative per-rule audit artifact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    evaluation_case_id: str
    dataset_id: str
    contract_id: str
    evaluations: tuple[RuleEvaluation, ...]


class InitialRiskAssessment(BaseModel):
    """Case-level Risk output; global context remains explicitly separated."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    evaluation_case_id: str
    dataset_id: str
    contract_id: str
    assessment_status: RiskAssessmentStatus
    overall_risk_level: RiskLevel
    triggered_rule_ids: tuple[str, ...]
    findings: tuple[RiskFinding, ...]
    source_alerts: tuple[RiskSourceAlert, ...]
    global_context_signals: tuple[RiskGlobalSignal, ...]
    human_confirmation_points: tuple[HumanConfirmationPoint, ...]
    limitations: tuple[RiskEvidenceLimitation, ...]
    finance_facts_artifact_id: str
    operations_facts_artifact_id: str


class RiskComponentResult(ComponentResult):
    """Typed side-effect-free result of one Risk invocation."""

    execution_mode: RiskExecutionMode | None = None
    pre_scan: RiskPreScan | None = None
    rule_evaluations: RiskRuleEvaluationSet | None = None
    risk_assessment: InitialRiskAssessment | None = None


class RiskRunState(BaseModel):
    """Workflow-owned checkpoint used to resume Risk after upstream artifacts arrive."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    risk_run_id: str
    evaluation_case_id: str
    dataset_id: str
    status: RiskRunStatus
    checkpoint_version: int
    pre_scan_artifact_id: str | None = None
    approval_checkpoint_artifact_id: str | None = None
    finance_facts_artifact_id: str | None = None
    operations_facts_artifact_id: str | None = None
    final_artifact_ids: tuple[str, ...] = ()
    pending_dependencies: tuple[RiskDependency, ...] = ()
    failure_reason: str | None = None


class RiskExecutionResult(BaseModel):
    """Validated Risk workflow response returned by API and CLI."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: str
    risk_run_id: str
    checkpoint_status: RiskRunStatus
    pre_scan: RiskPreScan | None = None
    approval_checkpoints: ApprovalCheckpointSet | None = None
    rule_evaluations: RiskRuleEvaluationSet | None = None
    risk_assessment: InitialRiskAssessment | None = None
    pending_dependencies: tuple[RiskDependency, ...] = ()
    approval_signals: tuple[ApprovalSignal, ...] = ()
    generated_artifacts: tuple[ArtifactEnvelope, ...] = ()
    validation_reports: tuple[ValidationReport, ...] = ()
    validation_errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    runtime_events: tuple[dict[str, Any], ...] = ()
