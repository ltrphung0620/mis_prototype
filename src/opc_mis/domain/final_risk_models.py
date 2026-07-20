"""Domain contracts for the deterministic Final Risk Check.

Final Risk consumes one validated Internal Decision Package. It preserves the
historical initial risk separately from the risk and governance items that
remain open at the final checkpoint.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    model_validator,
)

from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.components import ComponentResult
from opc_mis.domain.enums import (
    ApprovalRequestStatus,
    ComponentStatus,
    FinalRiskAssessmentStatus,
    FinalRiskConclusion,
    FinalRiskControlCode,
    MajorExceptionStatus,
    ProtectedAction,
    ResidualRiskStatus,
    RiskAssessmentStatus,
    RiskLevel,
    RiskSeverity,
    WorkflowStatus,
)
from opc_mis.domain.internal_decision_package_models import (
    InternalDecisionAssemblyPath,
)
from opc_mis.domain.lineage import deterministic_id
from opc_mis.domain.missing_data import MissingDataRequest
from opc_mis.domain.risk_models import RiskEvidenceLimitation
from opc_mis.domain.validation_reports import ValidationReport


class ResidualRiskFinding(BaseModel):
    """An explicit case finding that is still open at the final checkpoint."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    residual_finding_id: StrictStr = Field(min_length=1)
    source_finding_id: StrictStr = Field(min_length=1)
    code: StrictStr = Field(min_length=1)
    title: StrictStr = Field(min_length=1)
    detail: StrictStr = Field(min_length=1)
    severity: RiskSeverity
    status: ResidualRiskStatus = ResidualRiskStatus.OPEN_UNCHANGED
    evidence_ids: tuple[StrictStr, ...]

    @model_validator(mode="after")
    def validate_lineage(self) -> ResidualRiskFinding:
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("Residual finding evidence_ids must be unique")
        return self


class UnresolvedApprovalGate(BaseModel):
    """An explicitly active unresolved gate, never a dormant checkpoint."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    gate_id: StrictStr = Field(min_length=1)
    approval_request_id: StrictStr = Field(min_length=1)
    protected_action: ProtectedAction
    request_status: ApprovalRequestStatus
    checkpoint_ids: tuple[StrictStr, ...]
    reason: StrictStr = Field(min_length=1)
    evidence_ids: tuple[StrictStr, ...] = ()

    @model_validator(mode="after")
    def validate_unresolved_status(self) -> UnresolvedApprovalGate:
        if self.request_status not in {
            ApprovalRequestStatus.PENDING,
            ApprovalRequestStatus.EXPIRED,
        }:
            raise ValueError("Only PENDING or EXPIRED approval requests are unresolved")
        if len(set(self.checkpoint_ids)) != len(self.checkpoint_ids):
            raise ValueError("Unresolved gate checkpoint_ids must be unique")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("Unresolved gate evidence_ids must be unique")
        return self


class RequiredControl(BaseModel):
    """A control Decision must preserve; Final Risk does not execute it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    control_id: StrictStr = Field(min_length=1)
    code: FinalRiskControlCode
    description: StrictStr = Field(min_length=1)
    protected_action: ProtectedAction | None = None
    source_reference_ids: tuple[StrictStr, ...] = Field(min_length=1)
    evidence_ids: tuple[StrictStr, ...] = ()

    @model_validator(mode="after")
    def validate_references(self) -> RequiredControl:
        if len(set(self.source_reference_ids)) != len(self.source_reference_ids):
            raise ValueError("Required-control source references must be unique")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("Required-control evidence_ids must be unique")
        return self


class MajorExceptionSignal(BaseModel):
    """Evidence-bound critical residual risk; it is not an ApprovalRequest."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    signal_id: StrictStr = Field(min_length=1)
    code: Literal["CRITICAL_RESIDUAL_RISK"] = "CRITICAL_RESIDUAL_RISK"
    detail: StrictStr = Field(min_length=1)
    severity: RiskSeverity = RiskSeverity.CRITICAL
    source_residual_finding_ids: tuple[StrictStr, ...] = Field(min_length=1)
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_critical_signal(self) -> MajorExceptionSignal:
        if self.severity is not RiskSeverity.CRITICAL:
            raise ValueError("A major-exception signal must be CRITICAL")
        if len(set(self.source_residual_finding_ids)) != len(
            self.source_residual_finding_ids
        ):
            raise ValueError("Major-exception source findings must be unique")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("Major-exception evidence_ids must be unique")
        return self


class FinalRiskAssessment(BaseModel):
    """Authoritative residual-risk input for a later deterministic Decision policy."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    assessment_id: StrictStr = Field(min_length=1)
    evaluation_case_id: StrictStr = Field(min_length=1)
    dataset_id: StrictStr = Field(min_length=1)
    contract_id: StrictStr = Field(min_length=1)
    internal_decision_package_id: StrictStr = Field(min_length=1)
    internal_decision_package_artifact_id: StrictStr = Field(min_length=1)
    internal_decision_package_artifact_version: int = Field(ge=1)
    internal_decision_package_input_hash: StrictStr = Field(min_length=1)
    assembly_path: InternalDecisionAssemblyPath
    initial_risk_assessment_artifact_id: StrictStr = Field(min_length=1)

    assessment_status: FinalRiskAssessmentStatus
    initial_assessment_status: RiskAssessmentStatus
    initial_risk_level: RiskLevel
    residual_risk_level: RiskLevel
    conclusion: FinalRiskConclusion
    residual_findings: tuple[ResidualRiskFinding, ...]
    unresolved_approval_gates: tuple[UnresolvedApprovalGate, ...] = ()
    unresolved_approval_gate_ids: tuple[StrictStr, ...] = ()
    required_controls: tuple[RequiredControl, ...] = ()
    required_control_ids: tuple[StrictStr, ...] = ()
    major_exception_status: MajorExceptionStatus
    major_exception_signal: MajorExceptionSignal | None = None
    limitations: tuple[RiskEvidenceLimitation, ...] = ()
    evidence_ids: tuple[StrictStr, ...]

    recommendation_performed: Literal[False] = False
    approval_requested: Literal[False] = False
    external_action_performed: Literal[False] = False

    @model_validator(mode="after")
    def validate_final_risk_contract(self) -> FinalRiskAssessment:
        self._validate_unique_indexes()
        severity_order = {
            RiskSeverity.LOW: 1,
            RiskSeverity.MEDIUM: 2,
            RiskSeverity.HIGH: 3,
            RiskSeverity.CRITICAL: 4,
        }
        expected_residual_level = RiskLevel.NO_CASE_SIGNAL
        if self.residual_findings:
            highest = max(
                self.residual_findings,
                key=lambda item: severity_order[item.severity],
            )
            expected_residual_level = RiskLevel(highest.severity)
        if self.residual_risk_level is not expected_residual_level:
            raise ValueError(
                "Final Risk level must be derived only from open residual findings"
            )

        has_unresolved_confirmation = any(
            item.code is FinalRiskControlCode.HUMAN_CONFIRMATION_REQUIRED
            for item in self.required_controls
        )
        expected_conclusion = (
            FinalRiskConclusion.ATTENTION_REQUIRED
            if (
                self.residual_findings
                or self.unresolved_approval_gates
                or has_unresolved_confirmation
                or self.limitations
            )
            else FinalRiskConclusion.SAFE
        )
        if self.conclusion is not expected_conclusion:
            raise ValueError(
                "Final Risk conclusion contradicts unresolved risks, approvals, "
                "confirmations, or evidence limitations"
            )
        expected_status = (
            FinalRiskAssessmentStatus.LIMITED_BY_EVIDENCE
            if self.initial_assessment_status
            is RiskAssessmentStatus.LIMITED_BY_EVIDENCE
            else FinalRiskAssessmentStatus.COMPLETE
        )
        if self.assessment_status is not expected_status:
            raise ValueError("Final Risk completeness must preserve initial evidence limits")

        critical = tuple(
            item
            for item in self.residual_findings
            if item.severity is RiskSeverity.CRITICAL
        )
        expected_major_status = (
            MajorExceptionStatus.DETECTED
            if critical
            else (
                MajorExceptionStatus.NOT_EVALUABLE
                if self.assessment_status
                is FinalRiskAssessmentStatus.LIMITED_BY_EVIDENCE
                else MajorExceptionStatus.NOT_DETECTED
            )
        )
        if self.major_exception_status is not expected_major_status:
            raise ValueError("Major-exception status contradicts explicit residual risk")
        if expected_major_status is MajorExceptionStatus.DETECTED:
            if self.major_exception_signal is None:
                raise ValueError("Detected major exception requires one signal")
            expected_finding_ids = tuple(
                item.residual_finding_id for item in critical
            )
            if (
                self.major_exception_signal.source_residual_finding_ids
                != expected_finding_ids
            ):
                raise ValueError("Major-exception signal must index every critical finding")
        elif self.major_exception_signal is not None:
            raise ValueError("A non-detected major exception cannot contain a signal")

        known_evidence = set(self.evidence_ids)
        used_evidence = {
            evidence_id
            for item in (
                *self.residual_findings,
                *self.unresolved_approval_gates,
                *self.required_controls,
                *self.limitations,
            )
            for evidence_id in item.evidence_ids
        }
        if self.major_exception_signal is not None:
            used_evidence.update(self.major_exception_signal.evidence_ids)
        if not used_evidence.issubset(known_evidence):
            raise ValueError("Final Risk outputs reference unknown evidence IDs")

        expected_id = final_risk_assessment_id(
            internal_decision_package_artifact_id=(
                self.internal_decision_package_artifact_id
            ),
            internal_decision_package_artifact_version=(
                self.internal_decision_package_artifact_version
            ),
            internal_decision_package_input_hash=(
                self.internal_decision_package_input_hash
            ),
            internal_decision_package_id=self.internal_decision_package_id,
            assessment_status=self.assessment_status,
            residual_risk_level=self.residual_risk_level,
            residual_findings=self.residual_findings,
            unresolved_approval_gates=self.unresolved_approval_gates,
            required_controls=self.required_controls,
            major_exception_status=self.major_exception_status,
            major_exception_signal=self.major_exception_signal,
            limitations=self.limitations,
            evidence_ids=self.evidence_ids,
        )
        if self.assessment_id != expected_id:
            raise ValueError("Final Risk assessment_id is unstable")
        return self

    def _validate_unique_indexes(self) -> None:
        collections = (
            (
                "residual finding IDs",
                tuple(item.residual_finding_id for item in self.residual_findings),
            ),
            (
                "source finding IDs",
                tuple(item.source_finding_id for item in self.residual_findings),
            ),
            (
                "unresolved gate IDs",
                tuple(item.gate_id for item in self.unresolved_approval_gates),
            ),
            (
                "required control IDs",
                tuple(item.control_id for item in self.required_controls),
            ),
            ("evidence_ids", self.evidence_ids),
        )
        for label, values in collections:
            if len(set(values)) != len(values):
                raise ValueError(f"Final Risk {label} must be unique")
        if self.unresolved_approval_gate_ids != tuple(
            item.gate_id for item in self.unresolved_approval_gates
        ):
            raise ValueError("unresolved_approval_gate_ids must exactly index gates")
        if self.required_control_ids != tuple(
            item.control_id for item in self.required_controls
        ):
            raise ValueError("required_control_ids must exactly index controls")


class FinalRiskComponentResult(ComponentResult):
    """Side-effect-free result containing at most one Final Risk draft."""

    assessment: FinalRiskAssessment | None = None


class FinalRiskExecutionResult(BaseModel):
    """Validated Final Risk result returned through orchestration boundaries."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: StrictStr = Field(min_length=1)
    assessment: FinalRiskAssessment | None = None
    generated_artifacts: tuple[ArtifactEnvelope, ...] = ()
    validation_reports: tuple[ValidationReport, ...] = ()
    validation_errors: tuple[StrictStr, ...] = ()
    missing_data_requests: tuple[MissingDataRequest, ...] = ()
    warnings: tuple[StrictStr, ...] = ()
    runtime_events: tuple[dict[str, Any], ...] = ()


def final_risk_assessment_id(
    *,
    internal_decision_package_artifact_id: str,
    internal_decision_package_artifact_version: int,
    internal_decision_package_input_hash: str,
    internal_decision_package_id: str,
    assessment_status: FinalRiskAssessmentStatus,
    residual_risk_level: RiskLevel,
    residual_findings: tuple[ResidualRiskFinding, ...],
    unresolved_approval_gates: tuple[UnresolvedApprovalGate, ...],
    required_controls: tuple[RequiredControl, ...],
    major_exception_status: MajorExceptionStatus,
    major_exception_signal: MajorExceptionSignal | None,
    limitations: tuple[RiskEvidenceLimitation, ...],
    evidence_ids: tuple[str, ...],
) -> str:
    """Build identity only from exact upstream identity and deterministic output."""

    return deterministic_id(
        "FRA",
        internal_decision_package_artifact_id,
        internal_decision_package_artifact_version,
        internal_decision_package_input_hash,
        internal_decision_package_id,
        assessment_status,
        residual_risk_level,
        tuple(item.model_dump(mode="json") for item in residual_findings),
        tuple(item.model_dump(mode="json") for item in unresolved_approval_gates),
        tuple(item.model_dump(mode="json") for item in required_controls),
        major_exception_status,
        (
            major_exception_signal.model_dump(mode="json")
            if major_exception_signal is not None
            else None
        ),
        tuple(item.model_dump(mode="json") for item in limitations),
        evidence_ids,
    )
