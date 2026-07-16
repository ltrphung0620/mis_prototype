"""Application composition root for Planner, Finance, and Operations."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from opc_mis.business.agents.finance.component import FinanceAgent
from opc_mis.business.agents.finance.context_loader import FinanceContextLoader
from opc_mis.business.skills.operations.component import OperationsSkill
from opc_mis.business.skills.operations.context_loader import OperationsContextLoader
from opc_mis.business.skills.planner.component import PlannerSkill
from opc_mis.config import AppSettings
from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.dataset import DatasetSnapshot
from opc_mis.domain.enums import ArtifactType, EvaluationScope
from opc_mis.domain.finance_models import FinanceExecutionResult
from opc_mis.domain.lineage import deterministic_id
from opc_mis.domain.operations_models import OperationsExecutionResult
from opc_mis.domain.planner_models import EvaluationCase, PlannerExecutionResult
from opc_mis.domain.team_pack import SheetRegistry
from opc_mis.domain.workflow import WorkflowNode
from opc_mis.infrastructure.excel.dataset_adapter import ExcelDatasetIngestion
from opc_mis.infrastructure.openai.client import create_openai_client
from opc_mis.infrastructure.openai.fallback import DeterministicFinanceNarrativeComposer
from opc_mis.infrastructure.openai.finance_composer import (
    OpenAIFinanceNarrativeComposer,
    ResilientFinanceNarrativeComposer,
)
from opc_mis.infrastructure.persistence.memory_artifact_repository import (
    InMemoryArtifactRepository,
)
from opc_mis.infrastructure.persistence.memory_dataset_repository import (
    InMemoryDatasetRepository,
)
from opc_mis.infrastructure.persistence.memory_workflow_repository import (
    InMemoryWorkflowStateRepository,
)
from opc_mis.workflow.finance_orchestrator import FinanceAssessmentOrchestrator
from opc_mis.workflow.operations_orchestrator import OperationsAssessmentOrchestrator
from opc_mis.workflow.orchestrator import PlannerIntakeOrchestrator


class FinanceCaseNotFoundError(LookupError):
    """Raised when Finance is requested before a completed Planner case exists."""


class OperationsCaseNotFoundError(LookupError):
    """Raised when Operations is requested before a completed Planner case exists."""


class PlannerRuntime:
    """Own process-local adapters and expose the Planner workflow to interfaces."""

    def __init__(
        self,
        *,
        workbook_path: Path,
        dataset_id: str,
        settings: AppSettings | None = None,
    ) -> None:
        self.workbook_path = workbook_path.resolve()
        self.dataset_id = dataset_id
        self._datasets = InMemoryDatasetRepository()
        self._artifacts = InMemoryArtifactRepository()
        self._workflows = InMemoryWorkflowStateRepository()
        self._ingestion = ExcelDatasetIngestion(self._datasets)
        self._orchestrator = PlannerIntakeOrchestrator(
            planner=PlannerSkill(dataset_port=self._datasets),
            artifact_repository=self._artifacts,
            workflow_repository=self._workflows,
        )
        resolved_settings = settings or AppSettings.from_environment()
        fallback = DeterministicFinanceNarrativeComposer()
        if resolved_settings.openai_enabled and resolved_settings.openai_api_key:
            primary = OpenAIFinanceNarrativeComposer(
                client=create_openai_client(
                    api_key=resolved_settings.openai_api_key,
                    timeout_seconds=resolved_settings.openai_timeout_seconds,
                    max_retries=resolved_settings.openai_max_retries,
                ),
                model=resolved_settings.openai_model,
                prompt_path=resolved_settings.finance_prompt_path,
                prompt_version=resolved_settings.finance_prompt_version,
            )
            narrative_composer = ResilientFinanceNarrativeComposer(primary, fallback)
        else:
            narrative_composer = fallback
        self._finance_orchestrator = FinanceAssessmentOrchestrator(
            finance=FinanceAgent(
                context_loader=FinanceContextLoader(
                    datasets=self._datasets,
                    artifacts=self._artifacts,
                ),
                narrative_composer=narrative_composer,
            ),
            artifacts=self._artifacts,
        )
        self._operations_orchestrator = OperationsAssessmentOrchestrator(
            operations=OperationsSkill(
                context_loader=OperationsContextLoader(
                    datasets=self._datasets,
                    artifacts=self._artifacts,
                )
            ),
            artifacts=self._artifacts,
        )
        self._snapshot: DatasetSnapshot | None = None

    async def startup(self) -> None:
        """Ingest and register the configured read-only TeamPack once."""
        if self._snapshot is None:
            self._snapshot = await self._ingestion.ingest(
                dataset_id=self.dataset_id,
                workbook_path=self.workbook_path,
            )

    def contract_ids(self) -> tuple[str, ...]:
        """Return exact contract IDs available in the configured snapshot."""
        snapshot = self._require_snapshot()
        return tuple(record.record_id for record in snapshot.records(SheetRegistry.CONTRACTS))

    @property
    def snapshot_hash(self) -> str:
        """Expose the active snapshot hash for API diagnostics."""
        return self._require_snapshot().snapshot_hash

    async def evaluate(
        self,
        *,
        contract_id: str,
        evaluation_scope: tuple[EvaluationScope, ...],
    ) -> PlannerExecutionResult:
        """Execute Planner Intake for one contract through the Orchestrator."""
        snapshot = self._require_snapshot()
        context = ExecutionContext(
            dataset_id=self.dataset_id,
            workflow_run_id=deterministic_id(
                "RUN",
                self.dataset_id,
                snapshot.snapshot_hash,
                contract_id,
                evaluation_scope,
            ),
            input_artifact_ids=(
                deterministic_id("DSNAP", self.dataset_id, snapshot.snapshot_hash),
            ),
            requested_scope=evaluation_scope,
            component_input={"contract_id": contract_id},
            current_node=WorkflowNode.PLANNER_INTAKE.value,
        )
        return await self._orchestrator.run_planner(context)

    async def finance_assessment(self, *, evaluation_case_id: str) -> FinanceExecutionResult:
        """Run Finance from validated Planner artifacts for one existing case."""
        snapshot = self._require_snapshot()
        artifacts = await self._artifacts.list_by_case(evaluation_case_id)
        case_artifact = self._latest(artifacts, ArtifactType.EVALUATION_CASE)
        planner_artifact = self._latest(artifacts, ArtifactType.PLANNER_RESULT)
        if case_artifact is None or planner_artifact is None:
            raise FinanceCaseNotFoundError(
                "Run Planner successfully before requesting Finance for this case."
            )
        evaluation_case = EvaluationCase.model_validate(case_artifact.payload)
        input_ids = (case_artifact.artifact_id, planner_artifact.artifact_id)
        context = ExecutionContext(
            evaluation_case_id=evaluation_case_id,
            dataset_id=self.dataset_id,
            workflow_run_id=deterministic_id(
                "RUN",
                self.dataset_id,
                snapshot.snapshot_hash,
                evaluation_case_id,
                ArtifactType.FINANCE_ASSESSMENT,
                input_ids,
            ),
            input_artifact_ids=input_ids,
            requested_scope=evaluation_case.evaluation_scope,
            component_input={},
            current_node="FINANCE_ASSESSMENT",
        )
        return await self._finance_orchestrator.run(context)

    async def operations_assessment(
        self,
        *,
        evaluation_case_id: str,
        as_of_date: date | None = None,
    ) -> OperationsExecutionResult:
        """Run Operations from validated Planner artifacts for one existing case."""
        snapshot = self._require_snapshot()
        artifacts = await self._artifacts.list_by_case(evaluation_case_id)
        case_artifact = self._latest(artifacts, ArtifactType.EVALUATION_CASE)
        planner_artifact = self._latest(artifacts, ArtifactType.PLANNER_RESULT)
        if case_artifact is None or planner_artifact is None:
            raise OperationsCaseNotFoundError(
                "Run Planner successfully before requesting Operations for this case."
            )
        evaluation_case = EvaluationCase.model_validate(case_artifact.payload)
        input_ids = (case_artifact.artifact_id, planner_artifact.artifact_id)
        component_input = {"as_of_date": as_of_date.isoformat() if as_of_date is not None else None}
        context = ExecutionContext(
            evaluation_case_id=evaluation_case_id,
            dataset_id=self.dataset_id,
            workflow_run_id=deterministic_id(
                "RUN",
                self.dataset_id,
                snapshot.snapshot_hash,
                evaluation_case_id,
                ArtifactType.OPERATIONS_ASSESSMENT,
                input_ids,
                component_input,
            ),
            input_artifact_ids=input_ids,
            requested_scope=evaluation_case.evaluation_scope,
            component_input=component_input,
            current_node=WorkflowNode.OPERATIONS_ASSESSMENT.value,
        )
        return await self._operations_orchestrator.run(context)

    async def artifacts_for_case(self, evaluation_case_id: str) -> tuple[ArtifactEnvelope, ...]:
        """Expose immutable case artifacts for prototype inspection."""
        return await self._artifacts.list_by_case(evaluation_case_id)

    @staticmethod
    def _latest(
        artifacts: tuple[ArtifactEnvelope, ...], artifact_type: ArtifactType
    ) -> ArtifactEnvelope | None:
        matches = tuple(item for item in artifacts if item.artifact_type is artifact_type)
        return max(matches, key=lambda item: item.version, default=None)

    def _require_snapshot(self) -> DatasetSnapshot:
        if self._snapshot is None:
            raise RuntimeError("PlannerRuntime.startup() must run before API requests.")
        return self._snapshot
