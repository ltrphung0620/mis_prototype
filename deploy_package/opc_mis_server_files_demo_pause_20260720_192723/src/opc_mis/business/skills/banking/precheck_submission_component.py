"""Prepare a governed Banking precheck submission proposal without executing it."""

from collections.abc import Iterable

from opc_mis.business.skills.banking.precheck_submission_context import (
    BankingPrecheckSubmissionProposalContext,
    BankingPrecheckSubmissionProposalContextError,
    BankingPrecheckSubmissionProposalContextLoader,
)
from opc_mis.domain.artifacts import ArtifactDraft, ArtifactEnvelope
from opc_mis.domain.banking_models import (
    BankingOptionCandidate,
    BankingOptionPrecheckReadiness,
)
from opc_mis.domain.banking_precheck_submission_models import (
    BankingPrecheckCatalogTerms,
    BankingPrecheckFieldBindingReference,
    BankingPrecheckGovernanceSourceFacts,
    BankingPrecheckHandlingPolicyReference,
    BankingPrecheckSubmissionCandidate,
    BankingPrecheckSubmissionProposal,
    BankingPrecheckSubmissionProposalComponentResult,
)
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import (
    ArtifactType,
    ComponentStatus,
    ProtectedAction,
    SourceType,
)
from opc_mis.domain.events import RuntimeEvent
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.lineage import deterministic_id
from opc_mis.domain.team_pack import SheetRegistry

_TERM_FIELDS = (
    "annual_rate_or_fee",
    "processing_fee_rate",
    "collateral_ratio",
    "minimum_amount",
)


class BankingPrecheckSubmissionProposalBuildError(RuntimeError):
    """Raised when validated artifacts cannot form an exact all-ready batch."""


class BankingPrecheckSubmissionProposalSkill:
    """Batch every READY option without ranking, selecting, or calling a bank."""

    component_id = "BANKING_PRECHECK_SUBMISSION_PROPOSAL_SKILL"

    def __init__(
        self,
        *,
        context_loader: BankingPrecheckSubmissionProposalContextLoader,
    ) -> None:
        self._context_loader = context_loader

    async def execute(
        self,
        context: ExecutionContext,
    ) -> BankingPrecheckSubmissionProposalComponentResult:
        """Return one proposal draft and no external or Governance side effects."""
        try:
            proposal_context = await self._context_loader.load(context)
            proposal, evidence_refs = self._build(proposal_context)
        except (
            BankingPrecheckSubmissionProposalContextError,
            BankingPrecheckSubmissionProposalBuildError,
        ) as exc:
            return BankingPrecheckSubmissionProposalComponentResult(
                status=ComponentStatus.FAILED_SAFE,
                runtime_events=(
                    RuntimeEvent(
                        event_type="BANKING_PRECHECK_SUBMISSION_PROPOSAL_FAILED_SAFE",
                        message=str(exc),
                    ),
                ),
            )

        draft = ArtifactDraft(
            artifact_type=ArtifactType.BANKING_PRECHECK_SUBMISSION_PROPOSAL,
            evaluation_case_id=proposal.evaluation_case_id,
            producer=self.component_id,
            payload=proposal.model_dump(mode="json"),
            evidence_refs=evidence_refs,
            identity_inputs={
                "source_artifact_ids": proposal.source_artifact_ids,
                "matrix_id": proposal.matrix_id,
                "readiness_id": proposal.readiness_id,
                "review_id": proposal.review_id,
                "banking_request_id": proposal.banking_request_id,
                "candidate_option_ids": proposal.candidate_option_ids,
                "requested_amount": proposal.requested_amount,
                "requested_amount_currency": proposal.requested_amount_currency,
                "mapping_hash": proposal.mapping_hash,
                "proposed_action": proposal.proposed_action,
                "proposal_mode": proposal.proposal_mode,
            },
        )
        return BankingPrecheckSubmissionProposalComponentResult(
            status=ComponentStatus.COMPLETED,
            proposal=proposal,
            artifacts=(draft,),
            runtime_events=(
                RuntimeEvent(
                    event_type="BANKING_PRECHECK_SUBMISSION_PROPOSAL_PREPARED",
                    message=(
                        "Banking prepared one governed batch containing every READY "
                        "option without selecting or submitting an option."
                    ),
                    metadata={
                        "proposal_id": proposal.proposal_id,
                        "candidate_count": len(proposal.candidates),
                        "proposed_action": proposal.proposed_action.value,
                    },
                ),
            ),
        )

    def _build(
        self,
        context: BankingPrecheckSubmissionProposalContext,
    ) -> tuple[BankingPrecheckSubmissionProposal, tuple[EvidenceRef, ...]]:
        matrix = context.matrix
        readiness = context.readiness
        review = context.review
        evidence = self._source_evidence(context.source_artifacts)
        candidates_by_id = {item.option_id: item for item in matrix.candidates}
        readiness_by_id = {
            item.option_id: item for item in readiness.option_readiness
        }
        proposal_items: list[BankingPrecheckSubmissionCandidate] = []
        for option_id in readiness.ready_option_ids:
            try:
                candidate = candidates_by_id[option_id]
                option_readiness = readiness_by_id[option_id]
            except KeyError as exc:  # guarded again at the build boundary
                raise BankingPrecheckSubmissionProposalBuildError(
                    f"READY option {option_id} is missing from an authoritative input."
                ) from exc
            proposal_items.append(
                self._candidate(
                    context=context,
                    candidate=candidate,
                    option_readiness=option_readiness,
                    evidence=evidence,
                )
            )

        proposal_id = deterministic_id(
            "BPSP",
            matrix.evaluation_case_id,
            matrix.request_id,
            matrix.matrix_id,
            readiness.readiness_id,
            review.review_id,
            matrix.mapping_hash,
            matrix.requested_amount,
            matrix.requested_amount_currency,
            tuple(item.proposal_item_id for item in proposal_items),
            context.source_artifact_ids,
            ProtectedAction.SUBMIT_BANKING_PRECHECK,
        )
        evidence_refs = tuple(evidence[key] for key in sorted(evidence))
        proposal = BankingPrecheckSubmissionProposal(
            proposal_id=proposal_id,
            evaluation_case_id=matrix.evaluation_case_id,
            dataset_id=matrix.dataset_id,
            contract_id=matrix.contract_id,
            banking_request_id=matrix.request_id,
            matrix_id=matrix.matrix_id,
            readiness_id=readiness.readiness_id,
            review_id=review.review_id,
            mapping_policy_id=matrix.mapping_policy_id,
            mapping_version=matrix.mapping_version,
            mapping_hash=matrix.mapping_hash,
            requested_amount=matrix.requested_amount,
            requested_amount_currency=matrix.requested_amount_currency,
            proposal_mode="BATCH_ALL_READY_OPTIONS",
            proposed_action=ProtectedAction.SUBMIT_BANKING_PRECHECK,
            candidate_option_ids=readiness.ready_option_ids,
            non_ready_option_ids=readiness.pending_option_ids,
            candidates=tuple(proposal_items),
            source_artifact_ids=context.source_artifact_ids,
            evidence_ids=tuple(item.evidence_id for item in evidence_refs),
            precheck_executed=False,
            submission_executed=False,
        )
        return proposal, evidence_refs

    def _candidate(
        self,
        *,
        context: BankingPrecheckSubmissionProposalContext,
        candidate: BankingOptionCandidate,
        option_readiness: BankingOptionPrecheckReadiness,
        evidence: dict[str, EvidenceRef],
    ) -> BankingPrecheckSubmissionCandidate:
        precheck = candidate.precheck
        if precheck is None or option_readiness.api_id != precheck.api_id:
            raise BankingPrecheckSubmissionProposalBuildError(
                f"READY option {candidate.option_id} has inconsistent API metadata."
            )
        term_evidence = tuple(
            self._one_matrix_evidence(
                context.matrix_artifact,
                record_id=candidate.bank_product_id,
                field=field,
            )
            for field in _TERM_FIELDS
        )
        field_bindings = tuple(
            BankingPrecheckFieldBindingReference(
                required_field=item.required_field,
                source=item.source,
                source_reference=item.source_reference,
                source_artifact_id=item.source_artifact_id,
                source_record_ids=item.source_record_ids,
                evidence_ids=item.evidence_ids,
            )
            for item in option_readiness.field_resolutions
        )
        source_artifact_ids = set(context.source_artifact_ids)
        if any(
            item.source_artifact_id is not None
            and item.source_artifact_id not in source_artifact_ids
            for item in field_bindings
        ):
            raise BankingPrecheckSubmissionProposalBuildError(
                f"READY option {candidate.option_id} has a binding outside proposal lineage."
            )
        governance_source_facts = self._governance_source_facts(
            candidate=candidate,
            evidence=evidence,
        )
        supporting_ids = tuple(
            dict.fromkeys(
                (
                    *candidate.evidence_ids,
                    *precheck.evidence_ids,
                    *option_readiness.evidence_ids,
                    *(item.evidence_id for item in term_evidence),
                    *(
                        evidence_id
                        for binding in field_bindings
                        for evidence_id in binding.evidence_ids
                    ),
                )
            )
        )
        missing_evidence_ids = tuple(
            item for item in supporting_ids if item not in evidence
        )
        if missing_evidence_ids:
            raise BankingPrecheckSubmissionProposalBuildError(
                f"READY option {candidate.option_id} references unavailable evidence: "
                + ", ".join(missing_evidence_ids)
            )
        proposal_item_id = deterministic_id(
            "BPSPI",
            context.matrix.matrix_id,
            context.readiness.readiness_id,
            context.review.review_id,
            candidate.option_id,
            precheck.api_id,
            governance_source_facts.model_dump(mode="json"),
            tuple(
                (
                    item.required_field,
                    item.source,
                    item.source_reference,
                    item.source_artifact_id,
                    item.source_record_ids,
                )
                for item in field_bindings
            ),
        )
        derived = self._batch_evidence(
            context=context,
            proposal_item_id=proposal_item_id,
            candidate=candidate,
            supporting=tuple(evidence[item] for item in supporting_ids),
        )
        evidence[derived.evidence_id] = derived
        item_evidence_ids = (*supporting_ids, derived.evidence_id)
        return BankingPrecheckSubmissionCandidate(
            proposal_item_id=proposal_item_id,
            option_id=candidate.option_id,
            bank_product_id=candidate.bank_product_id,
            need_type=candidate.need_type,
            provider=candidate.provider,
            product_name=candidate.product_name,
            api_id=precheck.api_id,
            api_provider=precheck.provider,
            api_method=precheck.method,
            api_endpoint=precheck.endpoint,
            governance_source_facts=governance_source_facts,
            catalog_terms=BankingPrecheckCatalogTerms(
                annual_rate_or_fee=candidate.annual_rate_or_fee,
                processing_fee_rate=candidate.processing_fee_rate,
                collateral_ratio=candidate.collateral_ratio,
                minimum_amount=candidate.minimum_amount,
                minimum_amount_currency=candidate.minimum_amount_currency,
                evidence_ids=tuple(item.evidence_id for item in term_evidence),
            ),
            field_bindings=field_bindings,
            evidence_ids=item_evidence_ids,
        )

    @staticmethod
    def _governance_source_facts(
        *,
        candidate: BankingOptionCandidate,
        evidence: dict[str, EvidenceRef],
    ) -> BankingPrecheckGovernanceSourceFacts:
        """Carry exact policy facts without interpreting whether approval is needed."""
        precheck = candidate.precheck
        if precheck is None:  # pragma: no cover - guarded by the READY boundary
            raise BankingPrecheckSubmissionProposalBuildError(
                f"READY option {candidate.option_id} has no precheck policy source."
            )
        extension_matches = tuple(
            item
            for evidence_id in precheck.evidence_ids
            if (item := evidence.get(evidence_id)) is not None
            and item.source_type is SourceType.TEAM_PACK
            and item.sheet == SheetRegistry.API_CATALOG.sheet_name
            and item.record_id == precheck.api_id
            and item.field == "extension_rule"
            and item.display_value == precheck.extension_rule
        )
        if len(extension_matches) != 1:
            raise BankingPrecheckSubmissionProposalBuildError(
                f"READY option {candidate.option_id} lacks one exact API extension rule."
            )
        handling_references: list[BankingPrecheckHandlingPolicyReference] = []
        for guidance in candidate.handling_guidance:
            expected = {
                "rule_id": guidance.rule_id,
                "applies_to": guidance.applies_to,
                "requires_human_approval": (
                    guidance.source_requires_human_approval_text
                ),
            }
            matches = tuple(
                item
                for evidence_id in guidance.evidence_ids
                if (item := evidence.get(evidence_id)) is not None
                and item.source_type is SourceType.TEAM_PACK
                and item.sheet == SheetRegistry.API_HANDLING_RULES.sheet_name
                and item.record_id == guidance.rule_id
                and item.field in expected
                and item.display_value == expected[item.field]
            )
            if {item.field for item in matches} != set(expected) or len(matches) != len(
                expected
            ):
                raise BankingPrecheckSubmissionProposalBuildError(
                    f"READY option {candidate.option_id} has incomplete handling policy "
                    f"lineage for {guidance.rule_id}."
                )
            handling_references.append(
                BankingPrecheckHandlingPolicyReference(
                    rule_id=guidance.rule_id,
                    applies_to=guidance.applies_to,
                    requires_human_approval_text=(
                        guidance.source_requires_human_approval_text
                    ),
                    evidence_ids=tuple(item.evidence_id for item in matches),
                )
            )
        return BankingPrecheckGovernanceSourceFacts(
            api_extension_rule=precheck.extension_rule,
            api_extension_rule_evidence_id=extension_matches[0].evidence_id,
            handling_rules=tuple(handling_references),
        )

    @staticmethod
    def _source_evidence(
        artifacts: Iterable[ArtifactEnvelope],
    ) -> dict[str, EvidenceRef]:
        evidence: dict[str, EvidenceRef] = {}
        for artifact in artifacts:
            for item in artifact.evidence_refs:
                existing = evidence.get(item.evidence_id)
                if existing is not None and existing != item:
                    raise BankingPrecheckSubmissionProposalBuildError(
                        f"Conflicting evidence payload for {item.evidence_id}."
                    )
                evidence[item.evidence_id] = item
        if not evidence:
            raise BankingPrecheckSubmissionProposalBuildError(
                "Banking precheck submission requires source evidence."
            )
        return evidence

    @staticmethod
    def _one_matrix_evidence(
        artifact: ArtifactEnvelope,
        *,
        record_id: str,
        field: str,
    ) -> EvidenceRef:
        matches = tuple(
            item
            for item in artifact.evidence_refs
            if item.sheet == SheetRegistry.BANK_PRODUCTS.sheet_name
            and item.record_id == record_id
            and item.field == field
        )
        if len(matches) != 1:
            raise BankingPrecheckSubmissionProposalBuildError(
                "Expected one exact catalog-term evidence item for "
                f"{record_id}.{field}."
            )
        return matches[0]

    @staticmethod
    def _batch_evidence(
        *,
        context: BankingPrecheckSubmissionProposalContext,
        proposal_item_id: str,
        candidate: BankingOptionCandidate,
        supporting: tuple[EvidenceRef, ...],
    ) -> EvidenceRef:
        source_ids = tuple(item.evidence_id for item in supporting)
        display = {
            "option_id": candidate.option_id,
            "readiness": "READY",
            "proposal_mode": "BATCH_ALL_READY_OPTIONS",
        }
        return EvidenceRef(
            evidence_id=deterministic_id(
                "EVD",
                context.matrix.dataset_id,
                SourceType.DERIVED,
                "BANKING_PRECHECK_SUBMISSION_PROPOSAL",
                proposal_item_id,
                display,
                source_ids,
            ),
            source_type=SourceType.DERIVED,
            sheet="BANKING_PRECHECK_SUBMISSION_PROPOSAL",
            row_number=0,
            record_id=proposal_item_id,
            field="ready_option_included",
            display_value=display,
            source_evidence_ids=source_ids,
        )
