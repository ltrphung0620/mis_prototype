"""Validation and persistence for post-precheck evidence-reference intake."""

from pydantic import ValidationError

from opc_mis.business.agents.decision.post_precheck_evidence_component import (
    BankingPrecheckEvidenceIntake,
)
from opc_mis.domain.artifacts import ArtifactDraft, ArtifactEnvelope
from opc_mis.domain.banking_precheck_evidence_models import (
    BankingPrecheckEvidenceExecutionResult,
    BankingPrecheckEvidenceSupplement,
)
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import (
    ArtifactType,
    ComponentStatus,
    SourceType,
    ValidationStatus,
    WorkflowStatus,
)
from opc_mis.domain.validation_reports import ValidationReport
from opc_mis.domain.workflow import WorkflowNode
from opc_mis.governance.evidence_validator import EvidenceValidator
from opc_mis.ports.artifact_repository import ArtifactRepository
from opc_mis.workflow.artifact_factory import ArtifactFactory


class BankingPrecheckEvidencePersistenceError(RuntimeError):
    """Raised when evidence-supplement lineage is stale or ambiguous."""


class BankingPrecheckEvidenceOrchestrator:
    """Validate before persisting one exact evidence-reference handoff."""

    def __init__(
        self,
        *,
        intake: BankingPrecheckEvidenceIntake,
        artifacts: ArtifactRepository,
        evidence_validator: EvidenceValidator | None = None,
        artifact_factory: ArtifactFactory | None = None,
    ) -> None:
        self._intake = intake
        self._artifacts = artifacts
        self._validator = evidence_validator or EvidenceValidator()
        self._artifact_factory = artifact_factory or ArtifactFactory()

    async def run(
        self, context: ExecutionContext
    ) -> BankingPrecheckEvidenceExecutionResult:
        """Execute intake, validate its draft, then persist or reuse it."""
        result = await self._intake.execute(context)
        events = tuple(item.model_dump(mode="json") for item in result.runtime_events)
        if result.status is ComponentStatus.FAILED_SAFE:
            return self._failed(
                tuple(item.message for item in result.runtime_events),
                result.warnings,
                events,
            )
        contract_errors = self._contract_errors(result)
        if contract_errors:
            return self._failed(contract_errors, result.warnings, events)

        supplement = result.supplement
        draft = result.artifacts[0]
        if supplement is None:  # pragma: no cover - guarded above
            return self._failed(
                ("Evidence intake returned no typed supplement.",),
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
                supplement=supplement,
            )
        try:
            envelope = await self._persist_or_reuse(
                draft=draft,
                context=context,
                report=report,
                request_id=supplement.missing_request_id,
            )
        except BankingPrecheckEvidencePersistenceError as exc:
            return self._failed(
                (str(exc),),
                result.warnings,
                events,
                reports=(report,),
                supplement=supplement,
            )
        persisted = BankingPrecheckEvidenceSupplement.model_validate(envelope.payload)
        return BankingPrecheckEvidenceExecutionResult(
            status=WorkflowStatus.COMPLETED,
            component_status=result.status,
            current_node=WorkflowNode.BANKING_PRECHECK_EVIDENCE_INTAKE.value,
            supplement=persisted,
            generated_artifacts=(envelope,),
            validation_reports=(report,),
            warnings=result.warnings,
            runtime_events=events,
        )

    @staticmethod
    def _contract_errors(result: object) -> tuple[str, ...]:
        supplement = getattr(result, "supplement", None)
        artifacts = getattr(result, "artifacts", ())
        if not isinstance(supplement, BankingPrecheckEvidenceSupplement):
            return ("Evidence intake must return a typed supplement.",)
        if len(artifacts) != 1 or (
            artifacts[0].artifact_type
            is not ArtifactType.BANKING_PRECHECK_EVIDENCE_SUPPLEMENT
        ):
            return ("Evidence intake must return exactly one supplement draft.",)
        draft = artifacts[0]
        if draft.payload != supplement.model_dump(mode="json"):
            return ("Evidence supplement and artifact draft disagree.",)
        if tuple(item.evidence_id for item in draft.evidence_refs) != (
            supplement.evidence_ids
        ):
            return ("Evidence supplement index differs from its draft lineage.",)
        lineage_errors = BankingPrecheckEvidenceOrchestrator._lineage_errors(
            draft, supplement
        )
        if lineage_errors:
            return lineage_errors
        if getattr(result, "missing_data_requests", ()):
            return (
                "Evidence intake resolves only the selected input handoff and cannot "
                "raise replacement missing-data requests.",
            )
        if getattr(result, "approval_signals", ()) or getattr(
            result, "action_commands", ()
        ):
            return (
                "Evidence intake cannot approve or authorize a protected action.",
            )
        return ()

    @staticmethod
    def _lineage_errors(
        draft: ArtifactDraft,
        supplement: BankingPrecheckEvidenceSupplement,
    ) -> tuple[str, ...]:
        expected_user_values = {
            "evidence_reference_id": supplement.evidence_reference_id,
            "provided_by": supplement.provided_by,
            "evidence_note": supplement.evidence_note,
        }
        user_refs = tuple(
            item
            for item in draft.evidence_refs
            if item.source_type is SourceType.USER_INPUT
            and item.sheet == "BANKING_PRECHECK_EVIDENCE_SUPPLEMENT"
            and item.record_id == supplement.supplement_id
        )
        actual_user_values = {
            item.field: item.display_value
            for item in user_refs
        }
        if (
            actual_user_values != expected_user_values
            or len(user_refs) != len(expected_user_values)
        ):
            return (
                "Evidence supplement requires exact USER_INPUT lineage for its "
                "reference, provider, and note.",
            )
        resolution_refs = tuple(
            item
            for item in draft.evidence_refs
            if item.source_type is SourceType.DERIVED
            and item.sheet == "BANKING_PRECHECK_EVIDENCE_SUPPLEMENT"
            and item.record_id == supplement.supplement_id
            and item.field == "input_handoff_resolution"
        )
        if len(resolution_refs) != 1:
            return (
                "Evidence supplement requires one derived input-handoff record.",
            )
        resolution = resolution_refs[0]
        expected_display = {
            "missing_request_id": supplement.missing_request_id,
            "normalized_result_id": supplement.normalized_result_id,
            "option_id": supplement.option_id,
            "bank_product_id": supplement.bank_product_id,
            "required_field": supplement.required_field,
            "evidence_reference_id": supplement.evidence_reference_id,
            "input_handoff_resolved": True,
            "fresh_governed_precheck_required": True,
            "source_precheck_result_unchanged": True,
            "bank_approval_obtained": False,
        }
        user_ids = {item.evidence_id for item in user_refs}
        if resolution.display_value != expected_display or not user_ids.issubset(
            set(resolution.source_evidence_ids)
        ):
            return (
                "Derived input-handoff evidence does not match the supplement.",
            )
        non_user_source_ids = set(resolution.source_evidence_ids) - user_ids
        if not non_user_source_ids:
            return (
                "Derived input-handoff evidence must retain the source request lineage.",
            )
        return ()

    async def _persist_or_reuse(
        self,
        *,
        draft: ArtifactDraft,
        context: ExecutionContext,
        report: ValidationReport,
        request_id: str,
    ) -> ArtifactEnvelope:
        existing = await self._artifacts.list_by_case(draft.evaluation_case_id)
        current = self._current_for_request(existing, request_id)
        if current is not None and current.payload == draft.payload:
            if (
                current.validation_status not in {
                    ValidationStatus.VALID,
                    ValidationStatus.VALID_WITH_WARNINGS,
                }
                or current.evidence_refs != draft.evidence_refs
            ):
                raise BankingPrecheckEvidencePersistenceError(
                    "Existing evidence supplement differs from its validated lineage."
                )
            return current
        if current is not None and current.artifact_id not in context.input_artifact_ids:
            raise BankingPrecheckEvidencePersistenceError(
                "A changed evidence reference must include the current supplement "
                "as explicit revision lineage."
            )
        if current is None and len(context.input_artifact_ids) != 1:
            raise BankingPrecheckEvidencePersistenceError(
                "A first evidence supplement must reference only its current review."
            )
        version = 1 + max(
            (
                item.version
                for item in existing
                if item.artifact_type
                is ArtifactType.BANKING_PRECHECK_EVIDENCE_SUPPLEMENT
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
    def _current_for_request(
        artifacts: tuple[ArtifactEnvelope, ...], request_id: str
    ) -> ArtifactEnvelope | None:
        matches: list[ArtifactEnvelope] = []
        for artifact in artifacts:
            if (
                artifact.artifact_type
                is not ArtifactType.BANKING_PRECHECK_EVIDENCE_SUPPLEMENT
            ):
                continue
            try:
                supplement = BankingPrecheckEvidenceSupplement.model_validate(
                    artifact.payload
                )
            except ValidationError as exc:
                raise BankingPrecheckEvidencePersistenceError(
                    "Stored evidence supplement has an invalid schema."
                ) from exc
            if supplement.missing_request_id == request_id:
                matches.append(artifact)
        if not matches:
            return None
        highest_version = max(item.version for item in matches)
        latest = tuple(item for item in matches if item.version == highest_version)
        if len(latest) != 1:
            raise BankingPrecheckEvidencePersistenceError(
                "Current evidence supplement revision is ambiguous."
            )
        return latest[0]

    @staticmethod
    def _failed(
        errors: tuple[str, ...],
        warnings: tuple[str, ...],
        events: tuple[dict[str, object], ...],
        *,
        reports: tuple[ValidationReport, ...] = (),
        supplement: BankingPrecheckEvidenceSupplement | None = None,
    ) -> BankingPrecheckEvidenceExecutionResult:
        return BankingPrecheckEvidenceExecutionResult(
            status=WorkflowStatus.FAILED_SAFE,
            component_status=ComponentStatus.FAILED_SAFE,
            current_node=WorkflowNode.BANKING_PRECHECK_EVIDENCE_INTAKE.value,
            supplement=supplement,
            validation_reports=reports,
            validation_errors=errors,
            warnings=warnings,
            runtime_events=events,
        )
