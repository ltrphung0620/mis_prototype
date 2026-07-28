"""Side-effect-free deterministic Document Skill."""

from opc_mis.business.skills.document.checklist_builder import (
    DocumentChecklistBuilder,
)
from opc_mis.business.skills.document.context_loader import (
    DocumentContextError,
    DocumentContextLoader,
)
from opc_mis.business.skills.document.package_builder import (
    DocumentPackageBuilder,
    DocumentPackageBuildError,
)
from opc_mis.domain.artifacts import ArtifactDraft
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.document_models import DocumentSkillComponentResult
from opc_mis.domain.enums import ArtifactType, ComponentStatus
from opc_mis.domain.events import RuntimeEvent


class DocumentSkill:
    """Prepare internal drafts without persistence, approval, or external release."""

    component_id = "DOCUMENT_SKILL"

    def __init__(
        self,
        *,
        context_loader: DocumentContextLoader,
        package_builder: DocumentPackageBuilder,
        checklist_builder: DocumentChecklistBuilder | None = None,
    ) -> None:
        self._context_loader = context_loader
        self._package_builder = package_builder
        self._checklist_builder = checklist_builder or DocumentChecklistBuilder(
            required_profile_fields=package_builder.required_profile_fields
        )

    async def execute(self, context: ExecutionContext) -> DocumentSkillComponentResult:
        try:
            document_context = await self._context_loader.load(context)
            checklist_build = self._checklist_builder.build(document_context)
            package_build = self._package_builder.build(
                document_context, checklist_build
            )
        except (DocumentContextError, DocumentPackageBuildError, ValueError) as exc:
            return self._failed_safe(str(exc))

        checklist = checklist_build.checklist
        package = package_build.package_draft
        drafts: list[ArtifactDraft] = [
            ArtifactDraft(
                artifact_type=ArtifactType.DOCUMENT_CHECKLIST,
                evaluation_case_id=checklist.evaluation_case_id,
                producer=self.component_id,
                payload=checklist.model_dump(mode="json"),
                evidence_refs=checklist_build.evidence_refs,
                identity_inputs={
                    "preparation_request_id": checklist.preparation_request_id,
                    "source_artifact_ids": checklist.source_artifact_ids,
                    "item_ids": tuple(item.item_id for item in checklist.items),
                    "missing_document_codes": checklist.missing_document_codes,
                    "approval_condition_codes": (
                        checklist.approval_condition_codes
                    ),
                    "limitation_codes": checklist.limitation_codes,
                },
            ),
            ArtifactDraft(
                artifact_type=ArtifactType.DOCUMENT_PACKAGE_DRAFT,
                evaluation_case_id=package.evaluation_case_id,
                producer=self.component_id,
                payload=package.model_dump(mode="json"),
                evidence_refs=package_build.evidence_refs,
                identity_inputs={
                    "preparation_request_id": package.preparation_request_id,
                    "checklist_id": package.checklist_id,
                    "source_artifact_ids": package.source_artifact_ids,
                    "readiness": package.readiness,
                    "approval_condition_codes": (
                        package.approval_condition_codes
                    ),
                    "limitation_codes": package.limitation_codes,
                    "classification_decision_ids": (
                        package.classification_decision_ids
                    ),
                    "masking_manifest_id": package.masking_manifest_id,
                },
            ),
        ]
        release = package_build.release_package
        if release is not None:
            drafts.append(
                ArtifactDraft(
                    artifact_type=ArtifactType.DOCUMENT_RELEASE_PACKAGE,
                    evaluation_case_id=release.evaluation_case_id,
                    producer=self.component_id,
                    payload=release.model_dump(mode="json"),
                    evidence_refs=package_build.evidence_refs,
                    identity_inputs={
                        "package_draft_id": release.package_draft_id,
                        "preparation_request_id": release.preparation_request_id,
                        "checklist_id": release.checklist_id,
                        "source_artifact_ids": release.source_artifact_ids,
                        "document_codes": release.document_codes,
                        "document_manifest_item_ids": tuple(
                            item.manifest_item_id
                            for item in release.document_manifest
                        ),
                        "approval_condition_codes": (
                            release.approval_condition_codes
                        ),
                        "limitation_codes": release.limitation_codes,
                        "masking_manifest_id": release.masking_manifest_id,
                    },
                )
            )
        waiting = bool(checklist_build.missing_data_requests)
        warnings = tuple(
            dict.fromkeys(
                (
                    *(
                        f"DOCUMENT_MISSING_{item.document_code.value}"
                        for item in checklist.items
                        if item.missing_request_id is not None
                    ),
                    *(
                        limitation
                        for item in checklist.items
                        for limitation in item.limitation_codes
                    ),
                )
            )
        )
        return DocumentSkillComponentResult(
            status=(
                ComponentStatus.WAITING_FOR_INPUT
                if waiting
                else (
                    ComponentStatus.COMPLETED_WITH_WARNINGS
                    if warnings
                    else ComponentStatus.COMPLETED
                )
            ),
            checklist=checklist,
            package_draft=package,
            release_package=release,
            artifacts=tuple(drafts),
            missing_data_requests=checklist_build.missing_data_requests,
            warnings=warnings,
            runtime_events=(
                RuntimeEvent(
                    event_type=(
                        "DOCUMENT_PREPARATION_WAITING_FOR_INPUT"
                        if waiting
                        else "DOCUMENT_RELEASE_PACKAGE_READY"
                    ),
                    message=(
                        "Document prepared a masked internal draft and identified "
                        "blocking provider documents."
                        if waiting
                        else (
                            "Document prepared a masked release candidate; no external "
                            "release was authorized or performed."
                        )
                    ),
                    metadata={
                        "checklist_id": checklist.checklist_id,
                        "package_draft_id": package.package_draft_id,
                        "missing_document_count": len(
                            checklist.missing_document_codes
                        ),
                        "release_package_id": (
                            release.release_package_id if release is not None else None
                        ),
                    },
                ),
            ),
        )

    @staticmethod
    def _failed_safe(message: str) -> DocumentSkillComponentResult:
        return DocumentSkillComponentResult(
            status=ComponentStatus.FAILED_SAFE,
            runtime_events=(
                RuntimeEvent(
                    event_type="DOCUMENT_PREPARATION_FAILED_SAFE",
                    message=message,
                ),
            ),
        )
