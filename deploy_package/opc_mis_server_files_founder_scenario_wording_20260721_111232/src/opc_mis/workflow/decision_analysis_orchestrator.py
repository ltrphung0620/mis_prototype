"""Validate and persist AI-assisted Decision analysis and Decision Cards."""

from __future__ import annotations

from opc_mis.business.agents.decision.analysis_component import DecisionAnalysisAgent
from opc_mis.business.agents.decision.card_component import DecisionCardAssembler
from opc_mis.domain.artifacts import ArtifactDraft, ArtifactEnvelope
from opc_mis.domain.components import ComponentResult, ExecutionContext
from opc_mis.domain.decision_models import (
    AIDecisionAnalysis,
    DecisionAnalysisExecutionResult,
    DecisionCard,
    DecisionCardExecutionResult,
)
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


class DecisionPersistenceError(RuntimeError):
    """Raised when a Decision artifact cannot be safely persisted or reused."""


class DecisionAnalysisOrchestrator:
    """Own validation, identity, versioning, and persistence around Decision."""

    def __init__(
        self,
        *,
        analysis_agent: DecisionAnalysisAgent,
        card_assembler: DecisionCardAssembler,
        artifacts: ArtifactRepository,
        evidence_validator: EvidenceValidator | None = None,
        artifact_factory: ArtifactFactory | None = None,
    ) -> None:
        self._analysis_agent = analysis_agent
        self._card_assembler = card_assembler
        self._artifacts = artifacts
        self._validator = evidence_validator or EvidenceValidator()
        self._artifact_factory = artifact_factory or ArtifactFactory()

    async def run_analysis(
        self, context: ExecutionContext
    ) -> DecisionAnalysisExecutionResult:
        """Persist exactly one guarded AI Decision Analysis artifact."""
        result = await self._analysis_agent.execute(context)
        events = self._events(result)
        errors = self._common_errors(
            result=result,
            context=context,
            artifact_type=ArtifactType.AI_DECISION_ANALYSIS,
            typed_value=result.analysis,
        )
        if (
            result.analysis is not None
            and context.input_artifact_ids
            and result.analysis.final_risk_artifact.artifact_id
            != context.input_artifact_ids[0]
        ):
            errors = (*errors, "AI Decision Analysis binds another Final Risk.")
        if (
            result.scenario_packet is None
            or result.analysis is None
            or not result.artifacts
        ):
            return DecisionAnalysisExecutionResult(
                status=WorkflowStatus.FAILED_SAFE,
                component_status=ComponentStatus.FAILED_SAFE,
                current_node=WorkflowNode.DECISION_CARD_COMPOSITION.value,
                scenario_packet=result.scenario_packet,
                analysis=result.analysis,
                validation_errors=errors or ("Decision analysis failed safely.",),
                warnings=result.warnings,
                runtime_events=events,
            )
        packet = result.scenario_packet
        if (
            packet.final_risk_artifact != result.analysis.final_risk_artifact
            or packet.internal_decision_package_artifact
            != result.analysis.internal_decision_package_artifact
            or packet.packet_id != result.analysis.packet_id
            or tuple(
                item.evidence_id for item in result.artifacts[0].evidence_refs
            )
            != packet.known_evidence_ids
        ):
            errors = (*errors, "Decision analysis differs from its canonical packet.")
        if errors:
            return DecisionAnalysisExecutionResult(
                status=WorkflowStatus.FAILED_SAFE,
                component_status=ComponentStatus.FAILED_SAFE,
                current_node=WorkflowNode.DECISION_CARD_COMPOSITION.value,
                scenario_packet=packet,
                analysis=result.analysis,
                validation_errors=errors,
                warnings=result.warnings,
                runtime_events=events,
            )
        report, envelope, failure = await self._validate_and_persist(
            result.artifacts[0], context
        )
        if failure is not None or envelope is None:
            return DecisionAnalysisExecutionResult(
                status=WorkflowStatus.FAILED_SAFE,
                component_status=ComponentStatus.FAILED_SAFE,
                current_node=WorkflowNode.DECISION_CARD_COMPOSITION.value,
                scenario_packet=packet,
                analysis=result.analysis,
                validation_reports=(report,),
                validation_errors=(failure or "Decision analysis persistence failed.",),
                warnings=result.warnings,
                runtime_events=events,
            )
        analysis = AIDecisionAnalysis.model_validate(envelope.payload)
        return DecisionAnalysisExecutionResult(
            status=WorkflowStatus.COMPLETED,
            component_status=result.status,
            current_node=WorkflowNode.DECISION_CARD_COMPOSITION.value,
            scenario_packet=packet,
            analysis=analysis,
            generated_artifacts=(envelope,),
            validation_reports=(report,),
            warnings=result.warnings,
            runtime_events=events,
        )

    async def run_card(self, context: ExecutionContext) -> DecisionCardExecutionResult:
        """Persist exactly one detailed Card; do not request Founder approval."""
        result = await self._card_assembler.execute(context)
        events = self._events(result)
        errors = self._common_errors(
            result=result,
            context=context,
            artifact_type=ArtifactType.DECISION_CARD,
            typed_value=result.decision_card,
        )
        if (
            result.decision_card is not None
            and context.input_artifact_ids
            and result.decision_card.ai_analysis_artifact.artifact_id
            != context.input_artifact_ids[0]
        ):
            errors = (*errors, "Decision Card binds another AI analysis.")
        if errors or result.decision_card is None or not result.artifacts:
            return DecisionCardExecutionResult(
                status=WorkflowStatus.FAILED_SAFE,
                component_status=ComponentStatus.FAILED_SAFE,
                current_node=WorkflowNode.DECISION_CARD_COMPOSITION.value,
                decision_card=result.decision_card,
                validation_errors=errors or ("Decision Card failed safely.",),
                warnings=result.warnings,
                runtime_events=events,
            )
        report, envelope, failure = await self._validate_and_persist(
            result.artifacts[0], context
        )
        if failure is not None or envelope is None:
            return DecisionCardExecutionResult(
                status=WorkflowStatus.FAILED_SAFE,
                component_status=ComponentStatus.FAILED_SAFE,
                current_node=WorkflowNode.DECISION_CARD_COMPOSITION.value,
                decision_card=result.decision_card,
                validation_reports=(report,),
                validation_errors=(failure or "Decision Card persistence failed.",),
                warnings=result.warnings,
                runtime_events=events,
            )
        card = DecisionCard.model_validate(envelope.payload)
        return DecisionCardExecutionResult(
            status=WorkflowStatus.COMPLETED,
            component_status=result.status,
            current_node=WorkflowNode.DECISION_CARD_COMPOSITION.value,
            decision_card=card,
            generated_artifacts=(envelope,),
            validation_reports=(report,),
            warnings=result.warnings,
            runtime_events=events,
        )

    @staticmethod
    def _common_errors(
        *,
        result: ComponentResult,
        context: ExecutionContext,
        artifact_type: ArtifactType,
        typed_value: AIDecisionAnalysis | DecisionCard | None,
    ) -> tuple[str, ...]:
        errors: list[str] = []
        if result.status not in {
            ComponentStatus.COMPLETED,
            ComponentStatus.COMPLETED_WITH_WARNINGS,
        }:
            errors.append(f"{artifact_type.value} component did not complete.")
        if len(context.input_artifact_ids) != 1:
            errors.append(f"{artifact_type.value} requires exactly one direct input.")
        if typed_value is None:
            errors.append(f"{artifact_type.value} returned no typed payload.")
        if len(result.artifacts) != 1 or result.artifacts[0].artifact_type is not artifact_type:
            errors.append(f"{artifact_type.value} must return exactly one draft.")
        elif typed_value is not None and (
            result.artifacts[0].payload != typed_value.model_dump(mode="json")
        ):
            errors.append(f"{artifact_type.value} typed payload and draft disagree.")
        if typed_value is not None and (
            typed_value.evaluation_case_id != context.evaluation_case_id
            or typed_value.dataset_id != context.dataset_id
        ):
            errors.append(f"{artifact_type.value} belongs to another scope.")
        if (
            result.missing_data_requests
            or result.approval_signals
            or result.action_commands
        ):
            errors.append(f"{artifact_type.value} exceeds its component boundary.")
        return tuple(errors)

    async def _validate_and_persist(
        self,
        draft: ArtifactDraft,
        context: ExecutionContext,
    ) -> tuple[ValidationReport, ArtifactEnvelope | None, str | None]:
        report = await self._validator.validate(draft)
        if report.status is ValidationStatus.BLOCKED:
            return (
                report,
                None,
                "; ".join(report.blocking_errors)
                or "Evidence Validator blocked the Decision artifact.",
            )
        try:
            envelope = await self._persist_or_reuse(draft, context, report)
        except DecisionPersistenceError as exc:
            return report, None, str(exc)
        return report, envelope, None

    async def _persist_or_reuse(
        self,
        draft: ArtifactDraft,
        context: ExecutionContext,
        report: ValidationReport,
    ) -> ArtifactEnvelope:
        artifacts = await self._artifacts.list_by_case(draft.evaluation_case_id)
        expected_hash = artifact_input_hash(draft, context)
        matches = tuple(
            item
            for item in artifacts
            if item.artifact_type is draft.artifact_type
            and item.input_hash == expected_hash
        )
        if len(matches) > 1:
            raise DecisionPersistenceError(
                f"{draft.artifact_type.value} artifact identity is ambiguous."
            )
        if matches:
            existing = matches[0]
            if (
                existing.payload != draft.payload
                or existing.evidence_refs != draft.evidence_refs
                or existing.input_artifact_ids != context.input_artifact_ids
                or existing.validation_status
                not in {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}
            ):
                raise DecisionPersistenceError(
                    f"Existing {draft.artifact_type.value} artifact is not reusable."
                )
            return existing
        version = 1 + max(
            (
                item.version
                for item in artifacts
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
    def _events(result: ComponentResult) -> tuple[dict[str, object], ...]:
        return tuple(item.model_dump(mode="json") for item in result.runtime_events)
