"""Validate and persist one complete conditional-negotiation response set."""

from opc_mis.domain.approvals import ApprovalRequest
from opc_mis.domain.artifacts import ArtifactDraft, ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.decision_models import (
    AIDecisionAnalysis,
    DecisionAnalysisSource,
    DecisionCard,
    DecisionRecommendation,
    ExactDecisionArtifactRef,
)
from opc_mis.domain.enums import (
    ApprovalDecision,
    ApprovalRequestStatus,
    ArtifactType,
    ComponentStatus,
    ProtectedAction,
    SourceType,
    ValidationStatus,
    WorkflowStatus,
)
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.lineage import deterministic_id
from opc_mis.domain.negotiation_models import (
    NegotiationConditionOutcome,
    NegotiationOutcome,
    NegotiationOutcomeExecutionResult,
    NegotiationOutcomeInput,
    NegotiationOutcomeStatus,
    negotiation_outcome_action_payload,
)
from opc_mis.domain.post_decision_models import (
    ContractExecutionStatus,
    PostDecisionOutcome,
    PostDecisionUpdate,
    approval_business_identity,
)
from opc_mis.domain.workflow import WorkflowNode
from opc_mis.governance.evidence_validator import EvidenceValidator
from opc_mis.ports.artifact_repository import ArtifactRepository
from opc_mis.workflow.artifact_factory import ArtifactFactory, artifact_input_hash


class NegotiationOutcomeError(ValueError):
    """Raised when input is not bound to the current OpenAI Decision Card."""


class NegotiationOrchestrator:
    """Own canonicalization, validation, versioning, and persistence of responses."""

    component_id = "NEGOTIATION_OUTCOME_INTAKE"

    def __init__(
        self,
        *,
        artifacts: ArtifactRepository,
        validator: EvidenceValidator | None = None,
        artifact_factory: ArtifactFactory | None = None,
    ) -> None:
        self._artifacts = artifacts
        self._validator = validator or EvidenceValidator()
        self._artifact_factory = artifact_factory or ArtifactFactory()

    async def record(
        self,
        *,
        context: ExecutionContext,
        submission: NegotiationOutcomeInput,
    ) -> NegotiationOutcomeExecutionResult:
        artifacts = await self._artifacts.list_by_case(context.evaluation_case_id)
        card_artifact = self._required_artifact(
            artifacts,
            artifact_id=submission.decision_card_artifact_id,
            artifact_type=ArtifactType.DECISION_CARD,
        )
        card = DecisionCard.model_validate(card_artifact.payload)
        if (
            card.recommendation
            is not DecisionRecommendation.NEGOTIATE_CONDITIONS_TO_ACCEPT
            or not card.conditions
        ):
            raise NegotiationOutcomeError(
                "Negotiation input requires a conditional Decision Card with conditions."
            )
        analysis_artifact = self._required_artifact(
            artifacts,
            artifact_id=card.ai_analysis_artifact.artifact_id,
            artifact_type=ArtifactType.AI_DECISION_ANALYSIS,
        )
        analysis = AIDecisionAnalysis.model_validate(analysis_artifact.payload)
        if (
            analysis.source is not DecisionAnalysisSource.OPENAI
            or analysis.analysis_id != card.ai_analysis_id
        ):
            raise NegotiationOutcomeError(
                "Negotiation requires a Decision Card backed by verified OpenAI analysis."
            )
        condition_map = {item.condition_id: item for item in card.conditions}
        submitted_ids = tuple(item.condition_id for item in submission.condition_outcomes)
        if set(submitted_ids) != set(condition_map) or len(submitted_ids) != len(
            condition_map
        ):
            raise NegotiationOutcomeError(
                "A response is required for every current Decision Card condition."
            )

        input_map = {item.condition_id: item for item in submission.condition_outcomes}
        user_evidence = tuple(
            EvidenceRef(
                evidence_id=deterministic_id(
                    "EVD",
                    context.dataset_id,
                    SourceType.USER_INPUT,
                    "NEGOTIATION_OUTCOME_INPUT",
                    submission.workflow_run_id,
                    condition.condition_id,
                    input_map[condition.condition_id].customer_accepted,
                    input_map[condition.condition_id].founder_note,
                ),
                source_type=SourceType.USER_INPUT,
                sheet="NEGOTIATION_OUTCOME_INPUT",
                row_number=0,
                record_id=condition.condition_id,
                field="customer_response",
                display_value={
                    "customer_accepted": input_map[
                        condition.condition_id
                    ].customer_accepted,
                    "founder_note": input_map[condition.condition_id].founder_note,
                },
            )
            for condition in card.conditions
        )
        evidence_by_id = {item.evidence_id: item for item in card_artifact.evidence_refs}
        evidence_by_id.update({item.evidence_id: item for item in user_evidence})
        condition_outcomes = tuple(
            NegotiationConditionOutcome(
                condition_id=condition.condition_id,
                condition_code=condition.code,
                condition_title=condition.title,
                customer_accepted=input_map[condition.condition_id].customer_accepted,
                founder_note=input_map[condition.condition_id].founder_note,
                evidence_ids=tuple(
                    dict.fromkeys(
                        (*condition.evidence_ids, user_evidence[index].evidence_id)
                    )
                ),
            )
            for index, condition in enumerate(card.conditions)
        )
        all_accepted = all(item.customer_accepted for item in condition_outcomes)
        card_ref = ExactDecisionArtifactRef(
            artifact_id=card_artifact.artifact_id,
            artifact_type=card_artifact.artifact_type,
            version=card_artifact.version,
            input_hash=card_artifact.input_hash,
        )
        outcome_id = deterministic_id(
            "NGO",
            context.evaluation_case_id,
            context.dataset_id,
            card.contract_id,
            card_ref.model_dump(mode="json"),
            tuple(item.model_dump(mode="json") for item in condition_outcomes),
            submission.founder_summary,
        )
        outcome = NegotiationOutcome(
            negotiation_outcome_id=outcome_id,
            evaluation_case_id=context.evaluation_case_id,
            dataset_id=context.dataset_id,
            contract_id=card.contract_id,
            decision_card_artifact=card_ref,
            condition_outcomes=condition_outcomes,
            all_conditions_accepted=all_accepted,
            outcome_status=(
                NegotiationOutcomeStatus.ALL_CONDITIONS_ACCEPTED
                if all_accepted
                else NegotiationOutcomeStatus.ONE_OR_MORE_CONDITIONS_REJECTED
            ),
            founder_summary=submission.founder_summary,
            evidence_ids=tuple(sorted(evidence_by_id)),
        )
        draft = ArtifactDraft(
            artifact_type=ArtifactType.NEGOTIATION_OUTCOME,
            evaluation_case_id=context.evaluation_case_id,
            producer=self.component_id,
            payload=outcome.model_dump(mode="json"),
            evidence_refs=tuple(evidence_by_id[key] for key in sorted(evidence_by_id)),
            identity_inputs={
                "decision_card": card_ref.model_dump(mode="json"),
                "condition_outcomes": tuple(
                    item.model_dump(mode="json") for item in condition_outcomes
                ),
                "founder_summary": submission.founder_summary,
            },
        )
        report = await self._validator.validate(draft)
        if report.status is ValidationStatus.BLOCKED:
            return NegotiationOutcomeExecutionResult(
                status=WorkflowStatus.FAILED_SAFE,
                component_status=ComponentStatus.FAILED_SAFE,
                current_node=WorkflowNode.NEGOTIATION_OUTCOME_RECEIVED.value,
                outcome=outcome,
                validation_reports=(report,),
                validation_errors=report.blocking_errors,
            )
        artifact_context = context.model_copy(
            update={"input_artifact_ids": (card_artifact.artifact_id,)}
        )
        expected_hash = artifact_input_hash(draft, artifact_context)
        existing = tuple(
            item
            for item in artifacts
            if item.artifact_type is ArtifactType.NEGOTIATION_OUTCOME
            and item.input_hash == expected_hash
        )
        if existing:
            if len(existing) != 1 or existing[0].payload != draft.payload:
                raise NegotiationOutcomeError(
                    "Existing negotiation outcome cannot be reused safely."
                )
            envelope = existing[0]
        else:
            version = 1 + max(
                (
                    item.version
                    for item in artifacts
                    if item.artifact_type is ArtifactType.NEGOTIATION_OUTCOME
                ),
                default=0,
            )
            envelope = self._artifact_factory.create(
                draft=draft,
                context=artifact_context,
                validation_report=report,
                version=version,
            )
            await self._artifacts.save(envelope)
        return NegotiationOutcomeExecutionResult(
            status=WorkflowStatus.COMPLETED,
            component_status=ComponentStatus.COMPLETED,
            current_node=WorkflowNode.NEGOTIATION_OUTCOME_RECEIVED.value,
            outcome=NegotiationOutcome.model_validate(envelope.payload),
            generated_artifacts=(envelope,),
            validation_reports=(report,),
        )

    async def finalize(
        self,
        *,
        context: ExecutionContext,
        original_update_artifact: ArtifactEnvelope,
        outcome_artifact: ArtifactEnvelope,
        approval_request: ApprovalRequest,
    ) -> ArtifactEnvelope:
        """Create the final signed/not-signed route after exact Founder approval."""
        original = PostDecisionUpdate.model_validate(original_update_artifact.payload)
        outcome = NegotiationOutcome.model_validate(outcome_artifact.payload)
        decision = approval_request.decision_record
        if (
            approval_request.status is not ApprovalRequestStatus.APPROVED
            or decision is None
            or decision.decision is not ApprovalDecision.APPROVE
            or approval_request.command.action_type
            is not ProtectedAction.CONFIRM_NEGOTIATION_OUTCOME
            or approval_request.subject_artifact_id != outcome_artifact.artifact_id
            or approval_request.subject_artifact_version != outcome_artifact.version
            or approval_request.subject_input_hash != outcome_artifact.input_hash
            or approval_request.command.payload
            != negotiation_outcome_action_payload(outcome)
        ):
            raise NegotiationOutcomeError(
                "Founder approval does not bind the exact negotiation outcome."
            )
        if (
            original.outcome is not PostDecisionOutcome.NEGOTIATION_AUTHORIZED
            or original.decision_card_artifact.artifact_id
            != outcome.decision_card_artifact.artifact_id
        ):
            raise NegotiationOutcomeError(
                "Negotiation outcome does not resolve the approved conditional route."
            )
        evidence_by_id = {
            item.evidence_id: item
            for artifact in (original_update_artifact, outcome_artifact)
            for item in artifact.evidence_refs
        }
        evidence_refs = tuple(evidence_by_id[key] for key in sorted(evidence_by_id))
        evidence_ids = tuple(item.evidence_id for item in evidence_refs)
        outcome_ref = ExactDecisionArtifactRef(
            artifact_id=outcome_artifact.artifact_id,
            artifact_type=outcome_artifact.artifact_type,
            version=outcome_artifact.version,
            input_hash=outcome_artifact.input_hash,
        )
        final_outcome = (
            PostDecisionOutcome.FINAL_DECISION_ACCEPTED
            if outcome.all_conditions_accepted
            else PostDecisionOutcome.CASE_CLOSED_NO_EXTERNAL_ACTION
        )
        execution_status = (
            ContractExecutionStatus.SIGNED
            if outcome.all_conditions_accepted
            else ContractExecutionStatus.NOT_SIGNED
        )
        resolved_id = deterministic_id(
            "PDU-NEG",
            original.decision_card_artifact.model_dump(mode="json"),
            original.decision_card_id,
            approval_business_identity(original.founder_approval),
            original.recommendation,
            final_outcome,
            execution_status,
            original.approved_condition_ids,
            original.approved_negotiation_strategy_ids,
            original.selected_option_ids,
            (
                original.document_release_package.model_dump(mode="json")
                if original.document_release_package is not None
                else None
            ),
            outcome_ref.model_dump(mode="json"),
            outcome.negotiation_outcome_id,
            approval_request.request_id,
            evidence_ids,
        )
        resolved = PostDecisionUpdate(
            update_id=resolved_id,
            evaluation_case_id=original.evaluation_case_id,
            dataset_id=original.dataset_id,
            contract_id=original.contract_id,
            decision_card_artifact=original.decision_card_artifact,
            decision_card_id=original.decision_card_id,
            founder_approval=original.founder_approval,
            recommendation=original.recommendation,
            outcome=final_outcome,
            contract_execution_status=execution_status,
            approved_condition_ids=original.approved_condition_ids,
            approved_negotiation_strategy_ids=(
                original.approved_negotiation_strategy_ids
            ),
            selected_option_ids=original.selected_option_ids,
            document_release_package=original.document_release_package,
            negotiation_outcome_artifact=outcome_ref,
            negotiation_outcome_id=outcome.negotiation_outcome_id,
            negotiation_approval_request_id=approval_request.request_id,
            external_document_release_required=(
                outcome.all_conditions_accepted
                and original.document_release_package is not None
            ),
            evidence_ids=evidence_ids,
        )
        draft = ArtifactDraft(
            artifact_type=ArtifactType.POST_DECISION_UPDATE,
            evaluation_case_id=context.evaluation_case_id,
            producer="NEGOTIATION_FINALIZATION",
            payload=resolved.model_dump(mode="json"),
            evidence_refs=evidence_refs,
            identity_inputs={
                "decision_card_artifact": resolved.decision_card_artifact.model_dump(
                    mode="json"
                ),
                "decision_card_id": resolved.decision_card_id,
                "founder_approval": approval_business_identity(
                    resolved.founder_approval
                ),
                "recommendation": resolved.recommendation,
                "outcome": resolved.outcome,
                "contract_execution_status": resolved.contract_execution_status,
                "approved_condition_ids": resolved.approved_condition_ids,
                "approved_negotiation_strategy_ids": (
                    resolved.approved_negotiation_strategy_ids
                ),
                "selected_option_ids": resolved.selected_option_ids,
                "document_release_package": (
                    resolved.document_release_package.model_dump(mode="json")
                    if resolved.document_release_package is not None
                    else None
                ),
                "negotiation_outcome_artifact": outcome_ref.model_dump(mode="json"),
                "negotiation_outcome_id": resolved.negotiation_outcome_id,
                "negotiation_approval_request_id": (
                    resolved.negotiation_approval_request_id
                ),
            },
        )
        report = await self._validator.validate(draft)
        if report.status is ValidationStatus.BLOCKED:
            raise NegotiationOutcomeError(
                "; ".join(report.blocking_errors)
                or "Resolved negotiation update failed validation."
            )
        artifacts = await self._artifacts.list_by_case(context.evaluation_case_id)
        artifact_context = context.model_copy(
            update={
                "input_artifact_ids": (
                    original_update_artifact.artifact_id,
                    outcome_artifact.artifact_id,
                )
            }
        )
        expected_hash = artifact_input_hash(draft, artifact_context)
        existing = tuple(
            item
            for item in artifacts
            if item.artifact_type is ArtifactType.POST_DECISION_UPDATE
            and item.input_hash == expected_hash
        )
        if existing:
            if len(existing) != 1 or existing[0].payload != draft.payload:
                raise NegotiationOutcomeError(
                    "Resolved negotiation update cannot be reused safely."
                )
            return existing[0]
        version = 1 + max(
            (
                item.version
                for item in artifacts
                if item.artifact_type is ArtifactType.POST_DECISION_UPDATE
            ),
            default=0,
        )
        envelope = self._artifact_factory.create(
            draft=draft,
            context=artifact_context,
            validation_report=report,
            version=version,
        )
        await self._artifacts.save(envelope)
        return envelope

    @staticmethod
    def _required_artifact(
        artifacts: tuple[ArtifactEnvelope, ...],
        *,
        artifact_id: str,
        artifact_type: ArtifactType,
    ) -> ArtifactEnvelope:
        matches = tuple(
            item
            for item in artifacts
            if item.artifact_id == artifact_id
            and item.artifact_type is artifact_type
            and item.validation_status
            in {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}
        )
        if len(matches) != 1:
            raise NegotiationOutcomeError(
                f"Required {artifact_type.value} artifact is missing or ambiguous."
            )
        return matches[0]
