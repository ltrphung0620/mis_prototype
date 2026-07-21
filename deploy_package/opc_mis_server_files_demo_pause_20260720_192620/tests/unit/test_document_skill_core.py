"""Focused tests for Document checklist, masking, and reference-only intake."""

import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256

import pytest
from pydantic import ValidationError

from opc_mis.business.skills.document.checklist_builder import DocumentChecklistBuilder
from opc_mis.business.skills.document.component import DocumentSkill
from opc_mis.business.skills.document.context_loader import DocumentContext
from opc_mis.business.skills.document.evidence_intake import DocumentEvidenceIntake
from opc_mis.business.skills.document.package_builder import DocumentPackageBuilder
from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.dataset import DatasetRecord, DatasetSnapshot
from opc_mis.domain.document_models import (
    DocumentEvidenceReasonCode,
    DocumentEvidenceSubmission,
    DocumentEvidenceSupplement,
    DocumentPackageReadiness,
    DocumentPreparationRequest,
    DocumentRequirementCode,
    DocumentRequirementStatus,
    document_package_draft_id,
    document_preparation_request_id,
    document_release_action_payload,
)
from opc_mis.domain.enums import (
    ArtifactStatus,
    ArtifactType,
    BankingPrecheckResultAuthority,
    CashflowScope,
    ComponentStatus,
    CurrencyCode,
    EvaluationScope,
    SourceType,
    ValidationStatus,
)
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.lineage import deterministic_id
from opc_mis.domain.planner_models import EvaluationCase
from opc_mis.governance.evidence_validator import EvidenceValidator
from opc_mis.infrastructure.persistence.memory_artifact_repository import (
    InMemoryArtifactRepository,
)
from opc_mis.infrastructure.security.free_text_redactor import (
    DeterministicFreeTextRedactor,
)
from tests.unit.test_data_masking_foundation import _document, _policy

CASE_ID = "CASE-DOCUMENT-TEST"
DATASET_ID = "DATASET-DOCUMENT-TEST"
CONTRACT_ID = "CON-DOCUMENT-TEST"
REQUIRED_PROFILE_FIELDS = ("company_id", "company_name")


def _envelope(
    *,
    artifact_id: str,
    artifact_type: ArtifactType,
    payload: dict[str, object],
    evidence_refs: tuple[EvidenceRef, ...] = (),
) -> ArtifactEnvelope:
    return ArtifactEnvelope(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        evaluation_case_id=CASE_ID,
        producer="TEST",
        version=1,
        status=ArtifactStatus.CREATED,
        payload=payload,
        evidence_refs=evidence_refs,
        input_artifact_ids=(),
        input_hash="TEST-HASH",
        validation_status=ValidationStatus.VALID,
        validation_notes=(),
        created_at=datetime.now(UTC),
    )


def _record(
    sheet: str, row: int, record_id: str, values: dict[str, object]
) -> DatasetRecord:
    return DatasetRecord(
        sheet=sheet,
        row_number=row,
        record_id=record_id,
        values=values,
        display_values=dict(values),
    )


def _context() -> DocumentContext:
    evaluation_case = EvaluationCase(
        evaluation_case_id=CASE_ID,
        dataset_id=DATASET_ID,
        contract_id=CONTRACT_ID,
        customer_id="CUS-TEST",
        related_order_ids=(),
        related_invoice_ids=(),
        related_service_ids=(),
        related_credit_case_ids=(),
        evaluation_scope=(
            EvaluationScope.FINANCE,
            EvaluationScope.OPERATIONS,
            EvaluationScope.RISK,
        ),
        cashflow_scope=CashflowScope.OPC_GLOBAL,
        warnings=(),
        evidence_refs=(),
    )
    document_codes = tuple(DocumentRequirementCode)
    approval_conditions = (
        "CONTRACT_SIGNED",
        "CASHFLOW_BUFFER_CONFIRMED",
    )
    request_id = document_preparation_request_id(
        result_set_artifact_id="ART-RESULT",
        review_artifact_id="ART-REVIEW",
        normalized_result_id="BPNR-TEST",
        review_item_id="DPPRI-TEST",
        option_id="OPTION-TEST",
        required_document_codes=document_codes,
        approval_condition_codes=approval_conditions,
    )
    request_display = {
        "request_id": request_id,
        "contract_id": CONTRACT_ID,
        "bank_product_id": "BANKPROD-002",
        "requested_amount": 420_000_000,
        "currency": "VND",
        "request_type": "PERFORMANCE_BOND",
        "non_binding": True,
    }
    request_source = EvidenceRef(
        evidence_id=deterministic_id(
            "EVD",
            DATASET_ID,
            SourceType.USER_INPUT,
            "PROVIDER-RESULT-TEST",
            "normalized_result",
            request_display,
        ),
        source_type=SourceType.USER_INPUT,
        sheet="BANKING_PROVIDER_RESULT",
        row_number=0,
        record_id="PROVIDER-RESULT-TEST",
        field="normalized_result",
        display_value=request_display,
    )
    request_evidence = EvidenceRef(
        evidence_id=deterministic_id(
            "EVD",
            DATASET_ID,
            SourceType.DERIVED,
            "DOCUMENT_PREPARATION_REQUEST",
            request_id,
            request_display,
            (request_source.evidence_id,),
        ),
        source_type=SourceType.DERIVED,
        sheet="DOCUMENT_PREPARATION_REQUEST",
        row_number=0,
        record_id=request_id,
        field="provider_document_handoff",
        display_value=request_display,
        source_evidence_ids=(request_source.evidence_id,),
    )
    request = DocumentPreparationRequest(
        request_id=request_id,
        evaluation_case_id=CASE_ID,
        dataset_id=DATASET_ID,
        contract_id=CONTRACT_ID,
        normalized_result_id="BPNR-TEST",
        review_item_id="DPPRI-TEST",
        option_id="OPTION-TEST",
        bank_product_id="BANKPROD-002",
        api_id="API-002",
        provider="VietinBank",
        provider_reference="SIMULATED-REFERENCE",
        requested_amount=420_000_000,
        supported_amount=420_000_000,
        currency=CurrencyCode.VND,
        required_document_codes=document_codes,
        approval_condition_codes=approval_conditions,
        provider_result_authority=(
            BankingPrecheckResultAuthority.SIMULATED_NON_BINDING
        ),
        source_artifact_ids=("ART-REVIEW", "ART-RESULT"),
        evidence_ids=(request_evidence.evidence_id,),
    )
    contract = _record(
        "04_CONTRACTS",
        2,
        CONTRACT_ID,
        {
            "contract_id": CONTRACT_ID,
            "customer_id": "CUS-TEST",
            "contract_value": 4_200_000_000,
            "payment_terms": "Performance bond required before mobilization.",
        },
    )
    profile = (
        _record(
            "02_OPC_PROFILE",
            2,
            "company_id",
            {"field": "company_id", "value": "OPC-RAW-ID"},
        ),
        _record(
            "02_OPC_PROFILE",
            3,
            "company_name",
            {"field": "company_name", "value": "OPC Raw Company Name"},
        ),
    )
    cashflow = (
        _record(
            "09_CASHFLOW",
            2,
            "2026-06",
            {
                "month": "2026-06",
                "cash_reserve_minimum": 1_000_000_000,
                "projected_closing_cash": 290_000_000,
            },
        ),
    )
    snapshot = DatasetSnapshot(
        dataset_id=DATASET_ID,
        source_locator="SERVER-CONFIGURED",
        source_hash="SOURCE-HASH",
        snapshot_hash="SNAPSHOT-HASH",
        sheets={
            "04_CONTRACTS": [contract],
            "02_OPC_PROFILE": list(profile),
            "09_CASHFLOW": list(cashflow),
        },
        headers={},
        indexes={"04_CONTRACTS": {CONTRACT_ID: [contract]}},
        duplicate_ids={},
        validation_issues=[],
        missing_sheets=(),
        missing_headers={},
    )
    return DocumentContext(
        dataset=snapshot,
        evaluation_case_artifact=_envelope(
            artifact_id="ART-CASE",
            artifact_type=ArtifactType.EVALUATION_CASE,
            payload=evaluation_case.model_dump(mode="json"),
        ),
        request_artifact=_envelope(
            artifact_id="ART-DOCUMENT-REQUEST",
            artifact_type=ArtifactType.DOCUMENT_PREPARATION_REQUEST,
            payload=request.model_dump(mode="json"),
            evidence_refs=(request_source, request_evidence),
        ),
        supplement_artifacts=(),
        evaluation_case=evaluation_case,
        request=request,
        supplements=(),
        contract=contract,
        opc_profile_records=profile,
        cashflow_records=cashflow,
    )


def _without_company_profile_requirement() -> DocumentContext:
    context = _context()
    codes = tuple(
        item
        for item in context.request.required_document_codes
        if item is not DocumentRequirementCode.COMPANY_PROFILE
    )
    request_id = document_preparation_request_id(
        result_set_artifact_id="ART-RESULT",
        review_artifact_id="ART-REVIEW",
        normalized_result_id=context.request.normalized_result_id,
        review_item_id=context.request.review_item_id,
        option_id=context.request.option_id,
        required_document_codes=codes,
        approval_condition_codes=context.request.approval_condition_codes,
    )
    display = {
        "request_id": request_id,
        "contract_id": CONTRACT_ID,
        "bank_product_id": context.request.bank_product_id,
        "requested_amount": context.request.requested_amount,
        "currency": context.request.currency.value,
        "request_type": "PERFORMANCE_BOND",
        "non_binding": True,
    }
    source = EvidenceRef(
        evidence_id=deterministic_id(
            "EVD",
            DATASET_ID,
            SourceType.USER_INPUT,
            "PROVIDER-RESULT-NO-PROFILE",
            "normalized_result",
            display,
        ),
        source_type=SourceType.USER_INPUT,
        sheet="BANKING_PROVIDER_RESULT",
        row_number=0,
        record_id="PROVIDER-RESULT-NO-PROFILE",
        field="normalized_result",
        display_value=display,
    )
    evidence = EvidenceRef(
        evidence_id=deterministic_id(
            "EVD",
            DATASET_ID,
            SourceType.DERIVED,
            "DOCUMENT_PREPARATION_REQUEST",
            request_id,
            display,
            (source.evidence_id,),
        ),
        source_type=SourceType.DERIVED,
        sheet="DOCUMENT_PREPARATION_REQUEST",
        row_number=0,
        record_id=request_id,
        field="provider_document_handoff",
        display_value=display,
        source_evidence_ids=(source.evidence_id,),
    )
    request = context.request.model_copy(
        update={
            "request_id": request_id,
            "required_document_codes": codes,
            "evidence_ids": (evidence.evidence_id,),
        }
    )
    artifact = _envelope(
        artifact_id="ART-DOCUMENT-REQUEST-NO-PROFILE",
        artifact_type=ArtifactType.DOCUMENT_PREPARATION_REQUEST,
        payload=request.model_dump(mode="json"),
        evidence_refs=(source, evidence),
    )
    return replace(
        context,
        request=request,
        request_artifact=artifact,
        opc_profile_records=(),
    )


def _company_profile_only_context() -> DocumentContext:
    context = _context()
    codes = (DocumentRequirementCode.COMPANY_PROFILE,)
    request_id = document_preparation_request_id(
        result_set_artifact_id="ART-RESULT",
        review_artifact_id="ART-REVIEW",
        normalized_result_id=context.request.normalized_result_id,
        review_item_id=context.request.review_item_id,
        option_id=context.request.option_id,
        required_document_codes=codes,
        approval_condition_codes=context.request.approval_condition_codes,
    )
    display = {"request_id": request_id, "non_binding": True}
    evidence = EvidenceRef(
        evidence_id=deterministic_id(
            "EVD",
            DATASET_ID,
            SourceType.DERIVED,
            "DOCUMENT_PREPARATION_REQUEST",
            request_id,
            display,
        ),
        source_type=SourceType.DERIVED,
        sheet="DOCUMENT_PREPARATION_REQUEST",
        row_number=0,
        record_id=request_id,
        field="provider_document_handoff",
        display_value=display,
    )
    request = context.request.model_copy(
        update={
            "request_id": request_id,
            "required_document_codes": codes,
            "evidence_ids": (evidence.evidence_id,),
        }
    )
    artifact = _envelope(
        artifact_id="ART-DOCUMENT-REQUEST-PROFILE-ONLY",
        artifact_type=ArtifactType.DOCUMENT_PREPARATION_REQUEST,
        payload=request.model_dump(mode="json"),
        evidence_refs=(evidence,),
    )
    return replace(
        context,
        request=request,
        request_artifact=artifact,
        opc_profile_records=(),
    )


def _with_company_profile_supplement(context: DocumentContext) -> DocumentContext:
    document_type = DocumentRequirementCode.COMPANY_PROFILE
    missing_request_id = deterministic_id(
        "MDR",
        CASE_ID,
        "DOCUMENT_SKILL",
        context.request.request_id,
        document_type,
    )
    document_reference_id = "DOCREF-00000000-0000-4000-8000-000000000101"
    content_sha256 = "d" * 64
    provided_by = "FOUNDER"
    evidence_note = (
        DocumentEvidenceReasonCode.REQUESTED_DOCUMENT_REFERENCE_SUPPLIED
    )
    source_package_artifact_id = "ART-PRIOR-PROFILE-PACKAGE"
    supplement_id = deterministic_id(
        "DES",
        CASE_ID,
        context.request.request_id,
        source_package_artifact_id,
        missing_request_id,
        document_reference_id,
        content_sha256,
        document_type,
        provided_by,
        evidence_note,
    )
    evidence = EvidenceRef(
        evidence_id=deterministic_id(
            "EVD",
            DATASET_ID,
            SourceType.USER_INPUT,
            supplement_id,
            "document_reference_id",
            document_reference_id,
        ),
        source_type=SourceType.USER_INPUT,
        sheet="DOCUMENT_EVIDENCE_SUPPLEMENT",
        row_number=0,
        record_id=supplement_id,
        field="document_reference_id",
        display_value=document_reference_id,
    )
    supplement = DocumentEvidenceSupplement(
        supplement_id=supplement_id,
        evaluation_case_id=CASE_ID,
        dataset_id=DATASET_ID,
        contract_id=CONTRACT_ID,
        preparation_request_id=context.request.request_id,
        missing_request_id=missing_request_id,
        document_reference_id=document_reference_id,
        content_sha256=content_sha256,
        document_type=document_type,
        provided_by=provided_by,
        evidence_note=evidence_note,
        source_package_artifact_id=source_package_artifact_id,
        source_artifact_ids=(source_package_artifact_id,),
        evidence_ids=(evidence.evidence_id,),
    )
    artifact = _envelope(
        artifact_id="ART-COMPANY-PROFILE-SUPPLEMENT",
        artifact_type=ArtifactType.DOCUMENT_EVIDENCE_SUPPLEMENT,
        payload=supplement.model_dump(mode="json"),
        evidence_refs=(evidence,),
    )
    return replace(
        context,
        supplement_artifacts=(artifact,),
        supplements=(supplement,),
    )


def _with_required_document_supplement(
    context: DocumentContext,
    document_type: DocumentRequirementCode,
    *,
    reference_suffix: str,
    hash_character: str,
) -> DocumentContext:
    missing_request_id = deterministic_id(
        "MDR",
        CASE_ID,
        "DOCUMENT_SKILL",
        context.request.request_id,
        document_type,
    )
    document_reference_id = f"DOCREF-00000000-0000-4000-8000-{reference_suffix}"
    content_sha256 = hash_character * 64
    provided_by = "FOUNDER"
    evidence_note = (
        DocumentEvidenceReasonCode.REQUESTED_DOCUMENT_REFERENCE_SUPPLIED
    )
    source_package_artifact_id = "ART-PRIOR-PACKAGE"
    supplement_id = deterministic_id(
        "DES",
        CASE_ID,
        context.request.request_id,
        source_package_artifact_id,
        missing_request_id,
        document_reference_id,
        content_sha256,
        document_type,
        provided_by,
        evidence_note,
    )
    evidence = EvidenceRef(
        evidence_id=deterministic_id(
            "EVD",
            DATASET_ID,
            SourceType.USER_INPUT,
            supplement_id,
            "document_reference_id",
            document_reference_id,
        ),
        source_type=SourceType.USER_INPUT,
        sheet="DOCUMENT_EVIDENCE_SUPPLEMENT",
        row_number=0,
        record_id=supplement_id,
        field="document_reference_id",
        display_value=document_reference_id,
    )
    supplement = DocumentEvidenceSupplement(
        supplement_id=supplement_id,
        evaluation_case_id=CASE_ID,
        dataset_id=DATASET_ID,
        contract_id=CONTRACT_ID,
        preparation_request_id=context.request.request_id,
        missing_request_id=missing_request_id,
        document_reference_id=document_reference_id,
        content_sha256=content_sha256,
        document_type=document_type,
        provided_by=provided_by,
        evidence_note=evidence_note,
        source_package_artifact_id=source_package_artifact_id,
        source_artifact_ids=(source_package_artifact_id,),
        evidence_ids=(evidence.evidence_id,),
    )
    artifact = _envelope(
        artifact_id=f"ART-{document_type.value}-SUPPLEMENT",
        artifact_type=ArtifactType.DOCUMENT_EVIDENCE_SUPPLEMENT,
        payload=supplement.model_dump(mode="json"),
        evidence_refs=(evidence,),
    )
    return replace(
        context,
        supplement_artifacts=(*context.supplement_artifacts, artifact),
        supplements=(*context.supplements, supplement),
    )


def _ready_context() -> DocumentContext:
    context = _with_required_document_supplement(
        _context(),
        DocumentRequirementCode.PERFORMANCE_BOND_REQUEST_FORM,
        reference_suffix="000000000102",
        hash_character="c",
    )
    return _with_required_document_supplement(
        context,
        DocumentRequirementCode.CASHFLOW_BUFFER_EVIDENCE,
        reference_suffix="000000000103",
        hash_character="d",
    )


def test_document_core_drafts_signed_contract_and_masks_contract_and_company() -> None:
    context = _context()
    checklist = DocumentChecklistBuilder(
        required_profile_fields=REQUIRED_PROFILE_FIELDS
    ).build(context)

    signed = next(
        item
        for item in checklist.checklist.items
        if item.document_code is DocumentRequirementCode.SIGNED_CONTRACT
    )
    cashflow = next(
        item
        for item in checklist.checklist.items
        if item.document_code is DocumentRequirementCode.CASHFLOW_BUFFER_EVIDENCE
    )
    assert signed.status is DocumentRequirementStatus.DRAFTED
    assert signed.missing_request_id is None
    assert signed.limitation_codes == (
        "SIGNED_CONTRACT_PENDING_FOUNDER_ACCEPTANCE",
    )
    assert tuple(item.field for item in checklist.missing_data_requests) == (
        DocumentRequirementCode.PERFORMANCE_BOND_REQUEST_FORM.value,
        DocumentRequirementCode.CASHFLOW_BUFFER_EVIDENCE.value,
    )
    assert cashflow.status is DocumentRequirementStatus.MISSING

    package = DocumentPackageBuilder(
        masking_service=_policy(),
        required_profile_fields=REQUIRED_PROFILE_FIELDS,
    ).build(context, checklist)

    assert package.package_draft.readiness is DocumentPackageReadiness.WAITING_FOR_INPUT
    assert package.release_package is None
    serialized = json.dumps(package.package_draft.sanitized_payload, sort_keys=True)
    assert "OPC-RAW-ID" not in serialized
    assert "OPC Raw Company Name" not in serialized
    assert "CUS-TEST" not in serialized
    assert package.package_draft.sanitized_payload["contract_value"] != 4_200_000_000
    assert package.package_draft.masking_manifest.fail_closed is True
    assert package.package_draft.approval_condition_codes == (
        "CONTRACT_SIGNED",
        "CASHFLOW_BUFFER_CONFIRMED",
    )
    assert package.package_draft.limitation_codes == (
        "SIGNED_CONTRACT_PENDING_FOUNDER_ACCEPTANCE",
    )


def test_null_cashflow_fields_are_a_blocking_document_gap() -> None:
    context = _context()
    null_cashflow = _record(
        "09_CASHFLOW",
        2,
        "2026-06",
        {
            "month": "2026-06",
            "cash_reserve_minimum": None,
            "projected_closing_cash": None,
        },
    )
    context = replace(context, cashflow_records=(null_cashflow,))

    checklist = DocumentChecklistBuilder(
        required_profile_fields=REQUIRED_PROFILE_FIELDS
    ).build(context)
    cashflow = next(
        item
        for item in checklist.checklist.items
        if item.document_code is DocumentRequirementCode.CASHFLOW_BUFFER_EVIDENCE
    )

    assert cashflow.status is DocumentRequirementStatus.MISSING
    assert cashflow.limitation_codes == ()
    assert cashflow.missing_request_id is not None
    assert any(
        item.request_id == cashflow.missing_request_id
        and item.field == DocumentRequirementCode.CASHFLOW_BUFFER_EVIDENCE.value
        for item in checklist.missing_data_requests
    )


def test_company_profile_is_minimized_when_provider_does_not_require_it() -> None:
    context = _without_company_profile_requirement()
    checklist = DocumentChecklistBuilder(
        required_profile_fields=REQUIRED_PROFILE_FIELDS
    ).build(context)
    assert DocumentRequirementCode.COMPANY_PROFILE not in tuple(
        item.document_code for item in checklist.checklist.items
    )
    assert all(
        item.field != DocumentRequirementCode.COMPANY_PROFILE.value
        for item in checklist.missing_data_requests
    )

    package = DocumentPackageBuilder(
        masking_service=_policy(),
        required_profile_fields=REQUIRED_PROFILE_FIELDS,
    ).build(context, checklist)
    assert "company_id" not in package.package_draft.sanitized_payload
    assert "company_name" not in package.package_draft.sanitized_payload
    assert "company_id" not in tuple(
        item.field_name for item in package.package_draft.masking_manifest.items
    )


def test_ready_release_preserves_conditions_limitations_and_document_manifest() -> None:
    context = _ready_context()
    checklist = DocumentChecklistBuilder(
        required_profile_fields=REQUIRED_PROFILE_FIELDS
    ).build(context)
    package = DocumentPackageBuilder(
        masking_service=_policy(),
        required_profile_fields=REQUIRED_PROFILE_FIELDS,
    ).build(context, checklist)

    assert package.release_package is not None
    release = package.release_package
    assert release.approval_condition_codes == context.request.approval_condition_codes
    assert release.limitation_codes == (
        "SIGNED_CONTRACT_PENDING_FOUNDER_ACCEPTANCE",
        "DOCUMENT_REFERENCE_NOT_REPOSITORY_VERIFIED",
    )
    assert tuple(item.document_code for item in release.document_manifest) == (
        release.document_codes
    )
    cashflow = next(
        item
        for item in release.document_manifest
        if item.document_code is DocumentRequirementCode.CASHFLOW_BUFFER_EVIDENCE
    )
    signed = next(
        item
        for item in release.document_manifest
        if item.document_code is DocumentRequirementCode.SIGNED_CONTRACT
    )
    assert cashflow.status is DocumentRequirementStatus.AVAILABLE_WITH_LIMITATIONS
    assert cashflow.limitation_codes == (
        "DOCUMENT_REFERENCE_NOT_REPOSITORY_VERIFIED",
    )
    assert signed.status is DocumentRequirementStatus.DRAFTED
    assert signed.limitation_codes == (
        "SIGNED_CONTRACT_PENDING_FOUNDER_ACCEPTANCE",
    )
    assert signed.source_reference_ids == (CONTRACT_ID,)
    action = document_release_action_payload(release)
    assert action["approval_condition_codes"] == release.approval_condition_codes
    assert action["limitation_codes"] == release.limitation_codes
    assert action["document_manifest"]
    serialized = json.dumps(action, sort_keys=True)
    assert "filesystem_path" not in serialized
    assert "document_bytes" not in serialized


def test_document_component_does_not_wait_for_signed_contract_before_decision() -> None:
    class StaticContextLoader:
        async def load(self, _execution: ExecutionContext) -> DocumentContext:
            return _context()

    skill = DocumentSkill(
        context_loader=StaticContextLoader(),  # type: ignore[arg-type]
        package_builder=DocumentPackageBuilder(
            masking_service=_policy(),
            required_profile_fields=REQUIRED_PROFILE_FIELDS,
        ),
    )
    result = asyncio.run(
        skill.execute(
            ExecutionContext(
                evaluation_case_id=CASE_ID,
                dataset_id=DATASET_ID,
                workflow_run_id="RUN-DOCUMENT",
                requested_scope=(EvaluationScope.FINANCE,),
                component_input={},
                current_node="DOCUMENT_PREPARATION",
            )
        )
    )

    assert result.status is ComponentStatus.WAITING_FOR_INPUT
    assert result.checklist is not None
    assert result.package_draft is not None
    assert result.release_package is None
    assert tuple(item.artifact_type for item in result.artifacts) == (
        ArtifactType.DOCUMENT_CHECKLIST,
        ArtifactType.DOCUMENT_PACKAGE_DRAFT,
    )
    assert result.approval_signals == ()
    assert result.action_commands == ()
    reports = tuple(
        asyncio.run(
            EvidenceValidator(
                masking_policy=_document(),
                masking_service=_policy(),
            ).validate(item)
        )
        for item in result.artifacts
    )
    assert all(item.status is ValidationStatus.VALID for item in reports)


def test_evidence_validator_rejects_tampered_masking_context() -> None:
    class StaticContextLoader:
        async def load(self, _execution: ExecutionContext) -> DocumentContext:
            return _context()

    result = asyncio.run(
        DocumentSkill(
            context_loader=StaticContextLoader(),  # type: ignore[arg-type]
            package_builder=DocumentPackageBuilder(
                masking_service=_policy(),
                required_profile_fields=REQUIRED_PROFILE_FIELDS,
            ),
        ).execute(
            ExecutionContext(
                evaluation_case_id=CASE_ID,
                dataset_id=DATASET_ID,
                workflow_run_id="RUN-DOCUMENT-TAMPER",
                requested_scope=(EvaluationScope.FINANCE,),
                component_input={},
                current_node="DOCUMENT_PREPARATION",
            )
        )
    )
    package_draft = result.artifacts[1]
    payload = json.loads(json.dumps(package_draft.payload))
    payload["masking_manifest"]["items"][0]["recipient"] = "UNTRUSTED-RECIPIENT"
    report = asyncio.run(
        EvidenceValidator(
            masking_policy=_document(),
            masking_service=_policy(),
        ).validate(
            package_draft.model_copy(update={"payload": payload})
        )
    )

    assert report.status is ValidationStatus.BLOCKED
    assert any("invalid classification" in item for item in report.blocking_errors)


@pytest.mark.parametrize(
    ("field_name", "tampered_value"),
    (
        ("requested_amount", 999_999_999),
        ("contract_id", f"TOK-CONTRACT-ID-V1-{'A' * 26}"),
    ),
)
def test_validator_recomputes_masking_after_all_self_ids_are_rewritten(
    field_name: str,
    tampered_value: object,
) -> None:
    class StaticContextLoader:
        async def load(self, _execution: ExecutionContext) -> DocumentContext:
            return _context()

    result = asyncio.run(
        DocumentSkill(
            context_loader=StaticContextLoader(),  # type: ignore[arg-type]
            package_builder=DocumentPackageBuilder(
                masking_service=_policy(),
                required_profile_fields=REQUIRED_PROFILE_FIELDS,
            ),
        ).execute(
            ExecutionContext(
                evaluation_case_id=CASE_ID,
                dataset_id=DATASET_ID,
                workflow_run_id="RUN-DOCUMENT-SELF-REF-TAMPER",
                requested_scope=(EvaluationScope.FINANCE,),
                component_input={},
                current_node="DOCUMENT_PREPARATION",
            )
        )
    )
    draft = result.artifacts[1]
    payload = json.loads(json.dumps(draft.payload))
    payload["sanitized_payload"][field_name] = tampered_value
    manifest = payload["masking_manifest"]
    manifest_item = next(
        item for item in manifest["items"] if item["field_name"] == field_name
    )
    canonical_output = json.dumps(
        tampered_value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    manifest_item["output_digest"] = sha256(canonical_output).hexdigest()
    if manifest_item["output_reference"] is not None:
        manifest_item["output_reference"] = str(tampered_value)
    manifest_id = deterministic_id(
        "MASK",
        manifest["policy_id"],
        manifest["policy_version"],
        manifest["policy_document_sha256"],
        manifest["purpose"],
        manifest["recipient"],
        tuple(manifest["items"]),
    )
    manifest["manifest_id"] = manifest_id
    payload["masking_manifest_id"] = manifest_id
    payload["masking_manifest_item_ids"] = [
        deterministic_id("MASKI", manifest_id, item["field_name"])
        for item in manifest["items"]
    ]
    payload["package_draft_id"] = document_package_draft_id(
        request_artifact_id=payload["source_artifact_ids"][1],
        request_id=payload["preparation_request_id"],
        checklist_id=payload["checklist_id"],
        supplement_artifact_ids=tuple(payload["source_artifact_ids"][2:]),
        classification_decision_ids=tuple(payload["classification_decision_ids"]),
        masking_manifest_id=manifest_id,
    )
    identity_inputs = dict(draft.identity_inputs or {})
    identity_inputs["masking_manifest_id"] = manifest_id

    report = asyncio.run(
        EvidenceValidator(
            masking_policy=_document(),
            masking_service=_policy(),
        ).validate(
            draft.model_copy(
                update={"payload": payload, "identity_inputs": identity_inputs}
            )
        )
    )

    assert report.status is ValidationStatus.BLOCKED
    assert any(
        "not the exact trusted-policy output" in item
        for item in report.blocking_errors
    )


def test_document_evidence_submission_rejects_filesystem_paths() -> None:
    with pytest.raises(ValidationError, match="DOCREF-<UUIDv4>"):
        DocumentEvidenceSubmission(
            workflow_run_id="RUN-TEST",
            missing_request_id="MDR-TEST",
            document_reference_id=r"C:\\contracts\\signed.pdf",
            content_sha256="a" * 64,
            document_type=DocumentRequirementCode.SIGNED_CONTRACT,
            provided_by="FOUNDER",
            evidence_note=(
                DocumentEvidenceReasonCode.REQUESTED_DOCUMENT_REFERENCE_SUPPLIED
            ),
        )


def test_missing_required_profile_field_is_a_blocking_input_gap() -> None:
    context = _context()
    context = replace(
        context,
        opc_profile_records=tuple(
            item
            for item in context.opc_profile_records
            if item.record_id != "company_name"
        ),
    )
    checklist = DocumentChecklistBuilder(
        required_profile_fields=REQUIRED_PROFILE_FIELDS
    ).build(context)
    profile_item = next(
        item
        for item in checklist.checklist.items
        if item.document_code is DocumentRequirementCode.COMPANY_PROFILE
    )

    assert profile_item.status is DocumentRequirementStatus.MISSING
    assert profile_item.missing_request_id is not None
    assert any(
        item.field == DocumentRequirementCode.COMPANY_PROFILE.value
        for item in checklist.missing_data_requests
    )
    package = DocumentPackageBuilder(
        masking_service=_policy(),
        required_profile_fields=REQUIRED_PROFILE_FIELDS,
    ).build(context, checklist)
    assert package.package_draft.readiness is DocumentPackageReadiness.WAITING_FOR_INPUT
    assert package.release_package is None


def test_company_profile_reference_resumes_without_inventing_profile_fields() -> None:
    initial_context = _company_profile_only_context()
    checklist_builder = DocumentChecklistBuilder(
        required_profile_fields=REQUIRED_PROFILE_FIELDS
    )
    package_builder = DocumentPackageBuilder(
        masking_service=_policy(),
        required_profile_fields=REQUIRED_PROFILE_FIELDS,
    )

    initial_checklist = checklist_builder.build(initial_context)
    initial_profile = initial_checklist.checklist.items[0]
    assert initial_profile.document_code is DocumentRequirementCode.COMPANY_PROFILE
    assert initial_profile.status is DocumentRequirementStatus.MISSING
    initial_package = package_builder.build(initial_context, initial_checklist)
    assert initial_package.package_draft.readiness is (
        DocumentPackageReadiness.WAITING_FOR_INPUT
    )
    assert initial_package.release_package is None

    resumed_context = _with_company_profile_supplement(initial_context)
    resumed_checklist = checklist_builder.build(resumed_context)
    resumed_profile = resumed_checklist.checklist.items[0]
    assert resumed_profile.status is (
        DocumentRequirementStatus.AVAILABLE_WITH_LIMITATIONS
    )
    assert resumed_profile.source_reference_ids == (
        "DOCREF-00000000-0000-4000-8000-000000000101",
    )
    assert resumed_profile.limitation_codes == (
        "DOCUMENT_REFERENCE_NOT_REPOSITORY_VERIFIED",
    )
    assert resumed_checklist.missing_data_requests == ()

    resumed_package = package_builder.build(resumed_context, resumed_checklist)
    assert resumed_package.package_draft.readiness is (
        DocumentPackageReadiness.READY_FOR_INTERNAL_DECISION
    )
    assert resumed_package.release_package is not None
    assert "company_id" not in resumed_package.package_draft.sanitized_payload
    assert "company_name" not in resumed_package.package_draft.sanitized_payload
    assert tuple(
        item.field_name
        for item in resumed_package.package_draft.masking_manifest.items
        if item.field_name in REQUIRED_PROFILE_FIELDS
    ) == ()
    manifest_item = resumed_package.release_package.document_manifest[0]
    assert manifest_item.source_reference_ids == (
        "DOCREF-00000000-0000-4000-8000-000000000101",
    )
    assert manifest_item.limitation_codes == (
        "DOCUMENT_REFERENCE_NOT_REPOSITORY_VERIFIED",
    )


def test_unrelated_profile_field_is_ignored_before_masking() -> None:
    context = _context()
    unrelated = _record(
        "02_OPC_PROFILE",
        4,
        "internal_unknown_field",
        {
            "field": "internal_unknown_field",
            "value": {"nested": "must-not-enter-the-document-payload"},
        },
    )
    context = replace(
        context,
        opc_profile_records=(*context.opc_profile_records, unrelated),
    )
    checklist = DocumentChecklistBuilder(
        required_profile_fields=REQUIRED_PROFILE_FIELDS
    ).build(context)
    profile = next(
        item
        for item in checklist.checklist.items
        if item.document_code is DocumentRequirementCode.COMPANY_PROFILE
    )
    assert profile.status is DocumentRequirementStatus.AVAILABLE
    assert "internal_unknown_field" not in profile.source_reference_ids
    assert all(
        item.record_id != "internal_unknown_field"
        for item in checklist.evidence_refs
    )

    package = DocumentPackageBuilder(
        masking_service=_policy(),
        required_profile_fields=REQUIRED_PROFILE_FIELDS,
    ).build(context, checklist)
    assert "internal_unknown_field" not in package.package_draft.sanitized_payload
    assert "internal_unknown_field" not in tuple(
        item.field_name for item in package.package_draft.masking_manifest.items
    )


def test_evidence_intake_resolves_exact_request_without_raw_content() -> None:
    async def scenario() -> None:
        context = _context()
        context = replace(
            context,
            cashflow_records=(
                _record(
                    "09_CASHFLOW",
                    2,
                    "2026-06",
                    {
                        "month": "2026-06",
                        "cash_reserve_minimum": None,
                        "projected_closing_cash": None,
                    },
                ),
            ),
        )
        checklist = DocumentChecklistBuilder(
            required_profile_fields=REQUIRED_PROFILE_FIELDS
        ).build(context)
        package_build = DocumentPackageBuilder(
            masking_service=_policy(),
            required_profile_fields=REQUIRED_PROFILE_FIELDS,
        ).build(context, checklist)
        repository = InMemoryArtifactRepository()
        package_artifact = _envelope(
            artifact_id="ART-PACKAGE-DRAFT",
            artifact_type=ArtifactType.DOCUMENT_PACKAGE_DRAFT,
            payload=package_build.package_draft.model_dump(mode="json"),
            evidence_refs=package_build.evidence_refs,
        )
        await repository.save(package_artifact)
        request_id = next(
            item.request_id
            for item in checklist.missing_data_requests
            if item.field == DocumentRequirementCode.CASHFLOW_BUFFER_EVIDENCE.value
        )
        component = DocumentEvidenceIntake(
            artifacts=repository,
            redactor=DeterministicFreeTextRedactor(),
        )
        result = await component.execute(
            ExecutionContext(
                evaluation_case_id=CASE_ID,
                dataset_id=DATASET_ID,
                workflow_run_id="RUN-TEST",
                input_artifact_ids=(package_artifact.artifact_id,),
                requested_scope=(EvaluationScope.FINANCE,),
                component_input={
                    "submission": {
                        "workflow_run_id": "RUN-TEST",
                        "missing_request_id": request_id,
                        "document_reference_id": (
                            "DOCREF-00000000-0000-4000-8000-000000000103"
                        ),
                        "content_sha256": "b" * 64,
                        "document_type": "CASHFLOW_BUFFER_EVIDENCE",
                        "provided_by": "FOUNDER",
                        "evidence_note": "REQUESTED_DOCUMENT_REFERENCE_SUPPLIED",
                    },
                    "allowed_pending_request_id": request_id,
                },
                current_node="DOCUMENT_EVIDENCE_INTAKE",
            )
        )

        assert result.status is ComponentStatus.COMPLETED
        assert result.supplement is not None
        assert result.supplement.document_reference_id == (
            "DOCREF-00000000-0000-4000-8000-000000000103"
        )
        assert result.artifacts[0].artifact_type is (
            ArtifactType.DOCUMENT_EVIDENCE_SUPPLEMENT
        )
        assert "content" not in result.artifacts[0].payload
        assert "path" not in result.artifacts[0].payload
        report = await EvidenceValidator().validate(result.artifacts[0])
        assert report.status is ValidationStatus.VALID

        secret = "sensitive-document-token"
        rejected = await component.execute(
            ExecutionContext(
                evaluation_case_id=CASE_ID,
                dataset_id=DATASET_ID,
                workflow_run_id="RUN-TEST",
                input_artifact_ids=(package_artifact.artifact_id,),
                requested_scope=(EvaluationScope.FINANCE,),
                component_input={
                    "submission": {
                        "workflow_run_id": "RUN-TEST",
                        "missing_request_id": request_id,
                        "document_reference_id": (
                            "DOCREF-00000000-0000-4000-8000-000000000104"
                        ),
                        "content_sha256": "c" * 64,
                        "document_type": "CASHFLOW_BUFFER_EVIDENCE",
                        "provided_by": "FOUNDER",
                        "evidence_note": f"access_token={secret}",
                    },
                    "allowed_pending_request_id": request_id,
                },
                current_node="DOCUMENT_EVIDENCE_INTAKE",
            )
        )
        assert rejected.status is ComponentStatus.FAILED_SAFE
        assert secret not in rejected.model_dump_json()

        unsafe_notes = (
            r"Signed contract at C:\private\signed-contract.pdf",
            "Signed contract at https://files.example.test/private",
            f"Signed contract for {CONTRACT_ID}",
        )
        for index, unsafe_note in enumerate(unsafe_notes):
            unsafe = await component.execute(
                ExecutionContext(
                    evaluation_case_id=CASE_ID,
                    dataset_id=DATASET_ID,
                    workflow_run_id="RUN-TEST",
                    input_artifact_ids=(package_artifact.artifact_id,),
                    requested_scope=(EvaluationScope.FINANCE,),
                    component_input={
                        "submission": {
                            "workflow_run_id": "RUN-TEST",
                            "missing_request_id": request_id,
                            "document_reference_id": (
                                "DOCREF-00000000-0000-4000-8000-"
                                f"{index + 105:012d}"
                            ),
                            "content_sha256": f"{index + 1:x}" * 64,
                            "document_type": "CASHFLOW_BUFFER_EVIDENCE",
                            "provided_by": "FOUNDER",
                            "evidence_note": unsafe_note,
                        },
                        "allowed_pending_request_id": request_id,
                    },
                    current_node="DOCUMENT_EVIDENCE_INTAKE",
                )
            )
            assert unsafe.status is ComponentStatus.FAILED_SAFE
            assert unsafe_note not in unsafe.model_dump_json()

    asyncio.run(scenario())
