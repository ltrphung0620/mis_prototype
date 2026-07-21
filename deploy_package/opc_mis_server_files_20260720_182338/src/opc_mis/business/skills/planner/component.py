"""Side-effect-free Planner business component."""

from __future__ import annotations

from pydantic import ValidationError

from opc_mis.business.skills.planner.case_builder import CaseBuilder, CaseBuildOutcome
from opc_mis.business.skills.planner.requirement_registry import (
    RequirementFailure,
    RequirementRegistry,
)
from opc_mis.business.skills.planner.run_plan import build_run_plan
from opc_mis.domain.artifacts import ArtifactDraft
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import (
    ArtifactType,
    ComponentStatus,
    ReadinessStatus,
)
from opc_mis.domain.events import RuntimeEvent
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.lineage import LineageFactory, deterministic_id
from opc_mis.domain.missing_data import MissingDataRequest
from opc_mis.domain.planner_models import (
    DataReadiness,
    PlannerComponentResult,
    PlannerRequest,
    PlannerResult,
)
from opc_mis.ports.dataset_port import DatasetNotFoundError, DatasetPort


def _unique_evidence(evidence: tuple[EvidenceRef, ...]) -> tuple[EvidenceRef, ...]:
    by_id = {item.evidence_id: item for item in evidence}
    return tuple(by_id[key] for key in sorted(by_id))


class PlannerSkill:
    """Validate intake and create a traceable case without workflow side effects."""

    component_id = "PLANNER_SKILL"

    def __init__(
        self,
        *,
        dataset_port: DatasetPort,
        requirement_registry: RequirementRegistry | None = None,
        case_builder: CaseBuilder | None = None,
    ) -> None:
        self._dataset_port = dataset_port
        self._requirement_registry = requirement_registry or RequirementRegistry()
        self._case_builder = case_builder or CaseBuilder()

    async def execute(self, context: ExecutionContext) -> PlannerComponentResult:
        """Execute one Planner node and return drafts without persisting anything."""
        try:
            request = PlannerRequest(
                dataset_id=context.dataset_id,
                contract_id=context.component_input["contract_id"],
                evaluation_scope=context.requested_scope,
            )
            dataset = await self._dataset_port.get_snapshot(context.dataset_id)
        except (KeyError, ValidationError, DatasetNotFoundError) as exc:
            return PlannerComponentResult(
                status=ComponentStatus.FAILED_SAFE,
                planner_result=None,
                runtime_events=(RuntimeEvent(event_type="NODE_FAILED_SAFE", message=str(exc)),),
            )

        lineage = LineageFactory(request.dataset_id, dataset.source_hash)
        outcome = self._case_builder.build(request, dataset, lineage)
        failures = self._requirement_registry.evaluate(outcome)
        return self._complete_result(outcome, failures)

    def _complete_result(
        self,
        outcome: CaseBuildOutcome,
        failures: tuple[RequirementFailure, ...],
    ) -> PlannerComponentResult:
        blocked = bool(failures)
        missing_requests = tuple(self._missing_request(outcome, failure) for failure in failures)
        readiness_status = (
            ReadinessStatus.BLOCKED
            if blocked
            else (
                ReadinessStatus.READY_WITH_WARNINGS if outcome.warnings else ReadinessStatus.READY
            )
        )
        validation_notes = list(outcome.validation_notes)
        for sheet, duplicates in sorted(outcome.dataset.duplicate_ids.items()):
            validation_notes.append(
                f"Duplicate primary keys detected in {sheet}: {', '.join(duplicates)}"
            )
        for issue in outcome.dataset.validation_issues:
            validation_notes.append(
                f"{issue.code} {issue.sheet}.{issue.field} [{issue.record_id}]: {issue.reason}"
            )

        readiness = DataReadiness(
            status=readiness_status,
            blocking_missing_fields=tuple(
                f"{failure.target_record}.{failure.field}" for failure in failures
            ),
            non_blocking_warnings=outcome.warnings,
            validation_notes=tuple(validation_notes),
        )
        planner_result = PlannerResult(
            evaluation_case=outcome.evaluation_case,
            data_readiness=readiness,
            run_plan=build_run_plan(blocked),
            missing_data_requests=missing_requests,
            warnings=outcome.warnings,
            evidence_refs=outcome.evidence_refs,
        )
        status = (
            ComponentStatus.WAITING_FOR_INPUT
            if blocked
            else (
                ComponentStatus.COMPLETED_WITH_WARNINGS
                if outcome.warnings
                else ComponentStatus.COMPLETED
            )
        )
        drafts = self._create_artifact_drafts(outcome, planner_result)
        return PlannerComponentResult(
            status=status,
            planner_result=planner_result,
            artifacts=drafts,
            missing_data_requests=missing_requests,
            warnings=tuple(warning.warning_code for warning in outcome.warnings),
        )

    @staticmethod
    def _missing_request(
        outcome: CaseBuildOutcome,
        failure: RequirementFailure,
    ) -> MissingDataRequest:
        request_id = deterministic_id(
            "MDR",
            outcome.request.dataset_id,
            outcome.dataset.snapshot_hash,
            outcome.evaluation_case_id,
            failure.code,
            failure.target_record,
            failure.field,
        )
        return MissingDataRequest(
            request_id=request_id,
            evaluation_case_id=outcome.evaluation_case_id,
            raised_by=PlannerSkill.component_id,
            requirement_code=failure.code,
            target_record=failure.target_record,
            field=failure.field,
            expected_type=failure.expected_type,
            reason=failure.reason,
            evidence_refs=failure.evidence_refs,
        )

    @staticmethod
    def _create_artifact_drafts(
        outcome: CaseBuildOutcome,
        planner_result: PlannerResult,
    ) -> tuple[ArtifactDraft, ...]:
        artifact_evidence = _unique_evidence(
            outcome.evidence_refs
            + tuple(
                evidence
                for request in planner_result.missing_data_requests
                for evidence in request.evidence_refs
            )
        )
        common = {
            "evaluation_case_id": outcome.evaluation_case_id,
            "producer": PlannerSkill.component_id,
            "evidence_refs": artifact_evidence,
        }
        artifacts: list[ArtifactDraft] = []
        if planner_result.evaluation_case is not None:
            artifacts.append(
                ArtifactDraft(
                    artifact_type=ArtifactType.EVALUATION_CASE,
                    payload=planner_result.evaluation_case.model_dump(mode="json"),
                    **common,
                )
            )
        artifacts.append(
            ArtifactDraft(
                artifact_type=ArtifactType.PLANNER_RESULT,
                payload=planner_result.model_dump(mode="json"),
                **common,
            )
        )
        return tuple(artifacts)
