"""Deterministic Decision review after a governed Banking precheck."""

from opc_mis.business.agents.decision.post_precheck_context import (
    DecisionPostPrecheckContext,
    DecisionPostPrecheckContextError,
    DecisionPostPrecheckContextLoader,
)
from opc_mis.domain.artifacts import ArtifactDraft
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.decision_post_precheck_models import (
    DecisionPostPrecheckComponentResult,
    DecisionPostPrecheckOptionReview,
    DecisionPostPrecheckReview,
    decision_post_precheck_disposition,
    decision_post_precheck_evidence_id,
    decision_post_precheck_item_id,
    decision_post_precheck_outcome,
    decision_post_precheck_review_id,
)
from opc_mis.domain.enums import (
    ArtifactType,
    BankingPrecheckOutcome,
    ComponentStatus,
    DecisionPostPrecheckOutcome,
    SourceType,
)
from opc_mis.domain.events import RuntimeEvent
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.lineage import deterministic_id
from opc_mis.domain.missing_data import MissingDataRequest


class DecisionPostPrecheckReviewer:
    """Preserve and classify every result without selecting a Banking option."""

    component_id = "DECISION_POST_PRECHECK_REVIEW"

    def __init__(self, *, context_loader: DecisionPostPrecheckContextLoader) -> None:
        self._context_loader = context_loader

    async def execute(
        self, context: ExecutionContext
    ) -> DecisionPostPrecheckComponentResult:
        try:
            review_context = await self._context_loader.load(context)
            review, evidence_refs = self._build(review_context)
        except (DecisionPostPrecheckContextError, ValueError) as exc:
            return self._failed_safe(str(exc))

        draft = ArtifactDraft(
            artifact_type=ArtifactType.DECISION_POST_PRECHECK_REVIEW,
            evaluation_case_id=review.evaluation_case_id,
            producer=self.component_id,
            payload=review.model_dump(mode="json"),
            evidence_refs=evidence_refs,
            identity_inputs={
                "source_artifact_ids": review.source_artifact_ids,
                "result_set_id": review.result_set_id,
                "proposal_id": review.proposal_id,
                "review_item_ids": tuple(
                    item.review_item_id for item in review.option_reviews
                ),
                "outcome": review.outcome,
                "missing_data_request_ids": tuple(
                    item.request_id for item in review.missing_data_requests
                ),
                "source_authority": review.source_authority,
            },
        )
        if (
            review.outcome
            is DecisionPostPrecheckOutcome.FOLLOW_UP_EVIDENCE_REQUIRED
        ):
            status = ComponentStatus.WAITING_FOR_INPUT
        elif (
            review.outcome
            is DecisionPostPrecheckOutcome.CONDITIONAL_OPTIONS_AVAILABLE
        ):
            status = ComponentStatus.COMPLETED
        else:
            status = ComponentStatus.COMPLETED_WITH_WARNINGS
        warnings = (
            ()
            if status is ComponentStatus.COMPLETED
            else (f"DECISION_POST_PRECHECK_{review.outcome.value}",)
        )
        return DecisionPostPrecheckComponentResult(
            status=status,
            review=review,
            artifacts=(draft,),
            missing_data_requests=review.missing_data_requests,
            warnings=warnings,
            runtime_events=(
                RuntimeEvent(
                    event_type="DECISION_POST_PRECHECK_REVIEW_COMPLETED",
                    message=(
                        "Decision classified every non-binding Banking precheck "
                        "result without selection, ranking, approval, or document work."
                    ),
                    metadata={
                        "review_id": review.review_id,
                        "outcome": review.outcome.value,
                        "candidate_count": len(review.option_reviews),
                        "missing_request_count": len(
                            review.missing_data_requests
                        ),
                    },
                ),
            ),
        )

    def _build(
        self,
        context: DecisionPostPrecheckContext,
    ) -> tuple[DecisionPostPrecheckReview, tuple[EvidenceRef, ...]]:
        result_set = context.result_set
        evidence_by_id = {
            item.evidence_id: item
            for artifact in (
                context.result_set_artifact,
                context.proposal_artifact,
            )
            for item in artifact.evidence_refs
        }
        selected_evidence: dict[str, EvidenceRef] = {}
        option_reviews: list[DecisionPostPrecheckOptionReview] = []
        disposition_evidence: dict[str, EvidenceRef] = {}
        for result in result_set.results:
            source_evidence = tuple(
                evidence_by_id[evidence_id]
                for evidence_id in result.evidence_ids
            )
            pending_evidence_ids = list(result.evidence_ids)
            while pending_evidence_ids:
                evidence_id = pending_evidence_ids.pop()
                if evidence_id in selected_evidence:
                    continue
                evidence = evidence_by_id[evidence_id]
                selected_evidence[evidence.evidence_id] = evidence
                pending_evidence_ids.extend(evidence.source_evidence_ids)
            disposition = decision_post_precheck_disposition(result.outcome)
            review_item_id = decision_post_precheck_item_id(
                result_set_id=result_set.result_set_id,
                normalized_result_id=result.normalized_result_id,
                proposal_item_id=result.proposal_item_id,
                option_id=result.option_id,
                bank_product_id=result.bank_product_id,
                source_outcome=result.outcome,
                disposition=disposition,
                required_follow_up_fields=result.required_follow_up_fields,
            )
            display = {
                "review_item_id": review_item_id,
                "normalized_result_id": result.normalized_result_id,
                "proposal_item_id": result.proposal_item_id,
                "option_id": result.option_id,
                "bank_product_id": result.bank_product_id,
                "source_outcome": result.outcome.value,
                "disposition": disposition.value,
                "non_binding": True,
            }
            source_ids = tuple(item.evidence_id for item in source_evidence)
            derived = EvidenceRef(
                evidence_id=decision_post_precheck_evidence_id(
                    dataset_id=result_set.dataset_id,
                    review_item_id=review_item_id,
                    display=display,
                    source_evidence_ids=source_ids,
                ),
                source_type=SourceType.DERIVED,
                sheet="DECISION_POST_PRECHECK_REVIEW",
                row_number=0,
                record_id=review_item_id,
                field="precheck_disposition",
                display_value=display,
                source_evidence_ids=source_ids,
            )
            selected_evidence[derived.evidence_id] = derived
            disposition_evidence[result.normalized_result_id] = derived
            option_reviews.append(
                DecisionPostPrecheckOptionReview(
                    review_item_id=review_item_id,
                    normalized_result_id=result.normalized_result_id,
                    proposal_item_id=result.proposal_item_id,
                    option_id=result.option_id,
                    bank_product_id=result.bank_product_id,
                    api_id=result.api_id,
                    api_provider=result.api_provider,
                    source_outcome=result.outcome,
                    disposition=disposition,
                    reason_codes=result.reason_codes,
                    required_follow_up_fields=(
                        result.required_follow_up_fields
                    ),
                    evidence_ids=(derived.evidence_id,),
                    non_binding=True,
                )
            )
        reviews = tuple(option_reviews)
        missing_requests = self._missing_requests(
            context=context,
            option_reviews=reviews,
            disposition_evidence=disposition_evidence,
        )
        outcome = decision_post_precheck_outcome(
            tuple(item.source_outcome for item in reviews)
        )
        review_id = decision_post_precheck_review_id(
            result_set_artifact_id=context.result_set_artifact.artifact_id,
            result_set_id=result_set.result_set_id,
            proposal_artifact_id=context.proposal_artifact.artifact_id,
            item_ids=tuple(item.review_item_id for item in reviews),
            outcome=outcome,
            missing_request_ids=tuple(
                item.request_id for item in missing_requests
            ),
        )
        evidence_refs = tuple(
            selected_evidence[key] for key in sorted(selected_evidence)
        )
        review = DecisionPostPrecheckReview(
            review_id=review_id,
            evaluation_case_id=result_set.evaluation_case_id,
            dataset_id=result_set.dataset_id,
            contract_id=result_set.contract_id,
            result_set_artifact_id=context.result_set_artifact.artifact_id,
            result_set_id=result_set.result_set_id,
            proposal_artifact_id=context.proposal_artifact.artifact_id,
            proposal_id=context.proposal.proposal_id,
            source_authority=result_set.authority,
            outcome=outcome,
            option_reviews=reviews,
            candidate_option_ids=tuple(item.option_id for item in reviews),
            candidate_bank_product_ids=tuple(
                item.bank_product_id for item in reviews
            ),
            conditional_option_ids=self._option_ids(
                reviews, BankingPrecheckOutcome.CONDITIONAL_PRECHECK
            ),
            evidence_required_option_ids=self._option_ids(
                reviews, BankingPrecheckOutcome.MISSING_EVIDENCE
            ),
            not_eligible_option_ids=self._option_ids(
                reviews, BankingPrecheckOutcome.NOT_ELIGIBLE
            ),
            no_recommendation_option_ids=self._option_ids(
                reviews, BankingPrecheckOutcome.NO_RECOMMENDATION
            ),
            unavailable_option_ids=self._option_ids(
                reviews, BankingPrecheckOutcome.SERVICE_UNAVAILABLE
            ),
            required_input_fields=tuple(
                dict.fromkeys(item.field for item in missing_requests)
            ),
            missing_data_requests=missing_requests,
            source_artifact_ids=context.source_artifact_ids,
            evidence_ids=tuple(item.evidence_id for item in evidence_refs),
            non_binding=True,
            bank_approval_obtained=False,
            selection_performed=False,
            ranking_performed=False,
            documents_prepared=False,
        )
        return review, evidence_refs

    def _missing_requests(
        self,
        *,
        context: DecisionPostPrecheckContext,
        option_reviews: tuple[DecisionPostPrecheckOptionReview, ...],
        disposition_evidence: dict[str, EvidenceRef],
    ) -> tuple[MissingDataRequest, ...]:
        requests: list[MissingDataRequest] = []
        for item in option_reviews:
            if item.source_outcome is not BankingPrecheckOutcome.MISSING_EVIDENCE:
                continue
            if not item.required_follow_up_fields or any(
                not field.strip() for field in item.required_follow_up_fields
            ):
                raise ValueError(
                    "MISSING_EVIDENCE result lacks explicit follow-up fields; "
                    "Decision will not invent a requirement."
                )
            evidence = disposition_evidence[item.normalized_result_id]
            for field in item.required_follow_up_fields:
                requests.append(
                    MissingDataRequest(
                        request_id=deterministic_id(
                            "MDR",
                            context.result_set.evaluation_case_id,
                            context.result_set.result_set_id,
                            item.normalized_result_id,
                            item.option_id,
                            item.bank_product_id,
                            field,
                        ),
                        evaluation_case_id=(
                            context.result_set.evaluation_case_id
                        ),
                        raised_by=self.component_id,
                        requirement_code=(
                            "BANKING_PRECHECK_FOLLOW_UP_EVIDENCE_REQUIRED"
                        ),
                        target_record=item.normalized_result_id,
                        field=field,
                        expected_type=(
                            "explicit value or evidence reference for the named "
                            "precheck follow-up field"
                        ),
                        reason=(
                            "The non-binding precheck result explicitly identifies "
                            f"{field} as missing for option {item.option_id}."
                        ),
                        evidence_refs=(evidence,),
                    )
                )
        return tuple(requests)

    @staticmethod
    def _option_ids(
        reviews: tuple[DecisionPostPrecheckOptionReview, ...],
        outcome: BankingPrecheckOutcome,
    ) -> tuple[str, ...]:
        return tuple(
            item.option_id for item in reviews if item.source_outcome is outcome
        )

    @staticmethod
    def _failed_safe(message: str) -> DecisionPostPrecheckComponentResult:
        return DecisionPostPrecheckComponentResult(
            status=ComponentStatus.FAILED_SAFE,
            runtime_events=(
                RuntimeEvent(
                    event_type="DECISION_POST_PRECHECK_FAILED_SAFE",
                    message=message,
                ),
            ),
        )
