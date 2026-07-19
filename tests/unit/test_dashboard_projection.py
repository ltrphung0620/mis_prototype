"""Run-scoped Founder dashboard projection tests."""

from datetime import UTC, datetime

import pytest

from opc_mis.api.dashboard_projection import build_dashboard_projection
from opc_mis.api.dashboard_schemas import (
    DashboardApplicability,
    DashboardBusinessStatus,
    DashboardInteractionType,
    DashboardPendingInteraction,
    DashboardTaskStatus,
)
from opc_mis.domain.approvals import ApprovalDecisionRecord, ApprovalRequest
from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.case_workflow_models import WorkflowNodeState, WorkflowRunSummary
from opc_mis.domain.commands import ActionCommand
from opc_mis.domain.enums import (
    ApprovalDecision,
    ApprovalRequestStatus,
    ArtifactStatus,
    ArtifactType,
    CashflowScope,
    ContractRequirementType,
    CurrencyCode,
    DecisionPostBankingOutcome,
    DecisionRouteOutcome,
    EvaluationScope,
    FinanceCalculation,
    FinanceDataScope,
    FinanceFactQuality,
    FinanceMetric,
    FinanceUnit,
    ProtectedAction,
    ReadinessStatus,
    RequirementAmountSemantics,
    RequirementCertainty,
    RunTaskType,
    ValidationStatus,
    WorkflowNodeStatus,
    WorkflowStatus,
)
from opc_mis.domain.finance_models import FinanceFact, FinanceFacts
from opc_mis.domain.planner_models import (
    ContractRequirement,
    DataReadiness,
    EvaluationCase,
    PlannerResult,
    RunPlan,
)
from opc_mis.domain.workflow import WorkflowNode

NOW = datetime(2026, 7, 19, tzinfo=UTC)


def _summary(**updates: object) -> WorkflowRunSummary:
    values: dict[str, object] = {
        "workflow_run_id": "CWF-CURRENT",
        "evaluation_case_id": "CASE-1",
        "contract_id": "CONTRACT-1",
        "status": WorkflowStatus.RUNNING,
        "current_stage": WorkflowNode.PLANNER_INTAKE.value,
        "nodes": (),
    }
    values.update(updates)
    return WorkflowRunSummary.model_validate(values)


def _node(
    node: WorkflowNode,
    *,
    status: WorkflowNodeStatus = WorkflowNodeStatus.COMPLETED,
    output_artifact_ids: tuple[str, ...] = (),
) -> WorkflowNodeState:
    return WorkflowNodeState(
        workflow_run_id="CWF-CURRENT",
        node=node,
        status=status,
        attempt=1,
        output_artifact_ids=output_artifact_ids,
        started_at=NOW,
        completed_at=NOW if status.value.startswith("COMPLETED") else None,
    )


def _finance_artifact(artifact_id: str, *, reserve_gap: int) -> ArtifactEnvelope:
    facts = FinanceFacts(
        evaluation_case_id="CASE-1",
        dataset_id="DATASET-1",
        contract_id="CONTRACT-1",
        facts=(
            FinanceFact(
                fact_id=f"FACT-CONTRACT-{artifact_id}",
                metric=FinanceMetric.CONTRACT_VALUE,
                value=4_200_000_000,
                unit=FinanceUnit.VND,
                scope=FinanceDataScope.CASE_SPECIFIC,
                quality=FinanceFactQuality.VERIFIED,
                calculation=FinanceCalculation.SOURCE_VALUE,
                evidence_id=f"EVD-CONTRACT-{artifact_id}",
                source_evidence_ids=(f"SRC-CONTRACT-{artifact_id}",),
            ),
            FinanceFact(
                fact_id=f"FACT-{artifact_id}",
                metric=FinanceMetric.WORST_RESERVE_GAP,
                value=reserve_gap,
                unit=FinanceUnit.VND,
                scope=FinanceDataScope.OPC_GLOBAL,
                quality=FinanceFactQuality.VERIFIED,
                calculation=FinanceCalculation.MAX_NON_NEGATIVE_DIFFERENCE,
                evidence_id=f"EVD-{artifact_id}",
                source_evidence_ids=(f"SRC-{artifact_id}",),
                note="OPC-level projection; not attributable to this contract.",
            ),
        ),
        observations=(),
        limitations=(),
    )
    return ArtifactEnvelope(
        artifact_id=artifact_id,
        artifact_type=ArtifactType.FINANCE_FACTS,
        evaluation_case_id="CASE-1",
        producer="FINANCE_AGENT",
        version=1,
        status=ArtifactStatus.CREATED,
        payload=facts.model_dump(mode="json"),
        evidence_refs=(),
        input_artifact_ids=(),
        input_hash=f"HASH-{artifact_id}",
        validation_status=ValidationStatus.VALID,
        validation_notes=(),
        created_at=NOW,
    )


def _pending_approval(
    *,
    request_id: str,
    workflow_run_id: str,
    status: ApprovalRequestStatus = ApprovalRequestStatus.PENDING,
) -> ApprovalRequest:
    decision_record = (
        ApprovalDecisionRecord(
            decision=(
                ApprovalDecision.APPROVE
                if status is ApprovalRequestStatus.APPROVED
                else ApprovalDecision.REJECT
            ),
            decided_by="FOUNDER",
            reason="HUMAN_REVIEW_COMPLETED",
            decided_at=NOW,
        )
        if status
        in {ApprovalRequestStatus.APPROVED, ApprovalRequestStatus.REJECTED}
        else None
    )
    return ApprovalRequest(
        request_id=request_id,
        workflow_run_id=workflow_run_id,
        evaluation_case_id="CASE-1",
        dataset_id="DATASET-1",
        subject_artifact_id="ART-PROPOSAL",
        subject_artifact_version=1,
        subject_input_hash="SUBJECT-HASH",
        checkpoint_ids=("CHECKPOINT-1",),
        policy_artifact_id="ART-POLICY",
        policy_artifact_version=1,
        policy_input_hash="POLICY-HASH",
        policy_coverage_ids=("COVERAGE-1",),
        command=ActionCommand(
            action_type=ProtectedAction.SUBMIT_BANKING_PRECHECK,
            evaluation_case_id="CASE-1",
            payload_artifact_id="ART-PROPOSAL",
            requested_by="CASE_WORKFLOW_ORCHESTRATOR",
        ),
        status=status,
        created_at=NOW,
        decision_record=decision_record,
    )


def _planner_artifacts() -> tuple[ArtifactEnvelope, ArtifactEnvelope]:
    evaluation_case = EvaluationCase(
        evaluation_case_id="CASE-1",
        dataset_id="DATASET-1",
        contract_id="CONTRACT-1",
        customer_id="CUSTOMER-1",
        related_order_ids=("ORDER-1", "ORDER-2"),
        related_invoice_ids=("INVOICE-1",),
        related_service_ids=("SERVICE-1",),
        related_credit_case_ids=("CR-002",),
        evaluation_scope=(
            EvaluationScope.FINANCE,
            EvaluationScope.OPERATIONS,
            EvaluationScope.RISK,
        ),
        cashflow_scope=CashflowScope.OPC_GLOBAL,
        warnings=(),
        evidence_refs=(),
        contract_requirements=(
            ContractRequirement(
                requirement_id="REQ-1",
                requirement_type=ContractRequirementType.PERFORMANCE_BOND,
                certainty=RequirementCertainty.REQUIRED,
                requested_amount=420_000_000,
                requested_amount_currency=CurrencyCode.VND,
                amount_semantics=(
                    RequirementAmountSemantics.CREDIT_PROFILE_REQUESTED_AMOUNT
                ),
                credit_case_id="CR-002",
                source_record_ids=("SOURCE-1",),
                source_fields=("requested_amount",),
                evidence_ids=("EVD-1",),
            ),
        ),
    )
    planner_result = PlannerResult(
        evaluation_case=evaluation_case,
        data_readiness=DataReadiness(
            status=ReadinessStatus.READY_WITH_WARNINGS,
            blocking_missing_fields=(),
            non_blocking_warnings=(),
            validation_notes=(),
        ),
        run_plan=RunPlan(
            parallel_initial_tasks=(
                RunTaskType.FINANCE_ASSESSMENT,
                RunTaskType.OPERATIONS_ASSESSMENT,
                RunTaskType.INITIAL_RISK_SCAN,
            ),
            plan_reason="Run the complete initial assessment.",
        ),
        missing_data_requests=(),
        warnings=(),
        evidence_refs=(),
    )

    def envelope(
        artifact_id: str,
        artifact_type: ArtifactType,
        payload: dict[str, object],
    ) -> ArtifactEnvelope:
        return ArtifactEnvelope(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            evaluation_case_id="CASE-1",
            producer="PLANNER_SKILL",
            version=1,
            status=ArtifactStatus.CREATED,
            payload=payload,
            evidence_refs=(),
            input_artifact_ids=(),
            input_hash=f"HASH-{artifact_id}",
            validation_status=ValidationStatus.VALID,
            validation_notes=(),
            created_at=NOW,
        )

    return (
        envelope(
            "ART-CASE",
            ArtifactType.EVALUATION_CASE,
            evaluation_case.model_dump(mode="json"),
        ),
        envelope(
            "ART-PLANNER",
            ArtifactType.PLANNER_RESULT,
            planner_result.model_dump(mode="json"),
        ),
    )


def test_projection_exposes_canonical_order_and_parallel_initial_assessment() -> None:
    projection = build_dashboard_projection(
        summary=_summary(),
        artifacts=(),
        approvals=(),
    )

    assert [item.stage_id for item in projection.stages[:9]] == [
        "PLANNER_INTAKE",
        "INITIAL_RISK_PRE_SCAN",
        "INITIAL_ASSESSMENT_PARALLEL",
        "INITIAL_RISK_FINALIZATION",
        "DECISION_ROUTE_PLANNING",
        "BANKING_DISCOVERY_HANDOFF",
        "BANKING_INTERNAL_DISCOVERY",
        "BANKING_PRECHECK_READINESS",
        "DECISION_POST_BANKING_REVIEW",
    ]
    parallel = projection.stages[2]
    assert parallel.parallel is True
    assert [item.task_id for item in parallel.tasks] == [
        "FINANCE_ASSESSMENT",
        "OPERATIONS_ASSESSMENT",
    ]
    assert projection.progress.basis == "CANONICAL_WORKFLOW_TASKS"


def test_projection_exposes_typed_planner_input_without_evidence_details() -> None:
    case_artifact, planner_artifact = _planner_artifacts()
    summary = _summary(
        nodes=(
            _node(
                WorkflowNode.PLANNER_INTAKE,
                output_artifact_ids=(
                    case_artifact.artifact_id,
                    planner_artifact.artifact_id,
                ),
            ),
        ),
    )

    projection = build_dashboard_projection(
        summary=summary,
        artifacts=(case_artifact, planner_artifact),
        approvals=(),
    )

    assert projection.input.available is True
    assert projection.input.readiness_status is ReadinessStatus.READY_WITH_WARNINGS
    assert projection.input.blocking_missing_count == 0
    assert projection.input.warning_count == 0
    assert projection.input.linked_customer_count == 1
    assert projection.input.linked_order_count == 2
    assert projection.input.linked_invoice_count == 1
    assert projection.input.linked_service_count == 1
    assert projection.input.linked_credit_profile_count == 1
    assert len(projection.input.contract_requirements) == 1
    requirement = projection.input.contract_requirements[0]
    assert requirement.requirement_type is ContractRequirementType.PERFORMANCE_BOND
    assert requirement.certainty is RequirementCertainty.REQUIRED
    assert requirement.requested_amount == 420_000_000
    assert requirement.requested_amount_currency is CurrencyCode.VND
    assert requirement.credit_case_id == "CR-002"
    forbidden = str(projection.input.model_dump(mode="json")).lower()
    assert "evidence" not in forbidden
    assert "source" not in forbidden


def test_projection_uses_only_current_run_artifacts_and_omits_opc_global_metrics() -> None:
    current = _finance_artifact("ART-CURRENT", reserve_gap=710_000_000)
    stale = _finance_artifact("ART-STALE", reserve_gap=999_000_000)
    summary = _summary(
        current_stage=WorkflowNode.INITIAL_RISK_FINALIZATION.value,
        nodes=(
            _node(
                WorkflowNode.FINANCE_ASSESSMENT,
                output_artifact_ids=(current.artifact_id,),
            ),
        ),
    )

    projection = build_dashboard_projection(
        summary=summary,
        artifacts=(stale, current),
        approvals=(),
    )

    assert [item.artifact_id for item in projection.run_artifacts] == ["ART-CURRENT"]
    assert [(item.code, item.value, item.scope) for item in projection.metrics] == [
        ("CONTRACT_VALUE", 4_200_000_000, FinanceDataScope.CASE_SPECIFIC)
    ]
    assert all(item.code != "WORST_RESERVE_GAP" for item in projection.metrics)
    assert all(item.scope is FinanceDataScope.CASE_SPECIFIC for item in projection.metrics)
    serialized = projection.model_dump(mode="json")
    forbidden = str(serialized).lower()
    assert "evidence_ids" not in forbidden
    assert "source_evidence_ids" not in forbidden
    assert "narrative_source" not in forbidden
    assert "composer_model" not in forbidden


def test_projection_filters_approvals_by_workflow_and_protected_action() -> None:
    current = _pending_approval(request_id="APR-CURRENT", workflow_run_id="CWF-CURRENT")
    stale = _pending_approval(request_id="APR-STALE", workflow_run_id="CWF-OLD")
    summary = _summary(
        status=WorkflowStatus.WAITING_FOR_APPROVAL,
        current_stage=WorkflowNode.APPROVAL_GATE.value,
        decision_route_outcome=DecisionRouteOutcome.BANKING_DISCOVERY_REQUIRED,
        decision_post_banking_outcome=DecisionPostBankingOutcome.BANKING_PRECHECK_READY,
        pending_approval_ids=(current.request_id,),
        blocked_action=ProtectedAction.SUBMIT_BANKING_PRECHECK,
    )

    projection = build_dashboard_projection(
        summary=summary,
        artifacts=(),
        approvals=(stale, current),
    )

    assert projection.approval_request_ids == ("APR-CURRENT",)
    interaction = projection.pending_interactions[0]
    assert interaction.interaction_type is DashboardInteractionType.APPROVAL
    assert interaction.approval_request_ids == ("APR-CURRENT",)
    assert interaction.protected_action is ProtectedAction.SUBMIT_BANKING_PRECHECK
    assert interaction.subject_artifact_id == current.subject_artifact_id
    assert interaction.subject_artifact_version == current.subject_artifact_version
    task = next(
        task
        for stage in projection.stages
        for task in stage.tasks
        if task.task_id == "BANKING_PRECHECK_APPROVAL"
    )
    assert task.status is DashboardTaskStatus.WAITING_FOR_APPROVAL
    assert task.approval_request_ids == ("APR-CURRENT",)
    assert projection.business_status is (
        DashboardBusinessStatus.WAITING_FOR_BANKING_APPROVAL
    )


def test_pending_interaction_rejects_actionable_not_evaluable_review() -> None:
    with pytest.raises(ValueError, match="must be supplied together"):
        DashboardPendingInteraction(
            interaction_type=DashboardInteractionType.UNSUPPORTED_INPUT,
            title_vi="Chờ dữ liệu",
            instruction_vi="Bổ sung qua quy trình nghiệp vụ.",
            subject_artifact_id="ART-WITHOUT-VERSION",
        )

    with pytest.raises(ValueError, match="view-only"):
        DashboardPendingInteraction(
            interaction_type=DashboardInteractionType.NOT_EVALUABLE_REVIEW,
            title_vi="Xem Phiếu quyết định",
            instruction_vi="Chỉ xem.",
            subject_artifact_id="ART-CARD",
            subject_artifact_version=2,
            endpoint="/api/approval-requests/APR-1/decision",
        )

    with pytest.raises(ValueError, match="exact subject artifact"):
        DashboardPendingInteraction(
            interaction_type=DashboardInteractionType.APPROVAL,
            title_vi="Phê duyệt",
            instruction_vi="Xem trước khi quyết định.",
        )


@pytest.mark.parametrize(
    ("task_id", "expected_reason"),
    [
        (
            "BANKING_PRECHECK_EXECUTION",
            "không có yêu cầu nào được gửi tới ngân hàng",
        ),
        (
            "DECISION_POST_PRECHECK_REVIEW",
            "không có kết quả ngân hàng để rà soát",
        ),
        (
            "DECISION_DOCUMENT_HANDOFF",
            "không có phương án đã được rà soát để bàn giao chuẩn bị hồ sơ",
        ),
        (
            "DOCUMENT_PREPARATION",
            "không có bàn giao chuẩn bị hồ sơ để thực hiện",
        ),
    ],
)
@pytest.mark.parametrize(
    ("approval_status", "expected_resolution"),
    [
        (ApprovalRequestStatus.REJECTED, "Nhà sáng lập đã từ chối"),
        (ApprovalRequestStatus.EXPIRED, "đã hết hạn"),
    ],
)
def test_resolved_banking_approval_has_task_specific_downstream_reason(
    task_id: str,
    expected_reason: str,
    approval_status: ApprovalRequestStatus,
    expected_resolution: str,
) -> None:
    resolved = _pending_approval(
        request_id=f"APR-{approval_status.value}",
        workflow_run_id="CWF-CURRENT",
        status=approval_status,
    )
    projection = build_dashboard_projection(
        summary=_summary(
            status=WorkflowStatus.COMPLETED,
            current_stage=WorkflowNode.DECISION_CARD_READY.value,
            decision_route_outcome=DecisionRouteOutcome.BANKING_DISCOVERY_REQUIRED,
            decision_post_banking_outcome=(
                DecisionPostBankingOutcome.BANKING_PRECHECK_READY
            ),
        ),
        artifacts=(),
        approvals=(resolved,),
    )

    task = next(
        item
        for stage in projection.stages
        for item in stage.tasks
        if item.task_id == task_id
    )
    assert task.applicability is DashboardApplicability.NOT_APPLICABLE
    assert expected_resolution in task.applicability_reason_vi
    assert expected_reason in task.applicability_reason_vi


@pytest.mark.parametrize(
    ("current_stage", "interaction_type", "endpoint_suffix"),
    [
        (
            WorkflowNode.DECISION_POST_BANKING_REVIEW.value,
            DashboardInteractionType.BANKING_AMOUNT_INPUT,
            "/banking/input-supplements",
        ),
        (
            WorkflowNode.DECISION_POST_PRECHECK_REVIEW.value,
            DashboardInteractionType.BANKING_PRECHECK_EVIDENCE,
            "/banking/precheck-evidence-supplements",
        ),
        (
            WorkflowNode.DOCUMENT_PREPARATION.value,
            DashboardInteractionType.DOCUMENT_EVIDENCE,
            "/documents/evidence-supplements",
        ),
    ],
)
def test_projection_dispatches_typed_missing_input(
    current_stage: str,
    interaction_type: DashboardInteractionType,
    endpoint_suffix: str,
) -> None:
    projection = build_dashboard_projection(
        summary=_summary(
            status=WorkflowStatus.WAITING_FOR_INPUT,
            current_stage=current_stage,
            pending_missing_data_ids=("MDR-1",),
        ),
        artifacts=(),
        approvals=(),
    )

    interaction = projection.pending_interactions[0]
    assert interaction.interaction_type is interaction_type
    assert interaction.request_ids == ("MDR-1",)
    assert interaction.endpoint is not None
    assert interaction.endpoint.endswith(endpoint_suffix)


def test_projection_marks_direct_banking_branch_not_applicable() -> None:
    projection = build_dashboard_projection(
        summary=_summary(
            decision_route_outcome=DecisionRouteOutcome.DIRECT_INTERNAL_DECISION,
        ),
        artifacts=(),
        approvals=(),
    )

    banking = next(
        item for item in projection.stages if item.stage_id == "BANKING_INTERNAL_DISCOVERY"
    )
    assert banking.applicability is DashboardApplicability.NOT_APPLICABLE
    assert banking.status is DashboardTaskStatus.NOT_APPLICABLE


@pytest.mark.parametrize(
    ("current_stage", "expected"),
    [
        (
            WorkflowNode.NEGOTIATION_IN_PROGRESS.value,
            DashboardBusinessStatus.NEGOTIATION_IN_PROGRESS,
        ),
        (
            WorkflowNode.FINAL_DECISION_ACCEPTED.value,
            DashboardBusinessStatus.ACCEPTED,
        ),
        (
            WorkflowNode.FINAL_DECISION_NOT_ACCEPTED.value,
            DashboardBusinessStatus.NOT_ACCEPTED,
        ),
        (
            WorkflowNode.READY_FOR_EXTERNAL_SUBMISSION.value,
            DashboardBusinessStatus.READY_FOR_EXTERNAL_SUBMISSION,
        ),
    ],
)
def test_projection_separates_execution_and_business_terminal_status(
    current_stage: str,
    expected: DashboardBusinessStatus,
) -> None:
    projection = build_dashboard_projection(
        summary=_summary(
            status=WorkflowStatus.COMPLETED,
            current_stage=current_stage,
        ),
        artifacts=(),
        approvals=(),
    )

    assert projection.execution_status is WorkflowStatus.COMPLETED
    assert projection.business_status is expected


def test_stale_decision_card_is_not_exposed_without_current_node_output() -> None:
    stale_card = ArtifactEnvelope(
        artifact_id="ART-STALE-CARD",
        artifact_type=ArtifactType.DECISION_CARD,
        evaluation_case_id="CASE-1",
        producer="DECISION_AGENT",
        version=1,
        status=ArtifactStatus.CREATED,
        payload={},
        evidence_refs=(),
        input_artifact_ids=(),
        input_hash="STALE-HASH",
        validation_status=ValidationStatus.VALID,
        validation_notes=(),
        created_at=NOW,
    )

    projection = build_dashboard_projection(
        summary=_summary(decision_card_id="OLD-CARD"),
        artifacts=(stale_card,),
        approvals=(),
    )

    assert projection.decision_card.available is False
    assert projection.decision_card.artifact_id is None
    assert not projection.run_artifacts
