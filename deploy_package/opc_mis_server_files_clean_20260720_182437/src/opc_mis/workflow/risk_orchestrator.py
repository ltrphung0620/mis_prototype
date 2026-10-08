"""Workflow-owned validation, checkpointing, pause, and resume for Risk."""

from opc_mis.business.agents.risk.component import RiskAgent
from opc_mis.domain.approvals import ApprovalCheckpointSet
from opc_mis.domain.artifacts import ArtifactDraft, ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import (
    ArtifactType,
    ComponentStatus,
    RiskAssessmentStatus,
    RiskDependency,
    RiskExecutionMode,
    RiskRunStatus,
    ValidationStatus,
    WorkflowStatus,
)
from opc_mis.domain.risk_models import RiskExecutionResult, RiskPreScan, RiskRunState
from opc_mis.domain.validation_reports import ValidationReport
from opc_mis.domain.workflow import WorkflowNode
from opc_mis.governance.approval_policy_registry import (
    ApprovalPolicyError,
    ApprovalPolicyRegistry,
)
from opc_mis.governance.evidence_validator import EvidenceValidator
from opc_mis.ports.artifact_repository import ArtifactRepository
from opc_mis.ports.risk_state_repository import RiskStateRepository
from opc_mis.workflow.artifact_factory import ArtifactFactory, artifact_input_hash


class RiskAssessmentOrchestrator:
    """Persist pre-scan checkpoints and resume Risk when fact artifacts arrive."""

    def __init__(
        self,
        *,
        risk: RiskAgent,
        artifacts: ArtifactRepository,
        states: RiskStateRepository,
        validator: EvidenceValidator | None = None,
        artifact_factory: ArtifactFactory | None = None,
        approval_registry: ApprovalPolicyRegistry | None = None,
    ) -> None:
        self._risk = risk
        self._artifacts = artifacts
        self._states = states
        self._validator = validator or EvidenceValidator()
        self._artifact_factory = artifact_factory or ArtifactFactory()
        self._approval_registry = approval_registry or ApprovalPolicyRegistry()

    async def run_pre_scan(self, context: ExecutionContext) -> RiskExecutionResult:
        """Execute only the side-effect-free Risk source pre-scan."""
        return await self._run_component(context, RiskExecutionMode.PRE_SCAN)

    async def finalize(self, context: ExecutionContext) -> RiskExecutionResult:
        """Finalize only after workflow-owned dependency checks succeed."""
        pending = await self.missing_dependencies(context)
        if pending:
            return await self.wait_for_dependencies(context, pending)
        return await self._run_component(context, RiskExecutionMode.FINALIZE)

    async def wait_for_dependencies(
        self,
        context: ExecutionContext,
        pending: tuple[RiskDependency, ...] | None = None,
    ) -> RiskExecutionResult:
        """Persist workflow dependency state without invoking the Risk component."""
        previous = await self._states.get_by_case(context.evaluation_case_id or "")
        if previous is None or previous.pre_scan_artifact_id is None:
            return await self.run_pre_scan(context)
        dependencies = pending if pending is not None else await self.missing_dependencies(context)
        finance_id = await self._input_id(context, ArtifactType.FINANCE_FACTS)
        operations_id = await self._input_id(context, ArtifactType.OPERATIONS_FACTS)
        state = previous.model_copy(
            update={
                "status": RiskRunStatus.WAITING_FOR_FACTS,
                "checkpoint_version": previous.checkpoint_version + 1,
                "finance_facts_artifact_id": finance_id,
                "operations_facts_artifact_id": operations_id,
                "pending_dependencies": dependencies,
                "failure_reason": None,
            }
        )
        await self._states.save(state)
        pre_scan_artifact = await self._artifacts.get(previous.pre_scan_artifact_id)
        checkpoint_artifact = (
            await self._artifacts.get(previous.approval_checkpoint_artifact_id)
            if previous.approval_checkpoint_artifact_id is not None
            else None
        )
        pre_scan = (
            None
            if pre_scan_artifact is None
            else RiskPreScan.model_validate(pre_scan_artifact.payload)
        )
        checkpoint_set = (
            ApprovalCheckpointSet.model_validate(checkpoint_artifact.payload)
            if checkpoint_artifact is not None
            else None
        )
        return RiskExecutionResult(
            status=WorkflowStatus.WAITING_FOR_DEPENDENCIES,
            component_status=ComponentStatus.COMPLETED,
            current_node=WorkflowNode.INITIAL_RISK_FINALIZATION.value,
            risk_run_id=context.workflow_run_id,
            checkpoint_status=state.status,
            pre_scan=pre_scan,
            approval_checkpoints=checkpoint_set,
            pending_dependencies=dependencies,
            generated_artifacts=tuple(
                item
                for item in (pre_scan_artifact, checkpoint_artifact)
                if item is not None
            ),
        )

    async def missing_dependencies(
        self, context: ExecutionContext
    ) -> tuple[RiskDependency, ...]:
        """Return missing fact artifacts without executing business logic."""
        pending: list[RiskDependency] = []
        if await self._input_id(context, ArtifactType.FINANCE_FACTS) is None:
            pending.append(RiskDependency.FINANCE_FACTS)
        if await self._input_id(context, ArtifactType.OPERATIONS_FACTS) is None:
            pending.append(RiskDependency.OPERATIONS_FACTS)
        return tuple(pending)

    async def _run_component(
        self,
        context: ExecutionContext,
        mode: RiskExecutionMode,
    ) -> RiskExecutionResult:
        """Validate and persist one explicitly selected Risk business phase."""
        context = context.model_copy(
            update={
                "component_input": {
                    **context.component_input,
                    "execution_mode": mode.value,
                },
                "current_node": (
                    WorkflowNode.INITIAL_RISK_PRE_SCAN.value
                    if mode is RiskExecutionMode.PRE_SCAN
                    else WorkflowNode.INITIAL_RISK_FINALIZATION.value
                ),
            }
        )
        result = await self._risk.execute(context)
        previous = await self._states.get_by_case(context.evaluation_case_id or "")
        checkpoint_version = 1 if previous is None else previous.checkpoint_version + 1
        if result.status is ComponentStatus.FAILED_SAFE:
            reason = "; ".join(event.message for event in result.runtime_events)
            state = RiskRunState(
                risk_run_id=context.workflow_run_id,
                evaluation_case_id=context.evaluation_case_id or "UNKNOWN",
                dataset_id=context.dataset_id,
                status=RiskRunStatus.FAILED_SAFE,
                checkpoint_version=checkpoint_version,
                pre_scan_artifact_id=(previous.pre_scan_artifact_id if previous else None),
                approval_checkpoint_artifact_id=(
                    previous.approval_checkpoint_artifact_id if previous else None
                ),
                finance_facts_artifact_id=(
                    previous.finance_facts_artifact_id if previous else None
                ),
                operations_facts_artifact_id=(
                    previous.operations_facts_artifact_id if previous else None
                ),
                failure_reason=reason,
            )
            await self._states.save(state)
            return RiskExecutionResult(
                status=WorkflowStatus.FAILED_SAFE,
                component_status=result.status,
                current_node=context.current_node,
                risk_run_id=context.workflow_run_id,
                checkpoint_status=state.status,
                validation_errors=(reason,),
                runtime_events=tuple(
                    event.model_dump(mode="json") for event in result.runtime_events
                ),
            )

        try:
            checkpoint_draft = (
                self._approval_registry.create_draft(
                    pre_scan=result.pre_scan,
                    signals=result.approval_signals,
                )
                if mode is RiskExecutionMode.PRE_SCAN and result.pre_scan is not None
                else None
            )
        except ApprovalPolicyError as exc:
            state = RiskRunState(
                risk_run_id=context.workflow_run_id,
                evaluation_case_id=context.evaluation_case_id or "UNKNOWN",
                dataset_id=context.dataset_id,
                status=RiskRunStatus.FAILED_SAFE,
                checkpoint_version=checkpoint_version,
                pre_scan_artifact_id=(previous.pre_scan_artifact_id if previous else None),
                approval_checkpoint_artifact_id=(
                    previous.approval_checkpoint_artifact_id if previous else None
                ),
                failure_reason=str(exc),
            )
            await self._states.save(state)
            return RiskExecutionResult(
                status=WorkflowStatus.FAILED_SAFE,
                component_status=ComponentStatus.FAILED_SAFE,
                current_node=context.current_node,
                risk_run_id=context.workflow_run_id,
                checkpoint_status=state.status,
                pre_scan=result.pre_scan,
                validation_errors=(str(exc),),
            )

        checkpoint_set = (
            ApprovalCheckpointSet.model_validate(checkpoint_draft.payload)
            if checkpoint_draft is not None
            else None
        )
        if (
            checkpoint_set is None
            and previous is not None
            and previous.approval_checkpoint_artifact_id is not None
        ):
            existing_checkpoint = await self._artifacts.get(
                previous.approval_checkpoint_artifact_id
            )
            if existing_checkpoint is not None:
                checkpoint_set = ApprovalCheckpointSet.model_validate(
                    existing_checkpoint.payload
                )
        drafts = result.artifacts
        if checkpoint_draft is not None:
            drafts = (
                result.artifacts[0],
                checkpoint_draft,
                *result.artifacts[1:],
            )
        reports: list[ValidationReport] = []
        envelopes: list[ArtifactEnvelope] = []
        pre_scan_artifact: ArtifactEnvelope | None = (
            await self._artifacts.get(previous.pre_scan_artifact_id)
            if previous is not None and previous.pre_scan_artifact_id is not None
            else None
        )
        checkpoint_artifact: ArtifactEnvelope | None = (
            await self._artifacts.get(previous.approval_checkpoint_artifact_id)
            if previous is not None
            and previous.approval_checkpoint_artifact_id is not None
            else None
        )
        rule_artifact: ArtifactEnvelope | None = None
        for draft in drafts:
            execution_context = context
            if draft.artifact_type is ArtifactType.RISK_PRE_SCAN:
                execution_context = await self._pre_scan_context(context)
            elif draft.artifact_type is ArtifactType.APPROVAL_CHECKPOINTS:
                base_context = await self._pre_scan_context(context)
                execution_context = base_context.model_copy(
                    update={
                        "input_artifact_ids": tuple(
                            dict.fromkeys(
                                (
                                    *base_context.input_artifact_ids,
                                    *(
                                        (pre_scan_artifact.artifact_id,)
                                        if pre_scan_artifact is not None
                                        else ()
                                    ),
                                )
                            )
                        )
                    }
                )
            elif pre_scan_artifact is not None:
                execution_context = context.model_copy(
                    update={
                        "input_artifact_ids": tuple(
                            dict.fromkeys(
                                (*context.input_artifact_ids, pre_scan_artifact.artifact_id)
                            )
                        )
                    }
                )
            if (
                draft.artifact_type is ArtifactType.INITIAL_RISK_ASSESSMENT
                and rule_artifact is not None
            ):
                execution_context = execution_context.model_copy(
                    update={
                        "input_artifact_ids": tuple(
                            dict.fromkeys(
                                (*execution_context.input_artifact_ids, rule_artifact.artifact_id)
                            )
                        )
                    }
                )
            report = await self._validator.validate(draft)
            reports.append(report)
            if report.status is ValidationStatus.BLOCKED:
                state = RiskRunState(
                    risk_run_id=context.workflow_run_id,
                    evaluation_case_id=context.evaluation_case_id or "UNKNOWN",
                    dataset_id=context.dataset_id,
                    status=RiskRunStatus.FAILED_SAFE,
                    checkpoint_version=checkpoint_version,
                    pre_scan_artifact_id=(
                        pre_scan_artifact.artifact_id
                        if pre_scan_artifact is not None
                        else previous.pre_scan_artifact_id
                        if previous is not None
                        else None
                    ),
                    approval_checkpoint_artifact_id=(
                        checkpoint_artifact.artifact_id
                        if checkpoint_artifact is not None
                        else previous.approval_checkpoint_artifact_id
                        if previous is not None
                        else None
                    ),
                    failure_reason="; ".join(report.blocking_errors),
                )
                await self._states.save(state)
                return RiskExecutionResult(
                    status=WorkflowStatus.FAILED_SAFE,
                    component_status=ComponentStatus.FAILED_SAFE,
                    current_node=context.current_node,
                    risk_run_id=context.workflow_run_id,
                    checkpoint_status=state.status,
                    pre_scan=result.pre_scan,
                    approval_checkpoints=checkpoint_set,
                    validation_reports=tuple(reports),
                    validation_errors=report.blocking_errors,
                    warnings=result.warnings,
                )
            envelope = await self._persist_or_reuse(draft, execution_context, report)
            envelopes.append(envelope)
            if envelope.artifact_type is ArtifactType.RISK_PRE_SCAN:
                pre_scan_artifact = envelope
            elif envelope.artifact_type is ArtifactType.APPROVAL_CHECKPOINTS:
                checkpoint_artifact = envelope
            elif envelope.artifact_type is ArtifactType.RISK_RULE_EVALUATION:
                rule_artifact = envelope

        finance_id = await self._input_id(context, ArtifactType.FINANCE_FACTS)
        operations_id = await self._input_id(context, ArtifactType.OPERATIONS_FACTS)
        if mode is RiskExecutionMode.PRE_SCAN:
            pending = await self.missing_dependencies(context)
            state = RiskRunState(
                risk_run_id=context.workflow_run_id,
                evaluation_case_id=context.evaluation_case_id or "UNKNOWN",
                dataset_id=context.dataset_id,
                status=RiskRunStatus.WAITING_FOR_FACTS,
                checkpoint_version=checkpoint_version,
                pre_scan_artifact_id=(
                    pre_scan_artifact.artifact_id
                    if pre_scan_artifact is not None
                    else previous.pre_scan_artifact_id
                    if previous is not None
                    else None
                ),
                approval_checkpoint_artifact_id=(
                    checkpoint_artifact.artifact_id
                    if checkpoint_artifact is not None
                    else previous.approval_checkpoint_artifact_id
                    if previous is not None
                    else None
                ),
                finance_facts_artifact_id=finance_id,
                operations_facts_artifact_id=operations_id,
                pending_dependencies=pending,
            )
            await self._states.save(state)
            return RiskExecutionResult(
                status=WorkflowStatus.COMPLETED,
                component_status=result.status,
                current_node=WorkflowNode.INITIAL_RISK_PRE_SCAN.value,
                risk_run_id=context.workflow_run_id,
                checkpoint_status=state.status,
                pre_scan=result.pre_scan,
                approval_checkpoints=checkpoint_set,
                pending_dependencies=pending,
                approval_signals=result.approval_signals,
                generated_artifacts=tuple(envelopes),
                validation_reports=tuple(reports),
                warnings=result.warnings,
                runtime_events=tuple(
                    event.model_dump(mode="json") for event in result.runtime_events
                ),
            )

        assessment_status = (
            result.risk_assessment.assessment_status
            if result.risk_assessment is not None
            else RiskAssessmentStatus.LIMITED_BY_EVIDENCE
        )
        state = RiskRunState(
            risk_run_id=context.workflow_run_id,
            evaluation_case_id=context.evaluation_case_id or "UNKNOWN",
            dataset_id=context.dataset_id,
            status=(
                RiskRunStatus.COMPLETED_WITH_LIMITATIONS
                if assessment_status is RiskAssessmentStatus.LIMITED_BY_EVIDENCE
                else RiskRunStatus.COMPLETED
            ),
            checkpoint_version=checkpoint_version,
            pre_scan_artifact_id=pre_scan_artifact.artifact_id if pre_scan_artifact else None,
            approval_checkpoint_artifact_id=(
                checkpoint_artifact.artifact_id if checkpoint_artifact else None
            ),
            finance_facts_artifact_id=finance_id,
            operations_facts_artifact_id=operations_id,
            final_artifact_ids=tuple(
                item.artifact_id
                for item in envelopes
                if item.artifact_type
                in {ArtifactType.RISK_RULE_EVALUATION, ArtifactType.INITIAL_RISK_ASSESSMENT}
            ),
        )
        await self._states.save(state)
        return RiskExecutionResult(
            status=WorkflowStatus.COMPLETED,
            component_status=result.status,
            current_node=WorkflowNode.INITIAL_RISK_FINALIZATION.value,
            risk_run_id=context.workflow_run_id,
            checkpoint_status=state.status,
            pre_scan=result.pre_scan,
            approval_checkpoints=checkpoint_set,
            rule_evaluations=result.rule_evaluations,
            risk_assessment=result.risk_assessment,
            approval_signals=result.approval_signals,
            generated_artifacts=tuple(envelopes),
            validation_reports=tuple(reports),
            warnings=result.warnings,
            runtime_events=tuple(event.model_dump(mode="json") for event in result.runtime_events),
        )

    async def get_state(self, evaluation_case_id: str) -> RiskRunState | None:
        """Expose the workflow checkpoint without leaking persistence details."""
        return await self._states.get_by_case(evaluation_case_id)

    async def _pre_scan_context(self, context: ExecutionContext) -> ExecutionContext:
        base_ids: list[str] = []
        for artifact_id in context.input_artifact_ids:
            artifact = await self._artifacts.get(artifact_id)
            if artifact is not None and artifact.artifact_type in {
                ArtifactType.EVALUATION_CASE,
                ArtifactType.PLANNER_RESULT,
            }:
                base_ids.append(artifact_id)
        return context.model_copy(update={"input_artifact_ids": tuple(base_ids)})

    async def _input_id(
        self, context: ExecutionContext, artifact_type: ArtifactType
    ) -> str | None:
        """Return the one explicit input artifact ID of a requested type."""
        matches: list[str] = []
        for artifact_id in context.input_artifact_ids:
            artifact = await self._artifacts.get(artifact_id)
            if artifact is not None and artifact.artifact_type is artifact_type:
                matches.append(artifact_id)
        return matches[0] if len(matches) == 1 else None

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
                if item.artifact_type is draft.artifact_type and item.input_hash == input_hash
            ),
            None,
        )
        if current is not None:
            return current
        version = 1 + max(
            (item.version for item in existing if item.artifact_type is draft.artifact_type),
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
