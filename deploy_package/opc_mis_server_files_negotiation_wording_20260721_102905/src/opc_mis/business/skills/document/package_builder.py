"""Build minimized, policy-masked internal document package drafts."""

from dataclasses import dataclass

from opc_mis.business.skills.document.checklist_builder import DocumentChecklistBuild
from opc_mis.business.skills.document.context_loader import DocumentContext
from opc_mis.domain.document_models import (
    DocumentPackageDraft,
    DocumentPackageReadiness,
    DocumentReleaseManifestItem,
    DocumentReleasePackage,
    DocumentRequirementCode,
    document_package_draft_id,
)
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.lineage import LineageFactory, deterministic_id
from opc_mis.domain.masking_models import MaskableScalar
from opc_mis.ports.masking_service import MaskingService

DOCUMENT_RELEASE_PURPOSE = "PERFORMANCE_BOND_DOCUMENT_RELEASE"
_BASE_REQUIRED_FIELDS = (
    "contract_id",
    "requested_amount",
    "currency",
    "bank_product_id",
    "request_type",
)
_SIGNED_CONTRACT_FIELDS = (
    "customer_id",
    "contract_value",
    "payment_terms",
)


class DocumentPackageBuildError(RuntimeError):
    """Raised when a safe package cannot be built from validated evidence."""


@dataclass(frozen=True)
class DocumentPackageBuild:
    """Internal draft plus an optional complete release candidate."""

    package_draft: DocumentPackageDraft
    release_package: DocumentReleasePackage | None
    evidence_refs: tuple[EvidenceRef, ...]


class DocumentPackageBuilder:
    """Build package models using only results returned by injected masking policy."""

    def __init__(
        self,
        *,
        masking_service: MaskingService,
        required_profile_fields: tuple[str, ...],
    ) -> None:
        if not required_profile_fields or len(set(required_profile_fields)) != len(
            required_profile_fields
        ):
            raise ValueError("required_profile_fields must be explicit and unique")
        self._masking_service = masking_service
        self._required_profile_fields = required_profile_fields

    @property
    def required_profile_fields(self) -> tuple[str, ...]:
        """Expose reviewed minimum fields so checklist and masking stay aligned."""
        return self._required_profile_fields

    def build(
        self,
        context: DocumentContext,
        checklist_build: DocumentChecklistBuild,
    ) -> DocumentPackageBuild:
        company_profile_required = (
            DocumentRequirementCode.COMPANY_PROFILE in context.request.required_document_codes
        )
        company_profile_reference_supplied = company_profile_required and any(
            supplement.document_type is DocumentRequirementCode.COMPANY_PROFILE
            for supplement in context.supplements
        )
        structured_profile_required = (
            company_profile_required and not company_profile_reference_supplied
        )
        signed_contract_required = (
            DocumentRequirementCode.SIGNED_CONTRACT in context.request.required_document_codes
        )
        profile = self._profile(context) if structured_profile_required else {}
        contract_snapshot = self._contract_snapshot(context) if signed_contract_required else {}
        missing_profile_fields = (
            tuple(
                field
                for field in self._required_profile_fields
                if field not in profile
                or profile[field] is None
                or (isinstance(profile[field], str) and not profile[field].strip())
            )
            if structured_profile_required
            else ()
        )
        profile_check = next(
            (
                item
                for item in checklist_build.checklist.items
                if item.document_code.value == "COMPANY_PROFILE"
            ),
            None,
        )
        if missing_profile_fields and (
            profile_check is None or profile_check.status.value != "MISSING"
        ):
            raise DocumentPackageBuildError(
                "Checklist failed to block unavailable company-profile fields: "
                + ", ".join(missing_profile_fields)
            )
        payload: dict[str, MaskableScalar] = {
            "contract_id": context.request.contract_id,
            "requested_amount": context.request.requested_amount,
            "currency": context.request.currency.value,
            "bank_product_id": context.request.bank_product_id,
            "request_type": "PERFORMANCE_BOND",
            **contract_snapshot,
            **profile,
        }
        available_required_profile_fields = (
            tuple(
                field
                for field in self._required_profile_fields
                if field not in set(missing_profile_fields)
            )
            if structured_profile_required
            else ()
        )
        required_fields = (
            *_BASE_REQUIRED_FIELDS,
            *(_SIGNED_CONTRACT_FIELDS if signed_contract_required else ()),
            *available_required_profile_fields,
        )
        source_evidence_ids_by_field = self._masking_source_evidence(
            context=context,
            field_names=tuple(payload),
            available_evidence=checklist_build.evidence_refs,
        )
        masked = self._masking_service.mask_payload(
            payload,
            recipient=context.request.provider,
            purpose=DOCUMENT_RELEASE_PURPOSE,
            required_fields=required_fields,
            source_evidence_ids_by_field=source_evidence_ids_by_field,
        )
        omitted_required_fields = tuple(
            field for field in required_fields if field not in masked.values
        )
        if omitted_required_fields:
            raise DocumentPackageBuildError(
                "Outbound masking policy omitted required Document fields: "
                + ", ".join(omitted_required_fields)
            )
        decision_ids = tuple(item.decision_id for item in masked.classification_decisions)
        manifest_item_ids = tuple(
            deterministic_id("MASKI", masked.manifest.manifest_id, item.field_name)
            for item in masked.manifest.items
        )
        package_draft_id = document_package_draft_id(
            request_artifact_id=context.request_artifact.artifact_id,
            request_id=context.request.request_id,
            checklist_id=checklist_build.checklist.checklist_id,
            supplement_artifact_ids=tuple(
                item.artifact_id for item in context.supplement_artifacts
            ),
            classification_decision_ids=decision_ids,
            masking_manifest_id=masked.manifest.manifest_id,
        )
        readiness = (
            DocumentPackageReadiness.WAITING_FOR_INPUT
            if checklist_build.missing_data_requests
            else DocumentPackageReadiness.READY_FOR_INTERNAL_DECISION
        )
        lineage = LineageFactory(context.dataset.dataset_id, context.dataset.source_hash)
        evidence = {item.evidence_id: item for item in checklist_build.evidence_refs}
        sources = tuple(
            item
            for item in checklist_build.evidence_refs
            if item.evidence_id in set(checklist_build.checklist.evidence_ids)
        )
        derived = lineage.derived(
            sheet="DOCUMENT_PACKAGE_DRAFT",
            record_id=package_draft_id,
            field="masked_internal_package",
            display={
                "preparation_request_id": context.request.request_id,
                "checklist_id": checklist_build.checklist.checklist_id,
                "readiness": readiness.value,
                "recipient": context.request.provider,
                "purpose": DOCUMENT_RELEASE_PURPOSE,
                "classification_decision_ids": list(decision_ids),
                "masking_manifest_id": masked.manifest.manifest_id,
                "included_field_names": list(masked.values),
            },
            sources=sources,
        )
        evidence[derived.evidence_id] = derived
        evidence_refs = tuple(evidence[key] for key in sorted(evidence))
        package = DocumentPackageDraft(
            package_draft_id=package_draft_id,
            evaluation_case_id=context.request.evaluation_case_id,
            dataset_id=context.request.dataset_id,
            contract_id=context.request.contract_id,
            preparation_request_id=context.request.request_id,
            checklist_id=checklist_build.checklist.checklist_id,
            approval_condition_codes=(checklist_build.checklist.approval_condition_codes),
            limitation_codes=checklist_build.checklist.limitation_codes,
            recipient=context.request.provider,
            purpose=DOCUMENT_RELEASE_PURPOSE,
            readiness=readiness,
            sanitized_payload=masked.values,
            classification_decisions=masked.classification_decisions,
            masking_manifest=masked.manifest,
            classification_decision_ids=decision_ids,
            masking_manifest_id=masked.manifest.manifest_id,
            masking_manifest_item_ids=manifest_item_ids,
            missing_data_requests=checklist_build.missing_data_requests,
            source_artifact_ids=context.source_artifact_ids,
            evidence_ids=tuple(item.evidence_id for item in evidence_refs),
        )
        release = None
        if readiness is DocumentPackageReadiness.READY_FOR_INTERNAL_DECISION:
            document_manifest = tuple(
                DocumentReleaseManifestItem(
                    manifest_item_id=deterministic_id(
                        "DRMI",
                        item.item_id,
                        item.document_code,
                        item.status,
                        item.limitation_codes,
                        item.source_reference_ids,
                        item.evidence_ids,
                    ),
                    checklist_item_id=item.item_id,
                    document_code=item.document_code,
                    status=item.status,
                    limitation_codes=item.limitation_codes,
                    source_reference_ids=item.source_reference_ids,
                    evidence_ids=item.evidence_ids,
                )
                for item in checklist_build.checklist.items
            )
            release = DocumentReleasePackage(
                release_package_id=deterministic_id(
                    "DRP",
                    package.package_draft_id,
                    context.request.request_id,
                    checklist_build.checklist.checklist_id,
                    masked.manifest.manifest_id,
                ),
                package_draft_id=package.package_draft_id,
                evaluation_case_id=package.evaluation_case_id,
                dataset_id=package.dataset_id,
                contract_id=package.contract_id,
                preparation_request_id=package.preparation_request_id,
                checklist_id=package.checklist_id,
                approval_condition_codes=package.approval_condition_codes,
                limitation_codes=package.limitation_codes,
                recipient=package.recipient,
                purpose=package.purpose,
                document_codes=tuple(item.document_code for item in document_manifest),
                document_manifest=document_manifest,
                sanitized_payload=package.sanitized_payload,
                classification_decisions=package.classification_decisions,
                masking_manifest=package.masking_manifest,
                classification_decision_ids=package.classification_decision_ids,
                masking_manifest_id=package.masking_manifest_id,
                masking_manifest_item_ids=package.masking_manifest_item_ids,
                source_artifact_ids=package.source_artifact_ids,
                evidence_ids=package.evidence_ids,
            )
        return DocumentPackageBuild(
            package_draft=package,
            release_package=release,
            evidence_refs=evidence_refs,
        )

    def _profile(self, context: DocumentContext) -> dict[str, MaskableScalar]:
        required_fields = set(self._required_profile_fields)
        profile: dict[str, MaskableScalar] = {}
        for record in context.opc_profile_records:
            field = record.values.get("field")
            if not isinstance(field, str) or field not in required_fields:
                continue
            if field != record.record_id:
                raise DocumentPackageBuildError(
                    f"Required OPC profile field {field!r} has a mismatched record ID."
                )
            if field in profile:
                raise DocumentPackageBuildError(
                    f"Required OPC profile field {field!r} is duplicated."
                )
            value = record.values.get("value")
            if value is not None and not isinstance(value, (str, bool, int, float)):
                raise DocumentPackageBuildError(
                    f"OPC profile field {field!r} is not a JSON-safe scalar."
                )
            profile[field] = value
        return profile

    @staticmethod
    def _contract_snapshot(context: DocumentContext) -> dict[str, MaskableScalar]:
        """Select only explicit contract fields needed by the bank-facing dossier."""

        snapshot: dict[str, MaskableScalar] = {}
        for field in _SIGNED_CONTRACT_FIELDS:
            value = context.contract.values.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                raise DocumentPackageBuildError(
                    f"Signed-contract snapshot requires exact contract field {field!r}."
                )
            if not isinstance(value, (str, bool, int, float)):
                raise DocumentPackageBuildError(
                    f"Signed-contract field {field!r} is not a JSON-safe scalar."
                )
            snapshot[field] = value
        return snapshot

    @staticmethod
    def _masking_source_evidence(
        *,
        context: DocumentContext,
        field_names: tuple[str, ...],
        available_evidence: tuple[EvidenceRef, ...],
    ) -> dict[str, tuple[str, ...]]:
        """Bind every masking input to exact validated upstream evidence."""
        available_ids = {item.evidence_id for item in available_evidence}
        request_sources = context.request.evidence_ids
        if not request_sources or not set(request_sources).issubset(available_ids):
            raise DocumentPackageBuildError(
                "Document masking inputs lack validated request evidence."
            )
        sources: dict[str, tuple[str, ...]] = {}
        for field_name in field_names:
            if field_name in _BASE_REQUIRED_FIELDS:
                sources[field_name] = request_sources
                continue
            if field_name in _SIGNED_CONTRACT_FIELDS:
                contract_sources = tuple(
                    item.evidence_id
                    for item in available_evidence
                    if item.record_id == context.contract.record_id and item.field == field_name
                )
                if not contract_sources:
                    raise DocumentPackageBuildError(
                        f"Document masking field {field_name!r} lacks exact contract evidence."
                    )
                sources[field_name] = contract_sources
                continue
            profile_sources = tuple(
                item.evidence_id
                for item in available_evidence
                if item.record_id == field_name and item.field in {"field", "value"}
            )
            if not profile_sources:
                raise DocumentPackageBuildError(
                    f"Document masking field {field_name!r} lacks exact profile evidence."
                )
            sources[field_name] = profile_sources
        return sources
