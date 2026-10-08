"""Deterministically assemble a ready Internal Decision Package draft."""

from __future__ import annotations

from pydantic import ValidationError

from opc_mis.business.agents.decision.internal_package_context import (
    InternalDecisionPackageContext,
    InternalDecisionPackageContextError,
    InternalDecisionPackageContextLoader,
    InternalDecisionPackageMissingInputs,
)
from opc_mis.domain.artifacts import ArtifactDraft, ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import ArtifactType, ComponentStatus
from opc_mis.domain.events import RuntimeEvent
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.internal_decision_package_models import (
    InternalDecisionAssemblyPath,
    InternalDecisionAssemblyRequest,
    InternalDecisionPackage,
    InternalDecisionPackageComponentResult,
    internal_decision_governance_identity,
    internal_decision_missing_request_id,
    internal_decision_package_id,
)
from opc_mis.domain.missing_data import MissingDataRequest


class InternalDecisionPackageAssembler:
    """Assemble upstream snapshots without recommendation or side effects."""

    component_id = "INTERNAL_DECISION_PACKAGE_ASSEMBLER"

    def __init__(self, *, context_loader: InternalDecisionPackageContextLoader) -> None:
        self._context_loader = context_loader

    async def execute(
        self, context: ExecutionContext
    ) -> InternalDecisionPackageComponentResult:
        try:
            request = InternalDecisionAssemblyRequest.model_validate(
                context.component_input
            )
        except ValidationError as exc:
            return self._failed_safe(
                f"Invalid Internal Decision Package assembly request: {exc}"
            )
        try:
            package_context = await self._context_loader.load(context, request)
            package, evidence_refs = self._build(package_context)
        except InternalDecisionPackageMissingInputs as exc:
            missing = tuple(
                MissingDataRequest(
                    request_id=internal_decision_missing_request_id(
                        evaluation_case_id=(
                            context.evaluation_case_id or "UNKNOWN_CASE"
                        ),
                        assembly_path=request.assembly_path,
                        requirement_code=item.requirement_code,
                        field=item.field,
                    ),
                    evaluation_case_id=(
                        context.evaluation_case_id or "UNKNOWN_CASE"
                    ),
                    raised_by=self.component_id,
                    requirement_code=item.requirement_code,
                    target_record=item.target_record,
                    field=item.field,
                    expected_type=item.expected_type,
                    reason=item.reason,
                )
                for item in exc.missing
            )
            return InternalDecisionPackageComponentResult(
                status=ComponentStatus.WAITING_FOR_INPUT,
                missing_data_requests=missing,
                runtime_events=(
                    RuntimeEvent(
                        event_type="INTERNAL_DECISION_PACKAGE_WAITING_FOR_INPUT",
                        message=(
                            "Internal Decision Package assembly is waiting for "
                            "explicit validated upstream inputs."
                        ),
                        metadata={"missing_requirement_count": len(missing)},
                    ),
                ),
            )
        except (InternalDecisionPackageContextError, ValidationError, ValueError) as exc:
            return self._failed_safe(str(exc))

        warnings = self._warnings(request.assembly_path)
        status = (
            ComponentStatus.COMPLETED
            if not warnings
            else ComponentStatus.COMPLETED_WITH_WARNINGS
        )
        draft = ArtifactDraft(
            artifact_type=ArtifactType.INTERNAL_DECISION_PACKAGE,
            evaluation_case_id=package.evaluation_case_id,
            producer=self.component_id,
            payload=package.model_dump(mode="json"),
            evidence_refs=evidence_refs,
            identity_inputs={
                "assembly_path": package.assembly_path,
                "source_artifacts": tuple(
                    item.model_dump(mode="json")
                    for item in package.source_artifacts
                ),
                "governance_references": tuple(
                    internal_decision_governance_identity(item)
                    for item in package.governance_references
                ),
            },
        )
        return InternalDecisionPackageComponentResult(
            status=status,
            package=package,
            artifacts=(draft,),
            warnings=warnings,
            runtime_events=(
                RuntimeEvent(
                    event_type="INTERNAL_DECISION_PACKAGE_ASSEMBLED",
                    message=(
                        "Validated upstream snapshots were assembled for a later "
                        "internal Decision phase without recommendation, approval, "
                        "selection, or external action."
                    ),
                    metadata={
                        "assembly_path": package.assembly_path.value,
                        "source_artifact_count": len(package.source_artifacts),
                        "evidence_count": len(package.evidence_ids),
                    },
                ),
            ),
        )

    @staticmethod
    def _build(
        context: InternalDecisionPackageContext,
    ) -> tuple[InternalDecisionPackage, tuple[EvidenceRef, ...]]:
        evidence_refs = InternalDecisionPackageAssembler._evidence_refs(
            context.source_artifacts
        )
        evidence_ids = tuple(item.evidence_id for item in evidence_refs)
        governance = context.governance_references
        package_id = internal_decision_package_id(
            assembly_path=context.request.assembly_path,
            source_artifacts=context.source_artifact_refs,
            governance_references=governance,
        )
        package = InternalDecisionPackage(
            package_id=package_id,
            evaluation_case_id=context.evaluation_case.evaluation_case_id,
            dataset_id=context.evaluation_case.dataset_id,
            contract_id=context.evaluation_case.contract_id,
            assembly_path=context.request.assembly_path,
            evaluation_case_artifact_id=context.evaluation_case_artifact.artifact_id,
            finance_facts_artifact_id=context.finance_facts_artifact.artifact_id,
            finance_assessment_artifact_id=(
                context.finance_assessment_artifact.artifact_id
            ),
            operations_facts_artifact_id=(
                context.operations_facts_artifact.artifact_id
            ),
            operations_assessment_artifact_id=(
                context.operations_assessment_artifact.artifact_id
            ),
            risk_assessment_artifact_id=context.risk_assessment_artifact.artifact_id,
            approval_checkpoint_artifact_ids=tuple(
                item.artifact_id for item in context.approval_checkpoint_artifacts
            ),
            decision_route_plan_artifact_id=(
                context.decision_route_plan_artifact.artifact_id
            ),
            banking_discovery_request_artifact_id=_artifact_id(
                context.banking_discovery_request_artifact
            ),
            banking_option_matrix_artifact_id=_artifact_id(
                context.banking_option_matrix_artifact
            ),
            banking_discovery_result_artifact_id=_artifact_id(
                context.banking_discovery_result_artifact
            ),
            banking_option_advice_artifact_id=_artifact_id(
                context.banking_option_advice_artifact
            ),
            banking_precheck_readiness_artifact_id=_artifact_id(
                context.banking_precheck_readiness_artifact
            ),
            decision_post_banking_review_artifact_id=_artifact_id(
                context.decision_post_banking_review_artifact
            ),
            banking_precheck_proposal_artifact_id=_artifact_id(
                context.banking_precheck_proposal_artifact
            ),
            banking_precheck_result_set_artifact_id=_artifact_id(
                context.banking_precheck_result_set_artifact
            ),
            decision_post_precheck_review_artifact_id=_artifact_id(
                context.decision_post_precheck_review_artifact
            ),
            document_preparation_request_artifact_id=_artifact_id(
                context.document_preparation_request_artifact
            ),
            document_release_package_artifact_id=_artifact_id(
                context.document_release_package_artifact
            ),
            evaluation_case=context.evaluation_case,
            finance_facts=context.finance_facts,
            finance_assessment=context.finance_assessment,
            operations_facts=context.operations_facts,
            operations_assessment=context.operations_assessment,
            risk_assessment=context.risk_assessment,
            approval_checkpoints=context.approval_checkpoints,
            decision_route_plan=context.decision_route_plan,
            banking_discovery_request=context.banking_discovery_request,
            banking_option_matrix=context.banking_option_matrix,
            banking_discovery_result=context.banking_discovery_result,
            banking_option_advice=context.banking_option_advice,
            banking_precheck_readiness=context.banking_precheck_readiness,
            decision_post_banking_review=context.decision_post_banking_review,
            banking_precheck_proposal=context.banking_precheck_proposal,
            banking_precheck_result_set=context.banking_precheck_result_set,
            decision_post_precheck_review=context.decision_post_precheck_review,
            document_preparation_request=context.document_preparation_request,
            document_release_package=context.document_release_package,
            source_artifacts=context.source_artifact_refs,
            source_artifact_ids=context.source_artifact_ids,
            governance_references=governance,
            governance_reference_ids=tuple(
                item.approval_request_id for item in governance
            ),
            evidence_ids=evidence_ids,
        )
        return package, evidence_refs

    @staticmethod
    def _evidence_refs(
        artifacts: tuple[ArtifactEnvelope, ...],
    ) -> tuple[EvidenceRef, ...]:
        """Preserve source order and the first exact reference for each evidence ID."""
        seen: set[str] = set()
        ordered: list[EvidenceRef] = []
        for artifact in artifacts:
            for evidence in artifact.evidence_refs:
                if evidence.evidence_id in seen:
                    continue
                seen.add(evidence.evidence_id)
                ordered.append(evidence)
        return tuple(ordered)

    @staticmethod
    def _warnings(path: InternalDecisionAssemblyPath) -> tuple[str, ...]:
        if path in {
            InternalDecisionAssemblyPath.DIRECT_ROUTE,
            InternalDecisionAssemblyPath.CONDITIONAL_DOCUMENT_READY,
        }:
            return ()
        return (f"INTERNAL_DECISION_PACKAGE_PATH_{path.value}",)

    @staticmethod
    def _failed_safe(message: str) -> InternalDecisionPackageComponentResult:
        return InternalDecisionPackageComponentResult(
            status=ComponentStatus.FAILED_SAFE,
            runtime_events=(
                RuntimeEvent(
                    event_type="INTERNAL_DECISION_PACKAGE_FAILED_SAFE",
                    message=message,
                ),
            ),
        )


def _artifact_id(artifact: ArtifactEnvelope | None) -> str | None:
    return artifact.artifact_id if artifact is not None else None
