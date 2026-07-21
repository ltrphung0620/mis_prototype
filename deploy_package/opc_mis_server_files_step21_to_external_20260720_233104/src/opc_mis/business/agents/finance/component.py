"""Side-effect-free Finance Agent business component."""

import hashlib
import json

from opc_mis.business.agents.finance.condition_analyzer import FinanceConditionAnalyzer
from opc_mis.business.agents.finance.context_loader import (
    FinanceContextError,
    FinanceContextLoader,
)
from opc_mis.business.agents.finance.fact_builder import FinanceFactBuilder
from opc_mis.business.agents.finance.requirements import FinanceRequirementFailure
from opc_mis.domain.artifacts import ArtifactDraft
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import (
    ArtifactType,
    ComponentStatus,
    FinanceAssessmentStatus,
    FinanceNarrativeSource,
)
from opc_mis.domain.events import RuntimeEvent
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.finance_models import (
    FinanceAssessment,
    FinanceComponentResult,
    FinanceComposerInput,
    FinanceFacts,
)
from opc_mis.domain.lineage import LineageFactory, deterministic_id
from opc_mis.domain.missing_data import MissingDataRequest
from opc_mis.domain.serialization import json_safe
from opc_mis.ports.finance_narrative_port import FinanceNarrativePort


def _unique_evidence(*groups: tuple[EvidenceRef, ...]) -> tuple[EvidenceRef, ...]:
    by_id = {item.evidence_id: item for group in groups for item in group}
    return tuple(by_id[key] for key in sorted(by_id))


def _facts_hash(facts: FinanceFacts) -> str:
    encoded = json.dumps(
        json_safe(facts.model_dump(mode="json")),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class FinanceAgent:
    """Calculate Finance facts and compose bounded prose without workflow side effects."""

    component_id = "FINANCE_AGENT"

    def __init__(
        self,
        *,
        context_loader: FinanceContextLoader,
        narrative_composer: FinanceNarrativePort,
        fact_builder: FinanceFactBuilder | None = None,
        condition_analyzer: FinanceConditionAnalyzer | None = None,
    ) -> None:
        self._context_loader = context_loader
        self._narrative_composer = narrative_composer
        self._fact_builder = fact_builder or FinanceFactBuilder()
        self._condition_analyzer = condition_analyzer or FinanceConditionAnalyzer()

    async def execute(self, context: ExecutionContext) -> FinanceComponentResult:
        """Return drafts only; calculation never depends on narrative generation."""
        try:
            finance_context = await self._context_loader.load(context)
        except FinanceContextError as exc:
            return FinanceComponentResult(
                status=ComponentStatus.FAILED_SAFE,
                runtime_events=(RuntimeEvent(event_type="FINANCE_FAILED_SAFE", message=str(exc)),),
            )
        if finance_context.failures:
            requests = tuple(
                self._missing_request(
                    finance_context.evaluation_case.evaluation_case_id,
                    failure,
                )
                for failure in finance_context.failures
            )
            return FinanceComponentResult(
                status=ComponentStatus.WAITING_FOR_INPUT,
                missing_data_requests=requests,
                warnings=tuple(failure.code for failure in finance_context.failures),
            )

        lineage = LineageFactory(context.dataset_id, finance_context.dataset.source_hash)
        fact_build = self._fact_builder.build(finance_context, lineage)
        conditions = self._condition_analyzer.analyze(
            finance_context,
            fact_build.facts,
            lineage,
        )
        evidence = _unique_evidence(fact_build.evidence_refs, conditions.evidence_refs)
        finance_facts = FinanceFacts(
            evaluation_case_id=finance_context.evaluation_case.evaluation_case_id,
            dataset_id=context.dataset_id,
            contract_id=finance_context.evaluation_case.contract_id,
            facts=fact_build.facts,
            observations=conditions.observations,
            limitations=conditions.limitations,
        )
        composition = await self._narrative_composer.compose(
            FinanceComposerInput(
                facts=finance_facts.facts,
                observations=finance_facts.observations,
                limitations=finance_facts.limitations,
            )
        )
        facts_input_hash = _facts_hash(finance_facts)
        assessment = FinanceAssessment(
            evaluation_case_id=finance_facts.evaluation_case_id,
            dataset_id=finance_facts.dataset_id,
            contract_id=finance_facts.contract_id,
            assessment_status=(
                FinanceAssessmentStatus.LIMITED_BY_EVIDENCE
                if finance_facts.limitations
                else FinanceAssessmentStatus.COMPLETE
            ),
            facts_input_hash=facts_input_hash,
            fact_ids=tuple(fact.fact_id for fact in finance_facts.facts),
            observations=finance_facts.observations,
            limitations=finance_facts.limitations,
            narrative=composition.narrative,
            narrative_source=composition.source,
            composer_model=composition.model,
            prompt_version=composition.prompt_version,
        )
        warnings = [item.code for item in finance_facts.limitations]
        events: list[RuntimeEvent] = []
        if composition.source is FinanceNarrativeSource.DETERMINISTIC_FALLBACK:
            warnings.append("FINANCE_NARRATIVE_FALLBACK_USED")
            events.append(
                RuntimeEvent(
                    event_type="FALLBACK_USED",
                    message="Finance narrative used the deterministic fallback.",
                    metadata={"reason": composition.fallback_reason or "OPENAI_DISABLED"},
                )
            )
        drafts = (
            ArtifactDraft(
                artifact_type=ArtifactType.FINANCE_FACTS,
                evaluation_case_id=finance_facts.evaluation_case_id,
                producer=self.component_id,
                payload=finance_facts.model_dump(mode="json"),
                evidence_refs=evidence,
            ),
            ArtifactDraft(
                artifact_type=ArtifactType.FINANCE_ASSESSMENT,
                evaluation_case_id=finance_facts.evaluation_case_id,
                producer=self.component_id,
                payload=assessment.model_dump(mode="json"),
                evidence_refs=evidence,
                identity_inputs={
                    "facts_input_hash": facts_input_hash,
                    "narrative_source": composition.source,
                    "composer_model": composition.model,
                    "prompt_version": composition.prompt_version,
                },
            ),
        )
        status = (
            ComponentStatus.COMPLETED_WITH_WARNINGS
            if warnings or finance_facts.observations
            else ComponentStatus.COMPLETED
        )
        return FinanceComponentResult(
            status=status,
            artifacts=drafts,
            finance_facts=finance_facts,
            finance_assessment=assessment,
            warnings=tuple(warnings),
            runtime_events=tuple(events),
        )

    @classmethod
    def _missing_request(
        cls,
        case_id: str,
        failure: FinanceRequirementFailure,
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
