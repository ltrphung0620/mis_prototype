"""Workflow-owned validation and persistence for Banking amount input."""

from opc_mis.business.skills.banking.input_component import (
    BankingAmountInputIntake,
)
from opc_mis.domain.artifacts import ArtifactDraft, ArtifactEnvelope
from opc_mis.domain.banking_input_models import BankingInputExecutionResult
from opc_mis.domain.banking_models import BankingInputSupplement
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import (
    ArtifactType,
    ComponentStatus,
    ValidationStatus,
    WorkflowStatus,
)
from opc_mis.domain.validation_reports import ValidationReport
from opc_mis.domain.workflow import WorkflowNode
from opc_mis.governance.evidence_validator import EvidenceValidator
from opc_mis.ports.artifact_repository import ArtifactRepository
from opc_mis.workflow.artifact_factory import ArtifactFactory


class BankingInputOrchestrator:
    """Validate before persisting one immutable supplement version."""

    def __init__(
        self,
        *,
        intake: BankingAmountInputIntake,
        artifacts: ArtifactRepository,
        evidence_validator: EvidenceValidator | None = None,
        artifact_factory: ArtifactFactory | None = None,
    ) -> None:
        self._intake = intake
        self._artifacts = artifacts
        self._validator = evidence_validator or EvidenceValidator()
        self._artifact_factory = artifact_factory or ArtifactFactory()

    async def run(self, context: ExecutionContext) -> BankingInputExecutionResult:
        """Execute intake, validate its draft, then persist or reuse current payload."""
        result = await self._intake.execute(context)
        runtime_events = tuple(
            item.model_dump(mode="json") for item in result.runtime_events
        )
        if result.status is ComponentStatus.FAILED_SAFE:
            return BankingInputExecutionResult(
                status=WorkflowStatus.FAILED_SAFE,
                component_status=result.status,
                current_node=WorkflowNode.BANKING_INPUT_SUPPLEMENT.value,
                validation_errors=tuple(
                    item.message for item in result.runtime_events
                ),
                warnings=result.warnings,
                runtime_events=runtime_events,
            )
        contract_errors = self._contract_errors(result)
        if contract_errors:
            return self._failed(contract_errors, result.warnings, runtime_events)

        supplement = result.supplement
        draft = result.artifacts[0]
        if supplement is None:  # pragma: no cover - guarded by contract validation
            return self._failed(
                ("Banking input intake returned no supplement.",),
                result.warnings,
                runtime_events,
            )
        report = await self._validator.validate(draft)
        if report.status is ValidationStatus.BLOCKED:
            return self._failed(
                report.blocking_errors,
                result.warnings,
                runtime_events,
                reports=(report,),
                supplement=supplement,
            )
        envelope, persistence_error = await self._persist_or_reuse(
            draft=draft,
            context=context,
            report=report,
        )
        if envelope is None:
            return self._failed(
                (persistence_error or "Banking supplement persistence failed safe.",),
                result.warnings,
                runtime_events,
                reports=(report,),
                supplement=supplement,
            )
        persisted = BankingInputSupplement.model_validate(envelope.payload)
        return BankingInputExecutionResult(
            status=WorkflowStatus.COMPLETED,
            component_status=result.status,
            current_node=WorkflowNode.BANKING_INPUT_SUPPLEMENT.value,
            supplement=persisted,
            generated_artifacts=(envelope,),
            validation_reports=(report,),
            warnings=result.warnings,
            runtime_events=runtime_events,
        )

    @staticmethod
    def _contract_errors(result: object) -> tuple[str, ...]:
        supplement = getattr(result, "supplement", None)
        artifacts = getattr(result, "artifacts", ())
        if supplement is None:
            return ("Banking input intake must return a typed supplement.",)
        if len(artifacts) != 1 or (
            artifacts[0].artifact_type is not ArtifactType.BANKING_INPUT_SUPPLEMENT
        ):
            return (
                "Banking input intake must return exactly one supplement draft.",
            )
        if artifacts[0].payload != supplement.model_dump(mode="json"):
            return ("Banking input supplement and artifact draft disagree.",)
        if getattr(result, "approval_signals", ()) or getattr(
            result, "action_commands", ()
        ):
            return (
                "Banking input intake cannot emit approvals or action commands.",
            )
        return ()

    async def _persist_or_reuse(
        self,
        *,
        draft: ArtifactDraft,
        context: ExecutionContext,
        report: ValidationReport,
    ) -> tuple[ArtifactEnvelope | None, str | None]:
        existing = await self._artifacts.list_by_case(draft.evaluation_case_id)
        current = self._latest(existing, ArtifactType.BANKING_INPUT_SUPPLEMENT)
        if current is not None and current.payload == draft.payload:
            return current, None
        if current is not None and current.artifact_id not in context.input_artifact_ids:
            return (
                None,
                "A changed Banking supplement must include the current supplement "
                "as explicit revision lineage.",
            )
        if current is None and any(
            item.artifact_type is ArtifactType.BANKING_INPUT_SUPPLEMENT
            for item in existing
        ):  # pragma: no cover - max() invariant
            return None, "Current Banking supplement could not be resolved."
        version = 1 if current is None else current.version + 1
        envelope = self._artifact_factory.create(
            draft=draft,
            context=context,
            validation_report=report,
            version=version,
        )
        await self._artifacts.save(envelope)
        return envelope, None

    @staticmethod
    def _latest(
        artifacts: tuple[ArtifactEnvelope, ...], artifact_type: ArtifactType
    ) -> ArtifactEnvelope | None:
        return max(
            (item for item in artifacts if item.artifact_type is artifact_type),
            key=lambda item: item.version,
            default=None,
        )

    @staticmethod
    def _failed(
        errors: tuple[str, ...],
        warnings: tuple[str, ...],
        runtime_events: tuple[dict[str, object], ...],
        *,
        reports: tuple[ValidationReport, ...] = (),
        supplement: BankingInputSupplement | None = None,
    ) -> BankingInputExecutionResult:
        return BankingInputExecutionResult(
            status=WorkflowStatus.FAILED_SAFE,
            component_status=ComponentStatus.FAILED_SAFE,
            current_node=WorkflowNode.BANKING_INPUT_SUPPLEMENT.value,
            supplement=supplement,
            validation_reports=reports,
            validation_errors=errors,
            warnings=warnings,
            runtime_events=runtime_events,
        )
