"""Side-effect-free Decision handoff from conditional precheck to Document."""

from pydantic import ValidationError

from opc_mis.business.agents.decision.document_handoff_context import (
    DecisionDocumentHandoffContext,
    DecisionDocumentHandoffContextError,
    DecisionDocumentHandoffContextLoader,
)
from opc_mis.domain.artifacts import ArtifactDraft
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.document_models import (
    DecisionDocumentHandoffComponentResult,
    DocumentPreparationRequest,
    DocumentRequirementCode,
    document_preparation_request_id,
)
from opc_mis.domain.enums import (
    ArtifactType,
    BankingPrecheckOutcome,
    ComponentStatus,
    DecisionHandoffMode,
    DecisionPostPrecheckOptionDisposition,
    ProviderEligibilityStatus,
    ProviderGuaranteeDecision,
    SourceType,
)
from opc_mis.domain.events import RuntimeEvent
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.lineage import deterministic_id


class DecisionDocumentHandoff:
    """Create internal Document requests without selecting, persisting, or sending."""

    component_id = "DECISION_DOCUMENT_HANDOFF"

    def __init__(self, *, context_loader: DecisionDocumentHandoffContextLoader) -> None:
        self._context_loader = context_loader

    async def execute(
        self, context: ExecutionContext
    ) -> DecisionDocumentHandoffComponentResult:
        try:
            mode = DecisionHandoffMode(context.component_input["execution_mode"])
        except (KeyError, ValueError):
            return self._failed_safe(
                "Decision Document handoff requires explicit DOCUMENT_PREPARATION mode."
            )
        if mode is not DecisionHandoffMode.DOCUMENT_PREPARATION:
            return self._failed_safe("Unsupported Decision Document handoff mode.")
        try:
            handoff_context = await self._context_loader.load(context)
            requests, evidence_refs = self._build(handoff_context)
        except (DecisionDocumentHandoffContextError, ValidationError, ValueError) as exc:
            return self._failed_safe(str(exc))

        if not requests:
            return DecisionDocumentHandoffComponentResult(
                status=ComponentStatus.COMPLETED_WITH_WARNINGS,
                warnings=("DOCUMENT_HANDOFF_NO_VIABLE_CONDITIONAL_RESULT",),
                runtime_events=(
                    RuntimeEvent(
                        event_type="DECISION_DOCUMENT_HANDOFF_NOT_APPLICABLE",
                        message=(
                            "No full-coverage conditional provider result can enter "
                            "Document preparation; no request was created."
                        ),
                    ),
                ),
            )

        evidence_by_request = {
            request.request_id: self._evidence_closure(
                evidence_refs, request.evidence_ids
            )
            for request in requests
        }
        drafts = tuple(
            ArtifactDraft(
                artifact_type=ArtifactType.DOCUMENT_PREPARATION_REQUEST,
                evaluation_case_id=request.evaluation_case_id,
                producer=self.component_id,
                payload=request.model_dump(mode="json"),
                evidence_refs=evidence_by_request[request.request_id],
                identity_inputs={
                    "source_artifact_ids": request.source_artifact_ids,
                    "normalized_result_id": request.normalized_result_id,
                    "review_item_id": request.review_item_id,
                    "option_id": request.option_id,
                    "required_document_codes": request.required_document_codes,
                    "approval_condition_codes": request.approval_condition_codes,
                },
            )
            for request in requests
        )
        return DecisionDocumentHandoffComponentResult(
            status=ComponentStatus.COMPLETED,
            preparation_requests=requests,
            artifacts=drafts,
            runtime_events=(
                RuntimeEvent(
                    event_type="DOCUMENT_PREPARATION_REQUESTS_CREATED",
                    message=(
                        "Decision preserved every viable conditional provider result "
                        "as an independent internal Document request."
                    ),
                    metadata={"request_count": len(requests)},
                ),
            ),
        )

    def _build(
        self, context: DecisionDocumentHandoffContext
    ) -> tuple[tuple[DocumentPreparationRequest, ...], tuple[EvidenceRef, ...]]:
        evidence = {
            item.evidence_id: item
            for artifact in (context.review_artifact, context.result_set_artifact)
            for item in artifact.evidence_refs
        }
        requests: list[DocumentPreparationRequest] = []
        for result, review_item in zip(
            context.result_set.results,
            context.review.option_reviews,
            strict=True,
        ):
            if result.outcome is not BankingPrecheckOutcome.CONDITIONAL_PRECHECK:
                continue
            if (
                review_item.disposition
                is not DecisionPostPrecheckOptionDisposition.CONDITIONAL_REVIEW
            ):
                raise ValueError(
                    "A conditional Banking result lacks its exact conditional review."
                )
            if result.eligibility_status not in {
                ProviderEligibilityStatus.ELIGIBLE,
                ProviderEligibilityStatus.CONDITIONAL,
            } or result.guarantee_decision not in {
                ProviderGuaranteeDecision.WILLING,
                ProviderGuaranteeDecision.CONDITIONAL,
            }:
                raise ValueError(
                    "A conditional Banking result has a non-viable provider posture."
                )
            if result.supported_amount != result.requested_amount:
                # Partial coverage is intentionally left for a later increment.
                continue
            document_codes = tuple(
                DocumentRequirementCode(item) for item in result.required_documents
            )
            source_ids = tuple(
                dict.fromkeys((*result.evidence_ids, *review_item.evidence_ids))
            )
            missing_evidence = tuple(item for item in source_ids if item not in evidence)
            if missing_evidence:
                raise ValueError(
                    "Document handoff references unavailable provider evidence: "
                    + ", ".join(missing_evidence)
                )
            request_id = document_preparation_request_id(
                result_set_artifact_id=context.result_set_artifact.artifact_id,
                review_artifact_id=context.review_artifact.artifact_id,
                normalized_result_id=result.normalized_result_id,
                review_item_id=review_item.review_item_id,
                option_id=result.option_id,
                required_document_codes=document_codes,
                approval_condition_codes=result.approval_conditions,
            )
            display = {
                "request_id": request_id,
                "normalized_result_id": result.normalized_result_id,
                "review_item_id": review_item.review_item_id,
                "option_id": result.option_id,
                "contract_id": context.result_set.contract_id,
                "bank_product_id": result.bank_product_id,
                "requested_amount": result.requested_amount,
                "currency": result.currency.value,
                "request_type": "PERFORMANCE_BOND",
                "required_document_codes": [item.value for item in document_codes],
                "approval_condition_codes": list(result.approval_conditions),
                "non_binding": True,
            }
            derived = EvidenceRef(
                evidence_id=deterministic_id(
                    "EVD",
                    context.result_set.dataset_id,
                    SourceType.DERIVED,
                    "DOCUMENT_PREPARATION_REQUEST",
                    request_id,
                    display,
                    source_ids,
                ),
                source_type=SourceType.DERIVED,
                sheet="DOCUMENT_PREPARATION_REQUEST",
                row_number=0,
                record_id=request_id,
                field="provider_document_handoff",
                display_value=display,
                source_evidence_ids=source_ids,
            )
            evidence[derived.evidence_id] = derived
            requests.append(
                DocumentPreparationRequest(
                    request_id=request_id,
                    evaluation_case_id=context.result_set.evaluation_case_id,
                    dataset_id=context.result_set.dataset_id,
                    contract_id=context.result_set.contract_id,
                    normalized_result_id=result.normalized_result_id,
                    review_item_id=review_item.review_item_id,
                    option_id=result.option_id,
                    bank_product_id=result.bank_product_id,
                    api_id=result.api_id,
                    provider=result.api_provider,
                    provider_reference=result.provider_reference,
                    requested_amount=result.requested_amount,
                    supported_amount=result.supported_amount,
                    currency=result.currency,
                    required_document_codes=document_codes,
                    approval_condition_codes=result.approval_conditions,
                    provider_result_authority=result.authority,
                    source_artifact_ids=context.source_artifact_ids,
                    evidence_ids=(derived.evidence_id,),
                )
            )
        return tuple(requests), tuple(evidence[key] for key in sorted(evidence))

    @staticmethod
    def _evidence_closure(
        available: tuple[EvidenceRef, ...], selected_ids: tuple[str, ...]
    ) -> tuple[EvidenceRef, ...]:
        by_id = {item.evidence_id: item for item in available}
        pending = list(selected_ids)
        included: set[str] = set()
        while pending:
            evidence_id = pending.pop()
            evidence = by_id.get(evidence_id)
            if evidence is None:
                raise ValueError(
                    f"Document handoff evidence {evidence_id} is unavailable."
                )
            if evidence_id in included:
                continue
            included.add(evidence_id)
            pending.extend(evidence.source_evidence_ids)
        return tuple(by_id[item] for item in sorted(included))

    @staticmethod
    def _failed_safe(message: str) -> DecisionDocumentHandoffComponentResult:
        return DecisionDocumentHandoffComponentResult(
            status=ComponentStatus.FAILED_SAFE,
            runtime_events=(
                RuntimeEvent(
                    event_type="DECISION_DOCUMENT_HANDOFF_FAILED_SAFE",
                    message=message,
                ),
            ),
        )
