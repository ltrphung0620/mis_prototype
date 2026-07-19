"""Regression tests for Phase B1 persistence and completed-node recovery."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from opc_mis.domain.artifacts import ArtifactDraft, ArtifactEnvelope
from opc_mis.domain.banking_precheck_execution_models import (
    AuthorizedActionPermit,
    BankingPrecheckRawResponse,
    BankingPrecheckRequest,
    BankingPrecheckResultExecutionResult,
)
from opc_mis.domain.banking_precheck_submission_models import (
    BankingPrecheckSubmissionProposal,
)
from opc_mis.domain.case_workflow_models import (
    CaseWorkflowRun,
    WorkflowEvent,
    WorkflowNodeState,
)
from opc_mis.domain.enums import (
    ComponentStatus,
    EvaluationScope,
    ValidationStatus,
    WorkflowNodeStatus,
    WorkflowStatus,
)
from opc_mis.domain.validation_reports import ValidationReport
from opc_mis.domain.workflow import WorkflowNode
from opc_mis.governance.evidence_validator import EvidenceValidator
from opc_mis.infrastructure.persistence.memory_artifact_repository import (
    InMemoryArtifactRepository,
)
from opc_mis.ports.approval_request_repository import ApprovalRequestRepository
from opc_mis.ports.artifact_repository import ArtifactRepository
from opc_mis.ports.case_workflow_repository import CaseWorkflowRepository
from opc_mis.ports.runtime_event_repository import RuntimeEventRepository
from opc_mis.workflow.artifact_factory import ArtifactFactory
from opc_mis.workflow.banking_precheck_execution_orchestrator import (
    BankingPrecheckExecutionOrchestrator,
)
from opc_mis.workflow.case_workflow_orchestrator import (
    AutomaticWorkflowServices,
    CaseWorkflowOrchestrator,
)
from tests.unit.test_banking_precheck_result_component import (
    ADAPTER_CONFIG_HASH,
    ADAPTER_ID,
    APPROVAL_REQUEST_ID,
    PROPOSAL_ARTIFACT_ID,
)
from tests.unit.test_banking_precheck_result_component import (
    _setup as _result_setup,
)
from tests.unit.test_banking_precheck_result_validation import (
    _draft_and_policy,
)
from tests.unit.test_banking_precheck_submission_proposal import (
    CASE_ID,
    _proposal_policy,
)

_SAFE_FAILURE = (
    "Banking precheck execution failed safely; internal provider and "
    "infrastructure details were withheld."
)


class _Snapshot:
    def records(self, _sheet: object) -> tuple[()]:
        return ()


class _Dataset:
    async def get_snapshot(self, _dataset_id: str) -> _Snapshot:
        return _Snapshot()


class _PermitIssuer:
    def __init__(self, permit: AuthorizedActionPermit) -> None:
        self._permit = permit

    async def issue(self, **_kwargs: object) -> AuthorizedActionPermit:
        return self._permit


class _Resolver:
    def __init__(self, requests: tuple[BankingPrecheckRequest, ...]) -> None:
        self._requests = requests

    def resolve(self, **_kwargs: object) -> tuple[BankingPrecheckRequest, ...]:
        return self._requests


class _CountingAdapter:
    def __init__(
        self,
        *,
        configuration_hash: str,
        error: str | None = None,
    ) -> None:
        self.calls = 0
        self._configuration_hash = configuration_hash
        self.error = error

    @property
    def adapter_id(self) -> str:
        return ADAPTER_ID

    @property
    def configuration_hash(self) -> str:
        return self._configuration_hash

    async def submit(
        self,
        _request: BankingPrecheckRequest,
        _authorization: AuthorizedActionPermit,
    ) -> BankingPrecheckRawResponse:
        self.calls += 1
        raise RuntimeError(self.error or "adapter must not be invoked")


class _LoadedExecutionOrchestrator(BankingPrecheckExecutionOrchestrator):
    def __init__(self, *, loaded: tuple[Any, ...], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._loaded = loaded

    async def _load_inputs(self, _context: object) -> tuple[Any, ...]:
        return self._loaded


@dataclass(frozen=True)
class _ExecutionFixture:
    repository: InMemoryArtifactRepository
    orchestrator: BankingPrecheckExecutionOrchestrator
    context: Any
    draft: ArtifactDraft
    envelope: ArtifactEnvelope
    adapter: _CountingAdapter


async def _execution_fixture(
    *,
    save_result: bool,
    adapter_error: str | None = None,
) -> _ExecutionFixture:
    repository, component, component_context, component_input = await _result_setup(
        candidate_count=1
    )
    draft, simulation_policy = await _draft_and_policy()
    validator = EvidenceValidator(
        banking_policy=_proposal_policy(),
        banking_precheck_simulation_policy=simulation_policy,
    )
    report = await validator.validate(draft)
    assert report.status in {
        ValidationStatus.VALID,
        ValidationStatus.VALID_WITH_WARNINGS,
    }
    envelope = ArtifactFactory(
        clock=lambda: datetime(2026, 7, 18, 13, 0, tzinfo=UTC)
    ).create(
        draft=draft,
        context=component_context,
        validation_report=report,
        version=1,
    )
    if save_result:
        await repository.save(envelope)
    proposal_artifact = await repository.get(PROPOSAL_ARTIFACT_ID)
    assert proposal_artifact is not None
    proposal = BankingPrecheckSubmissionProposal.model_validate(
        proposal_artifact.payload
    )
    adapter = _CountingAdapter(
        configuration_hash=simulation_policy.configuration_hash,
        error=adapter_error,
    )
    orchestrator = _LoadedExecutionOrchestrator(
        loaded=(proposal_artifact, None, None, proposal, None, None),
        result_component=component,
        request_resolver=_Resolver(component_input.requests),
        permit_issuer=_PermitIssuer(component_input.permit),
        adapter=adapter,
        datasets=_Dataset(),
        artifacts=repository,
        evidence_validator=validator,
    )
    context = component_context.model_copy(
        update={
            "component_input": {
                "approval_request_id": APPROVAL_REQUEST_ID,
                "reuse_existing_only": save_result,
            },
            "current_node": WorkflowNode.BANKING_PRECHECK_EXECUTION.value,
        }
    )
    return _ExecutionFixture(
        repository=repository,
        orchestrator=orchestrator,
        context=context,
        draft=draft,
        envelope=envelope,
        adapter=adapter,
    )


def test_completed_execution_revalidates_exact_artifact_without_adapter_call() -> None:
    async def scenario() -> None:
        fixture = await _execution_fixture(save_result=True)

        result = await fixture.orchestrator.run(fixture.context)

        assert result.status is WorkflowStatus.COMPLETED
        assert result.generated_artifacts == (fixture.envelope,)
        assert fixture.adapter.calls == 0

    asyncio.run(scenario())


def test_completed_execution_blocks_valid_marked_tampered_evidence_without_retry() -> None:
    async def scenario() -> None:
        fixture = await _execution_fixture(save_result=True)
        changed_evidence = tuple(
            evidence.model_copy(update={"source_evidence_ids": ("EVD-MISSING",)})
            if evidence.sheet == "BANKING_PRECHECK_RESULT_SET"
            and evidence.field == "normalized_result"
            else evidence
            for evidence in fixture.envelope.evidence_refs
        )
        await fixture.repository.save(
            fixture.envelope.model_copy(update={"evidence_refs": changed_evidence})
        )

        result = await fixture.orchestrator.run(fixture.context)

        assert result.status is WorkflowStatus.FAILED_SAFE
        assert result.validation_errors
        assert fixture.adapter.calls == 0

    asyncio.run(scenario())


def test_unexpected_adapter_error_is_redacted_from_execution_result() -> None:
    async def scenario() -> None:
        secret = "PROVIDER-SECRET-RESPONSE-DETAIL"
        fixture = await _execution_fixture(
            save_result=False,
            adapter_error=secret,
        )

        result = await fixture.orchestrator.run(fixture.context)

        assert result.status is WorkflowStatus.FAILED_SAFE
        assert result.validation_errors == (_SAFE_FAILURE,)
        assert secret not in " ".join(result.validation_errors)
        assert fixture.adapter.calls == 1

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "update",
    (
        {"validation_status": ValidationStatus.BLOCKED},
        {"payload": {"tampered": True}},
        {"evidence_refs": ()},
        {"input_artifact_ids": ("ART-OTHER-LINEAGE",)},
    ),
)
def test_persist_or_reuse_rejects_non_exact_or_unvalidated_same_hash(
    update: dict[str, object],
) -> None:
    async def scenario() -> None:
        fixture = await _execution_fixture(save_result=False)
        await fixture.repository.save(fixture.envelope.model_copy(update=update))

        with pytest.raises(ValueError, match="conflicts"):
            await fixture.orchestrator._persist_or_reuse(
                fixture.draft,
                fixture.context,
                ValidationReport(status=ValidationStatus.VALID),
            )

    asyncio.run(scenario())


class _WorkflowRepository:
    def __init__(self, node: WorkflowNodeState) -> None:
        self.node = node
        self.saved_nodes: list[WorkflowNodeState] = []

    async def get_node(self, _workflow_run_id: str, _node: str) -> WorkflowNodeState:
        return self.node

    async def save_node(self, node: WorkflowNodeState) -> None:
        self.saved_nodes.append(node)
        self.node = node


class _Events:
    def __init__(self) -> None:
        self.events: list[WorkflowEvent] = []

    async def append(
        self,
        *,
        workflow_run_id: str,
        event_type: str,
        node: WorkflowNode | None,
        metadata: dict[str, Any],
        created_at: datetime,
    ) -> WorkflowEvent:
        event = WorkflowEvent(
            event_id=f"EVENT-{len(self.events) + 1}",
            workflow_run_id=workflow_run_id,
            sequence=len(self.events) + 1,
            event_type=event_type,
            node=node,
            metadata=metadata,
            created_at=created_at,
        )
        self.events.append(event)
        return event


class _CaseServices:
    dataset_id = "DATASET-RECOVERY"
    snapshot_hash = "SNAPSHOT-RECOVERY"
    banking_precheck_adapter_configuration_hash = ADAPTER_CONFIG_HASH

    def __init__(
        self,
        *,
        adapter_id: str,
        execution_result: BankingPrecheckResultExecutionResult,
    ) -> None:
        self.banking_precheck_adapter_id = adapter_id
        self.execution_result = execution_result
        self.reuse_calls: list[bool] = []
        self.adapter_invocations = 0
        self.error: str | None = None

    async def banking_precheck_execution(
        self,
        *,
        reuse_existing_only: bool = False,
        **_kwargs: object,
    ) -> BankingPrecheckResultExecutionResult:
        self.reuse_calls.append(reuse_existing_only)
        if self.error is not None:
            raise RuntimeError(self.error)
        if not reuse_existing_only:
            self.adapter_invocations += 1
        return self.execution_result


def _case_orchestrator(
    *,
    services: _CaseServices,
    repository: _WorkflowRepository,
    events: _Events,
) -> CaseWorkflowOrchestrator:
    return CaseWorkflowOrchestrator(
        services=cast(AutomaticWorkflowServices, services),
        workflows=cast(CaseWorkflowRepository, repository),
        artifacts=cast(ArtifactRepository, object()),
        approvals=cast(ApprovalRequestRepository, object()),
        events=cast(RuntimeEventRepository, events),
    )


def _run_and_node(
    *,
    proposal_artifact: ArtifactEnvelope,
    adapter_id: str,
    input_hash_adapter_id: str | None = None,
) -> tuple[CaseWorkflowRun, WorkflowNodeState, _CaseServices, _WorkflowRepository, _Events]:
    now = datetime(2026, 7, 18, 14, 0, tzinfo=UTC)
    run = CaseWorkflowRun(
        workflow_run_id="WORKFLOW-RECOVERY",
        dataset_id="DATASET-RECOVERY",
        dataset_snapshot_hash="SNAPSHOT-RECOVERY",
        evaluation_case_id=CASE_ID,
        contract_id="CONTRACT-RECOVERY",
        status=WorkflowStatus.RUNNING,
        current_stage=WorkflowNode.BANKING_PRECHECK_EXECUTION.value,
        requested_scope=(
            EvaluationScope.FINANCE,
            EvaluationScope.OPERATIONS,
            EvaluationScope.RISK,
        ),
        created_at=now,
        updated_at=now,
    )
    result = BankingPrecheckResultExecutionResult(
        status=WorkflowStatus.COMPLETED,
        component_status=ComponentStatus.COMPLETED_WITH_WARNINGS,
        current_node=WorkflowNode.BANKING_PRECHECK_EXECUTION.value,
    )
    services = _CaseServices(adapter_id=adapter_id, execution_result=result)
    events = _Events()
    placeholder = WorkflowNodeState(
        workflow_run_id=run.workflow_run_id,
        node=WorkflowNode.BANKING_PRECHECK_EXECUTION,
        status=WorkflowNodeStatus.COMPLETED_WITH_WARNINGS,
        attempt=1,
        input_hash="PLACEHOLDER",
        output_artifact_ids=("ART-RESULT",),
        started_at=now,
        completed_at=now,
    )
    repository = _WorkflowRepository(placeholder)
    orchestrator = _case_orchestrator(
        services=services,
        repository=repository,
        events=events,
    )
    identity_inputs = (
        proposal_artifact.artifact_id,
        proposal_artifact.version,
        proposal_artifact.input_hash,
        APPROVAL_REQUEST_ID,
        input_hash_adapter_id or adapter_id,
        ADAPTER_CONFIG_HASH,
    )
    repository.node = placeholder.model_copy(
        update={
            "input_hash": orchestrator._node_input_hash(
                run,
                WorkflowNode.BANKING_PRECHECK_EXECUTION,
                identity_inputs,
            )
        }
    )
    return run, repository.node, services, repository, events


def test_matching_completed_node_uses_reuse_only_without_new_attempt() -> None:
    async def scenario() -> None:
        fixture = await _execution_fixture(save_result=True)
        proposal_artifact = cast(
            ArtifactEnvelope,
            await fixture.repository.get(PROPOSAL_ARTIFACT_ID),
        )
        run, node, services, repository, events = _run_and_node(
            proposal_artifact=proposal_artifact,
            adapter_id=ADAPTER_ID,
        )
        orchestrator = _case_orchestrator(
            services=services,
            repository=repository,
            events=events,
        )

        result = await orchestrator._banking_precheck_execution(
            run,
            proposal_artifact=proposal_artifact,
            approval_request_id=APPROVAL_REQUEST_ID,
        )

        assert result is not None
        assert result.status is WorkflowStatus.COMPLETED
        assert services.reuse_calls == [True]
        assert services.adapter_invocations == 0
        assert repository.saved_nodes == []
        assert repository.node == node

    asyncio.run(scenario())


def test_adapter_id_change_invalidates_completed_node_identity() -> None:
    async def scenario() -> None:
        fixture = await _execution_fixture(save_result=True)
        proposal_artifact = cast(
            ArtifactEnvelope,
            await fixture.repository.get(PROPOSAL_ARTIFACT_ID),
        )
        run, _, services, repository, events = _run_and_node(
            proposal_artifact=proposal_artifact,
            adapter_id="ADAPTER-NEW",
            input_hash_adapter_id="ADAPTER-OLD",
        )
        orchestrator = _case_orchestrator(
            services=services,
            repository=repository,
            events=events,
        )

        result = await orchestrator._banking_precheck_execution(
            run,
            proposal_artifact=proposal_artifact,
            approval_request_id=APPROVAL_REQUEST_ID,
        )

        assert result is not None
        assert services.reuse_calls == [False]
        assert services.adapter_invocations == 1
        assert repository.saved_nodes[0].attempt == 2

    asyncio.run(scenario())


def test_unexpected_execution_service_error_is_redacted_in_persisted_node() -> None:
    async def scenario() -> None:
        repository, _, _, _ = await _result_setup(candidate_count=1)
        proposal_artifact = cast(
            ArtifactEnvelope,
            await repository.get(PROPOSAL_ARTIFACT_ID),
        )
        run, _, services, workflows, events = _run_and_node(
            proposal_artifact=proposal_artifact,
            adapter_id=ADAPTER_ID,
            input_hash_adapter_id="STALE-ADAPTER",
        )
        secret = "PRIVATE-INFRASTRUCTURE-FAILURE"
        services.error = secret
        orchestrator = _case_orchestrator(
            services=services,
            repository=workflows,
            events=events,
        )

        result = await orchestrator._banking_precheck_execution(
            run,
            proposal_artifact=proposal_artifact,
            approval_request_id=APPROVAL_REQUEST_ID,
        )

        assert result is not None
        assert result.status is WorkflowStatus.FAILED_SAFE
        assert result.validation_errors == (_SAFE_FAILURE,)
        persisted_reason = workflows.saved_nodes[-1].failure_reason
        assert persisted_reason == result.validation_errors[0]
        assert secret not in persisted_reason

    asyncio.run(scenario())
