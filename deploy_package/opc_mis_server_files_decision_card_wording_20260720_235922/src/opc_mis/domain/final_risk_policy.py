"""Pure deterministic policy for the Final Risk assessment contract."""

from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.enums import (
    FinalRiskAssessmentStatus,
    FinalRiskConclusion,
    FinalRiskControlCode,
    MajorExceptionStatus,
    ProtectedAction,
    ResidualRiskStatus,
    RiskAssessmentStatus,
    RiskLevel,
    RiskSeverity,
)
from opc_mis.domain.final_risk_models import (
    FinalRiskAssessment,
    MajorExceptionSignal,
    RequiredControl,
    ResidualRiskFinding,
    final_risk_assessment_id,
)
from opc_mis.domain.internal_decision_package_models import InternalDecisionPackage
from opc_mis.domain.lineage import deterministic_id


def build_final_risk_assessment(
    *,
    package_artifact: ArtifactEnvelope,
    package: InternalDecisionPackage,
) -> FinalRiskAssessment:
    """Derive the one canonical assessment from an exact ready package."""
    initial = package.risk_assessment
    findings = final_risk_residual_findings(package)
    controls = final_risk_required_controls(package)
    assessment_status = (
        FinalRiskAssessmentStatus.LIMITED_BY_EVIDENCE
        if initial.assessment_status is RiskAssessmentStatus.LIMITED_BY_EVIDENCE
        else FinalRiskAssessmentStatus.COMPLETE
    )
    major_status, major_signal = final_risk_major_exception(
        package=package,
        findings=findings,
        assessment_status=assessment_status,
    )
    residual_risk_level = final_residual_risk_level(findings)
    conclusion = final_risk_conclusion(
        findings=findings,
        unresolved_approval_gate_count=0,
        controls=controls,
        has_evidence_limitations=bool(initial.limitations),
    )
    assessment_id = final_risk_assessment_id(
        internal_decision_package_artifact_id=package_artifact.artifact_id,
        internal_decision_package_artifact_version=package_artifact.version,
        internal_decision_package_input_hash=package_artifact.input_hash,
        internal_decision_package_id=package.package_id,
        assessment_status=assessment_status,
        residual_risk_level=residual_risk_level,
        residual_findings=findings,
        unresolved_approval_gates=(),
        required_controls=controls,
        major_exception_status=major_status,
        major_exception_signal=major_signal,
        limitations=initial.limitations,
        evidence_ids=package.evidence_ids,
    )
    return FinalRiskAssessment(
        assessment_id=assessment_id,
        evaluation_case_id=package.evaluation_case_id,
        dataset_id=package.dataset_id,
        contract_id=package.contract_id,
        internal_decision_package_id=package.package_id,
        internal_decision_package_artifact_id=package_artifact.artifact_id,
        internal_decision_package_artifact_version=package_artifact.version,
        internal_decision_package_input_hash=package_artifact.input_hash,
        assembly_path=package.assembly_path,
        initial_risk_assessment_artifact_id=(
            package.risk_assessment_artifact_id
        ),
        assessment_status=assessment_status,
        initial_assessment_status=initial.assessment_status,
        initial_risk_level=initial.overall_risk_level,
        residual_risk_level=residual_risk_level,
        conclusion=conclusion,
        residual_findings=findings,
        unresolved_approval_gates=(),
        unresolved_approval_gate_ids=(),
        required_controls=controls,
        required_control_ids=tuple(item.control_id for item in controls),
        major_exception_status=major_status,
        major_exception_signal=major_signal,
        limitations=initial.limitations,
        evidence_ids=package.evidence_ids,
    )


def final_residual_risk_level(
    findings: tuple[ResidualRiskFinding, ...],
) -> RiskLevel:
    """Aggregate only findings that are still open at the final checkpoint."""

    if not findings:
        return RiskLevel.NO_CASE_SIGNAL
    severity_order = {
        RiskSeverity.LOW: 1,
        RiskSeverity.MEDIUM: 2,
        RiskSeverity.HIGH: 3,
        RiskSeverity.CRITICAL: 4,
    }
    highest = max(findings, key=lambda item: severity_order[item.severity])
    return RiskLevel(highest.severity)


def final_risk_conclusion(
    *,
    findings: tuple[ResidualRiskFinding, ...],
    unresolved_approval_gate_count: int,
    controls: tuple[RequiredControl, ...],
    has_evidence_limitations: bool,
) -> FinalRiskConclusion:
    """Conclude SAFE only when no risk or human/evidence uncertainty remains."""

    has_unresolved_confirmation = any(
        item.code is FinalRiskControlCode.HUMAN_CONFIRMATION_REQUIRED
        for item in controls
    )
    if (
        findings
        or unresolved_approval_gate_count
        or has_unresolved_confirmation
        or has_evidence_limitations
    ):
        return FinalRiskConclusion.ATTENTION_REQUIRED
    return FinalRiskConclusion.SAFE


def final_risk_residual_findings(
    package: InternalDecisionPackage,
) -> tuple[ResidualRiskFinding, ...]:
    """Carry exact findings that have no explicit resolution in the package."""
    return tuple(
        ResidualRiskFinding(
            residual_finding_id=deterministic_id(
                "RRF",
                package.package_id,
                finding.finding_id,
                ResidualRiskStatus.OPEN_UNCHANGED,
                finding.evidence_ids,
            ),
            source_finding_id=finding.finding_id,
            code=finding.code,
            title=finding.title,
            detail=finding.detail,
            severity=finding.severity,
            evidence_ids=finding.evidence_ids,
        )
        for finding in package.risk_assessment.findings
    )


def final_risk_required_controls(
    package: InternalDecisionPackage,
) -> tuple[RequiredControl, ...]:
    """Derive exact controls while keeping dormant checkpoints non-active."""
    controls: list[RequiredControl] = []

    def add(
        *,
        code: FinalRiskControlCode,
        description: str,
        source_reference_ids: tuple[str, ...],
        evidence_ids: tuple[str, ...],
        protected_action: ProtectedAction | None = None,
    ) -> None:
        controls.append(
            RequiredControl(
                control_id=deterministic_id(
                    "FRC",
                    package.package_id,
                    code,
                    source_reference_ids,
                    protected_action,
                    evidence_ids,
                ),
                code=code,
                description=description,
                protected_action=protected_action,
                source_reference_ids=source_reference_ids,
                evidence_ids=evidence_ids,
            )
        )

    for point in package.risk_assessment.human_confirmation_points:
        add(
            code=FinalRiskControlCode.HUMAN_CONFIRMATION_REQUIRED,
            description=point.question,
            source_reference_ids=(point.confirmation_id,),
            evidence_ids=point.evidence_ids,
        )
    for limitation in package.risk_assessment.limitations:
        add(
            code=FinalRiskControlCode.EVIDENCE_LIMITATION_MUST_BE_PRESERVED,
            description=(
                "Preserve this evidence limitation; do not convert the unknown "
                f"into a fact: {limitation.detail}"
            ),
            source_reference_ids=(limitation.limitation_id,),
            evidence_ids=limitation.evidence_ids,
        )
    for checkpoint_set in package.approval_checkpoints:
        for checkpoint in checkpoint_set.checkpoints:
            add(
                code=(
                    FinalRiskControlCode.GOVERNANCE_EVALUATION_BEFORE_PROTECTED_ACTION
                ),
                description=(
                    "If the protected action is later proposed, Governance must "
                    "evaluate this registered checkpoint before execution."
                ),
                source_reference_ids=(checkpoint.checkpoint_id,),
                evidence_ids=checkpoint.evidence_ids,
                protected_action=checkpoint.protected_action,
            )
    for reference in package.governance_references:
        add(
            code=FinalRiskControlCode.GOVERNANCE_REJECTION_MUST_BE_HONORED,
            description=(
                "The resolved Founder rejection remains binding for the exact "
                "protected-action subject and cannot be reused or bypassed."
            ),
            source_reference_ids=(reference.approval_request_id,),
            evidence_ids=(),
            protected_action=reference.action,
        )
    if package.banking_precheck_result_set is not None:
        result_set = package.banking_precheck_result_set
        add(
            code=FinalRiskControlCode.SIMULATED_BANKING_RESULT_IS_NON_BINDING,
            description=(
                "The Banking precheck result is simulated and non-binding; it "
                "must not be represented as a bank offer or approval."
            ),
            source_reference_ids=(result_set.result_set_id,),
            evidence_ids=result_set.evidence_ids,
        )
    if package.document_release_package is not None:
        release = package.document_release_package
        add(
            code=(
                FinalRiskControlCode.DOCUMENT_RELEASE_REQUIRES_SEPARATE_AUTHORIZATION
            ),
            description=(
                "The masked Document package is an internal candidate only; a "
                "separate evidence-bound proposal and Governance authorization "
                "are required before external release."
            ),
            source_reference_ids=(release.release_package_id,),
            evidence_ids=release.evidence_ids,
            protected_action=ProtectedAction.SEND_DOCUMENT_TO_EXTERNAL_PARTNER,
        )

    unique: dict[str, RequiredControl] = {}
    for control in controls:
        existing = unique.setdefault(control.control_id, control)
        if existing != control:
            raise ValueError("Final Risk required-control identity collision.")
    return tuple(unique.values())


def final_risk_major_exception(
    *,
    package: InternalDecisionPackage,
    findings: tuple[ResidualRiskFinding, ...],
    assessment_status: FinalRiskAssessmentStatus,
) -> tuple[MajorExceptionStatus, MajorExceptionSignal | None]:
    """Conclude major-exception status only from explicit critical evidence."""
    critical = tuple(
        item for item in findings if item.severity is RiskSeverity.CRITICAL
    )
    if not critical:
        status = (
            MajorExceptionStatus.NOT_EVALUABLE
            if assessment_status is FinalRiskAssessmentStatus.LIMITED_BY_EVIDENCE
            else MajorExceptionStatus.NOT_DETECTED
        )
        return status, None
    finding_ids = tuple(item.residual_finding_id for item in critical)
    evidence_ids = tuple(
        dict.fromkeys(
            evidence_id
            for finding in critical
            for evidence_id in finding.evidence_ids
        )
    )
    signal = MajorExceptionSignal(
        signal_id=deterministic_id(
            "MES", package.package_id, finding_ids, evidence_ids
        ),
        detail=(
            "One or more explicit case-specific CRITICAL findings remain open; "
            "a later Governance/Decision phase must not silently bypass them."
        ),
        source_residual_finding_ids=finding_ids,
        evidence_ids=evidence_ids,
    )
    return MajorExceptionStatus.DETECTED, signal
