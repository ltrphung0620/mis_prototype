"""Resolve an authorized Banking precheck request from explicit proposal bindings."""

from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.banking_models import BankingInputSupplement
from opc_mis.domain.banking_precheck_execution_models import (
    AuthorizedActionPermit,
    BankingCompanyProfileField,
    BankingPrecheckRequest,
    banking_precheck_idempotency_key,
    banking_precheck_request_hash,
)
from opc_mis.domain.banking_precheck_submission_models import (
    BankingPrecheckFieldBindingReference,
    BankingPrecheckSubmissionCandidate,
    BankingPrecheckSubmissionProposal,
)
from opc_mis.domain.dataset import DatasetRecord
from opc_mis.domain.enums import (
    ArtifactType,
    BankingPrecheckFieldSource,
    CurrencyCode,
    ProtectedAction,
    SourceType,
    ValidationStatus,
)
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.lineage import deterministic_id
from opc_mis.domain.planner_models import EvaluationCase
from opc_mis.domain.team_pack import SheetRegistry

_VALID_ARTIFACT_STATUSES = {
    ValidationStatus.VALID,
    ValidationStatus.VALID_WITH_WARNINGS,
}
_EXPECTED_FIELDS = ("contract_id", "amount", "company_profile")


class BankingPrecheckRequestResolutionError(RuntimeError):
    """Raised when approved references cannot be resolved exactly and safely."""


class BankingPrecheckRequestResolver:
    """Build in-memory adapter requests without persisting sensitive field values."""

    def resolve(
        self,
        *,
        proposal_artifact: ArtifactEnvelope,
        evaluation_case_artifact: ArtifactEnvelope,
        supplement_artifact: ArtifactEnvelope,
        proposal: BankingPrecheckSubmissionProposal,
        evaluation_case: EvaluationCase,
        supplement: BankingInputSupplement,
        opc_profile_records: tuple[DatasetRecord, ...],
        authorization: AuthorizedActionPermit,
    ) -> tuple[BankingPrecheckRequest, ...]:
        """Resolve every approved candidate in proposal order from exact source IDs."""
        self._validate_context(
            proposal_artifact=proposal_artifact,
            evaluation_case_artifact=evaluation_case_artifact,
            supplement_artifact=supplement_artifact,
            proposal=proposal,
            evaluation_case=evaluation_case,
            supplement=supplement,
            authorization=authorization,
        )
        profile_by_id = self._profile_index(opc_profile_records)
        approved_evidence_by_id = self._approved_evidence_index(
            proposal_artifact=proposal_artifact,
            proposal=proposal,
        )
        requests = tuple(
            self._request(
                candidate=candidate,
                proposal_artifact=proposal_artifact,
                evaluation_case_artifact=evaluation_case_artifact,
                supplement_artifact=supplement_artifact,
                proposal=proposal,
                evaluation_case=evaluation_case,
                supplement=supplement,
                profile_by_id=profile_by_id,
                approved_evidence_by_id=approved_evidence_by_id,
                authorization=authorization,
            )
            for candidate in proposal.candidates
        )
        if tuple(item.option_id for item in requests) != proposal.candidate_option_ids:
            raise BankingPrecheckRequestResolutionError(
                "Resolved request order does not match the approved candidate batch."
            )
        return requests

    @staticmethod
    def _validate_context(
        *,
        proposal_artifact: ArtifactEnvelope,
        evaluation_case_artifact: ArtifactEnvelope,
        supplement_artifact: ArtifactEnvelope,
        proposal: BankingPrecheckSubmissionProposal,
        evaluation_case: EvaluationCase,
        supplement: BankingInputSupplement,
        authorization: AuthorizedActionPermit,
    ) -> None:
        expected_types = (
            (proposal_artifact, ArtifactType.BANKING_PRECHECK_SUBMISSION_PROPOSAL),
            (evaluation_case_artifact, ArtifactType.EVALUATION_CASE),
            (supplement_artifact, ArtifactType.BANKING_INPUT_SUPPLEMENT),
        )
        if any(
            artifact.artifact_type is not artifact_type
            or artifact.validation_status not in _VALID_ARTIFACT_STATUSES
            for artifact, artifact_type in expected_types
        ):
            raise BankingPrecheckRequestResolutionError(
                "Precheck execution requires validated proposal, case, and supplement artifacts."
            )
        if proposal_artifact.payload != proposal.model_dump(mode="json"):
            raise BankingPrecheckRequestResolutionError(
                "The approved proposal payload does not match its persisted envelope."
            )
        if evaluation_case_artifact.payload != evaluation_case.model_dump(mode="json"):
            raise BankingPrecheckRequestResolutionError(
                "The evaluation case payload does not match its persisted envelope."
            )
        if supplement_artifact.payload != supplement.model_dump(mode="json"):
            raise BankingPrecheckRequestResolutionError(
                "The Banking supplement payload does not match its persisted envelope."
            )
        if (
            authorization.protected_action
            is not ProtectedAction.SUBMIT_BANKING_PRECHECK
            or authorization.subject_artifact_id != proposal_artifact.artifact_id
            or authorization.subject_artifact_version != proposal_artifact.version
            or authorization.subject_input_hash != proposal_artifact.input_hash
            or authorization.evaluation_case_id != proposal.evaluation_case_id
        ):
            raise BankingPrecheckRequestResolutionError(
                "Governance permit does not authorize this exact proposal envelope."
            )
        expected_identity = (
            proposal.evaluation_case_id,
            proposal.dataset_id,
            proposal.contract_id,
        )
        if (
            evaluation_case.evaluation_case_id,
            evaluation_case.dataset_id,
            evaluation_case.contract_id,
        ) != expected_identity or (
            supplement.evaluation_case_id,
            supplement.dataset_id,
            supplement.contract_id,
        ) != expected_identity:
            raise BankingPrecheckRequestResolutionError(
                "Proposal, evaluation case, and Banking supplement identities disagree."
            )
        if (
            proposal.requested_amount != supplement.requested_amount
            or proposal.requested_amount_currency
            is not supplement.requested_amount_currency
            or proposal.requested_amount_currency is not CurrencyCode.VND
        ):
            raise BankingPrecheckRequestResolutionError(
                "Approved proposal amount does not match the explicit VND supplement."
            )
        if (
            evaluation_case_artifact.artifact_id not in proposal.source_artifact_ids
            or supplement_artifact.artifact_id not in proposal.source_artifact_ids
        ):
            raise BankingPrecheckRequestResolutionError(
                "Approved proposal is missing exact case or amount artifact lineage."
            )
        if (
            proposal.precheck_executed
            or proposal.submission_executed
            or not proposal.candidates
        ):
            raise BankingPrecheckRequestResolutionError(
                "Only a non-executed protected precheck proposal can be resolved."
            )

    @staticmethod
    def _profile_index(
        records: tuple[DatasetRecord, ...],
    ) -> dict[str, DatasetRecord]:
        if not records:
            raise BankingPrecheckRequestResolutionError(
                "The explicit 02_OPC_PROFILE source is unavailable."
            )
        indexed: dict[str, DatasetRecord] = {}
        for record in records:
            if (
                record.sheet != SheetRegistry.OPC_PROFILE.sheet_name
                or record.record_id in indexed
                or record.values.get("field") != record.record_id
                or "value" not in record.values
            ):
                raise BankingPrecheckRequestResolutionError(
                    "02_OPC_PROFILE must contain unique field/value records keyed by field."
                )
            indexed[record.record_id] = record
        return indexed

    @staticmethod
    def _approved_evidence_index(
        *,
        proposal_artifact: ArtifactEnvelope,
        proposal: BankingPrecheckSubmissionProposal,
    ) -> dict[str, EvidenceRef]:
        evidence_by_id: dict[str, EvidenceRef] = {}
        for evidence in proposal_artifact.evidence_refs:
            if evidence.evidence_id in evidence_by_id:
                raise BankingPrecheckRequestResolutionError(
                    "Approved proposal lineage contains duplicate evidence IDs."
                )
            evidence_by_id[evidence.evidence_id] = evidence
        if set(evidence_by_id) != set(proposal.evidence_ids):
            raise BankingPrecheckRequestResolutionError(
                "Approved proposal evidence index does not exactly match its immutable "
                "lineage."
            )
        return evidence_by_id

    def _request(
        self,
        *,
        candidate: BankingPrecheckSubmissionCandidate,
        proposal_artifact: ArtifactEnvelope,
        evaluation_case_artifact: ArtifactEnvelope,
        supplement_artifact: ArtifactEnvelope,
        proposal: BankingPrecheckSubmissionProposal,
        evaluation_case: EvaluationCase,
        supplement: BankingInputSupplement,
        profile_by_id: dict[str, DatasetRecord],
        approved_evidence_by_id: dict[str, EvidenceRef],
        authorization: AuthorizedActionPermit,
    ) -> BankingPrecheckRequest:
        bindings = tuple(candidate.field_bindings)
        if tuple(item.required_field for item in bindings) != _EXPECTED_FIELDS:
            raise BankingPrecheckRequestResolutionError(
                f"Candidate {candidate.option_id} does not expose the supported exact "
                "contract_id/amount/company_profile binding set."
            )
        contract_binding, amount_binding, profile_binding = bindings
        self._validate_artifact_binding(
            contract_binding,
            field="contract_id",
            source=BankingPrecheckFieldSource.EVALUATION_CASE,
            source_reference="EvaluationCase.contract_id",
            artifact_id=evaluation_case_artifact.artifact_id,
            record_ids=(evaluation_case.contract_id,),
        )
        self._validate_artifact_binding(
            amount_binding,
            field="amount",
            source=BankingPrecheckFieldSource.BANKING_INPUT_SUPPLEMENT,
            source_reference="BankingInputSupplement.requested_amount",
            artifact_id=supplement_artifact.artifact_id,
            record_ids=(supplement.supplement_id,),
        )
        if (
            profile_binding.required_field != "company_profile"
            or profile_binding.source is not BankingPrecheckFieldSource.OPC_PROFILE
            or profile_binding.source_reference != "02_OPC_PROFILE[field,value]"
            or profile_binding.source_artifact_id is not None
            or not profile_binding.source_record_ids
            or len(set(profile_binding.source_record_ids))
            != len(profile_binding.source_record_ids)
        ):
            raise BankingPrecheckRequestResolutionError(
                f"Candidate {candidate.option_id} has an invalid explicit OPC profile binding."
            )
        missing_profile_ids = tuple(
            record_id
            for record_id in profile_binding.source_record_ids
            if record_id not in profile_by_id
        )
        if missing_profile_ids:
            raise BankingPrecheckRequestResolutionError(
                "Approved company_profile references unavailable 02_OPC_PROFILE records: "
                + ", ".join(missing_profile_ids)
            )
        company_profile = self._approved_company_profile(
            candidate=candidate,
            proposal=proposal,
            binding=profile_binding,
            profile_by_id=profile_by_id,
            approved_evidence_by_id=approved_evidence_by_id,
        )
        request_hash = banking_precheck_request_hash(
            dataset_id=proposal.dataset_id,
            evaluation_case_id=proposal.evaluation_case_id,
            contract_id=proposal.contract_id,
            proposal_artifact_id=proposal_artifact.artifact_id,
            proposal_id=proposal.proposal_id,
            proposal_item_id=candidate.proposal_item_id,
            option_id=candidate.option_id,
            bank_product_id=candidate.bank_product_id,
            api_id=candidate.api_id,
            api_provider=candidate.api_provider,
            api_method=candidate.api_method,
            api_endpoint=candidate.api_endpoint,
            requested_amount=supplement.requested_amount,
            requested_amount_currency=supplement.requested_amount_currency,
            company_profile=company_profile,
        )
        return BankingPrecheckRequest(
            request_id=deterministic_id(
                "BPRQ",
                proposal_artifact.artifact_id,
                candidate.proposal_item_id,
                request_hash,
            ),
            dataset_id=proposal.dataset_id,
            evaluation_case_id=proposal.evaluation_case_id,
            contract_id=proposal.contract_id,
            proposal_artifact_id=proposal_artifact.artifact_id,
            proposal_id=proposal.proposal_id,
            proposal_item_id=candidate.proposal_item_id,
            option_id=candidate.option_id,
            bank_product_id=candidate.bank_product_id,
            api_id=candidate.api_id,
            api_provider=candidate.api_provider,
            api_method=candidate.api_method,
            api_endpoint=candidate.api_endpoint,
            requested_amount=supplement.requested_amount,
            requested_amount_currency=supplement.requested_amount_currency,
            company_profile=company_profile,
            request_hash=request_hash,
            idempotency_key=banking_precheck_idempotency_key(
                permit_id=authorization.permit_id,
                proposal_artifact_id=proposal_artifact.artifact_id,
                proposal_item_id=candidate.proposal_item_id,
                request_hash=request_hash,
            ),
        )

    @classmethod
    def _approved_company_profile(
        cls,
        *,
        candidate: BankingPrecheckSubmissionCandidate,
        proposal: BankingPrecheckSubmissionProposal,
        binding: BankingPrecheckFieldBindingReference,
        profile_by_id: dict[str, DatasetRecord],
        approved_evidence_by_id: dict[str, EvidenceRef],
    ) -> tuple[BankingCompanyProfileField, ...]:
        if len(binding.evidence_ids) != 1:
            raise BankingPrecheckRequestResolutionError(
                f"Candidate {candidate.option_id} has ambiguous approved company_profile "
                "binding evidence."
            )
        resolution = approved_evidence_by_id.get(binding.evidence_ids[0])
        expected_display = {
            "status": "RESOLVED",
            "source": BankingPrecheckFieldSource.OPC_PROFILE.value,
            "source_reference": "02_OPC_PROFILE[field,value]",
        }
        if (
            resolution is None
            or resolution.source_type is not SourceType.DERIVED
            or resolution.sheet != "BANKING_PRECHECK_READINESS"
            or resolution.record_id != proposal.matrix_id
            or resolution.field != "company_profile"
            or resolution.display_value != expected_display
        ):
            raise BankingPrecheckRequestResolutionError(
                f"Candidate {candidate.option_id} lacks one exact approved "
                "company_profile readiness lineage item."
            )
        if len(set(resolution.source_evidence_ids)) != len(
            resolution.source_evidence_ids
        ):
            raise BankingPrecheckRequestResolutionError(
                f"Candidate {candidate.option_id} has duplicate company_profile source "
                "evidence references."
            )
        missing_source_ids = tuple(
            evidence_id
            for evidence_id in resolution.source_evidence_ids
            if evidence_id not in approved_evidence_by_id
        )
        if missing_source_ids:
            raise BankingPrecheckRequestResolutionError(
                f"Candidate {candidate.option_id} company_profile lineage references "
                "unavailable approved evidence."
            )

        expected_keys = {
            (record_id, field)
            for record_id in binding.source_record_ids
            for field in ("field", "value")
        }
        linked_profile_evidence = tuple(
            approved_evidence_by_id[evidence_id]
            for evidence_id in resolution.source_evidence_ids
            if approved_evidence_by_id[evidence_id].source_type is SourceType.TEAM_PACK
            and approved_evidence_by_id[evidence_id].sheet
            == SheetRegistry.OPC_PROFILE.sheet_name
        )
        linked_keys = {
            (evidence.record_id, evidence.field)
            for evidence in linked_profile_evidence
        }
        if linked_keys != expected_keys or len(linked_profile_evidence) != len(
            expected_keys
        ):
            raise BankingPrecheckRequestResolutionError(
                f"Candidate {candidate.option_id} company_profile binding does not cover "
                "its exact approved 02_OPC_PROFILE field/value lineage."
            )

        profile_fields: list[BankingCompanyProfileField] = []
        for record_id in binding.source_record_ids:
            record = profile_by_id[record_id]
            for field in ("field", "value"):
                matches = tuple(
                    evidence
                    for evidence in approved_evidence_by_id.values()
                    if evidence.source_type is SourceType.TEAM_PACK
                    and evidence.sheet == SheetRegistry.OPC_PROFILE.sheet_name
                    and evidence.record_id == record_id
                    and evidence.field == field
                )
                if len(matches) != 1:
                    raise BankingPrecheckRequestResolutionError(
                        "Approved proposal lineage must contain exactly one "
                        f"02_OPC_PROFILE {record_id}.{field} evidence item."
                    )
                evidence = matches[0]
                if evidence.evidence_id not in resolution.source_evidence_ids:
                    raise BankingPrecheckRequestResolutionError(
                        f"Approved company_profile binding does not reference exact "
                        f"02_OPC_PROFILE {record_id}.{field} evidence."
                    )
                if (
                    field not in record.values
                    or field not in record.display_values
                    or evidence.row_number != record.row_number
                    or not cls._same_json_scalar(
                        evidence.display_value, record.values[field]
                    )
                    or not cls._same_json_scalar(
                        evidence.display_value, record.display_values[field]
                    )
                ):
                    raise BankingPrecheckRequestResolutionError(
                        f"Current 02_OPC_PROFILE {record_id}.{field} does not match the "
                        "approved proposal evidence."
                    )
            profile_fields.append(
                BankingCompanyProfileField(
                    field=record_id,
                    value=record.values["value"],
                )
            )
        return tuple(profile_fields)

    @staticmethod
    def _same_json_scalar(actual: object, expected: object) -> bool:
        scalar_types = (bool, int, float, str)
        if actual is None or expected is None:
            return actual is None and expected is None
        return (
            isinstance(actual, scalar_types)
            and isinstance(expected, scalar_types)
            and type(actual) is type(expected)
            and actual == expected
        )

    @staticmethod
    def _validate_artifact_binding(
        binding: BankingPrecheckFieldBindingReference,
        *,
        field: str,
        source: BankingPrecheckFieldSource,
        source_reference: str,
        artifact_id: str,
        record_ids: tuple[str, ...],
    ) -> None:
        if (
            binding.required_field != field
            or binding.source is not source
            or binding.source_reference != source_reference
            or binding.source_artifact_id != artifact_id
            or binding.source_record_ids != record_ids
        ):
            raise BankingPrecheckRequestResolutionError(
                f"Approved {field} binding does not match its exact persisted source."
            )
