"""Build a run-scoped, founder-facing projection from durable workflow state."""

from dataclasses import dataclass

from opc_mis.api.dashboard_schemas import (
    DashboardApplicability,
    DashboardArtifactReference,
    DashboardBusinessStatus,
    DashboardContractRequirement,
    DashboardDecisionCardSummary,
    DashboardInputSummary,
    DashboardInteractionType,
    DashboardMetric,
    DashboardPendingInteraction,
    DashboardProgress,
    DashboardStage,
    DashboardTask,
    DashboardTaskStatus,
    DashboardWorkflowProjection,
)
from opc_mis.domain.approvals import ApprovalRequest
from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.banking_models import BankingDiscoveryRequest
from opc_mis.domain.case_workflow_models import WorkflowNodeState, WorkflowRunSummary
from opc_mis.domain.decision_models import DecisionCard, DecisionRecommendation
from opc_mis.domain.enums import (
    ApprovalRequestStatus,
    ArtifactType,
    DecisionPostBankingOutcome,
    DecisionPostPrecheckOutcome,
    DecisionRouteOutcome,
    FinanceDataScope,
    FinanceFactQuality,
    FinanceMetric,
    FinanceUnit,
    ProtectedAction,
    ReadinessStatus,
    WorkflowNodeStatus,
    WorkflowStatus,
)
from opc_mis.domain.finance_models import FinanceFacts
from opc_mis.domain.planner_models import EvaluationCase, PlannerResult
from opc_mis.domain.post_decision_models import PostDecisionUpdate
from opc_mis.domain.workflow import WorkflowNode


@dataclass(frozen=True)
class _TaskDefinition:
    task_id: str
    owner_id: str
    title_vi: str
    node: WorkflowNode | None = None
    protected_action: ProtectedAction | None = None
    virtual_ready: bool = False


@dataclass(frozen=True)
class _StageDefinition:
    stage_id: str
    title_vi: str
    tasks: tuple[_TaskDefinition, ...]
    parallel: bool = False


_STAGES = (
    _StageDefinition(
        "PLANNER_INTAKE",
        "Tiếp nhận và lập hồ sơ đánh giá",
        (
            _TaskDefinition(
                "PLANNER_INTAKE",
                "PLANNER",
                "Xác thực hợp đồng và tạo hồ sơ đánh giá",
                WorkflowNode.PLANNER_INTAKE,
            ),
        ),
    ),
    _StageDefinition(
        "INITIAL_RISK_PRE_SCAN",
        "Quét rủi ro sơ bộ",
        (
            _TaskDefinition(
                "INITIAL_RISK_PRE_SCAN",
                "RISK",
                "Quét tín hiệu rủi ro trước đánh giá chuyên môn",
                WorkflowNode.INITIAL_RISK_PRE_SCAN,
            ),
        ),
    ),
    _StageDefinition(
        "INITIAL_ASSESSMENT_PARALLEL",
        "Đánh giá Tài chính và Vận hành song song",
        (
            _TaskDefinition(
                "FINANCE_ASSESSMENT",
                "FINANCE",
                "Đánh giá tài chính",
                WorkflowNode.FINANCE_ASSESSMENT,
            ),
            _TaskDefinition(
                "OPERATIONS_ASSESSMENT",
                "OPERATIONS",
                "Đánh giá vận hành",
                WorkflowNode.OPERATIONS_ASSESSMENT,
            ),
        ),
        parallel=True,
    ),
    _StageDefinition(
        "INITIAL_RISK_FINALIZATION",
        "Hoàn tất đánh giá rủi ro ban đầu",
        (
            _TaskDefinition(
                "INITIAL_RISK_FINALIZATION",
                "RISK",
                "Hợp nhất kết quả Tài chính và Vận hành",
                WorkflowNode.INITIAL_RISK_FINALIZATION,
            ),
        ),
    ),
    _StageDefinition(
        "DECISION_ROUTE_PLANNING",
        "Xác định nhu cầu vốn từ ngân hàng nếu cần",
        (
            _TaskDefinition(
                "DECISION_ROUTE_PLANNING",
                "DECISION",
                "Xác định hợp đồng có cần nguồn vốn hoặc bảo lãnh từ ngân hàng hay không",
                WorkflowNode.DECISION_ROUTE_PLANNING,
            ),
        ),
    ),
    _StageDefinition(
        "BANKING_DISCOVERY_HANDOFF",
        "Bàn giao khảo sát ngân hàng cho Banking Integration Skill",
        (
            _TaskDefinition(
                "BANKING_DISCOVERY_HANDOFF",
                "DECISION",
                "Bàn giao nhu cầu và evidence cho Banking Integration Skill",
                WorkflowNode.BANKING_DISCOVERY_HANDOFF,
            ),
        ),
    ),
    _StageDefinition(
        "BANKING_INTERNAL_DISCOVERY",
        "Khảo sát phương án ngân hàng",
        (
            _TaskDefinition(
                "BANKING_INTERNAL_DISCOVERY",
                "BANKING",
                "Đối chiếu danh mục và lập ma trận phương án",
                WorkflowNode.BANKING_INTERNAL_DISCOVERY,
            ),
        ),
    ),
    _StageDefinition(
        "BANKING_PRECHECK_READINESS",
        "Kiểm tra dữ liệu đầu vào cho precheck",
        (
            _TaskDefinition(
                "BANKING_PRECHECK_READINESS",
                "BANKING",
                "Đối chiếu dữ liệu bắt buộc trước khi chạy precheck",
                WorkflowNode.BANKING_PRECHECK_READINESS,
            ),
        ),
    ),
    _StageDefinition(
        "DECISION_POST_BANKING_REVIEW",
        "Dữ liệu đầu vào có đủ để chạy precheck?",
        (
            _TaskDefinition(
                "DECISION_POST_BANKING_REVIEW",
                "DECISION",
                "Kết luận có phương án nào đủ dữ liệu để chạy precheck hay không",
                WorkflowNode.DECISION_POST_BANKING_REVIEW,
            ),
        ),
    ),
    _StageDefinition(
        "BANKING_PRECHECK_SUBMISSION_PROPOSAL",
        "Chuẩn bị yêu cầu precheck — chưa gửi",
        (
            _TaskDefinition(
                "BANKING_PRECHECK_SUBMISSION_PROPOSAL",
                "BANKING",
                "Tạo chính xác yêu cầu precheck để trình Founder, chưa gửi tới ngân hàng",
                WorkflowNode.BANKING_PRECHECK_SUBMISSION_PROPOSAL,
            ),
        ),
    ),
    _StageDefinition(
        "BANKING_PRECHECK_APPROVAL",
        "Founder duyệt precheck",
        (
            _TaskDefinition(
                "BANKING_PRECHECK_APPROVAL",
                "GOVERNANCE",
                "Founder quyết định có cho phép chạy precheck với ngân hàng hay không",
                protected_action=ProtectedAction.SUBMIT_BANKING_PRECHECK,
            ),
        ),
    ),
    _StageDefinition(
        "BANKING_PRECHECK_EXECUTION",
        "Chạy precheck và nhận phản hồi từ ngân hàng",
        (
            _TaskDefinition(
                "BANKING_PRECHECK_EXECUTION",
                "BANKING",
                "Chạy precheck đã được Founder cho phép và tiếp nhận phản hồi",
                WorkflowNode.BANKING_PRECHECK_EXECUTION,
            ),
        ),
    ),
    _StageDefinition(
        "DECISION_POST_PRECHECK_REVIEW",
        "Đọc kết quả precheck và xác định bước tiếp theo",
        (
            _TaskDefinition(
                "DECISION_POST_PRECHECK_REVIEW",
                "DECISION",
                "Phân loại phản hồi precheck và xác định tuyến xử lý tiếp theo",
                WorkflowNode.DECISION_POST_PRECHECK_REVIEW,
            ),
        ),
    ),
    _StageDefinition(
        "DECISION_DOCUMENT_HANDOFF",
        "Bàn giao yêu cầu chuẩn bị hồ sơ cho Document Skill",
        (
            _TaskDefinition(
                "DECISION_DOCUMENT_HANDOFF",
                "DECISION",
                "Bàn giao yêu cầu và điều kiện hồ sơ cho Document Skill",
                WorkflowNode.DECISION_DOCUMENT_HANDOFF,
            ),
        ),
    ),
    _StageDefinition(
        "DOCUMENT_PREPARATION",
        "Chuẩn bị hồ sơ nội bộ",
        (
            _TaskDefinition(
                "DOCUMENT_PREPARATION",
                "DOCUMENT",
                "Lập checklist, masking và bộ hồ sơ nội bộ",
                WorkflowNode.DOCUMENT_PREPARATION,
            ),
        ),
    ),
    _StageDefinition(
        "INTERNAL_DECISION_PACKAGE_ASSEMBLY",
        "Tổng hợp hồ sơ quyết định nội bộ",
        (
            _TaskDefinition(
                "INTERNAL_DECISION_PACKAGE_ASSEMBLY",
                "DECISION",
                "Hợp nhất các kết quả vào hồ sơ quyết định nội bộ",
                WorkflowNode.INTERNAL_DECISION_PACKAGE_ASSEMBLY,
            ),
        ),
    ),
    _StageDefinition(
        "FINAL_RISK_CHECK",
        "Kiểm tra rủi ro cuối",
        (
            _TaskDefinition(
                "FINAL_RISK_CHECK",
                "RISK",
                "Xác định rủi ro còn lại và biện pháp kiểm soát",
                WorkflowNode.FINAL_RISK_CHECK,
            ),
        ),
    ),
    _StageDefinition(
        "DECISION_CARD_COMPOSITION",
        "Lập Phiếu quyết định",
        (
            _TaskDefinition(
                "DECISION_CARD_COMPOSITION",
                "DECISION",
                "Tổng hợp phân tích và Phiếu quyết định",
                WorkflowNode.DECISION_CARD_COMPOSITION,
            ),
        ),
    ),
    _StageDefinition(
        "FINAL_DECISION_APPROVAL",
        "Founder quyết định",
        (
            _TaskDefinition(
                "FINAL_DECISION_APPROVAL",
                "GOVERNANCE",
                "Ghi nhận quyết định cuối của Founder",
                protected_action=ProtectedAction.CONFIRM_FINAL_CONTRACT_DECISION,
            ),
        ),
    ),
    _StageDefinition(
        "POST_DECISION_UPDATE",
        "Cập nhật sau quyết định",
        (
            _TaskDefinition(
                "POST_DECISION_UPDATE",
                "DECISION",
                "Cập nhật kết quả nghiệp vụ sau quyết định",
                WorkflowNode.POST_DECISION_UPDATE,
            ),
        ),
    ),
    _StageDefinition(
        "EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL",
        "Lập đề xuất gửi hồ sơ ra bên ngoài",
        (
            _TaskDefinition(
                "EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL",
                "DECISION",
                "Tạo đề xuất gửi hồ sơ, chưa thực hiện gửi",
                WorkflowNode.EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL,
            ),
        ),
    ),
    _StageDefinition(
        "EXTERNAL_RELEASE_APPROVAL",
        "Phê duyệt quyền gửi hồ sơ ra bên ngoài",
        (
            _TaskDefinition(
                "EXTERNAL_RELEASE_APPROVAL",
                "GOVERNANCE",
                "Founder quyết định có cho phép phát hành hồ sơ",
                protected_action=ProtectedAction.SEND_DOCUMENT_TO_EXTERNAL_PARTNER,
            ),
        ),
    ),
    _StageDefinition(
        "READY_FOR_EXTERNAL_SUBMISSION",
        "Sẵn sàng gửi hồ sơ ra bên ngoài",
        (
            _TaskDefinition(
                "READY_FOR_EXTERNAL_SUBMISSION",
                "WORKFLOW",
                "Xác nhận hồ sơ sẵn sàng; hệ thống chưa tự gửi",
                virtual_ready=True,
            ),
        ),
    ),
)


_STATUS_LABELS = {
    DashboardTaskStatus.NOT_STARTED: "Chưa bắt đầu",
    DashboardTaskStatus.RUNNING: "Đang thực hiện",
    DashboardTaskStatus.WAITING_FOR_DEPENDENCIES: "Đang chờ bước phụ thuộc",
    DashboardTaskStatus.WAITING_FOR_INPUT: "Đang chờ bổ sung dữ liệu",
    DashboardTaskStatus.WAITING_FOR_APPROVAL: "Đang chờ phê duyệt",
    DashboardTaskStatus.COMPLETED: "Đã hoàn tất",
    DashboardTaskStatus.COMPLETED_WITH_WARNINGS: "Đã hoàn tất, có lưu ý",
    DashboardTaskStatus.REJECTED: "Đã bị từ chối",
    DashboardTaskStatus.EXPIRED: "Yêu cầu đã hết hiệu lực",
    DashboardTaskStatus.BLOCKED: "Đã bị chặn",
    DashboardTaskStatus.FAILED_SAFE: "Đã dừng an toàn",
    DashboardTaskStatus.NOT_APPLICABLE: "Không áp dụng",
}

_EXECUTION_LABELS = {
    WorkflowStatus.PENDING: "Chưa bắt đầu",
    WorkflowStatus.RUNNING: "Đang thực hiện",
    WorkflowStatus.COMPLETED: "Lượt xử lý đã kết thúc",
    WorkflowStatus.WAITING_FOR_DEPENDENCIES: "Đang chờ bước phụ thuộc",
    WorkflowStatus.WAITING_FOR_INPUT: "Đang chờ bổ sung dữ liệu",
    WorkflowStatus.WAITING_FOR_APPROVAL: "Đang chờ phê duyệt",
    WorkflowStatus.BLOCKED: "Lượt xử lý đã bị chặn",
    WorkflowStatus.FAILED_SAFE: "Lượt xử lý đã dừng an toàn",
}

_BUSINESS_LABELS = {
    DashboardBusinessStatus.ASSESSMENT_IN_PROGRESS: "Đang đánh giá cơ hội",
    DashboardBusinessStatus.WAITING_FOR_INPUT: "Cần bổ sung dữ liệu",
    DashboardBusinessStatus.WAITING_FOR_BANKING_APPROVAL: (
        "Đang chờ quyết định cho phép kiểm tra sơ bộ với ngân hàng"
    ),
    DashboardBusinessStatus.PREPARING_DECISION: "Đang chuẩn bị đề xuất quyết định",
    DashboardBusinessStatus.WAITING_FOR_FINAL_DECISION: (
        "Phiếu quyết định đã sẵn sàng, đang chờ Founder"
    ),
    DashboardBusinessStatus.WAITING_FOR_EXTERNAL_RELEASE_APPROVAL: (
        "Đang chờ cho phép phát hành hồ sơ ra bên ngoài"
    ),
    DashboardBusinessStatus.NOT_EVALUABLE: "Chưa đủ cơ sở để đưa ra đề xuất",
    DashboardBusinessStatus.NEGOTIATION_IN_PROGRESS: "Đang thực hiện đàm phán",
    DashboardBusinessStatus.ACCEPTED: "Hợp đồng đã được chấp nhận",
    DashboardBusinessStatus.NOT_ACCEPTED: "Hợp đồng không được chấp nhận",
    DashboardBusinessStatus.READY_FOR_EXTERNAL_SUBMISSION: (
        "Hồ sơ sẵn sàng để gửi ra bên ngoài"
    ),
    DashboardBusinessStatus.BLOCKED: "Cơ hội đang bị chặn",
    DashboardBusinessStatus.FAILED_SAFE: "Đánh giá đã dừng an toàn",
}

_NODE_STATUS_MAP = {
    WorkflowNodeStatus.PENDING: DashboardTaskStatus.NOT_STARTED,
    WorkflowNodeStatus.RUNNING: DashboardTaskStatus.RUNNING,
    WorkflowNodeStatus.WAITING_FOR_DEPENDENCIES: (
        DashboardTaskStatus.WAITING_FOR_DEPENDENCIES
    ),
    WorkflowNodeStatus.WAITING_FOR_INPUT: DashboardTaskStatus.WAITING_FOR_INPUT,
    WorkflowNodeStatus.WAITING_FOR_APPROVAL: DashboardTaskStatus.WAITING_FOR_APPROVAL,
    WorkflowNodeStatus.COMPLETED: DashboardTaskStatus.COMPLETED,
    WorkflowNodeStatus.COMPLETED_WITH_WARNINGS: (
        DashboardTaskStatus.COMPLETED_WITH_WARNINGS
    ),
    WorkflowNodeStatus.BLOCKED: DashboardTaskStatus.BLOCKED,
    WorkflowNodeStatus.FAILED_SAFE: DashboardTaskStatus.FAILED_SAFE,
}

_RECOMMENDATION_LABELS = {
    DecisionRecommendation.ACCEPT: "Chấp nhận",
    DecisionRecommendation.NEGOTIATE_CONDITIONS_TO_ACCEPT: (
        "Đàm phán điều kiện trước khi chấp nhận"
    ),
    DecisionRecommendation.DO_NOT_ACCEPT: "Không chấp nhận",
    DecisionRecommendation.NOT_EVALUABLE: "Chưa đủ cơ sở để đề xuất",
}

_READINESS_LABELS = {
    ReadinessStatus.READY: "Dữ liệu đã sẵn sàng cho đánh giá ban đầu",
    ReadinessStatus.READY_WITH_WARNINGS: (
        "Dữ liệu đã sẵn sàng nhưng còn lưu ý không gây dừng"
    ),
    ReadinessStatus.BLOCKED: "Dữ liệu còn thiếu và đang gây tạm dừng",
}

_CURRENT_STAGE_LABELS = {
    definition.stage_id: definition.title_vi for definition in _STAGES
} | {
    WorkflowNode.DATASET_INGESTION.value: "Kiểm tra bộ dữ liệu đầu vào",
    WorkflowNode.INITIAL_ASSESSMENT.value: "Đánh giá Tài chính và Vận hành song song",
    WorkflowNode.RISK_WAITING_FOR_FACTS.value: "Rủi ro đang chờ số liệu chuyên môn",
    WorkflowNode.RISK_FINALIZING.value: "Đang hoàn tất đánh giá rủi ro ban đầu",
    WorkflowNode.APPROVAL_GATE.value: "Cổng phê duyệt đang hoạt động",
    WorkflowNode.WAITING_FOR_APPROVAL.value: "Đang chờ Founder phê duyệt",
    WorkflowNode.BANKING_INPUT_SUPPLEMENT.value: "Tiếp nhận dữ liệu ngân hàng bổ sung",
    WorkflowNode.BANKING_PRECHECK_EVIDENCE_INTAKE.value: (
        "Tiếp nhận bằng chứng kiểm tra sơ bộ bổ sung"
    ),
    WorkflowNode.DOCUMENT_INPUT_INTAKE.value: "Tiếp nhận tài liệu bổ sung",
    WorkflowNode.INTERNAL_DECISION_PACKAGE_READY.value: (
        "Hồ sơ quyết định nội bộ đã sẵn sàng"
    ),
    WorkflowNode.FINAL_RISK_READY.value: "Kết quả kiểm tra rủi ro cuối đã sẵn sàng",
    WorkflowNode.DECISION_CARD_READY.value: "Phiếu quyết định đã sẵn sàng",
    WorkflowNode.NEGOTIATION_IN_PROGRESS.value: "Đang thực hiện đàm phán",
    WorkflowNode.FINAL_DECISION_ACCEPTED.value: "Hợp đồng đã được chấp nhận",
    WorkflowNode.FINAL_DECISION_NOT_ACCEPTED.value: "Hợp đồng không được chấp nhận",
    WorkflowNode.READY_FOR_EXTERNAL_SUBMISSION.value: (
        "Hồ sơ sẵn sàng để gửi ra bên ngoài"
    ),
    WorkflowNode.BANKING_PRECHECK_RETRY_REQUIRED.value: (
        "Cần thực hiện lại bước kiểm tra sơ bộ sau khi bổ sung bằng chứng"
    ),
}


def build_dashboard_projection(
    *,
    summary: WorkflowRunSummary,
    artifacts: tuple[ArtifactEnvelope, ...],
    approvals: tuple[ApprovalRequest, ...],
) -> DashboardWorkflowProjection:
    """Create a chronological projection using only outputs owned by this run."""

    nodes = {item.node: item for item in summary.nodes}
    output_ids = {
        artifact_id for node in summary.nodes for artifact_id in node.output_artifact_ids
    }
    run_artifacts = tuple(
        item for item in artifacts if item.artifact_id in output_ids
    )
    artifacts_by_id = {item.artifact_id: item for item in run_artifacts}
    run_approvals = tuple(
        sorted(
            (
                item
                for item in approvals
                if item.workflow_run_id == summary.workflow_run_id
            ),
            key=lambda item: (item.created_at, item.request_id),
        )
    )
    approvals_by_action = {
        action: tuple(
            item for item in run_approvals if item.command.action_type is action
        )
        for action in ProtectedAction
    }
    external_release_required = _external_release_required(
        nodes=nodes,
        artifacts_by_id=artifacts_by_id,
    )
    task_context = _TaskContext(
        summary=summary,
        nodes=nodes,
        artifacts_by_id=artifacts_by_id,
        approvals_by_action=approvals_by_action,
        external_release_required=external_release_required,
    )
    stages = tuple(
        _project_stage(index=index, definition=definition, context=task_context)
        for index, definition in enumerate(_STAGES, start=1)
    )
    tasks = tuple(task for stage in stages for task in stage.tasks)
    resolved = sum(
        task.status
        in {
            DashboardTaskStatus.COMPLETED,
            DashboardTaskStatus.COMPLETED_WITH_WARNINGS,
            DashboardTaskStatus.REJECTED,
            DashboardTaskStatus.EXPIRED,
            DashboardTaskStatus.NOT_APPLICABLE,
        }
        for task in tasks
    )
    business_status = _business_status(summary)
    decision_card = _decision_card_summary(
        summary=summary,
        nodes=nodes,
        artifacts_by_id=artifacts_by_id,
    )
    decision_card_artifact = (
        artifacts_by_id.get(decision_card.artifact_id)
        if decision_card.artifact_id is not None
        else None
    )
    return DashboardWorkflowProjection(
        workflow_run_id=summary.workflow_run_id,
        evaluation_case_id=summary.evaluation_case_id,
        contract_id=summary.contract_id,
        execution_status=summary.status,
        execution_status_label_vi=_EXECUTION_LABELS[summary.status],
        business_status=business_status,
        business_status_label_vi=_BUSINESS_LABELS[business_status],
        current_stage=summary.current_stage,
        current_stage_label_vi=_CURRENT_STAGE_LABELS.get(
            summary.current_stage,
            "Giai đoạn kỹ thuật chưa có nhãn trình bày",
        ),
        progress=DashboardProgress(
            resolved_task_count=resolved,
            total_task_count=len(tasks),
            percent=round(resolved / len(tasks) * 100),
        ),
        stages=stages,
        run_artifacts=tuple(
            DashboardArtifactReference(
                artifact_id=item.artifact_id,
                artifact_type=item.artifact_type,
                version=item.version,
                validation_status=item.validation_status,
            )
            for item in run_artifacts
        ),
        approval_request_ids=tuple(item.request_id for item in run_approvals),
        pending_interactions=_pending_interactions(
            summary=summary,
            run_approvals=run_approvals,
            decision_card=decision_card,
            decision_card_artifact=decision_card_artifact,
        ),
        input=_input_summary(
            summary=summary,
            nodes=nodes,
            artifacts_by_id=artifacts_by_id,
        ),
        metrics=_dashboard_metrics(
            nodes=nodes,
            artifacts_by_id=artifacts_by_id,
        ),
        decision_card=decision_card,
    )


@dataclass(frozen=True)
class _TaskContext:
    summary: WorkflowRunSummary
    nodes: dict[WorkflowNode, WorkflowNodeState]
    artifacts_by_id: dict[str, ArtifactEnvelope]
    approvals_by_action: dict[ProtectedAction, tuple[ApprovalRequest, ...]]
    external_release_required: bool | None


def _project_stage(
    *,
    index: int,
    definition: _StageDefinition,
    context: _TaskContext,
) -> DashboardStage:
    tasks = tuple(_project_task(item, context) for item in definition.tasks)
    applicability = _stage_applicability(tasks)
    status = _stage_status(tasks)
    return DashboardStage(
        stage_id=definition.stage_id,
        sequence=index,
        title_vi=definition.title_vi,
        parallel=definition.parallel,
        applicability=applicability,
        status=status,
        status_label_vi=_STATUS_LABELS[status],
        tasks=tasks,
    )


def _project_task(
    definition: _TaskDefinition,
    context: _TaskContext,
) -> DashboardTask:
    applicability, reason = _task_applicability(definition, context)
    node = context.nodes.get(definition.node) if definition.node is not None else None
    artifact_ids = tuple(
        artifact_id
        for artifact_id in (node.output_artifact_ids if node is not None else ())
        if artifact_id in context.artifacts_by_id
    )
    approval_requests = (
        context.approvals_by_action.get(definition.protected_action, ())
        if definition.protected_action is not None
        else ()
    )
    resolution_status: str | None = None
    if applicability is DashboardApplicability.NOT_APPLICABLE:
        status = DashboardTaskStatus.NOT_APPLICABLE
    elif definition.protected_action is not None:
        status, resolution_status = _approval_task_status(
            approval_requests,
            definition.protected_action,
            context.summary,
        )
    elif definition.virtual_ready:
        status = (
            DashboardTaskStatus.COMPLETED
            if context.summary.ready_for_external_submission
            else DashboardTaskStatus.NOT_STARTED
        )
    elif node is not None:
        status = _NODE_STATUS_MAP[node.status]
    else:
        status = _current_stage_status(definition, context.summary)
    return DashboardTask(
        task_id=definition.task_id,
        owner_id=definition.owner_id,
        title_vi=definition.title_vi,
        applicability=applicability,
        applicability_reason_vi=reason,
        status=status,
        status_label_vi=_STATUS_LABELS[status],
        artifact_ids=artifact_ids,
        approval_request_ids=tuple(item.request_id for item in approval_requests),
        resolution_status=resolution_status,
    )


def _task_applicability(
    definition: _TaskDefinition,
    context: _TaskContext,
) -> tuple[DashboardApplicability, str]:
    if definition.node is not None and definition.node in context.nodes:
        return DashboardApplicability.APPLICABLE, "Bước đã được tạo trong lượt xử lý này."
    if definition.protected_action is not None and context.approvals_by_action.get(
        definition.protected_action
    ):
        return DashboardApplicability.APPLICABLE, "Cổng kiểm soát đã được kích hoạt."

    task_id = definition.task_id
    route = context.summary.decision_route_outcome
    banking_base = {
        "BANKING_DISCOVERY_HANDOFF",
        "BANKING_INTERNAL_DISCOVERY",
        "BANKING_PRECHECK_READINESS",
        "DECISION_POST_BANKING_REVIEW",
    }
    banking_precheck = {
        "BANKING_PRECHECK_SUBMISSION_PROPOSAL",
        "BANKING_PRECHECK_APPROVAL",
    }
    after_banking_approval = {
        "BANKING_PRECHECK_EXECUTION",
        "DECISION_POST_PRECHECK_REVIEW",
    }
    document_tasks = {"DECISION_DOCUMENT_HANDOFF", "DOCUMENT_PREPARATION"}
    if task_id in banking_base | banking_precheck | after_banking_approval | document_tasks:
        if route is DecisionRouteOutcome.DIRECT_INTERNAL_DECISION:
            return (
                DashboardApplicability.NOT_APPLICABLE,
                "Tuyến quyết định đi thẳng tới hồ sơ nội bộ, không cần ngân hàng.",
            )
        if route is None:
            return (
                DashboardApplicability.UNDETERMINED,
                "Chưa có kết quả định tuyến để xác định nhánh ngân hàng.",
            )
    if task_id in banking_base:
        return DashboardApplicability.APPLICABLE, "Hợp đồng đi qua tuyến ngân hàng."

    post_banking = context.summary.decision_post_banking_outcome
    if task_id in banking_precheck | after_banking_approval | document_tasks:
        if post_banking in {
            DecisionPostBankingOutcome.NO_PRECHECK_PATH,
            DecisionPostBankingOutcome.NO_VIABLE_OPTION,
            DecisionPostBankingOutcome.UNSUPPORTED_PRECHECK_MAPPING,
        }:
            return (
                DashboardApplicability.NOT_APPLICABLE,
                "Rà soát sau khảo sát không mở tuyến kiểm tra sơ bộ với ngân hàng.",
            )
        if post_banking in {None, DecisionPostBankingOutcome.BANKING_INPUT_REQUIRED}:
            return (
                DashboardApplicability.UNDETERMINED,
                "Cần hoàn tất rà soát sau khảo sát trước khi xác định bước này.",
            )
    if task_id in banking_precheck:
        return DashboardApplicability.APPLICABLE, (
            "Tuyến kiểm tra sơ bộ với ngân hàng đã sẵn sàng."
        )

    banking_approval = _latest_approval(
        context.approvals_by_action.get(ProtectedAction.SUBMIT_BANKING_PRECHECK, ())
    )
    if (
        task_id in after_banking_approval | document_tasks
        and banking_approval is not None
        and banking_approval.status
        in {
            ApprovalRequestStatus.REJECTED,
            ApprovalRequestStatus.EXPIRED,
        }
    ):
        approval_resolution = (
            "Founder đã từ chối cho phép gửi yêu cầu kiểm tra sơ bộ tới ngân hàng"
            if banking_approval.status is ApprovalRequestStatus.REJECTED
            else "Yêu cầu phê duyệt gửi kiểm tra sơ bộ tới ngân hàng đã hết hạn"
        )
        consequence_by_task = {
            "BANKING_PRECHECK_EXECUTION": (
                "không có yêu cầu nào được gửi tới ngân hàng."
            ),
            "DECISION_POST_PRECHECK_REVIEW": (
                "không có kết quả ngân hàng để rà soát."
            ),
            "DECISION_DOCUMENT_HANDOFF": (
                "không có phương án đã được rà soát để bàn giao chuẩn bị hồ sơ."
            ),
            "DOCUMENT_PREPARATION": (
                "không có bàn giao chuẩn bị hồ sơ để thực hiện."
            ),
        }
        return (
            DashboardApplicability.NOT_APPLICABLE,
            f"{approval_resolution}; {consequence_by_task[task_id]}",
        )
    if task_id in after_banking_approval:
        return DashboardApplicability.APPLICABLE, (
            "Bước thuộc tuyến kiểm tra sơ bộ với ngân hàng có quản trị."
        )

    if task_id in document_tasks:
        post_precheck = context.summary.decision_post_precheck_outcome
        if post_precheck is DecisionPostPrecheckOutcome.CONDITIONAL_OPTIONS_AVAILABLE:
            return (
                DashboardApplicability.APPLICABLE,
                "Có phương án có điều kiện cần chuẩn bị hồ sơ.",
            )
        if post_precheck in {None, DecisionPostPrecheckOutcome.FOLLOW_UP_EVIDENCE_REQUIRED}:
            return (
                DashboardApplicability.UNDETERMINED,
                "Chưa có kết quả kiểm tra sơ bộ với ngân hàng để xác định nhu cầu hồ sơ.",
            )
        return (
            DashboardApplicability.NOT_APPLICABLE,
            "Kết quả kiểm tra sơ bộ với ngân hàng không yêu cầu chuẩn bị hồ sơ.",
        )

    if task_id in {"FINAL_DECISION_APPROVAL", "POST_DECISION_UPDATE"}:
        recommendation = context.summary.decision_recommendation
        if recommendation is DecisionRecommendation.NOT_EVALUABLE:
            return (
                DashboardApplicability.NOT_APPLICABLE,
                "Phiếu quyết định chưa đủ cơ sở để mở quyết định cuối.",
            )
        if recommendation is None:
            return (
                DashboardApplicability.UNDETERMINED,
                "Chưa có Phiếu quyết định để xác định bước này.",
            )
        if task_id == "POST_DECISION_UPDATE":
            final_approval = _latest_approval(
                context.approvals_by_action.get(
                    ProtectedAction.CONFIRM_FINAL_CONTRACT_DECISION,
                    (),
                )
            )
            if final_approval is not None and final_approval.status in {
                ApprovalRequestStatus.REJECTED,
                ApprovalRequestStatus.EXPIRED,
            }:
                return (
                    DashboardApplicability.NOT_APPLICABLE,
                    "Quyết định cuối không được xác nhận nên không có cập nhật sau quyết định.",
                )
        return DashboardApplicability.APPLICABLE, "Phiếu quyết định có thể được xem xét."

    if task_id in {
        "EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL",
        "EXTERNAL_RELEASE_APPROVAL",
        "READY_FOR_EXTERNAL_SUBMISSION",
    }:
        if (
            context.summary.decision_recommendation
            is DecisionRecommendation.NOT_EVALUABLE
        ):
            return (
                DashboardApplicability.NOT_APPLICABLE,
                "Phiếu quyết định chưa đủ cơ sở nên không mở tuyến phát hành bên ngoài.",
            )
        if context.external_release_required is None:
            return (
                DashboardApplicability.UNDETERMINED,
                "Chưa có cập nhật sau quyết định để xác định nhu cầu phát hành hồ sơ.",
            )
        if not context.external_release_required:
            return (
                DashboardApplicability.NOT_APPLICABLE,
                "Kết quả sau quyết định không yêu cầu phát hành hồ sơ ra bên ngoài.",
            )
        external_approval = _latest_approval(
            context.approvals_by_action.get(
                ProtectedAction.SEND_DOCUMENT_TO_EXTERNAL_PARTNER,
                (),
            )
        )
        if (
            task_id == "READY_FOR_EXTERNAL_SUBMISSION"
            and external_approval is not None
            and external_approval.status
            in {
                ApprovalRequestStatus.REJECTED,
                ApprovalRequestStatus.EXPIRED,
            }
        ):
            return (
                DashboardApplicability.NOT_APPLICABLE,
                "Quyền phát hành hồ sơ không được phê duyệt.",
            )
        return (
            DashboardApplicability.APPLICABLE,
            "Quyết định đã chấp nhận và yêu cầu phát hành hồ sơ.",
        )

    return DashboardApplicability.APPLICABLE, "Bước bắt buộc của quy trình chính."


def _approval_task_status(
    requests: tuple[ApprovalRequest, ...],
    action: ProtectedAction,
    summary: WorkflowRunSummary,
) -> tuple[DashboardTaskStatus, str | None]:
    latest = _latest_approval(requests)
    if latest is not None:
        mapping = {
            ApprovalRequestStatus.PENDING: DashboardTaskStatus.WAITING_FOR_APPROVAL,
            ApprovalRequestStatus.AUTHORIZED_WITHOUT_HUMAN: DashboardTaskStatus.COMPLETED,
            ApprovalRequestStatus.APPROVED: DashboardTaskStatus.COMPLETED,
            ApprovalRequestStatus.REJECTED: DashboardTaskStatus.REJECTED,
            ApprovalRequestStatus.EXPIRED: DashboardTaskStatus.EXPIRED,
        }
        return mapping[latest.status], latest.status.value
    if (
        summary.status is WorkflowStatus.WAITING_FOR_APPROVAL
        and summary.blocked_action is action
    ):
        return DashboardTaskStatus.WAITING_FOR_APPROVAL, None
    return DashboardTaskStatus.NOT_STARTED, None


def _latest_approval(
    requests: tuple[ApprovalRequest, ...],
) -> ApprovalRequest | None:
    return requests[-1] if requests else None


def _current_stage_status(
    definition: _TaskDefinition,
    summary: WorkflowRunSummary,
) -> DashboardTaskStatus:
    if definition.node is None or summary.current_stage != definition.node.value:
        return DashboardTaskStatus.NOT_STARTED
    mapping = {
        WorkflowStatus.PENDING: DashboardTaskStatus.NOT_STARTED,
        WorkflowStatus.RUNNING: DashboardTaskStatus.RUNNING,
        WorkflowStatus.WAITING_FOR_DEPENDENCIES: (
            DashboardTaskStatus.WAITING_FOR_DEPENDENCIES
        ),
        WorkflowStatus.WAITING_FOR_INPUT: DashboardTaskStatus.WAITING_FOR_INPUT,
        WorkflowStatus.WAITING_FOR_APPROVAL: DashboardTaskStatus.WAITING_FOR_APPROVAL,
        WorkflowStatus.BLOCKED: DashboardTaskStatus.BLOCKED,
        WorkflowStatus.FAILED_SAFE: DashboardTaskStatus.FAILED_SAFE,
        WorkflowStatus.COMPLETED: DashboardTaskStatus.COMPLETED,
    }
    return mapping[summary.status]


def _stage_applicability(
    tasks: tuple[DashboardTask, ...],
) -> DashboardApplicability:
    values = {item.applicability for item in tasks}
    if values == {DashboardApplicability.NOT_APPLICABLE}:
        return DashboardApplicability.NOT_APPLICABLE
    if DashboardApplicability.APPLICABLE in values:
        return DashboardApplicability.APPLICABLE
    return DashboardApplicability.UNDETERMINED


def _stage_status(tasks: tuple[DashboardTask, ...]) -> DashboardTaskStatus:
    values = {item.status for item in tasks}
    priorities = (
        DashboardTaskStatus.FAILED_SAFE,
        DashboardTaskStatus.BLOCKED,
        DashboardTaskStatus.WAITING_FOR_INPUT,
        DashboardTaskStatus.WAITING_FOR_APPROVAL,
        DashboardTaskStatus.WAITING_FOR_DEPENDENCIES,
        DashboardTaskStatus.RUNNING,
    )
    for value in priorities:
        if value in values:
            return value
    if values == {DashboardTaskStatus.NOT_APPLICABLE}:
        return DashboardTaskStatus.NOT_APPLICABLE
    resolved = {
        DashboardTaskStatus.COMPLETED,
        DashboardTaskStatus.COMPLETED_WITH_WARNINGS,
        DashboardTaskStatus.REJECTED,
        DashboardTaskStatus.EXPIRED,
        DashboardTaskStatus.NOT_APPLICABLE,
    }
    if values.issubset(resolved):
        if DashboardTaskStatus.COMPLETED_WITH_WARNINGS in values:
            return DashboardTaskStatus.COMPLETED_WITH_WARNINGS
        if DashboardTaskStatus.REJECTED in values:
            return DashboardTaskStatus.REJECTED
        if DashboardTaskStatus.EXPIRED in values:
            return DashboardTaskStatus.EXPIRED
        return DashboardTaskStatus.COMPLETED
    return DashboardTaskStatus.NOT_STARTED


def _business_status(summary: WorkflowRunSummary) -> DashboardBusinessStatus:
    if summary.status is WorkflowStatus.BLOCKED:
        return DashboardBusinessStatus.BLOCKED
    if summary.status is WorkflowStatus.FAILED_SAFE:
        return DashboardBusinessStatus.FAILED_SAFE
    if summary.status is WorkflowStatus.WAITING_FOR_INPUT:
        return DashboardBusinessStatus.WAITING_FOR_INPUT
    if summary.status is WorkflowStatus.WAITING_FOR_APPROVAL:
        if summary.blocked_action is ProtectedAction.SUBMIT_BANKING_PRECHECK:
            return DashboardBusinessStatus.WAITING_FOR_BANKING_APPROVAL
        if summary.blocked_action is ProtectedAction.SEND_DOCUMENT_TO_EXTERNAL_PARTNER:
            return DashboardBusinessStatus.WAITING_FOR_EXTERNAL_RELEASE_APPROVAL
        return DashboardBusinessStatus.WAITING_FOR_FINAL_DECISION
    if summary.current_stage == WorkflowNode.NEGOTIATION_IN_PROGRESS.value:
        return DashboardBusinessStatus.NEGOTIATION_IN_PROGRESS
    if summary.current_stage == WorkflowNode.FINAL_DECISION_ACCEPTED.value:
        return DashboardBusinessStatus.ACCEPTED
    if summary.current_stage == WorkflowNode.FINAL_DECISION_NOT_ACCEPTED.value:
        return DashboardBusinessStatus.NOT_ACCEPTED
    if summary.current_stage == WorkflowNode.READY_FOR_EXTERNAL_SUBMISSION.value:
        return DashboardBusinessStatus.READY_FOR_EXTERNAL_SUBMISSION
    if summary.decision_recommendation is DecisionRecommendation.NOT_EVALUABLE:
        return DashboardBusinessStatus.NOT_EVALUABLE
    if summary.internal_decision_package_ready:
        return DashboardBusinessStatus.PREPARING_DECISION
    return DashboardBusinessStatus.ASSESSMENT_IN_PROGRESS


def _pending_interactions(
    *,
    summary: WorkflowRunSummary,
    run_approvals: tuple[ApprovalRequest, ...],
    decision_card: DashboardDecisionCardSummary,
    decision_card_artifact: ArtifactEnvelope | None,
) -> tuple[DashboardPendingInteraction, ...]:
    interactions: list[DashboardPendingInteraction] = []
    pending_ids = set(summary.pending_approval_ids)
    for approval in run_approvals:
        if (
            approval.status is not ApprovalRequestStatus.PENDING
            or approval.request_id not in pending_ids
        ):
            continue
        action = approval.command.action_type
        interactions.append(
            DashboardPendingInteraction(
                interaction_type=DashboardInteractionType.APPROVAL,
                title_vi=_approval_title(action),
                instruction_vi=(
                    "Xem nội dung và kết quả liên quan trước khi phê duyệt hoặc từ chối."
                ),
                approval_request_ids=(approval.request_id,),
                protected_action=action,
                subject_artifact_id=approval.subject_artifact_id,
                subject_artifact_version=approval.subject_artifact_version,
                endpoint=f"/api/approval-requests/{approval.request_id}/decision",
                required_fields=("decision", "decided_by", "reason"),
            )
        )
    if (
        decision_card.available
        and decision_card.recommendation is DecisionRecommendation.NOT_EVALUABLE
        and decision_card.artifact_id is not None
        and decision_card_artifact is not None
        and decision_card_artifact.artifact_id == decision_card.artifact_id
        and decision_card_artifact.artifact_type is ArtifactType.DECISION_CARD
    ):
        interactions.append(
            DashboardPendingInteraction(
                interaction_type=DashboardInteractionType.NOT_EVALUABLE_REVIEW,
                title_vi="Xem Phiếu quyết định chưa đủ cơ sở đánh giá",
                instruction_vi=(
                    "Phiếu quyết định hiện chưa đủ cơ sở để đưa ra đề xuất. "
                    "Đây là chế độ chỉ xem; hệ thống không yêu cầu hoặc cho phép "
                    "phê duyệt hợp đồng từ trạng thái này. Vì vậy, bước "
                    "phê duyệt cuối và các bước sau quyết định không được mở."
                ),
                subject_artifact_id=decision_card_artifact.artifact_id,
                subject_artifact_version=decision_card_artifact.version,
            )
        )
    if summary.status is not WorkflowStatus.WAITING_FOR_INPUT:
        return tuple(interactions)
    request_ids = summary.pending_missing_data_ids
    if summary.current_stage == WorkflowNode.DECISION_POST_BANKING_REVIEW.value:
        interaction_type = DashboardInteractionType.BANKING_AMOUNT_INPUT
        title = "Bổ sung số tiền yêu cầu cho phương án ngân hàng"
        instruction = "Nhập số tiền VND và ghi chú nghiệp vụ cho yêu cầu đang chờ."
        endpoint = (
            f"/api/cases/{summary.evaluation_case_id}/banking/input-supplements"
            if summary.evaluation_case_id is not None
            else None
        )
        fields = (
            "workflow_run_id",
            "missing_request_id",
            "requested_amount",
            "requested_amount_currency",
            "evidence_note",
        )
    elif summary.current_stage == WorkflowNode.DECISION_POST_PRECHECK_REVIEW.value:
        interaction_type = DashboardInteractionType.BANKING_PRECHECK_EVIDENCE
        title = "Bổ sung tham chiếu cho kết quả kiểm tra sơ bộ với ngân hàng"
        instruction = "Cung cấp mã tham chiếu bằng chứng và ghi chú; không tải dữ liệu thô."
        endpoint = (
            f"/api/cases/{summary.evaluation_case_id}/banking/"
            "precheck-evidence-supplements"
            if summary.evaluation_case_id is not None
            else None
        )
        fields = (
            "workflow_run_id",
            "missing_request_id",
            "evidence_reference_id",
            "evidence_note",
        )
    elif summary.current_stage == WorkflowNode.DOCUMENT_PREPARATION.value:
        interaction_type = DashboardInteractionType.DOCUMENT_EVIDENCE
        title = "Bổ sung hồ sơ bắt buộc"
        instruction = (
            "Tải lên đúng tệp PDF hoặc DOCX đang được yêu cầu. Quy trình sẽ tạm dừng "
            "an toàn và không đi tiếp cho đến khi đủ Đơn đề nghị bảo lãnh thực hiện "
            "và Tài liệu chứng minh nguồn bù dòng tiền."
        )
        endpoint = (
            f"/api/cases/{summary.evaluation_case_id}/documents/evidence-supplements"
            if summary.evaluation_case_id is not None
            else None
        )
        fields = (
            "workflow_run_id",
            "missing_request_id",
            "document_reference_id",
            "content_sha256",
            "document_type",
            "evidence_note",
        )
    else:
        interaction_type = DashboardInteractionType.UNSUPPORTED_INPUT
        title = "Cần bổ sung dữ liệu qua quy trình nghiệp vụ"
        instruction = (
            "Chưa có biểu mẫu dashboard an toàn cho loại dữ liệu này; hệ thống không tự suy đoán."
        )
        endpoint = None
        fields = ()
    interactions.append(
        DashboardPendingInteraction(
            interaction_type=interaction_type,
            title_vi=title,
            instruction_vi=instruction,
            request_ids=request_ids,
            endpoint=endpoint,
            required_fields=fields,
        )
    )
    return tuple(interactions)


def _approval_title(action: ProtectedAction) -> str:
    return {
        ProtectedAction.SUBMIT_BANKING_PRECHECK: (
            "Cho phép gửi yêu cầu kiểm tra sơ bộ tới ngân hàng"
        ),
        ProtectedAction.CONFIRM_FINAL_CONTRACT_DECISION: (
            "Xác nhận quyết định cuối đối với hợp đồng"
        ),
        ProtectedAction.SEND_DOCUMENT_TO_EXTERNAL_PARTNER: (
            "Cho phép phát hành hồ sơ cho đối tác bên ngoài"
        ),
        ProtectedAction.COMMIT_LARGE_FINANCIAL_DECISION: (
            "Xác nhận cam kết tài chính có kiểm soát"
        ),
    }[action]


def _input_summary(
    *,
    summary: WorkflowRunSummary,
    nodes: dict[WorkflowNode, WorkflowNodeState],
    artifacts_by_id: dict[str, ArtifactEnvelope],
) -> DashboardInputSummary:
    planner_node = nodes.get(WorkflowNode.PLANNER_INTAKE)
    case_artifact = _node_artifact(
        node=planner_node,
        artifacts_by_id=artifacts_by_id,
        artifact_type=ArtifactType.EVALUATION_CASE,
    )
    result_artifact = _node_artifact(
        node=planner_node,
        artifacts_by_id=artifacts_by_id,
        artifact_type=ArtifactType.PLANNER_RESULT,
    )
    planner_result = (
        PlannerResult.model_validate(result_artifact.payload)
        if result_artifact is not None
        else None
    )
    evaluation_case = (
        EvaluationCase.model_validate(case_artifact.payload)
        if case_artifact is not None
        else planner_result.evaluation_case
        if planner_result is not None
        else None
    )
    if (
        evaluation_case is None
        or evaluation_case.evaluation_case_id != summary.evaluation_case_id
        or evaluation_case.contract_id != summary.contract_id
    ):
        return DashboardInputSummary(
            available=False,
            readiness_label_vi="Planner chưa tạo dữ liệu đầu vào cho lượt xử lý này",
        )
    readiness = planner_result.data_readiness if planner_result is not None else None
    requirements = tuple(
        DashboardContractRequirement(
            requirement_type=item.requirement_type,
            certainty=item.certainty,
            requested_amount=item.requested_amount,
            requested_amount_currency=item.requested_amount_currency,
            credit_case_id=item.credit_case_id,
        )
        for item in evaluation_case.contract_requirements
    )
    return DashboardInputSummary(
        available=True,
        readiness_status=readiness.status if readiness is not None else None,
        readiness_label_vi=(
            _READINESS_LABELS[readiness.status]
            if readiness is not None
            else "Hồ sơ đã được tạo; trạng thái sẵn sàng chưa có"
        ),
        blocking_missing_count=(
            len(planner_result.missing_data_requests)
            if planner_result is not None
            else 0
        ),
        warning_count=len(planner_result.warnings) if planner_result is not None else 0,
        linked_customer_count=1,
        linked_order_count=len(evaluation_case.related_order_ids),
        linked_invoice_count=len(evaluation_case.related_invoice_ids),
        linked_service_count=len(evaluation_case.related_service_ids),
        linked_credit_profile_count=len(evaluation_case.related_credit_case_ids),
        contract_requirements=requirements,
    )


def _dashboard_metrics(
    *,
    nodes: dict[WorkflowNode, WorkflowNodeState],
    artifacts_by_id: dict[str, ArtifactEnvelope],
) -> tuple[DashboardMetric, ...]:
    finance_artifact = _node_artifact(
        node=nodes.get(WorkflowNode.FINANCE_ASSESSMENT),
        artifacts_by_id=artifacts_by_id,
        artifact_type=ArtifactType.FINANCE_FACTS,
    )
    metrics: list[DashboardMetric] = []
    if finance_artifact is not None:
        facts = FinanceFacts.model_validate(finance_artifact.payload)
        selected = {
            FinanceMetric.CONTRACT_VALUE: ("Giá trị hợp đồng", None),
            FinanceMetric.CONTRACT_GROSS_MARGIN_SOURCE: (
                "Biên lợi nhuận gộp ghi nhận trên hợp đồng",
                None,
            ),
            FinanceMetric.ORDER_GROSS_MARGIN: (
                "Biên lợi nhuận gộp của các đơn hàng đã liên kết",
                "Chỉ phản ánh các đơn hàng có quan hệ rõ ràng với hợp đồng.",
            ),
        }
        by_metric = {item.metric: item for item in facts.facts}
        for metric, (label, note) in selected.items():
            fact = by_metric.get(metric)
            if fact is None or fact.scope is not FinanceDataScope.CASE_SPECIFIC:
                continue
            metrics.append(
                DashboardMetric(
                    code=metric.value,
                    label_vi=label,
                    value=fact.value,
                    unit=fact.unit,
                    scope=fact.scope,
                    quality=fact.quality,
                    note_vi=note,
                )
            )
    banking_artifact = _node_artifact(
        node=nodes.get(WorkflowNode.BANKING_DISCOVERY_HANDOFF),
        artifacts_by_id=artifacts_by_id,
        artifact_type=ArtifactType.BANKING_DISCOVERY_REQUEST,
    )
    if banking_artifact is not None:
        request = BankingDiscoveryRequest.model_validate(banking_artifact.payload)
        if request.requested_amount is not None:
            metrics.append(
                DashboardMetric(
                    code="BANKING_REQUESTED_AMOUNT",
                    label_vi="Số tiền hỗ trợ ngân hàng được yêu cầu cho hợp đồng",
                    value=request.requested_amount,
                    unit=FinanceUnit.VND,
                    scope=FinanceDataScope.CASE_SPECIFIC,
                    quality=FinanceFactQuality.VERIFIED,
                    note_vi=(
                        "Đây là nhu cầu gắn với yêu cầu hợp đồng, không phải "
                        "thiếu hụt tiền mặt toàn OPC."
                    ),
                )
            )
    return tuple(metrics)


def _decision_card_summary(
    *,
    summary: WorkflowRunSummary,
    nodes: dict[WorkflowNode, WorkflowNodeState],
    artifacts_by_id: dict[str, ArtifactEnvelope],
) -> DashboardDecisionCardSummary:
    artifact = _node_artifact(
        node=nodes.get(WorkflowNode.DECISION_CARD_COMPOSITION),
        artifacts_by_id=artifacts_by_id,
        artifact_type=ArtifactType.DECISION_CARD,
    )
    if artifact is None:
        return DashboardDecisionCardSummary(
            available=False,
            recommendation_label_vi="Chưa có Phiếu quyết định cho lượt xử lý này",
        )
    card = DecisionCard.model_validate(artifact.payload)
    if summary.decision_card_id != card.decision_card_id:
        return DashboardDecisionCardSummary(
            available=False,
            recommendation_label_vi=(
                "Phiếu quyết định hiện có không khớp lượt xử lý này"
            ),
        )
    return DashboardDecisionCardSummary(
        available=True,
        artifact_id=artifact.artifact_id,
        decision_card_id=card.decision_card_id,
        recommendation=card.recommendation,
        recommendation_label_vi=_RECOMMENDATION_LABELS[card.recommendation],
        confidence=card.confidence,
        executive_summary=card.executive_summary,
    )


def _external_release_required(
    *,
    nodes: dict[WorkflowNode, WorkflowNodeState],
    artifacts_by_id: dict[str, ArtifactEnvelope],
) -> bool | None:
    artifact = _node_artifact(
        node=nodes.get(WorkflowNode.POST_DECISION_UPDATE),
        artifacts_by_id=artifacts_by_id,
        artifact_type=ArtifactType.POST_DECISION_UPDATE,
    )
    if artifact is None:
        return None
    return PostDecisionUpdate.model_validate(
        artifact.payload
    ).external_document_release_required


def _node_artifact(
    *,
    node: WorkflowNodeState | None,
    artifacts_by_id: dict[str, ArtifactEnvelope],
    artifact_type: ArtifactType,
) -> ArtifactEnvelope | None:
    if node is None:
        return None
    candidates = tuple(
        artifacts_by_id[artifact_id]
        for artifact_id in node.output_artifact_ids
        if artifact_id in artifacts_by_id
        and artifacts_by_id[artifact_id].artifact_type is artifact_type
    )
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item.version, item.created_at))
