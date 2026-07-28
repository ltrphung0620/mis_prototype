"""Validate and persist the deterministic Internal Decision Package."""

from opc_mis.business.agents.decision.internal_package_component import (
    InternalDecisionPackageAssembler,
)
from opc_mis.domain.artifacts import ArtifactDraft, ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import (
    ArtifactType,
    ComponentStatus,
    ValidationStatus,
    WorkflowStatus,
)
from opc_mis.domain.internal_decision_package_models import (
    InternalDecisionPackage,
    InternalDecisionPackageExecutionResult,
)
from opc_mis.domain.validation_reports import ValidationReport
from opc_mis.domain.workflow import WorkflowNode
from opc_mis.governance.evidence_validator import EvidenceValidator
from opc_mis.ports.artifact_repository import ArtifactRepository
from opc_mis.workflow.artifact_factory import ArtifactFactory, artifact_input_hash


class InternalDecisionPackagePersistenceError(RuntimeError):
    """Raised when an existing package cannot be safely reused."""


class InternalDecisionPackageOrchestrator:
    """Own validation, persistence, and idempotency for the internal package."""

    def __init__(
        self,
        *,
        assembler: InternalDecisionPackageAssembler,
        artifacts: ArtifactRepository,
        evidence_validator: EvidenceValidator | None = None,
        artifact_factory: ArtifactFactory | None = None,
    ) -> None:
        self._assembler = assembler
        self._artifacts = artifacts
        self._validator = evidence_validator or EvidenceValidator()
        self._artifact_factory = artifact_factory or ArtifactFactory()

    async def run(
        self, context: ExecutionContext
    ) -> InternalDecisionPackageExecutionResult:
        """Validate before persistence and return one typed package result."""
        result = await self._assembler.execute(context)
        events = tuple(item.model_dump(mode="json") for item in result.runtime_events)
        if result.status is ComponentStatus.FAILED_SAFE:
            return self._failed(
                tuple(item.message for item in result.runtime_events),
                result.warnings,
                events,
            )
        if result.status is ComponentStatus.WAITING_FOR_INPUT:
            errors = self._waiting_contract_errors(result)
            if errors:
                return self._failed(errors, result.warnings, events)
            return InternalDecisionPackageExecutionResult(
                status=WorkflowStatus.WAITING_FOR_INPUT,
                component_status=result.status,
                current_node=WorkflowNode.INTERNAL_DECISION_PACKAGE_ASSEMBLY.value,
                missing_data_requests=result.missing_data_requests,
                warnings=result.warnings,
                runtime_events=events,
            )
        errors = self._contract_errors(result, context)
        if errors:
            return self._failed(errors, result.warnings, events)

        package = result.package
        draft = result.artifacts[0]
        if package is None:  # pragma: no cover - guarded by _contract_errors
            return self._failed(
                ("Internal Decision Package returned no typed output.",),
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
            )
        try:
            envelope = await self._persist_or_reuse(draft, context, report)
        except InternalDecisionPackagePersistenceError as exc:
            return self._failed(
                (str(exc),),
                result.warnings,
                events,
                reports=(report,),
            )

        persisted = InternalDecisionPackage.model_validate(envelope.payload)
        return InternalDecisionPackageExecutionResult(
            status=WorkflowStatus.COMPLETED,
            component_status=result.status,
            current_node=WorkflowNode.INTERNAL_DECISION_PACKAGE_ASSEMBLY.value,
            package=persisted,
            generated_artifacts=(envelope,),
            validation_reports=(report,),
            missing_data_requests=persisted.missing_data_requests,
            warnings=result.warnings,
            runtime_events=events,
        )

    @staticmethod
    def _waiting_contract_errors(result: object) -> tuple[str, ...]:
        """Require an explicit non-persisting wait contract for missing inputs."""
        if getattr(result, "package", None) is not None or getattr(
            result, "artifacts", ()
        ):
            return (
                "A waiting Internal Decision Package cannot emit a package draft.",
            )
        if not getattr(result, "missing_data_requests", ()):
            return (
                "A waiting Internal Decision Package requires a MissingDataRequest.",
            )
        if getattr(result, "approval_signals", ()) or getattr(
            result, "action_commands", ()
        ):
            return (
                "Internal Decision Package cannot approve or execute external actions.",
            )
        return ()

    @staticmethod
    def _contract_errors(
        result: object, context: ExecutionContext
    ) -> tuple[str, ...]:
        package = getattr(result, "package", None)
        drafts = tuple(getattr(result, "artifacts", ()))
        if not isinstance(package, InternalDecisionPackage):
            return ("Internal Decision Package must return one typed package.",)
        if len(drafts) != 1 or (
            drafts[0].artifact_type is not ArtifactType.INTERNAL_DECISION_PACKAGE
        ):
            return (
                "Internal Decision Package must return exactly one package draft.",
            )
        if drafts[0].payload != package.model_dump(mode="json"):
            return ("Internal Decision Package and artifact draft disagree.",)
        if package.source_artifact_ids != context.input_artifact_ids:
            return (
                "Internal Decision Package lineage differs from exact execution inputs.",
            )
        missing = tuple(getattr(result, "missing_data_requests", ()))
        if missing != package.missing_data_requests:
            return (
                "Internal Decision Package result and missing requests disagree.",
            )
        if missing:
            return (
                "A completed Internal Decision Package cannot contain missing requests.",
            )
        if getattr(result, "approval_signals", ()) or getattr(
            result, "action_commands", ()
        ):
            return (
                "Internal Decision Package cannot approve or execute external actions.",
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
        matches = tuple(
            item
            for item in existing
            if item.artifact_type is draft.artifact_type
            and item.input_hash == input_hash
        )
        if len(matches) > 1:
            raise InternalDecisionPackagePersistenceError(
                "Internal Decision Package artifact identity is ambiguous."
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
                raise InternalDecisionPackagePersistenceError(
                    "Existing Internal Decision Package differs from its exact "
                    "validated inputs."
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
    ) -> InternalDecisionPackageExecutionResult:
        return InternalDecisionPackageExecutionResult(
            status=WorkflowStatus.FAILED_SAFE,
            component_status=ComponentStatus.FAILED_SAFE,
            current_node=WorkflowNode.INTERNAL_DECISION_PACKAGE_ASSEMBLY.value,
            validation_reports=reports,
            validation_errors=errors,
            warnings=warnings,
            runtime_events=events,
        )
