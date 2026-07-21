"""Deterministic Final Risk Check over one Internal Decision Package."""

from pydantic import ValidationError

from opc_mis.business.agents.risk.final_context_loader import (
    FinalRiskContextError,
    FinalRiskContextLoader,
)
from opc_mis.domain.artifacts import ArtifactDraft
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import (
    ArtifactType,
    ComponentStatus,
    FinalRiskAssessmentStatus,
    MajorExceptionStatus,
)
from opc_mis.domain.events import RuntimeEvent
from opc_mis.domain.final_risk_models import (
    FinalRiskAssessment,
    FinalRiskComponentResult,
)
from opc_mis.domain.final_risk_policy import build_final_risk_assessment


class FinalRiskCheck:
    """Preserve residual risk and controls without making a Decision."""

    component_id = "FINAL_RISK_CHECK"

    def __init__(self, *, context_loader: FinalRiskContextLoader) -> None:
        self._context_loader = context_loader

    async def execute(self, context: ExecutionContext) -> FinalRiskComponentResult:
        try:
            final_context = await self._context_loader.load(context)
            assessment = build_final_risk_assessment(
                package_artifact=final_context.package_artifact,
                package=final_context.package,
            )
        except (FinalRiskContextError, ValidationError, ValueError) as exc:
            return self._failed_safe(str(exc))

        warnings = self._warnings(assessment)
        status = (
            ComponentStatus.COMPLETED_WITH_WARNINGS
            if warnings
            else ComponentStatus.COMPLETED
        )
        artifact = final_context.package_artifact
        draft = ArtifactDraft(
            artifact_type=ArtifactType.FINAL_RISK_ASSESSMENT,
            evaluation_case_id=assessment.evaluation_case_id,
            producer=self.component_id,
            payload=assessment.model_dump(mode="json"),
            evidence_refs=artifact.evidence_refs,
            identity_inputs={
                "internal_decision_package_artifact_id": artifact.artifact_id,
                "internal_decision_package_artifact_version": artifact.version,
                "internal_decision_package_input_hash": artifact.input_hash,
                "internal_decision_package_id": final_context.package.package_id,
            },
        )
        return FinalRiskComponentResult(
            status=status,
            assessment=assessment,
            artifacts=(draft,),
            warnings=warnings,
            runtime_events=(
                RuntimeEvent(
                    event_type="FINAL_RISK_CHECK_COMPLETED",
                    message=(
                        "Final Risk preserved explicit residual findings, approval-gate "
                        "state, and required controls without making a recommendation."
                    ),
                    metadata={
                        "assessment_id": assessment.assessment_id,
                        "residual_risk_level": assessment.residual_risk_level.value,
                        "conclusion": assessment.conclusion.value,
                        "major_exception_status": (
                            assessment.major_exception_status.value
                        ),
                        "unresolved_approval_gate_count": len(
                            assessment.unresolved_approval_gates
                        ),
                        "required_control_count": len(
                            assessment.required_controls
                        ),
                    },
                ),
            ),
        )

    @staticmethod
    def _warnings(assessment: FinalRiskAssessment) -> tuple[str, ...]:
        warnings: list[str] = []
        if assessment.assessment_status is (
            FinalRiskAssessmentStatus.LIMITED_BY_EVIDENCE
        ):
            warnings.append("FINAL_RISK_LIMITED_BY_EVIDENCE")
        if assessment.major_exception_status is MajorExceptionStatus.DETECTED:
            warnings.append("MAJOR_EXCEPTION_DETECTED")
        return tuple(warnings)

    @staticmethod
    def _failed_safe(message: str) -> FinalRiskComponentResult:
        return FinalRiskComponentResult(
            status=ComponentStatus.FAILED_SAFE,
            runtime_events=(
                RuntimeEvent(
                    event_type="FINAL_RISK_CHECK_FAILED_SAFE",
                    message=message,
                ),
            ),
        )
