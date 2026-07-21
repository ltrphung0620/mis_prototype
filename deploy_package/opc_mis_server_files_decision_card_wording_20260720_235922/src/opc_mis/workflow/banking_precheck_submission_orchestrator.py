"""Workflow validation and persistence for a governed Banking precheck proposal."""

from opc_mis.business.skills.banking.precheck_submission_component import (
    BankingPrecheckSubmissionProposalSkill,
)
from opc_mis.domain.artifacts import ArtifactDraft, ArtifactEnvelope
from opc_mis.domain.banking_models import BankingCatalogPolicy
from opc_mis.domain.banking_precheck_submission_models import (
    BankingPrecheckSubmissionProposal,
    BankingPrecheckSubmissionProposalExecutionResult,
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


class BankingPrecheckSubmissionProposalOrchestrator:
    """Persist a validated proposal without authorizing or executing its action."""

    def __init__(
        self,
        *,
        proposer: BankingPrecheckSubmissionProposalSkill,
        artifacts: ArtifactRepository,
        policy: BankingCatalogPolicy,
        artifact_factory: ArtifactFactory | None = None,
    ) -> None:
        self._proposer = proposer
        self._artifacts = artifacts
        self._validator = EvidenceValidator(banking_policy=policy)
        self._artifact_factory = artifact_factory or ArtifactFactory()

    async def run(
        self,
        context: ExecutionContext,
    ) -> BankingPrecheckSubmissionProposalExecutionResult:
        """Prepare, validate, and persist exactly one side-effect-free proposal."""
        result = await self._proposer.execute(context)
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
        proposal = result.proposal
        draft = result.artifacts[0]
        if proposal is None:  # pragma: no cover - guarded by contract validation
            return self._failed(
                ("Banking precheck submission returned no typed proposal.",),
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
                proposal=proposal,
            )
        envelope = await self._persist_or_reuse(draft, context, report)
        persisted = BankingPrecheckSubmissionProposal.model_validate(envelope.payload)
        return BankingPrecheckSubmissionProposalExecutionResult(
            status=WorkflowStatus.COMPLETED,
            component_status=result.status,
            current_node=WorkflowNode.BANKING_PRECHECK_SUBMISSION_PROPOSAL.value,
            proposal=persisted,
            generated_artifacts=(envelope,),
            validation_reports=(report,),
            warnings=result.warnings,
            runtime_events=events,
        )

    @staticmethod
    def _contract_errors(result: object) -> tuple[str, ...]:
        proposal = getattr(result, "proposal", None)
        artifacts = getattr(result, "artifacts", ())
        if proposal is None:
            return ("Banking precheck submission must return a typed proposal.",)
        if len(artifacts) != 1 or (
            artifacts[0].artifact_type
            is not ArtifactType.BANKING_PRECHECK_SUBMISSION_PROPOSAL
        ):
            return (
                "Banking precheck submission must return exactly one proposal draft.",
            )
        if artifacts[0].payload != proposal.model_dump(mode="json"):
            return ("Banking precheck proposal and artifact draft disagree.",)
        if getattr(result, "approval_signals", ()) or getattr(
            result, "action_commands", ()
        ):
            return (
                "The proposal component cannot register Governance state or emit a "
                "command before its artifact is persisted.",
            )
        if getattr(result, "missing_data_requests", ()):
            return ("A ready submission proposal cannot request additional input.",)
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
        proposal: BankingPrecheckSubmissionProposal | None = None,
    ) -> BankingPrecheckSubmissionProposalExecutionResult:
        return BankingPrecheckSubmissionProposalExecutionResult(
            status=WorkflowStatus.FAILED_SAFE,
            component_status=ComponentStatus.FAILED_SAFE,
            current_node=WorkflowNode.BANKING_PRECHECK_SUBMISSION_PROPOSAL.value,
            proposal=proposal,
            validation_reports=reports,
            validation_errors=errors,
            warnings=warnings,
            runtime_events=events,
        )
