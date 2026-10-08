"""Workflow-owned validation and persistence for Banking precheck readiness."""

from opc_mis.business.skills.banking.precheck_readiness_component import (
    BankingPrecheckReadinessSkill,
)
from opc_mis.domain.artifacts import ArtifactDraft, ArtifactEnvelope
from opc_mis.domain.banking_models import (
    BankingCatalogPolicy,
    BankingPrecheckReadiness,
    BankingPrecheckReadinessExecutionResult,
)
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
from opc_mis.workflow.artifact_factory import ArtifactFactory, artifact_input_hash


class BankingPrecheckReadinessOrchestrator:
    """Validate and persist readiness without invoking an external precheck."""

    def __init__(
        self,
        *,
        readiness: BankingPrecheckReadinessSkill,
        artifacts: ArtifactRepository,
        policy: BankingCatalogPolicy,
        artifact_factory: ArtifactFactory | None = None,
    ) -> None:
        self._readiness = readiness
        self._artifacts = artifacts
        self._validator = EvidenceValidator(banking_policy=policy)
        self._artifact_factory = artifact_factory or ArtifactFactory()

    async def run(
        self, context: ExecutionContext
    ) -> BankingPrecheckReadinessExecutionResult:
        """Run deterministic readiness and persist exactly one validated draft."""
        result = await self._readiness.execute(context)
        events = tuple(item.model_dump(mode="json") for item in result.runtime_events)
        if result.status is ComponentStatus.FAILED_SAFE:
            return self._failed(
                tuple(item.message for item in result.runtime_events),
                result.warnings,
                events,
            )
        errors = self._contract_errors(result)
        if errors:
            return self._failed(errors, result.warnings, events)
        readiness = result.readiness
        draft = result.artifacts[0]
        if readiness is None:  # pragma: no cover - guarded by contract validation
            return self._failed(
                ("Banking readiness returned no typed assessment.",),
                result.warnings,
                events,
            )
        report = await self._validator.validate(draft)
        if report.status is ValidationStatus.BLOCKED:
            return self._failed(
                report.blocking_errors,
                result.warnings,
                events,
                reports=(report,),
                readiness=readiness,
            )
        envelope = await self._persist_or_reuse(draft, context, report)
        persisted = BankingPrecheckReadiness.model_validate(envelope.payload)
        return BankingPrecheckReadinessExecutionResult(
            status=WorkflowStatus.COMPLETED,
            component_status=result.status,
            current_node=WorkflowNode.BANKING_PRECHECK_READINESS.value,
            readiness=persisted,
            generated_artifacts=(envelope,),
            validation_reports=(report,),
            warnings=result.warnings,
            runtime_events=events,
        )

    @staticmethod
    def _contract_errors(result: object) -> tuple[str, ...]:
        readiness = getattr(result, "readiness", None)
        artifacts = getattr(result, "artifacts", ())
        if readiness is None:
            return ("Banking readiness must return a typed assessment.",)
        if len(artifacts) != 1 or (
            artifacts[0].artifact_type is not ArtifactType.BANKING_PRECHECK_READINESS
        ):
            return ("Banking readiness must return exactly one readiness draft.",)
        if artifacts[0].payload != readiness.model_dump(mode="json"):
            return ("Banking readiness object and artifact draft disagree.",)
        if getattr(result, "approval_signals", ()) or getattr(
            result, "action_commands", ()
        ):
            return ("Banking readiness cannot emit approvals or action commands.",)
        if getattr(result, "missing_data_requests", ()):
            return (
                "Banking readiness cannot pause; Decision owns missing-data requests.",
            )
        return ()

    async def _persist_or_reuse(
        self,
        draft: ArtifactDraft,
        context: ExecutionContext,
        report: ValidationReport,
    ) -> ArtifactEnvelope:
        existing = await self._artifacts.list_by_case(draft.evaluation_case_id)
        input_hash = artifact_input_hash(draft, context)
        current = next(
            (
                item
                for item in existing
                if item.artifact_type is draft.artifact_type
                and item.input_hash == input_hash
            ),
            None,
        )
        if current is not None:
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
        readiness: BankingPrecheckReadiness | None = None,
    ) -> BankingPrecheckReadinessExecutionResult:
        return BankingPrecheckReadinessExecutionResult(
            status=WorkflowStatus.FAILED_SAFE,
            component_status=ComponentStatus.FAILED_SAFE,
            current_node=WorkflowNode.BANKING_PRECHECK_READINESS.value,
            readiness=readiness,
            validation_reports=reports,
            validation_errors=errors,
            warnings=warnings,
            runtime_events=events,
        )
