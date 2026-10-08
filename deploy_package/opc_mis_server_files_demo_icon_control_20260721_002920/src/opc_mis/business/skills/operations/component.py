"""Side-effect-free deterministic Operations Skill."""

import hashlib
import json

from pydantic import ValidationError

from opc_mis.business.skills.operations.condition_analyzer import OperationsConditionAnalyzer
from opc_mis.business.skills.operations.context_loader import (
    OperationsContextError,
    OperationsContextLoader,
)
from opc_mis.business.skills.operations.fact_builder import OperationsFactBuilder
from opc_mis.business.skills.operations.requirements import OperationsRequirementFailure
from opc_mis.business.skills.operations.summary_builder import build_operations_summary
from opc_mis.domain.artifacts import ArtifactDraft
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import ArtifactType, ComponentStatus, OperationsAssessmentStatus
from opc_mis.domain.events import RuntimeEvent
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.lineage import LineageFactory, deterministic_id
from opc_mis.domain.missing_data import MissingDataRequest
from opc_mis.domain.operations_models import (
    OperationsAssessment,
    OperationsComponentResult,
    OperationsFacts,
    OperationsRequest,
)
from opc_mis.domain.serialization import json_safe


def _unique_evidence(*groups: tuple[EvidenceRef, ...]) -> tuple[EvidenceRef, ...]:
    by_id = {item.evidence_id: item for group in groups for item in group}
    return tuple(by_id[key] for key in sorted(by_id))


def _facts_hash(facts: OperationsFacts) -> str:
    encoded = json.dumps(
        json_safe(facts.model_dump(mode="json")),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class OperationsSkill:
    """Assess planned delivery evidence without making downstream decisions."""

    component_id = "OPERATIONS_SKILL"

    def __init__(
        self,
        *,
        context_loader: OperationsContextLoader,
        fact_builder: OperationsFactBuilder | None = None,
        condition_analyzer: OperationsConditionAnalyzer | None = None,
    ) -> None:
        self._context_loader = context_loader
        self._fact_builder = fact_builder or OperationsFactBuilder()
        self._condition_analyzer = condition_analyzer or OperationsConditionAnalyzer()

    async def execute(self, context: ExecutionContext) -> OperationsComponentResult:
        try:
            request = OperationsRequest(
                dataset_id=context.dataset_id,
                evaluation_case_id=context.evaluation_case_id or "",
                as_of_date=context.component_input.get("as_of_date"),
            )
        except ValidationError as exc:
            return self._failed_safe(f"Invalid Operations request: {exc}")
        if not request.evaluation_case_id:
            return self._failed_safe("Operations requires evaluation_case_id.")
        try:
            operations_context = await self._context_loader.load(context)
        except OperationsContextError as exc:
            return self._failed_safe(str(exc))
        if operations_context.failures:
            requests = tuple(
                self._missing_request(request.evaluation_case_id, failure)
                for failure in operations_context.failures
            )
            return OperationsComponentResult(
                status=ComponentStatus.WAITING_FOR_INPUT,
                missing_data_requests=requests,
                warnings=tuple(failure.code for failure in operations_context.failures),
            )

        lineage = LineageFactory(context.dataset_id, operations_context.dataset.source_hash)
        fact_build = self._fact_builder.build(
            operations_context,
            lineage,
            as_of_date=request.as_of_date,
        )
        conditions = self._condition_analyzer.analyze(
            operations_context,
            fact_build.facts,
            fact_build.source_notes,
            lineage,
            has_as_of_date=request.as_of_date is not None,
        )
        evidence = _unique_evidence(fact_build.evidence_refs, conditions.evidence_refs)
        facts = OperationsFacts(
            evaluation_case_id=request.evaluation_case_id,
            dataset_id=request.dataset_id,
            contract_id=operations_context.evaluation_case.contract_id,
            as_of_date=request.as_of_date,
            facts=fact_build.facts,
            order_schedules=fact_build.order_schedules,
            source_notes=fact_build.source_notes,
            observations=conditions.observations,
            limitations=conditions.limitations,
        )
        facts_input_hash = _facts_hash(facts)
        assessment = OperationsAssessment(
            evaluation_case_id=facts.evaluation_case_id,
            dataset_id=facts.dataset_id,
            contract_id=facts.contract_id,
            assessment_status=(
                OperationsAssessmentStatus.LIMITED_BY_EVIDENCE
                if facts.limitations
                else OperationsAssessmentStatus.COMPLETE
            ),
            facts_input_hash=facts_input_hash,
            fact_ids=tuple(fact.fact_id for fact in facts.facts),
            observations=facts.observations,
            limitations=facts.limitations,
            summary=build_operations_summary(facts.evaluation_case_id, facts.facts),
        )
        warnings = tuple(item.code for item in facts.limitations)
        drafts = (
            ArtifactDraft(
                artifact_type=ArtifactType.OPERATIONS_FACTS,
                evaluation_case_id=facts.evaluation_case_id,
                producer=self.component_id,
                payload=facts.model_dump(mode="json"),
                evidence_refs=evidence,
            ),
            ArtifactDraft(
                artifact_type=ArtifactType.OPERATIONS_ASSESSMENT,
                evaluation_case_id=facts.evaluation_case_id,
                producer=self.component_id,
                payload=assessment.model_dump(mode="json"),
                evidence_refs=evidence,
                identity_inputs={"facts_input_hash": facts_input_hash},
            ),
        )
        status = (
            ComponentStatus.COMPLETED_WITH_WARNINGS
            if warnings or facts.observations
            else ComponentStatus.COMPLETED
        )
        return OperationsComponentResult(
            status=status,
            artifacts=drafts,
            operations_facts=facts,
            operations_assessment=assessment,
            warnings=warnings,
        )

    @staticmethod
    def _failed_safe(message: str) -> OperationsComponentResult:
        return OperationsComponentResult(
            status=ComponentStatus.FAILED_SAFE,
            runtime_events=(RuntimeEvent(event_type="OPERATIONS_FAILED_SAFE", message=message),),
        )

    @classmethod
    def _missing_request(
        cls,
        case_id: str,
        failure: OperationsRequirementFailure,
    ) -> MissingDataRequest:
        return MissingDataRequest(
            request_id=deterministic_id(
                "MDR",
                case_id,
                cls.component_id,
                failure.code,
                failure.target_record,
                failure.field,
            ),
            evaluation_case_id=case_id,
            raised_by=cls.component_id,
            requirement_code=failure.code,
            target_record=failure.target_record,
            field=failure.field,
            expected_type=failure.expected_type,
            reason=failure.reason,
            evidence_refs=failure.evidence_refs,
        )
