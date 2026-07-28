"""Optional, bounded Banking option advisor over a persisted deterministic matrix."""

from opc_mis.business.skills.banking.advisor_context import (
    BankingAdvisorContextError,
    BankingAdvisorContextLoader,
)
from opc_mis.domain.artifacts import ArtifactDraft
from opc_mis.domain.banking_models import (
    BankingAdviceComponentResult,
    BankingAdviceComposition,
    BankingAdvisorInput,
    BankingAdvisorOption,
    BankingOptionAdvice,
    BankingOptionAdviceDraft,
    BankingOptionSuggestion,
)
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import (
    ArtifactType,
    BankingAdviceSource,
    BankingAdviceStatus,
    ComponentStatus,
)
from opc_mis.domain.events import RuntimeEvent
from opc_mis.domain.lineage import deterministic_id
from opc_mis.ports.banking_option_advisor_port import BankingOptionAdvisorPort


class BankingAdvisorBoundaryError(RuntimeError):
    """Raised when a port result references options outside the matrix."""


class BankingOptionAdvisorSkill:
    """Phrase matrix options without selecting, approving, or executing one."""

    component_id = "BANKING_OPTION_ADVISOR_SKILL"
    _NOT_INVOKED_PROMPT_VERSION = "banking-option-advisor-v1"

    def __init__(
        self,
        *,
        context_loader: BankingAdvisorContextLoader,
        advisor: BankingOptionAdvisorPort,
    ) -> None:
        self._context_loader = context_loader
        self._advisor = advisor

    async def execute(self, context: ExecutionContext) -> BankingAdviceComponentResult:
        """Return one advisory draft tied to an explicit persisted matrix artifact."""
        try:
            advisor_context = await self._context_loader.load(context)
        except BankingAdvisorContextError as exc:
            return self._failed_safe(str(exc))

        matrix = advisor_context.matrix
        advisor_input = BankingAdvisorInput(
            matrix_id=matrix.matrix_id,
            options=tuple(
                BankingAdvisorOption(
                    option_id=candidate.option_id,
                    need_type=candidate.need_type,
                    provider=candidate.provider,
                    product_name=candidate.product_name,
                    criterion_statuses=tuple(
                        f"{criterion.code.value}:{criterion.status.value}"
                        for criterion in candidate.criteria
                    ),
                    limitation_codes=tuple(gap.code for gap in matrix.data_gaps),
                )
                for candidate in matrix.candidates
            ),
            allowed_option_combinations=matrix.allowed_option_combinations,
        )
        if len(matrix.candidates) < 2:
            composition = self._not_invoked_composition()
        else:
            composition = await self._advisor.compose(advisor_input)

        try:
            suggestions = self._guarded_suggestions(
                matrix_id=matrix.matrix_id,
                composition=composition,
                advisor_input=advisor_input,
            )
            status = self._advice_status(
                composition,
                candidate_count=len(matrix.candidates),
            )
        except BankingAdvisorBoundaryError as exc:
            return self._failed_safe(str(exc))

        advice = BankingOptionAdvice(
            advice_id=deterministic_id(
                "BOADV",
                advisor_context.matrix_artifact.artifact_id,
                matrix.matrix_id,
                composition.source,
                composition.model,
                composition.prompt_version,
            ),
            evaluation_case_id=matrix.evaluation_case_id,
            matrix_id=matrix.matrix_id,
            advisor_configuration_hash=str(
                context.component_input.get(
                    "advisor_configuration_hash", "UNSPECIFIED"
                )
            ),
            status=status,
            source=composition.source,
            overview=composition.advice.overview,
            suggestions=suggestions,
            model=composition.model,
            prompt_version=composition.prompt_version,
            fallback_reason=composition.fallback_reason,
        )
        draft = ArtifactDraft(
            artifact_type=ArtifactType.BANKING_OPTION_ADVICE,
            evaluation_case_id=matrix.evaluation_case_id,
            producer=self.component_id,
            payload=advice.model_dump(mode="json"),
            evidence_refs=advisor_context.matrix_artifact.evidence_refs,
            identity_inputs={
                "matrix_artifact_id": advisor_context.matrix_artifact.artifact_id,
                "matrix_id": matrix.matrix_id,
                "advisor_configuration_hash": advice.advisor_configuration_hash,
                "advice_source": advice.source,
                "model": advice.model,
                "prompt_version": advice.prompt_version,
            },
        )
        warnings: tuple[str, ...] = ()
        events: list[RuntimeEvent] = []
        if composition.source is BankingAdviceSource.DETERMINISTIC_FALLBACK:
            warnings = ("BANKING_OPTION_ADVICE_FALLBACK_USED",)
            events.append(
                RuntimeEvent(
                    event_type="FALLBACK_USED",
                    message="Banking option advice used the deterministic fallback.",
                    metadata={
                        "reason": composition.fallback_reason or "OPENAI_DISABLED"
                    },
                )
            )
        events.append(
            RuntimeEvent(
                event_type=(
                    "BANKING_OPTION_ADVISOR_NOT_INVOKED"
                    if status is BankingAdviceStatus.NOT_INVOKED
                    else "BANKING_OPTION_ADVICE_CREATED"
                ),
                message=(
                    "Banking option advisor was not invoked because fewer than two "
                    "configured candidates were available."
                    if status is BankingAdviceStatus.NOT_INVOKED
                    else "Banking created non-authoritative option advice."
                ),
                metadata={
                    "advice_status": status.value,
                    "advice_source": composition.source.value,
                },
            )
        )
        return BankingAdviceComponentResult(
            status=(
                ComponentStatus.COMPLETED_WITH_WARNINGS
                if warnings
                else ComponentStatus.COMPLETED
            ),
            option_advice=advice,
            artifacts=(draft,),
            warnings=warnings,
            runtime_events=tuple(events),
        )

    @classmethod
    def _not_invoked_composition(cls) -> BankingAdviceComposition:
        return BankingAdviceComposition(
            advice=BankingOptionAdviceDraft(
                overview=(
                    "The option advisor was not invoked because fewer than two "
                    "configured candidates are available. The deterministic matrix "
                    "remains authoritative."
                ),
                suggestions=(),
            ),
            source=BankingAdviceSource.NOT_INVOKED,
            model="not-invoked",
            prompt_version=cls._NOT_INVOKED_PROMPT_VERSION,
        )

    @staticmethod
    def _advice_status(
        composition: BankingAdviceComposition,
        *,
        candidate_count: int,
    ) -> BankingAdviceStatus:
        if candidate_count < 2:
            if (
                composition.source is not BankingAdviceSource.NOT_INVOKED
                or composition.advice.suggestions
            ):
                raise BankingAdvisorBoundaryError(
                    "A non-comparative matrix must produce NOT_INVOKED advice only."
                )
            return BankingAdviceStatus.NOT_INVOKED
        if composition.source is BankingAdviceSource.NOT_INVOKED:
            raise BankingAdvisorBoundaryError(
                "A comparative matrix cannot be labeled as non-invoked."
            )
        return BankingAdviceStatus.ADVISORY_ONLY

    @staticmethod
    def _guarded_suggestions(
        *,
        matrix_id: str,
        composition: BankingAdviceComposition,
        advisor_input: BankingAdvisorInput,
    ) -> tuple[BankingOptionSuggestion, ...]:
        known = {item.option_id for item in advisor_input.options}
        allowed = {
            tuple(sorted(combination))
            for combination in advisor_input.allowed_option_combinations
        }
        seen: set[tuple[str, ...]] = set()
        suggestions: list[BankingOptionSuggestion] = []
        for draft in composition.advice.suggestions:
            if len(set(draft.option_ids)) != len(draft.option_ids):
                raise BankingAdvisorBoundaryError(
                    "Banking advice contains duplicate option IDs in one suggestion."
                )
            if not set(draft.option_ids).issubset(known):
                raise BankingAdvisorBoundaryError(
                    "Banking advice references an option outside the deterministic matrix."
                )
            canonical = tuple(sorted(draft.option_ids))
            if len(canonical) > 1 and canonical not in allowed:
                raise BankingAdvisorBoundaryError(
                    "Banking advice contains an unconfigured option combination."
                )
            if canonical in seen:
                raise BankingAdvisorBoundaryError(
                    "Banking advice contains a duplicate option suggestion."
                )
            seen.add(canonical)
            suggestions.append(
                BankingOptionSuggestion(
                    suggestion_id=deterministic_id(
                        "BOSUG", matrix_id, canonical
                    ),
                    option_ids=canonical,
                    rationale=draft.rationale,
                )
            )
        return tuple(suggestions)

    @classmethod
    def _failed_safe(cls, message: str) -> BankingAdviceComponentResult:
        return BankingAdviceComponentResult(
            status=ComponentStatus.FAILED_SAFE,
            runtime_events=(
                RuntimeEvent(
                    event_type="BANKING_OPTION_ADVISOR_FAILED_SAFE",
                    message=message,
                ),
            ),
        )
