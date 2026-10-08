"""Master Workflow Decision nodes bind to exact upstream artifact revisions."""

import asyncio
from datetime import UTC, datetime
from typing import cast

from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.banking_models import BankingDiscoveryHandoffExecutionResult
from opc_mis.domain.case_workflow_models import CaseWorkflowRun
from opc_mis.domain.decision_post_banking_models import (
    DecisionPostBankingExecutionResult,
)
from opc_mis.domain.decision_route_models import DecisionRouteExecutionResult
from opc_mis.domain.enums import (
    ArtifactStatus,
    ArtifactType,
    BankingDiscoveryHandoffStatus,
    ComponentStatus,
    EvaluationScope,
    ValidationStatus,
    WorkflowStatus,
)
from opc_mis.infrastructure.persistence.memory_approval_request_repository import (
    InMemoryApprovalRequestRepository,
)
from opc_mis.infrastructure.persistence.memory_artifact_repository import (
    InMemoryArtifactRepository,
)
from opc_mis.infrastructure.persistence.sqlite_database import SQLiteDatabase
from opc_mis.infrastructure.persistence.sqlite_runtime_event_repository import (
    SQLiteRuntimeEventRepository,
)
from opc_mis.infrastructure.persistence.sqlite_workflow_repository import (
    SQLiteCaseWorkflowRepository,
)
from opc_mis.workflow.case_workflow_orchestrator import (
    AutomaticWorkflowServices,
    CaseWorkflowOrchestrator,
)

CASE_ID = "CASE-DECISION-NODE-IDENTITY"
RUN_ID = "RUN-DECISION-NODE-IDENTITY"


class _DecisionServices:
    dataset_id = "DATASET-DECISION-NODE-IDENTITY"
    snapshot_hash = "SNAPSHOT-DECISION-NODE-IDENTITY"

    def __init__(self) -> None:
        self.route_calls = 0
        self.handoff_calls = 0
        self.post_banking_calls = 0

    async def decision_initial_route(
        self, *, evaluation_case_id: str
    ) -> DecisionRouteExecutionResult:
        assert evaluation_case_id == CASE_ID
        self.route_calls += 1
        return DecisionRouteExecutionResult(
            status=WorkflowStatus.COMPLETED,
            component_status=ComponentStatus.COMPLETED,
            current_node="DECISION_ROUTE_PLANNED",
        )

    async def decision_banking_handoff(
        self, *, evaluation_case_id: str
    ) -> BankingDiscoveryHandoffExecutionResult:
        assert evaluation_case_id == CASE_ID
        self.handoff_calls += 1
        return BankingDiscoveryHandoffExecutionResult(
            status=WorkflowStatus.COMPLETED,
            component_status=ComponentStatus.COMPLETED,
            current_node="BANKING_DISCOVERY_REQUESTED",
            handoff_status=BankingDiscoveryHandoffStatus.REQUEST_CREATED,
        )

    async def decision_post_banking_review(
        self, *, evaluation_case_id: str
    ) -> DecisionPostBankingExecutionResult:
        assert evaluation_case_id == CASE_ID
        self.post_banking_calls += 1
        return DecisionPostBankingExecutionResult(
            status=WorkflowStatus.COMPLETED,
            component_status=ComponentStatus.COMPLETED,
            current_node="DECISION_POST_BANKING_REVIEW",
        )


def _run() -> CaseWorkflowRun:
    now = datetime.now(UTC)
    return CaseWorkflowRun(
        workflow_run_id=RUN_ID,
        dataset_id=_DecisionServices.dataset_id,
        dataset_snapshot_hash=_DecisionServices.snapshot_hash,
        evaluation_case_id=CASE_ID,
        contract_id="CON-DECISION-NODE-IDENTITY",
        status=WorkflowStatus.RUNNING,
        current_stage="DECISION_TEST",
        requested_scope=(EvaluationScope.RISK,),
        created_at=now,
        updated_at=now,
    )


def _artifact(artifact_type: ArtifactType, version: int) -> ArtifactEnvelope:
    return ArtifactEnvelope(
        artifact_id=f"ART-{artifact_type.value}-{version}",
        artifact_type=artifact_type,
        evaluation_case_id=CASE_ID,
        producer="TEST",
        version=version,
        status=ArtifactStatus.CREATED,
        payload={},
        evidence_refs=(),
        input_artifact_ids=(f"ART-UPSTREAM-{version}",),
        input_hash=f"HASH-{artifact_type.value}-{version}",
        validation_status=ValidationStatus.VALID,
        validation_notes=(),
        created_at=datetime.now(UTC),
    )


def test_decision_nodes_rerun_only_when_exact_upstream_revision_changes() -> None:
    async def execute() -> None:
        database = SQLiteDatabase(":memory:")
        await database.initialize()
        try:
            workflows = SQLiteCaseWorkflowRepository(database)
            artifacts = InMemoryArtifactRepository()
            services = _DecisionServices()
            orchestrator = CaseWorkflowOrchestrator(
                services=cast(AutomaticWorkflowServices, services),
                workflows=workflows,
                artifacts=artifacts,
                approvals=InMemoryApprovalRequestRepository(),
                events=SQLiteRuntimeEventRepository(database),
            )
            run = _run()

            for artifact_type in (
                ArtifactType.EVALUATION_CASE,
                ArtifactType.FINANCE_FACTS,
                ArtifactType.OPERATIONS_FACTS,
                ArtifactType.INITIAL_RISK_ASSESSMENT,
                ArtifactType.APPROVAL_CHECKPOINTS,
            ):
                await artifacts.save(_artifact(artifact_type, 1))

            first_route = await orchestrator._decision_initial_route(run)
            exact_route_retry = await orchestrator._decision_initial_route(run)
            await artifacts.save(_artifact(ArtifactType.FINANCE_FACTS, 2))
            changed_route = await orchestrator._decision_initial_route(run)
            route_node = await workflows.get_node(RUN_ID, "DECISION_ROUTE_PLANNING")

            assert first_route is not None
            assert exact_route_retry is None
            assert changed_route is not None
            assert services.route_calls == 2
            assert route_node is not None and route_node.attempt == 2

            await artifacts.save(_artifact(ArtifactType.DECISION_ROUTE_PLAN, 1))
            first_handoff = await orchestrator._decision_banking_handoff(run)
            exact_handoff_retry = await orchestrator._decision_banking_handoff(run)
            await artifacts.save(_artifact(ArtifactType.DECISION_ROUTE_PLAN, 2))
            changed_handoff = await orchestrator._decision_banking_handoff(run)
            handoff_node = await workflows.get_node(RUN_ID, "BANKING_DISCOVERY_HANDOFF")

            assert first_handoff is not None
            assert exact_handoff_retry is None
            assert changed_handoff is not None
            assert services.handoff_calls == 2
            assert handoff_node is not None and handoff_node.attempt == 2

            await artifacts.save(_artifact(ArtifactType.BANKING_OPTION_MATRIX, 1))
            await artifacts.save(
                _artifact(ArtifactType.BANKING_PRECHECK_READINESS, 1)
            )
            first_review = await orchestrator._decision_post_banking_review(run)
            exact_review_retry = await orchestrator._decision_post_banking_review(run)
            await artifacts.save(
                _artifact(ArtifactType.BANKING_PRECHECK_READINESS, 2)
            )
            changed_review = await orchestrator._decision_post_banking_review(run)
            review_node = await workflows.get_node(
                RUN_ID, "DECISION_POST_BANKING_REVIEW"
            )

            assert first_review is not None
            assert exact_review_retry is None
            assert changed_review is not None
            assert services.post_banking_calls == 2
            assert review_node is not None and review_node.attempt == 2
        finally:
            await database.close()

    asyncio.run(execute())
