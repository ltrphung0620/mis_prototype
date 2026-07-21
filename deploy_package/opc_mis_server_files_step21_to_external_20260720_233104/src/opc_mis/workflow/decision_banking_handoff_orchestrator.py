"""Workflow validation and persistence for Decision-to-Banking handoff."""

from opc_mis.business.agents.decision.banking_handoff_component import (
    DecisionBankingHandoff,
)
from opc_mis.domain.artifacts import ArtifactDraft, ArtifactEnvelope
from opc_mis.domain.banking_models import (
    BankingDiscoveryHandoffExecutionResult,
    BankingDiscoveryRequest,
)
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import (
    ArtifactType,
    BankingDiscoveryHandoffStatus,
    ComponentStatus,
    ValidationStatus,
    WorkflowStatus,
)
from opc_mis.domain.validation_reports import ValidationReport
from opc_mis.domain.workflow import WorkflowNode
from opc_mis.governance.evidence_validator import EvidenceValidator
from opc_mis.ports.artifact_repository import ArtifactRepository
from opc_mis.workflow.artifact_factory import ArtifactFactory, artifact_input_hash


class DecisionBankingHandoffPersistenceError(RuntimeError):
    """Raised when a same-hash handoff artifact is not an exact validated match."""


class DecisionBankingHandoffOrchestrator:
    """Persist a validated internal request without running Banking Skill."""

    def __init__(
        self,
        *,
        handoff: DecisionBankingHandoff,
        artifacts: ArtifactRepository,
        validator: EvidenceValidator | None = None,
        artifact_factory: ArtifactFactory | None = None,
    ) -> None:
        self._handoff = handoff
        self._artifacts = artifacts
        self._validator = validator or EvidenceValidator()
        self._artifact_factory = artifact_factory or ArtifactFactory()

    async def run(
        self, context: ExecutionContext
    ) -> BankingDiscoveryHandoffExecutionResult:
        result = await self._handoff.execute(context)
        events = tuple(
            event.model_dump(mode="json") for event in result.runtime_events
        )
        if result.status is ComponentStatus.FAILED_SAFE:
            return BankingDiscoveryHandoffExecutionResult(
                status=WorkflowStatus.FAILED_SAFE,
                component_status=result.status,
                current_node=WorkflowNode.BANKING_DISCOVERY_HANDOFF.value,
                handoff_status=result.handoff_status,
                validation_errors=tuple(
                    event.message for event in result.runtime_events
                ),
                runtime_events=events,
            )
        if result.status is ComponentStatus.WAITING_FOR_INPUT:
            return BankingDiscoveryHandoffExecutionResult(
                status=WorkflowStatus.WAITING_FOR_INPUT,
                component_status=result.status,
                current_node=WorkflowNode.BANKING_DISCOVERY_HANDOFF.value,
                handoff_status=result.handoff_status,
                missing_data_requests=result.missing_data_requests,
                runtime_events=events,
            )
        if result.handoff_status is BankingDiscoveryHandoffStatus.NOT_APPLICABLE:
            return BankingDiscoveryHandoffExecutionResult(
                status=WorkflowStatus.COMPLETED,
                component_status=result.status,
                current_node=WorkflowNode.DECISION_ROUTE_PLANNED.value,
                handoff_status=result.handoff_status,
                runtime_events=events,
            )

        draft = self._one_request_draft(result.artifacts)
        report = await self._validator.validate(draft)
        if report.status is ValidationStatus.BLOCKED:
            return BankingDiscoveryHandoffExecutionResult(
                status=WorkflowStatus.FAILED_SAFE,
                component_status=ComponentStatus.FAILED_SAFE,
                current_node=WorkflowNode.BANKING_DISCOVERY_HANDOFF.value,
                handoff_status=BankingDiscoveryHandoffStatus.FAILED_SAFE,
                banking_discovery_request=result.banking_discovery_request,
                validation_reports=(report,),
                validation_errors=report.blocking_errors,
                warnings=result.warnings,
                runtime_events=events,
            )
        try:
            envelope = await self._persist_or_reuse(draft, context, report)
        except DecisionBankingHandoffPersistenceError as exc:
            return BankingDiscoveryHandoffExecutionResult(
                status=WorkflowStatus.FAILED_SAFE,
                component_status=ComponentStatus.FAILED_SAFE,
                current_node=WorkflowNode.BANKING_DISCOVERY_HANDOFF.value,
                handoff_status=BankingDiscoveryHandoffStatus.FAILED_SAFE,
                banking_discovery_request=result.banking_discovery_request,
                validation_reports=(report,),
                validation_errors=(str(exc),),
                warnings=result.warnings,
                runtime_events=events,
            )
        request = BankingDiscoveryRequest.model_validate(envelope.payload)
        return BankingDiscoveryHandoffExecutionResult(
            status=WorkflowStatus.COMPLETED,
            component_status=result.status,
            current_node=WorkflowNode.BANKING_DISCOVERY_REQUESTED.value,
            handoff_status=result.handoff_status,
            banking_discovery_request=request,
            generated_artifacts=(envelope,),
            validation_reports=(report,),
            warnings=result.warnings,
            runtime_events=events,
        )

    @staticmethod
    def _one_request_draft(drafts: tuple[ArtifactDraft, ...]) -> ArtifactDraft:
        matches = tuple(
            item
            for item in drafts
            if item.artifact_type is ArtifactType.BANKING_DISCOVERY_REQUEST
        )
        if len(matches) != 1:
            raise RuntimeError(
                "Decision Banking handoff must return exactly one "
                "BANKING_DISCOVERY_REQUEST draft."
            )
        return matches[0]

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
                raise DecisionBankingHandoffPersistenceError(
                    "Existing Decision Banking handoff artifact does not match its "
                    "exact validated business inputs."
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
