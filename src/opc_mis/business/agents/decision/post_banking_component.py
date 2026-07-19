"""Deterministic Decision review after Banking precheck readiness."""

from opc_mis.business.agents.decision.post_banking_context import (
    DecisionPostBankingContext,
    DecisionPostBankingContextError,
    DecisionPostBankingContextLoader,
)
from opc_mis.domain.artifacts import ArtifactDraft
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.decision_post_banking_models import (
    DecisionPostBankingComponentResult,
    DecisionPostBankingReview,
)
from opc_mis.domain.enums import (
    ArtifactType,
    BankingPrecheckFieldSource,
    BankingPrecheckFieldStatus,
    BankingPrecheckReadinessStatus,
    ComponentStatus,
    DecisionPostBankingOutcome,
)
from opc_mis.domain.events import RuntimeEvent
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.lineage import deterministic_id
from opc_mis.domain.missing_data import MissingDataRequest


class DecisionPostBankingReviewer:
    """Classify readiness and durably request input without selecting an option."""

    component_id = "DECISION_POST_BANKING_REVIEW"

    def __init__(self, *, context_loader: DecisionPostBankingContextLoader) -> None:
        self._context_loader = context_loader

    async def execute(
        self, context: ExecutionContext
    ) -> DecisionPostBankingComponentResult:
        try:
            review_context = await self._context_loader.load(context)
        except DecisionPostBankingContextError as exc:
            return DecisionPostBankingComponentResult(
                status=ComponentStatus.FAILED_SAFE,
                runtime_events=(
                    RuntimeEvent(
                        event_type="DECISION_POST_BANKING_FAILED_SAFE",
                        message=str(exc),
                    ),
                ),
            )

        missing_requests = self._missing_requests(review_context)
        outcome = self._outcome(review_context, missing_requests)
        evidence_refs = self._evidence(review_context)
        matrix = review_context.matrix
        readiness = review_context.readiness
        review = DecisionPostBankingReview(
            review_id=deterministic_id(
                "DPBR",
                matrix.matrix_id,
                matrix.request_id,
                readiness.readiness_id,
                outcome,
                tuple(item.request_id for item in missing_requests),
                review_context.source_artifact_ids,
            ),
            evaluation_case_id=matrix.evaluation_case_id,
            dataset_id=matrix.dataset_id,
            contract_id=matrix.contract_id,
            matrix_id=matrix.matrix_id,
            banking_request_id=matrix.request_id,
            readiness_id=readiness.readiness_id,
            outcome=outcome,
            candidate_option_ids=tuple(item.option_id for item in matrix.candidates),
            precheck_ready_option_ids=readiness.ready_option_ids,
            pending_option_ids=readiness.pending_option_ids,
            required_input_fields=tuple(item.field for item in missing_requests),
            missing_data_requests=missing_requests,
            source_artifact_ids=review_context.source_artifact_ids,
            evidence_ids=tuple(item.evidence_id for item in evidence_refs),
            precheck_executed=False,
        )
        draft = ArtifactDraft(
            artifact_type=ArtifactType.DECISION_POST_BANKING_REVIEW,
            evaluation_case_id=review.evaluation_case_id,
            producer=self.component_id,
            payload=review.model_dump(mode="json"),
            evidence_refs=evidence_refs,
            identity_inputs={
                "source_artifact_ids": review.source_artifact_ids,
                "matrix_id": review.matrix_id,
                "banking_request_id": review.banking_request_id,
                "readiness_id": review.readiness_id,
                "outcome": review.outcome,
                "missing_data_request_ids": tuple(
                    item.request_id for item in missing_requests
                ),
            },
        )
        status = (
            ComponentStatus.WAITING_FOR_INPUT
            if outcome is DecisionPostBankingOutcome.BANKING_INPUT_REQUIRED
            else ComponentStatus.COMPLETED
            if outcome is DecisionPostBankingOutcome.BANKING_PRECHECK_READY
            else ComponentStatus.COMPLETED_WITH_WARNINGS
        )
        warnings = (
            ()
            if outcome is DecisionPostBankingOutcome.BANKING_PRECHECK_READY
            else (f"DECISION_POST_BANKING_{outcome.value}",)
        )
        return DecisionPostBankingComponentResult(
            status=status,
            review=review,
            artifacts=(draft,),
            missing_data_requests=missing_requests,
            warnings=warnings,
            runtime_events=(
                RuntimeEvent(
                    event_type="DECISION_POST_BANKING_REVIEW_COMPLETED",
                    message=(
                        "Decision classified Banking readiness without selecting a "
                        "product or executing a protected action."
                    ),
                    metadata={
                        "outcome": outcome.value,
                        "missing_request_count": len(missing_requests),
                    },
                ),
            ),
        )

    @classmethod
    def _missing_requests(
        cls,
        context: DecisionPostBankingContext,
    ) -> tuple[MissingDataRequest, ...]:
        evidence_by_id = {
            item.evidence_id: item
            for artifact in (
                context.matrix_artifact,
                context.readiness_artifact,
            )
            for item in artifact.evidence_refs
        }
        requests: list[MissingDataRequest] = []
        seen: set[tuple[BankingPrecheckFieldSource | None, str | None]] = set()
        for option in context.readiness.option_readiness:
            for resolution in option.field_resolutions:
                if resolution.status not in {
                    BankingPrecheckFieldStatus.MISSING_INPUT,
                    BankingPrecheckFieldStatus.SOURCE_UNAVAILABLE,
                }:
                    continue
                key = (resolution.source, resolution.source_reference)
                if key in seen:
                    continue
                seen.add(key)
                code, field, expected_type, reason = cls._requirement_contract(
                    resolution.source
                )
                evidence_refs = tuple(
                    evidence_by_id[evidence_id]
                    for evidence_id in resolution.evidence_ids
                )
                requests.append(
                    MissingDataRequest(
                        request_id=deterministic_id(
                            "MDR",
                            context.matrix.evaluation_case_id,
                            context.matrix.request_id,
                            cls.component_id,
                            code,
                            field,
                        ),
                        evaluation_case_id=context.matrix.evaluation_case_id,
                        raised_by=cls.component_id,
                        requirement_code=code,
                        target_record=context.matrix.request_id,
                        field=field,
                        expected_type=expected_type,
                        reason=reason,
                        evidence_refs=evidence_refs,
                    )
                )
        return tuple(requests)

    @staticmethod
    def _requirement_contract(
        source: BankingPrecheckFieldSource | None,
    ) -> tuple[str, str, str, str]:
        if source is BankingPrecheckFieldSource.BANKING_INPUT_SUPPLEMENT:
            return (
                "BANKING_PRECHECK_AMOUNT_REQUIRED",
                "requested_amount",
                "positive integer VND amount",
                (
                    "The configured Banking precheck requires an amount from an "
                    "immutable BankingInputSupplement."
                ),
            )
        if source is BankingPrecheckFieldSource.OPC_PROFILE:
            return (
                "BANKING_COMPANY_PROFILE_REQUIRED",
                "company_profile",
                "one or more exact 02_OPC_PROFILE field/value records",
                (
                    "The configured Banking precheck requires a company profile "
                    "reference from 02_OPC_PROFILE."
                ),
            )
        return (
            "BANKING_PRECHECK_SOURCE_REQUIRED",
            "contract_id",
            "validated EvaluationCase contract_id",
            "The configured Banking precheck source is unavailable.",
        )

    @staticmethod
    def _outcome(
        context: DecisionPostBankingContext,
        missing_requests: tuple[MissingDataRequest, ...],
    ) -> DecisionPostBankingOutcome:
        if missing_requests:
            return DecisionPostBankingOutcome.BANKING_INPUT_REQUIRED
        readiness = context.readiness
        if readiness.ready_option_ids:
            return DecisionPostBankingOutcome.BANKING_PRECHECK_READY
        if (
            readiness.status
            is BankingPrecheckReadinessStatus.OPTION_REQUIREMENTS_NOT_MET
        ):
            return DecisionPostBankingOutcome.NO_VIABLE_OPTION
        if readiness.status is BankingPrecheckReadinessStatus.NOT_CONFIGURED:
            return DecisionPostBankingOutcome.NO_PRECHECK_PATH
        if readiness.status is BankingPrecheckReadinessStatus.UNSUPPORTED_MAPPING:
            return DecisionPostBankingOutcome.UNSUPPORTED_PRECHECK_MAPPING
        return DecisionPostBankingOutcome.NO_VIABLE_OPTION

    @staticmethod
    def _evidence(
        context: DecisionPostBankingContext,
    ) -> tuple[EvidenceRef, ...]:
        by_id = {
            item.evidence_id: item
            for artifact in (
                context.matrix_artifact,
                context.readiness_artifact,
            )
            for item in artifact.evidence_refs
        }
        return tuple(by_id[key] for key in sorted(by_id))
