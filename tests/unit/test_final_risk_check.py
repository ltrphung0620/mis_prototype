"""Focused tests for deterministic Final Risk domain/business boundaries."""

import asyncio

from opc_mis.business.agents.risk.final_component import FinalRiskCheck
from opc_mis.business.agents.risk.final_context_loader import FinalRiskContextLoader
from opc_mis.domain.approvals import ApprovalCheckpoint, ApprovalCheckpointSet
from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import (
    ApprovalTriggerEvent,
    ArtifactType,
    ComponentStatus,
    EvaluationScope,
    FinalRiskAssessmentStatus,
    FinalRiskConclusion,
    FinalRiskControlCode,
    MajorExceptionStatus,
    ProtectedAction,
    RiskAssessmentStatus,
    RiskLevel,
    RiskScope,
    RiskSeverity,
    RuleOperator,
    SourceType,
    ValidationStatus,
)
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.final_risk_models import FinalRiskAssessment
from opc_mis.domain.risk_models import (
    HumanConfirmationPoint,
    InitialRiskAssessment,
    RiskEvidenceLimitation,
    RiskFinding,
)
from opc_mis.infrastructure.persistence.memory_artifact_repository import (
    InMemoryArtifactRepository,
)
from tests.unit.test_internal_decision_package_orchestrator import (
    CASE_ID,
    CONTRACT_ID,
    DATASET_ID,
    _direct_artifacts,
    _save_all,
)
from tests.unit.test_internal_decision_package_orchestrator import (
    _context as internal_package_context,
)
from tests.unit.test_internal_decision_package_orchestrator import (
    _system as internal_package_system,
)


def _evidence() -> EvidenceRef:
    return EvidenceRef(
        evidence_id="EVD-FINAL-RISK",
        source_type=SourceType.DERIVED,
        sheet="RISK",
        row_number=0,
        record_id="RISK-FINAL-TEST",
        field="risk",
        display_value="explicit risk evidence",
    )


async def _package_artifact(
    *,
    risk: InitialRiskAssessment | None = None,
    checkpoints: ApprovalCheckpointSet | None = None,
) -> tuple[InMemoryArtifactRepository, ArtifactEnvelope]:
    repository, _, orchestrator = internal_package_system()
    evidence = _evidence()
    sources = list(_direct_artifacts())
    if risk is not None:
        index = next(
            index
            for index, item in enumerate(sources)
            if item.artifact_type is ArtifactType.INITIAL_RISK_ASSESSMENT
        )
        sources[index] = sources[index].model_copy(
            update={
                "payload": risk.model_dump(mode="json"),
                "evidence_refs": (evidence,),
            }
        )
    if checkpoints is not None:
        index = next(
            index
            for index, item in enumerate(sources)
            if item.artifact_type is ArtifactType.APPROVAL_CHECKPOINTS
        )
        sources[index] = sources[index].model_copy(
            update={
                "payload": checkpoints.model_dump(mode="json"),
                "evidence_refs": (evidence,),
            }
        )
    source_tuple = tuple(sources)
    await _save_all(repository, source_tuple)
    result = await orchestrator.run(internal_package_context(source_tuple))
    assert result.status.value == "COMPLETED"
    assert len(result.generated_artifacts) == 1
    return repository, result.generated_artifacts[0]


def _execution_context(package_artifact_id: str) -> ExecutionContext:
    return ExecutionContext(
        evaluation_case_id=CASE_ID,
        dataset_id=DATASET_ID,
        workflow_run_id="RUN-FINAL-RISK",
        input_artifact_ids=(package_artifact_id,),
        requested_scope=(EvaluationScope.RISK,),
        current_node="FINAL_RISK_CHECK",
    )


def _risk(
    *,
    assessment_status: RiskAssessmentStatus,
    risk_level: RiskLevel,
    severity: RiskSeverity,
    limitations: tuple[RiskEvidenceLimitation, ...] = (),
    confirmations: tuple[HumanConfirmationPoint, ...] = (),
) -> InitialRiskAssessment:
    return InitialRiskAssessment(
        evaluation_case_id=CASE_ID,
        dataset_id=DATASET_ID,
        contract_id=CONTRACT_ID,
        assessment_status=assessment_status,
        overall_risk_level=risk_level,
        triggered_rule_ids=("RR-FINAL",),
        findings=(
            RiskFinding(
                finding_id="RFN-FINAL",
                code="RULE_TRIGGERED",
                title="Explicit final-risk fixture",
                detail="An evidence-backed case risk remains open.",
                severity=severity,
                source_rule_id="RR-FINAL",
                evidence_ids=("EVD-FINAL-RISK",),
            ),
        ),
        source_alerts=(),
        global_context_signals=(),
        human_confirmation_points=confirmations,
        limitations=limitations,
        finance_facts_artifact_id="ART-FINANCE_FACTS",
        operations_facts_artifact_id="ART-OPERATIONS_FACTS",
    )


def test_complete_final_risk_is_stable_and_has_no_decision_side_effects() -> None:
    async def scenario() -> None:
        repository, package = await _package_artifact()
        component = FinalRiskCheck(
            context_loader=FinalRiskContextLoader(artifacts=repository)
        )
        context = _execution_context(package.artifact_id)

        first = await component.execute(context)
        second = await component.execute(context)

        assert first.status is ComponentStatus.COMPLETED
        assert first.assessment is not None
        assert second.assessment == first.assessment
        assert first.assessment.assessment_status is FinalRiskAssessmentStatus.COMPLETE
        assert first.assessment.initial_risk_level is RiskLevel.NO_CASE_SIGNAL
        assert first.assessment.residual_risk_level is RiskLevel.NO_CASE_SIGNAL
        assert first.assessment.conclusion is FinalRiskConclusion.SAFE
        assert first.assessment.major_exception_status is (
            MajorExceptionStatus.NOT_DETECTED
        )
        assert first.assessment.unresolved_approval_gate_ids == ()
        assert first.assessment.recommendation_performed is False
        assert first.assessment.approval_requested is False
        assert first.assessment.external_action_performed is False
        assert first.approval_signals == ()
        assert first.action_commands == ()
        assert len(first.artifacts) == 1
        assert first.artifacts[0].artifact_type is ArtifactType.FINAL_RISK_ASSESSMENT
        assert first.artifacts[0].payload == first.assessment.model_dump(mode="json")

        legacy_payload = first.assessment.model_dump(
            mode="python", exclude={"conclusion"}
        )
        restored = FinalRiskAssessment.model_validate(legacy_payload)
        assert restored.conclusion is FinalRiskConclusion.SAFE

    asyncio.run(scenario())


def test_critical_explicit_finding_emits_major_exception_but_no_approval() -> None:
    async def scenario() -> None:
        risk = _risk(
            assessment_status=RiskAssessmentStatus.COMPLETE,
            risk_level=RiskLevel.CRITICAL,
            severity=RiskSeverity.CRITICAL,
        )
        repository, package = await _package_artifact(risk=risk)
        component = FinalRiskCheck(
            context_loader=FinalRiskContextLoader(artifacts=repository)
        )

        result = await component.execute(_execution_context(package.artifact_id))

        assert result.status is ComponentStatus.COMPLETED_WITH_WARNINGS
        assert result.assessment is not None
        assert result.assessment.residual_risk_level is RiskLevel.CRITICAL
        assert result.assessment.conclusion is (
            FinalRiskConclusion.ATTENTION_REQUIRED
        )
        assert result.assessment.major_exception_status is MajorExceptionStatus.DETECTED
        assert result.assessment.major_exception_signal is not None
        assert result.assessment.major_exception_signal.evidence_ids == (
            "EVD-FINAL-RISK",
        )
        legacy_payload = result.assessment.model_dump(
            mode="python", exclude={"conclusion"}
        )
        restored = FinalRiskAssessment.model_validate(legacy_payload)
        assert restored.conclusion is FinalRiskConclusion.ATTENTION_REQUIRED
        assert result.warnings == ("MAJOR_EXCEPTION_DETECTED",)
        assert result.approval_signals == ()
        assert result.action_commands == ()

    asyncio.run(scenario())


def test_critical_finding_without_lineage_fails_safe_instead_of_claiming_exception() -> None:
    async def scenario() -> None:
        risk = _risk(
            assessment_status=RiskAssessmentStatus.COMPLETE,
            risk_level=RiskLevel.CRITICAL,
            severity=RiskSeverity.CRITICAL,
        )
        finding = risk.findings[0].model_copy(update={"evidence_ids": ()})
        risk = risk.model_copy(update={"findings": (finding,)})
        repository, package = await _package_artifact(risk=risk)
        component = FinalRiskCheck(
            context_loader=FinalRiskContextLoader(artifacts=repository)
        )

        result = await component.execute(_execution_context(package.artifact_id))

        assert result.status is ComponentStatus.FAILED_SAFE
        assert result.assessment is None
        assert result.artifacts == ()
        assert result.approval_signals == ()
        assert result.action_commands == ()

    asyncio.run(scenario())


def test_limited_risk_preserves_controls_and_dormant_checkpoint_is_not_gate() -> None:
    async def scenario() -> None:
        limitation = RiskEvidenceLimitation(
            limitation_id="RLM-FINAL",
            code="RULE_NOT_EVALUABLE",
            detail="A source rule lacks an exact final fact.",
            scope=RiskScope.CASE_SPECIFIC,
            rule_id="RR-LIMITED",
            evidence_ids=("EVD-FINAL-RISK",),
        )
        confirmation = HumanConfirmationPoint(
            confirmation_id="HCP-FINAL",
            reason_code="SOURCE_ALERT_REVIEW",
            question="Founder must confirm the explicit source alert context.",
            severity=RiskSeverity.HIGH,
            evidence_ids=("EVD-FINAL-RISK",),
        )
        risk = _risk(
            assessment_status=RiskAssessmentStatus.LIMITED_BY_EVIDENCE,
            risk_level=RiskLevel.HIGH,
            severity=RiskSeverity.HIGH,
            limitations=(limitation,),
            confirmations=(confirmation,),
        )
        checkpoints = ApprovalCheckpointSet(
            evaluation_case_id=CASE_ID,
            dataset_id=DATASET_ID,
            contract_id=CONTRACT_ID,
            checkpoints=(
                ApprovalCheckpoint(
                    checkpoint_id="CHK-FINAL",
                    evaluation_case_id=CASE_ID,
                    source_rule_id="RR-GATE",
                    approval_type="HUMAN_APPROVAL",
                    trigger_event=ApprovalTriggerEvent.LARGE_FINANCIAL_DECISION_REQUESTED,
                    protected_action=ProtectedAction.COMMIT_LARGE_FINANCIAL_DECISION,
                    condition={
                        "source_field": "requested_amount",
                        "operator": RuleOperator.GREATER_THAN_OR_EQUAL,
                        "threshold": 300_000_000,
                    },
                    evidence_ids=("EVD-FINAL-RISK",),
                ),
            ),
        )
        repository, package = await _package_artifact(
            risk=risk,
            checkpoints=checkpoints,
        )
        component = FinalRiskCheck(
            context_loader=FinalRiskContextLoader(artifacts=repository)
        )

        result = await component.execute(_execution_context(package.artifact_id))

        assert result.assessment is not None
        assessment = result.assessment
        assert assessment.assessment_status is (
            FinalRiskAssessmentStatus.LIMITED_BY_EVIDENCE
        )
        assert assessment.residual_risk_level is RiskLevel.HIGH
        assert assessment.conclusion is FinalRiskConclusion.ATTENTION_REQUIRED
        assert assessment.major_exception_status is MajorExceptionStatus.NOT_EVALUABLE
        assert assessment.unresolved_approval_gates == ()
        assert {item.code for item in assessment.required_controls} == {
            FinalRiskControlCode.HUMAN_CONFIRMATION_REQUIRED,
            FinalRiskControlCode.EVIDENCE_LIMITATION_MUST_BE_PRESERVED,
            FinalRiskControlCode.GOVERNANCE_EVALUATION_BEFORE_PROTECTED_ACTION,
        }
        assert result.warnings == ("FINAL_RISK_LIMITED_BY_EVIDENCE",)

    asyncio.run(scenario())


def test_invalid_or_unvalidated_package_fails_safe_without_artifact() -> None:
    async def scenario() -> None:
        _, package = await _package_artifact()
        repository = InMemoryArtifactRepository()
        await repository.save(
            package.model_copy(update={"validation_status": ValidationStatus.BLOCKED})
        )
        component = FinalRiskCheck(
            context_loader=FinalRiskContextLoader(artifacts=repository)
        )

        result = await component.execute(_execution_context(package.artifact_id))

        assert result.status is ComponentStatus.FAILED_SAFE
        assert result.assessment is None
        assert result.artifacts == ()
        assert result.approval_signals == ()
        assert result.action_commands == ()

    asyncio.run(scenario())
