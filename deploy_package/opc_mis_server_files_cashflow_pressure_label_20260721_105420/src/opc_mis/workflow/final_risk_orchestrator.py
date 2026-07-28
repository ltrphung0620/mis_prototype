"""Validate and persist the deterministic Final Risk Check output."""

from pydantic import ValidationError

from opc_mis.business.agents.risk.final_component import FinalRiskCheck
from opc_mis.domain.artifacts import ArtifactDraft, ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import (
    ArtifactType,
    ComponentStatus,
    ValidationStatus,
    WorkflowStatus,
)
from opc_mis.domain.final_risk_models import (
    FinalRiskAssessment,
    FinalRiskExecutionResult,
)
from opc_mis.domain.final_risk_policy import build_final_risk_assessment
from opc_mis.domain.internal_decision_package_models import InternalDecisionPackage
from opc_mis.domain.validation_reports import ValidationReport
from opc_mis.domain.workflow import WorkflowNode
from opc_mis.governance.evidence_validator import EvidenceValidator
from opc_mis.ports.artifact_repository import ArtifactRepository
from opc_mis.workflow.artifact_factory import ArtifactFactory, artifact_input_hash


class FinalRiskPersistenceError(RuntimeError):
    """Raised when a persisted Final Risk artifact cannot be safely reused."""


class FinalRiskOrchestrator:
    """Own Final Risk validation, persistence, versioning, and idempotency."""

    def __init__(
        self,
        *,
        final_risk: FinalRiskCheck,
        artifacts: ArtifactRepository,
        evidence_validator: EvidenceValidator | None = None,
        artifact_factory: ArtifactFactory | None = None,
    ) -> None:
        self._final_risk = final_risk
        self._artifacts = artifacts
        self._validator = evidence_validator or EvidenceValidator()
        self._artifact_factory = artifact_factory or ArtifactFactory()

    async def run(self, context: ExecutionContext) -> FinalRiskExecutionResult:
        """Execute Final Risk, validate its one draft, then persist or reuse it."""
        result = await self._final_risk.execute(context)
        events = tuple(item.model_dump(mode="json") for item in result.runtime_events)
        if result.status is ComponentStatus.FAILED_SAFE:
            return self._failed(
                tuple(item.message for item in result.runtime_events)
                or ("Final Risk Check failed safely.",),
                result.warnings,
                events,
            )

        errors = self._contract_errors(result, context)
        if errors:
            return self._failed(errors, result.warnings, events)

        assessment = result.assessment
        draft = result.artifacts[0]
        if assessment is None:  # pragma: no cover - guarded by contract validation
            return self._failed(
                ("Final Risk Check returned no typed assessment.",),
                result.warnings,
                events,
            )
        source_errors = await self._source_errors(
            assessment=assessment,
            draft=draft,
            context=context,
        )
        if source_errors:
            return self._failed(source_errors, result.warnings, events)
        report = await self._validator.validate(draft)
        if report.status is ValidationStatus.BLOCKED:
            return self._failed(
                report.blocking_errors,
                result.warnings,
                events,
                reports=(report,),
                assessment=assessment,
            )
        try:
            envelope = await self._persist_or_reuse(draft, context, report)
        except FinalRiskPersistenceError as exc:
            return self._failed(
                (str(exc),),
                result.warnings,
                events,
                reports=(report,),
                assessment=assessment,
            )

        persisted = FinalRiskAssessment.model_validate(envelope.payload)
        return FinalRiskExecutionResult(
            status=WorkflowStatus.COMPLETED,
            component_status=result.status,
            current_node=WorkflowNode.FINAL_RISK_CHECK.value,
            assessment=persisted,
            generated_artifacts=(envelope,),
            validation_reports=(report,),
            warnings=result.warnings,
            runtime_events=events,
        )

    @staticmethod
    def _contract_errors(
        result: object, context: ExecutionContext
    ) -> tuple[str, ...]:
        """Enforce the component boundary before validating any artifact draft."""
        assessment = getattr(result, "assessment", None)
        drafts = tuple(getattr(result, "artifacts", ()))
        if getattr(result, "status", None) not in {
            ComponentStatus.COMPLETED,
            ComponentStatus.COMPLETED_WITH_WARNINGS,
        }:
            return ("Final Risk Check must complete or fail safely; it cannot pause.",)
        if len(context.input_artifact_ids) != 1:
            return (
                "Final Risk Check requires exactly one Internal Decision Package input.",
            )
        if not isinstance(assessment, FinalRiskAssessment):
            return ("Final Risk Check must return one typed assessment.",)
        if len(drafts) != 1 or (
            drafts[0].artifact_type is not ArtifactType.FINAL_RISK_ASSESSMENT
        ):
            return ("Final Risk Check must return exactly one assessment draft.",)
        if drafts[0].payload != assessment.model_dump(mode="json"):
            return ("Final Risk assessment and artifact draft disagree.",)
        if drafts[0].evaluation_case_id != context.evaluation_case_id:
            return ("Final Risk assessment belongs to another evaluation case.",)
        if assessment.evaluation_case_id != context.evaluation_case_id:
            return ("Final Risk payload belongs to another evaluation case.",)
        if assessment.dataset_id != context.dataset_id:
            return ("Final Risk payload belongs to another dataset.",)
        if (
            assessment.internal_decision_package_artifact_id
            != context.input_artifact_ids[0]
        ):
            return (
                "Final Risk payload references another Internal Decision Package.",
            )
        if getattr(result, "missing_data_requests", ()):
            return (
                "Final Risk Check cannot create a late user-input pause from a ready package.",
            )
        if getattr(result, "approval_signals", ()) or getattr(
            result, "action_commands", ()
        ):
            return (
                "Final Risk Check cannot activate approval or protected actions.",
            )
        return ()

    async def _source_errors(
        self,
        *,
        assessment: FinalRiskAssessment,
        draft: ArtifactDraft,
        context: ExecutionContext,
    ) -> tuple[str, ...]:
        """Bind every derived field to the exact validated package snapshot."""
        source = await self._artifacts.get(context.input_artifact_ids[0])
        if (
            source is None
            or source.artifact_type is not ArtifactType.INTERNAL_DECISION_PACKAGE
            or source.evaluation_case_id != context.evaluation_case_id
        ):
            return ("Final Risk source Internal Decision Package is unavailable.",)
        if source.validation_status not in {
            ValidationStatus.VALID,
            ValidationStatus.VALID_WITH_WARNINGS,
        }:
            return ("Final Risk source Internal Decision Package is not validated.",)
        try:
            package = InternalDecisionPackage.model_validate(source.payload)
            expected_assessment = build_final_risk_assessment(
                package_artifact=source,
                package=package,
            )
        except (ValidationError, ValueError) as exc:
            return (f"Final Risk source package cannot be evaluated: {exc}",)

        expected_identity = {
            "internal_decision_package_artifact_id": source.artifact_id,
            "internal_decision_package_artifact_version": source.version,
            "internal_decision_package_input_hash": source.input_hash,
            "internal_decision_package_id": package.package_id,
        }
        errors: list[str] = []
        if draft.identity_inputs != expected_identity:
            errors.append(
                "Final Risk draft identity is not bound to the exact package."
            )
        if (
            draft.evidence_refs != source.evidence_refs
            or assessment.evidence_ids
            != tuple(item.evidence_id for item in source.evidence_refs)
        ):
            errors.append(
                "Final Risk evidence differs from the exact package evidence."
            )
        if assessment != expected_assessment:
            errors.append(
                "Final Risk assessment differs from the canonical exact-package "
                "derivation."
            )
        return tuple(errors)

    async def _persist_or_reuse(
        self,
        draft: ArtifactDraft,
        context: ExecutionContext,
        report: ValidationReport,
    ) -> ArtifactEnvelope:
        existing = await self._artifacts.list_by_case(draft.evaluation_case_id)
        input_hash = artifact_input_hash(draft, context)
        matches = tuple(
            item
            for item in existing
            if item.artifact_type is draft.artifact_type
            and item.input_hash == input_hash
        )
        if len(matches) > 1:
            raise FinalRiskPersistenceError(
                "Final Risk artifact identity is ambiguous."
            )
        if matches:
            current = matches[0]
            if (
                current.validation_status
                not in {
                    ValidationStatus.VALID,
                    ValidationStatus.VALID_WITH_WARNINGS,
                }
                or current.payload != draft.payload
                or current.evidence_refs != draft.evidence_refs
                or current.input_artifact_ids != context.input_artifact_ids
            ):
                raise FinalRiskPersistenceError(
                    "Existing Final Risk artifact differs from its exact validated input."
                )
            return current

        version = 1 + max(
            (
                item.version
                for item in existing
                if item.artifact_type is draft.artifact_type
            ),
            default=0,
        )
        envelope = self._artifact_factory.create(
            draft=draft,
            context=context,
            validation_report=report,
            version=version,
        )
        await self._artifacts.save(envelope)
        return envelope

    @staticmethod
    def _failed(
        errors: tuple[str, ...],
        warnings: tuple[str, ...],
        events: tuple[dict[str, object], ...],
        *,
        reports: tuple[ValidationReport, ...] = (),
        assessment: FinalRiskAssessment | None = None,
    ) -> FinalRiskExecutionResult:
        return FinalRiskExecutionResult(
            status=WorkflowStatus.FAILED_SAFE,
            component_status=ComponentStatus.FAILED_SAFE,
            current_node=WorkflowNode.FINAL_RISK_CHECK.value,
            assessment=assessment,
            validation_reports=reports,
            validation_errors=errors,
            warnings=warnings,
            runtime_events=events,
        )
