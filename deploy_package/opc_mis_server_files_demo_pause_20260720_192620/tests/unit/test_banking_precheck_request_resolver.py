"""Exact request/evidence binding tests for Banking precheck execution."""

from datetime import UTC, datetime

import pytest

from opc_mis.business.skills.banking.precheck_request_resolver import (
    BankingPrecheckRequestResolutionError,
    BankingPrecheckRequestResolver,
)
from opc_mis.domain.banking_precheck_execution_models import AuthorizedActionPermit
from opc_mis.domain.banking_precheck_submission_models import (
    BankingPrecheckCatalogTerms,
    BankingPrecheckFieldBindingReference,
    BankingPrecheckGovernanceSourceFacts,
    BankingPrecheckSubmissionCandidate,
    BankingPrecheckSubmissionProposal,
)
from opc_mis.domain.enums import (
    ArtifactType,
    BankingNeedType,
    BankingPrecheckFieldSource,
    CurrencyCode,
    ProtectedAction,
    SourceType,
)
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.team_pack import SheetRegistry
from tests.unit.test_banking_discovery import (
    AMOUNT_EVIDENCE,
    BASE_EVIDENCE,
    CASE_ID,
    CONTRACT_ID,
    _case,
    _envelope,
    _record,
    _request,
)

MATRIX_ID = "MATRIX-REQUEST-AMOUNT"
PROPOSAL_ID = "PROPOSAL-REQUEST-AMOUNT"
OPTION_ID = "OPTION-PERFORMANCE-BOND"
PROPOSAL_ITEM_ID = "PROPOSAL-ITEM-PERFORMANCE-BOND"


def _derived(
    *,
    evidence_id: str,
    field: str,
    display_value: object,
    sources: tuple[str, ...],
) -> EvidenceRef:
    return EvidenceRef(
        evidence_id=evidence_id,
        source_type=SourceType.DERIVED,
        sheet="BANKING_PRECHECK_READINESS",
        row_number=0,
        record_id=MATRIX_ID,
        field=field,
        display_value=display_value,
        source_evidence_ids=sources,
    )


def _fixture() -> dict[str, object]:
    evaluation_case = _case(related_credit_case_ids=("CREDIT-UNRELATED",))
    discovery_request = _request()
    case_artifact = _envelope(
        artifact_id="ARTIFACT-EVALUATION-CASE",
        artifact_type=ArtifactType.EVALUATION_CASE,
        payload=evaluation_case.model_dump(mode="json"),
        evidence_refs=evaluation_case.evidence_refs,
    )
    request_artifact = _envelope(
        artifact_id="ARTIFACT-BANKING-REQUEST",
        artifact_type=ArtifactType.BANKING_DISCOVERY_REQUEST,
        payload=discovery_request.model_dump(mode="json"),
        evidence_refs=(BASE_EVIDENCE, AMOUNT_EVIDENCE),
    )
    profile_record = _record(
        SheetRegistry.OPC_PROFILE.sheet_name,
        2,
        "company_id",
        {"field": "company_id", "value": "OPC-001"},
    )
    profile_field = EvidenceRef(
        evidence_id="EVD-PROFILE-FIELD",
        source_type=SourceType.TEAM_PACK,
        sheet=SheetRegistry.OPC_PROFILE.sheet_name,
        row_number=2,
        record_id="company_id",
        field="field",
        display_value="company_id",
    )
    profile_value = EvidenceRef(
        evidence_id="EVD-PROFILE-VALUE",
        source_type=SourceType.TEAM_PACK,
        sheet=SheetRegistry.OPC_PROFILE.sheet_name,
        row_number=2,
        record_id="company_id",
        field="value",
        display_value="OPC-001",
    )
    contract_resolution = _derived(
        evidence_id="EVD-RESOLVED-CONTRACT",
        field="contract_id",
        display_value={
            "status": "RESOLVED",
            "source": BankingPrecheckFieldSource.EVALUATION_CASE.value,
            "source_reference": "EvaluationCase.contract_id",
        },
        sources=(BASE_EVIDENCE.evidence_id,),
    )
    amount_resolution = _derived(
        evidence_id="EVD-RESOLVED-AMOUNT",
        field="amount",
        display_value={
            "status": "RESOLVED",
            "source": BankingPrecheckFieldSource.BANKING_DISCOVERY_REQUEST.value,
            "source_reference": "BankingDiscoveryRequest.requested_amount",
        },
        sources=(AMOUNT_EVIDENCE.evidence_id,),
    )
    profile_resolution = _derived(
        evidence_id="EVD-RESOLVED-PROFILE",
        field="company_profile",
        display_value={
            "status": "RESOLVED",
            "source": BankingPrecheckFieldSource.OPC_PROFILE.value,
            "source_reference": "02_OPC_PROFILE[field,value]",
        },
        sources=(profile_field.evidence_id, profile_value.evidence_id),
    )
    proposal_evidence = (
        BASE_EVIDENCE,
        AMOUNT_EVIDENCE,
        profile_field,
        profile_value,
        contract_resolution,
        amount_resolution,
        profile_resolution,
    )
    field_bindings = (
        BankingPrecheckFieldBindingReference(
            required_field="contract_id",
            source=BankingPrecheckFieldSource.EVALUATION_CASE,
            source_reference="EvaluationCase.contract_id",
            source_artifact_id=case_artifact.artifact_id,
            source_record_ids=(CONTRACT_ID,),
            evidence_ids=(contract_resolution.evidence_id,),
        ),
        BankingPrecheckFieldBindingReference(
            required_field="amount",
            source=BankingPrecheckFieldSource.BANKING_DISCOVERY_REQUEST,
            source_reference="BankingDiscoveryRequest.requested_amount",
            source_artifact_id=request_artifact.artifact_id,
            source_record_ids=("REQ-PERFORMANCE-BOND", "CREDIT-UNRELATED"),
            evidence_ids=(amount_resolution.evidence_id,),
        ),
        BankingPrecheckFieldBindingReference(
            required_field="company_profile",
            source=BankingPrecheckFieldSource.OPC_PROFILE,
            source_reference="02_OPC_PROFILE[field,value]",
            source_artifact_id=None,
            source_record_ids=("company_id",),
            evidence_ids=(profile_resolution.evidence_id,),
        ),
    )
    candidate = BankingPrecheckSubmissionCandidate(
        proposal_item_id=PROPOSAL_ITEM_ID,
        option_id=OPTION_ID,
        bank_product_id="BANKPROD-002",
        need_type=BankingNeedType.PERFORMANCE_BOND,
        provider="VietinBank",
        product_name="Performance bond",
        api_id="API-002",
        api_provider="VietinBank",
        api_method="POST",
        api_endpoint="/openapi/v1/guarantee/precheck",
        governance_source_facts=BankingPrecheckGovernanceSourceFacts(
            api_extension_rule="Human approval before submission",
            api_extension_rule_evidence_id=BASE_EVIDENCE.evidence_id,
        ),
        catalog_terms=BankingPrecheckCatalogTerms(
            annual_rate_or_fee=0.012,
            processing_fee_rate=0,
            collateral_ratio=0.2,
            minimum_amount=300_000_000,
            minimum_amount_currency=CurrencyCode.VND,
            evidence_ids=(BASE_EVIDENCE.evidence_id,),
        ),
        field_bindings=field_bindings,
        evidence_ids=tuple(item.evidence_id for item in proposal_evidence),
    )
    proposal = BankingPrecheckSubmissionProposal(
        proposal_id=PROPOSAL_ID,
        evaluation_case_id=CASE_ID,
        dataset_id=evaluation_case.dataset_id,
        contract_id=CONTRACT_ID,
        banking_request_id=discovery_request.request_id,
        matrix_id=MATRIX_ID,
        readiness_id="READINESS-REQUEST-AMOUNT",
        review_id="REVIEW-REQUEST-AMOUNT",
        mapping_policy_id="POLICY-TEST",
        mapping_version="banking-catalog-v2",
        mapping_hash="POLICY-HASH",
        requested_amount=discovery_request.requested_amount,
        requested_amount_currency=CurrencyCode.VND,
        candidate_option_ids=(OPTION_ID,),
        candidates=(candidate,),
        source_artifact_ids=(
            case_artifact.artifact_id,
            request_artifact.artifact_id,
            "ARTIFACT-MATRIX",
            "ARTIFACT-READINESS",
            "ARTIFACT-REVIEW",
        ),
        evidence_ids=tuple(item.evidence_id for item in proposal_evidence),
    )
    proposal_artifact = _envelope(
        artifact_id="ARTIFACT-PROPOSAL",
        artifact_type=ArtifactType.BANKING_PRECHECK_SUBMISSION_PROPOSAL,
        payload=proposal.model_dump(mode="json"),
        evidence_refs=proposal_evidence,
    )
    permit = AuthorizedActionPermit(
        permit_id="PERMIT-PRECHECK",
        workflow_run_id="RUN-PRECHECK",
        evaluation_case_id=CASE_ID,
        approval_request_id="APPROVAL-PRECHECK",
        protected_action=ProtectedAction.SUBMIT_BANKING_PRECHECK,
        subject_artifact_id=proposal_artifact.artifact_id,
        subject_artifact_version=proposal_artifact.version,
        subject_input_hash=proposal_artifact.input_hash,
        authorized_by="FOUNDER",
        authorized_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    return {
        "evaluation_case": evaluation_case,
        "discovery_request": discovery_request,
        "case_artifact": case_artifact,
        "request_artifact": request_artifact,
        "proposal": proposal,
        "proposal_artifact": proposal_artifact,
        "profile_record": profile_record,
        "permit": permit,
    }


def _resolve(fixture: dict[str, object]):
    return BankingPrecheckRequestResolver().resolve(
        proposal_artifact=fixture["proposal_artifact"],
        evaluation_case_artifact=fixture["case_artifact"],
        discovery_request_artifact=fixture["request_artifact"],
        proposal=fixture["proposal"],
        evaluation_case=fixture["evaluation_case"],
        discovery_request=fixture["discovery_request"],
        opc_profile_records=(fixture["profile_record"],),
        authorization=fixture["permit"],
    )


def test_resolver_uses_discovery_request_amount_without_supplement() -> None:
    requests = _resolve(_fixture())

    assert len(requests) == 1
    assert requests[0].requested_amount == 420_000_000
    assert requests[0].requested_amount_currency is CurrencyCode.VND
    assert requests[0].contract_id == CONTRACT_ID
    assert requests[0].company_profile[0].field == "company_id"


def test_resolver_rejects_substituted_approved_amount_evidence() -> None:
    fixture = _fixture()
    proposal_artifact = fixture["proposal_artifact"]
    changed = tuple(
        item.model_copy(update={"display_value": 419_000_000})
        if item.evidence_id == AMOUNT_EVIDENCE.evidence_id
        else item
        for item in proposal_artifact.evidence_refs
    )
    fixture["proposal_artifact"] = proposal_artifact.model_copy(
        update={"evidence_refs": changed}
    )

    with pytest.raises(
        BankingPrecheckRequestResolutionError,
        match="does not match the persisted Banking discovery request evidence",
    ):
        _resolve(fixture)
