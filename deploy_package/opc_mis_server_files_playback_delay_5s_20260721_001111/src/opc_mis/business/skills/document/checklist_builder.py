"""Deterministic provider-document checklist construction."""

from dataclasses import dataclass

from opc_mis.business.skills.document.context_loader import DocumentContext
from opc_mis.domain.document_models import (
    DocumentChecklist,
    DocumentChecklistItem,
    DocumentRequirementCode,
    DocumentRequirementStatus,
    document_checklist_id,
)
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.lineage import LineageFactory, deterministic_id
from opc_mis.domain.missing_data import MissingDataRequest

_DOCUMENT_SKILL_ID = "DOCUMENT_SKILL"
_UNVERIFIED_REFERENCE_LIMITATION = "DOCUMENT_REFERENCE_NOT_REPOSITORY_VERIFIED"
_PENDING_FOUNDER_ACCEPTANCE_LIMITATION = "SIGNED_CONTRACT_PENDING_FOUNDER_ACCEPTANCE"
_CONTRACT_SNAPSHOT_FIELDS = (
    "contract_id",
    "customer_id",
    "contract_value",
    "payment_terms",
)


@dataclass(frozen=True)
class DocumentChecklistBuild:
    """Checklist plus the exact blocking requests and evidence closure."""

    checklist: DocumentChecklist
    missing_data_requests: tuple[MissingDataRequest, ...]
    evidence_refs: tuple[EvidenceRef, ...]


class DocumentChecklistBuilder:
    """Classify only provider-declared requirements using explicit evidence."""

    def __init__(self, *, required_profile_fields: tuple[str, ...]) -> None:
        if not required_profile_fields or len(set(required_profile_fields)) != len(
            required_profile_fields
        ):
            raise ValueError("required_profile_fields must be explicit and unique")
        self._required_profile_fields = required_profile_fields

    def build(self, context: DocumentContext) -> DocumentChecklistBuild:
        lineage = LineageFactory(context.dataset.dataset_id, context.dataset.source_hash)
        evidence = self._upstream_evidence(context)
        items: list[DocumentChecklistItem] = []
        missing_requests: list[MissingDataRequest] = []
        supplements = {item.document_type: item for item in context.supplements}
        supplement_artifacts = {
            item.document_type: artifact
            for item, artifact in zip(
                context.supplements, context.supplement_artifacts, strict=True
            )
        }

        for code in context.request.required_document_codes:
            supplement = supplements.get(code)
            if supplement is not None:
                artifact = supplement_artifacts[code]
                supplement_sources = tuple(
                    item
                    for item in artifact.evidence_refs
                    if item.evidence_id in set(supplement.evidence_ids)
                )
                contract_sources = (
                    tuple(
                        lineage.record_field(context.contract, field)
                        for field in _CONTRACT_SNAPSHOT_FIELDS
                        if field in context.contract.values
                        and context.contract.values[field] is not None
                    )
                    if code is DocumentRequirementCode.SIGNED_CONTRACT
                    else ()
                )
                sources = (*supplement_sources, *contract_sources)
                item, missing = self._item(
                    context=context,
                    code=code,
                    status=DocumentRequirementStatus.AVAILABLE_WITH_LIMITATIONS,
                    reason=(
                        "Authorized staff supplied an opaque reference and declared "
                        "content digest; repository and signature verification are not "
                        "implemented in this prototype."
                    ),
                    source_reference_ids=(supplement.document_reference_id,),
                    limitations=(_UNVERIFIED_REFERENCE_LIMITATION,),
                    sources=sources,
                    lineage=lineage,
                    evidence=evidence,
                )
            elif code is DocumentRequirementCode.SIGNED_CONTRACT:
                contract_sources = tuple(
                    lineage.record_field(context.contract, field)
                    for field in _CONTRACT_SNAPSHOT_FIELDS
                    if field in context.contract.values
                    and context.contract.values[field] is not None
                )
                item, missing = self._item(
                    context=context,
                    code=code,
                    status=DocumentRequirementStatus.DRAFTED,
                    reason=(
                        "A masked contract snapshot can be prepared from exact TeamPack "
                        "evidence. It becomes the signed-contract dossier entry only "
                        "after the Founder approves an ACCEPT Decision Card."
                    ),
                    source_reference_ids=(context.contract.record_id,),
                    limitations=(_PENDING_FOUNDER_ACCEPTANCE_LIMITATION,),
                    sources=contract_sources or self._request_sources(context),
                    lineage=lineage,
                    evidence=evidence,
                )
            elif code is DocumentRequirementCode.COMPANY_PROFILE:
                relevant_profile_records = tuple(
                    record
                    for record in context.opc_profile_records
                    if record.values.get("field") in self._required_profile_fields
                )
                profile_sources = tuple(
                    lineage.record_field(record, field)
                    for record in relevant_profile_records
                    for field in ("field", "value")
                )
                missing_profile_fields = self._missing_profile_fields(context)
                if relevant_profile_records and not missing_profile_fields:
                    status = DocumentRequirementStatus.AVAILABLE
                    reason = (
                        "Structured OPC profile evidence is available; outbound values "
                        "must pass data minimization and masking."
                    )
                else:
                    status = DocumentRequirementStatus.MISSING
                    reason = (
                        "Required OPC company-profile fields are unavailable: "
                        + ", ".join(missing_profile_fields)
                        if missing_profile_fields
                        else "A complete, uniquely keyed OPC company profile is unavailable."
                    )
                item, missing = self._item(
                    context=context,
                    code=code,
                    status=status,
                    reason=reason,
                    source_reference_ids=tuple(item.record_id for item in relevant_profile_records),
                    limitations=(),
                    sources=profile_sources or self._request_sources(context),
                    lineage=lineage,
                    evidence=evidence,
                )
            elif code is DocumentRequirementCode.PERFORMANCE_BOND_REQUEST_FORM:
                item, missing = self._item(
                    context=context,
                    code=code,
                    status=DocumentRequirementStatus.MISSING,
                    reason=(
                        "Founder must supply the exact performance-bond request-form "
                        "reference before the internal dossier is complete."
                    ),
                    source_reference_ids=(context.request.request_id,),
                    limitations=(),
                    sources=self._request_sources(context),
                    lineage=lineage,
                    evidence=evidence,
                )
            elif code is DocumentRequirementCode.CASHFLOW_BUFFER_EVIDENCE:
                cashflow_sources = tuple(
                    lineage.record_field(record, field)
                    for record in context.cashflow_records
                    for field in (
                        "month",
                        "cash_reserve_minimum",
                        "projected_closing_cash",
                    )
                )
                item, missing = self._item(
                    context=context,
                    code=code,
                    status=DocumentRequirementStatus.MISSING,
                    reason=(
                        "Founder must upload a PDF or DOCX cashflow-buffer evidence "
                        "document before the internal dossier can continue. TeamPack "
                        "OPC_GLOBAL cashflow facts are context only and do not replace "
                        "this required document."
                    ),
                    source_reference_ids=(context.request.request_id,),
                    limitations=(),
                    sources=cashflow_sources or self._request_sources(context),
                    lineage=lineage,
                    evidence=evidence,
                )
            else:
                raise RuntimeError(f"Unsupported provider document requirement: {code.value}")
            items.append(item)
            if missing is not None:
                missing_requests.append(missing)

        item_tuple = tuple(items)
        missing_tuple = tuple(missing_requests)
        source_artifact_ids = context.source_artifact_ids
        checklist_id = document_checklist_id(
            request_artifact_id=context.request_artifact.artifact_id,
            request_id=context.request.request_id,
            item_ids=tuple(item.item_id for item in item_tuple),
        )
        evidence_refs = tuple(evidence[key] for key in sorted(evidence))
        checklist = DocumentChecklist(
            checklist_id=checklist_id,
            evaluation_case_id=context.request.evaluation_case_id,
            dataset_id=context.request.dataset_id,
            contract_id=context.request.contract_id,
            preparation_request_id=context.request.request_id,
            approval_condition_codes=context.request.approval_condition_codes,
            items=item_tuple,
            missing_document_codes=tuple(
                item.document_code
                for item in item_tuple
                if item.status is DocumentRequirementStatus.MISSING
            ),
            limitation_codes=tuple(
                dict.fromkeys(
                    limitation for item in item_tuple for limitation in item.limitation_codes
                )
            ),
            source_artifact_ids=source_artifact_ids,
            evidence_ids=tuple(item.evidence_id for item in evidence_refs),
        )
        return DocumentChecklistBuild(
            checklist=checklist,
            missing_data_requests=missing_tuple,
            evidence_refs=evidence_refs,
        )

    @staticmethod
    def _item(
        *,
        context: DocumentContext,
        code: DocumentRequirementCode,
        status: DocumentRequirementStatus,
        reason: str,
        source_reference_ids: tuple[str, ...],
        limitations: tuple[str, ...],
        sources: tuple[EvidenceRef, ...],
        lineage: LineageFactory,
        evidence: dict[str, EvidenceRef],
    ) -> tuple[DocumentChecklistItem, MissingDataRequest | None]:
        for source in sources:
            evidence[source.evidence_id] = source
        missing_request_id = (
            deterministic_id(
                "MDR",
                context.request.evaluation_case_id,
                _DOCUMENT_SKILL_ID,
                context.request.request_id,
                code,
            )
            if status is DocumentRequirementStatus.MISSING
            else None
        )
        item_id = deterministic_id(
            "DCI",
            context.request_artifact.artifact_id,
            context.request.request_id,
            code,
            status,
            source_reference_ids,
            limitations,
            missing_request_id,
        )
        derived = lineage.derived(
            sheet="DOCUMENT_CHECKLIST",
            record_id=item_id,
            field=code.value,
            display={
                "document_code": code.value,
                "status": status.value,
                "limitation_codes": list(limitations),
                "missing_request_id": missing_request_id,
            },
            sources=sources,
        )
        evidence[derived.evidence_id] = derived
        item = DocumentChecklistItem(
            item_id=item_id,
            document_code=code,
            status=status,
            reason=reason,
            limitation_codes=limitations,
            source_reference_ids=source_reference_ids,
            evidence_ids=(derived.evidence_id,),
            missing_request_id=missing_request_id,
        )
        missing = None
        if missing_request_id is not None:
            missing = MissingDataRequest(
                request_id=missing_request_id,
                evaluation_case_id=context.request.evaluation_case_id,
                raised_by=_DOCUMENT_SKILL_ID,
                requirement_code=f"DOCUMENT_{code.value}_REQUIRED",
                target_record=context.request.request_id,
                field=code.value,
                expected_type=(
                    "opaque document_reference_id plus caller-declared SHA-256 content hash"
                ),
                reason=reason,
                evidence_refs=(derived,),
            )
        return item, missing

    def _missing_profile_fields(self, context: DocumentContext) -> tuple[str, ...]:
        required_fields = set(self._required_profile_fields)
        records: dict[str, object] = {}
        invalid_fields: set[str] = set()
        for item in context.opc_profile_records:
            field = item.values.get("field")
            if not isinstance(field, str) or field not in required_fields:
                continue
            if field != item.record_id or field in records:
                invalid_fields.add(field)
                continue
            records[field] = item.values.get("value")
        return tuple(
            field
            for field in self._required_profile_fields
            if field in invalid_fields
            or field not in records
            or records[field] is None
            or (isinstance(records[field], str) and not records[field].strip())
        )

    @staticmethod
    def _request_sources(context: DocumentContext) -> tuple[EvidenceRef, ...]:
        requested = set(context.request.evidence_ids)
        return tuple(
            item for item in context.request_artifact.evidence_refs if item.evidence_id in requested
        )

    @staticmethod
    def _upstream_evidence(context: DocumentContext) -> dict[str, EvidenceRef]:
        return {
            item.evidence_id: item
            for artifact in (
                context.evaluation_case_artifact,
                context.request_artifact,
                *context.supplement_artifacts,
            )
            for item in artifact.evidence_refs
        }
