"""Typed contracts for deterministic Internal Decision Package assembly.

The package is a read-only snapshot of already validated business artifacts.  It
does not recommend, select, approve, persist, or execute an external action.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator

from opc_mis.domain.approvals import ApprovalCheckpointSet
from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.banking_models import (
    BankingDiscoveryRequest,
    BankingDiscoveryResult,
    BankingOptionAdvice,
    BankingOptionMatrix,
    BankingPrecheckReadiness,
)
from opc_mis.domain.banking_precheck_execution_models import (
    BankingPrecheckResultSet,
)
from opc_mis.domain.banking_precheck_submission_models import (
    BankingPrecheckSubmissionProposal,
)
from opc_mis.domain.components import ComponentResult
from opc_mis.domain.decision_post_banking_models import DecisionPostBankingReview
from opc_mis.domain.decision_post_precheck_models import DecisionPostPrecheckReview
from opc_mis.domain.decision_route_models import DecisionRoutePlan
from opc_mis.domain.document_models import (
    DocumentPreparationRequest,
    DocumentReleasePackage,
)
from opc_mis.domain.enums import (
    ApprovalDecision,
    ApprovalRequestStatus,
    ArtifactType,
    ComponentStatus,
    DecisionPostBankingOutcome,
    DecisionPostPrecheckOutcome,
    DecisionRouteOutcome,
    ProtectedAction,
    ValidationStatus,
    WorkflowStatus,
)
from opc_mis.domain.finance_models import FinanceAssessment, FinanceFacts
from opc_mis.domain.lineage import deterministic_id
from opc_mis.domain.missing_data import MissingDataRequest
from opc_mis.domain.operations_models import OperationsAssessment, OperationsFacts
from opc_mis.domain.planner_models import EvaluationCase
from opc_mis.domain.risk_models import InitialRiskAssessment
from opc_mis.domain.serialization import json_safe
from opc_mis.domain.validation_reports import ValidationReport


class InternalDecisionAssemblyPath(StrEnum):
    """Evidence-backed path that ended before internal decision preparation."""

    DIRECT_ROUTE = "DIRECT_ROUTE"
    BANKING_NO_VIABLE_OPTION = "BANKING_NO_VIABLE_OPTION"
    BANKING_NO_PRECHECK_PATH = "BANKING_NO_PRECHECK_PATH"
    BANKING_PRECHECK_DECLINED = "BANKING_PRECHECK_DECLINED"
    BANKING_NON_ACTIONABLE = "BANKING_NON_ACTIONABLE"
    CONDITIONAL_DOCUMENT_READY = "CONDITIONAL_DOCUMENT_READY"


class InternalDecisionPackageReadiness(StrEnum):
    """Assembly readiness; no partial package is emitted."""

    READY = "READY"


class InternalDecisionAssemblyRequest(BaseModel):
    """Workflow-selected assembly path with an exact Governance reference."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    assembly_path: InternalDecisionAssemblyPath
    approval_request_id: StrictStr | None = None

    @model_validator(mode="after")
    def validate_governance_reference(self) -> InternalDecisionAssemblyRequest:
        requires_approval = (
            self.assembly_path
            is InternalDecisionAssemblyPath.BANKING_PRECHECK_DECLINED
        )
        if requires_approval != (self.approval_request_id is not None):
            raise ValueError(
                "approval_request_id is required only for BANKING_PRECHECK_DECLINED"
            )
        return self


class InternalDecisionSourceArtifactRef(BaseModel):
    """Exact immutable identity of one validated source envelope."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: StrictStr = Field(min_length=1)
    artifact_type: ArtifactType
    version: int = Field(ge=1)
    input_hash: StrictStr = Field(min_length=1)
    validation_status: ValidationStatus
    evidence_ids: tuple[StrictStr, ...] = ()

    @model_validator(mode="after")
    def validate_reference(self) -> InternalDecisionSourceArtifactRef:
        if self.validation_status not in {
            ValidationStatus.VALID,
            ValidationStatus.VALID_WITH_WARNINGS,
        }:
            raise ValueError("Internal Decision sources must already be validated")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("source artifact evidence_ids must be unique")
        return self


class InternalDecisionGovernanceReference(BaseModel):
    """Exact rejected precheck decision used only as an assembly-path fact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    approval_request_id: StrictStr = Field(min_length=1)
    workflow_run_id: StrictStr = Field(min_length=1)
    status: ApprovalRequestStatus
    action: ProtectedAction
    subject_artifact_id: StrictStr = Field(min_length=1)
    subject_artifact_version: int = Field(ge=1)
    subject_input_hash: StrictStr = Field(min_length=1)
    checkpoint_ids: tuple[StrictStr, ...]
    policy_artifact_id: StrictStr = Field(min_length=1)
    policy_artifact_version: int = Field(ge=1)
    policy_input_hash: StrictStr = Field(min_length=1)
    policy_coverage_ids: tuple[StrictStr, ...] = ()
    decision: ApprovalDecision
    decided_by: StrictStr = Field(min_length=1)
    decision_reason: StrictStr = Field(min_length=1)
    decided_at: datetime

    @model_validator(mode="after")
    def validate_decline(self) -> InternalDecisionGovernanceReference:
        if (
            self.status is not ApprovalRequestStatus.REJECTED
            or self.action is not ProtectedAction.SUBMIT_BANKING_PRECHECK
            or self.decision is not ApprovalDecision.REJECT
        ):
            raise ValueError(
                "Governance reference must be a rejected Banking precheck request"
            )
        if len(set(self.checkpoint_ids)) != len(self.checkpoint_ids):
            raise ValueError("Governance checkpoint IDs must be unique")
        if len(set(self.policy_coverage_ids)) != len(self.policy_coverage_ids):
            raise ValueError("Governance policy coverage IDs must be unique")
        if self.decided_at.tzinfo is None:
            raise ValueError("Governance decision time must be timezone-aware")
        return self


def internal_decision_governance_identity(
    reference: InternalDecisionGovernanceReference,
) -> dict[str, Any]:
    """Return stable business identity without workflow IDs or event timestamps."""
    return {
        "status": reference.status,
        "action": reference.action,
        "subject_artifact_id": reference.subject_artifact_id,
        "subject_artifact_version": reference.subject_artifact_version,
        "subject_input_hash": reference.subject_input_hash,
        "checkpoint_ids": reference.checkpoint_ids,
        "policy_artifact_id": reference.policy_artifact_id,
        "policy_artifact_version": reference.policy_artifact_version,
        "policy_input_hash": reference.policy_input_hash,
        "policy_coverage_ids": reference.policy_coverage_ids,
        "decision": reference.decision,
        "decided_by": reference.decided_by,
        "decision_reason": reference.decision_reason,
    }


def internal_decision_package_id(
    *,
    assembly_path: InternalDecisionAssemblyPath,
    source_artifacts: tuple[InternalDecisionSourceArtifactRef, ...],
    governance_references: tuple[InternalDecisionGovernanceReference, ...],
) -> str:
    """Build identity only from exact durable business and Governance inputs."""
    return deterministic_id(
        "IDP",
        assembly_path,
        tuple(item.model_dump(mode="json") for item in source_artifacts),
        tuple(
            internal_decision_governance_identity(item)
            for item in governance_references
        ),
    )


def internal_decision_missing_request_id(
    *,
    evaluation_case_id: str,
    assembly_path: InternalDecisionAssemblyPath,
    requirement_code: str,
    field: str,
) -> str:
    """Build a stable blocking-request identity for one assembly prerequisite."""
    return deterministic_id(
        "MDR",
        evaluation_case_id,
        "INTERNAL_DECISION_PACKAGE_ASSEMBLER",
        assembly_path,
        requirement_code,
        field,
    )


class InternalDecisionPackage(BaseModel):
    """Exact snapshots for a later Decision policy, never a recommendation itself."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    package_id: StrictStr = Field(min_length=1)
    evaluation_case_id: StrictStr = Field(min_length=1)
    dataset_id: StrictStr = Field(min_length=1)
    contract_id: StrictStr = Field(min_length=1)
    assembly_path: InternalDecisionAssemblyPath
    readiness: InternalDecisionPackageReadiness = (
        InternalDecisionPackageReadiness.READY
    )

    evaluation_case_artifact_id: StrictStr = Field(min_length=1)
    finance_facts_artifact_id: StrictStr = Field(min_length=1)
    finance_assessment_artifact_id: StrictStr = Field(min_length=1)
    operations_facts_artifact_id: StrictStr = Field(min_length=1)
    operations_assessment_artifact_id: StrictStr = Field(min_length=1)
    risk_assessment_artifact_id: StrictStr = Field(min_length=1)
    approval_checkpoint_artifact_ids: tuple[StrictStr, ...] = Field(min_length=1)
    decision_route_plan_artifact_id: StrictStr = Field(min_length=1)

    banking_discovery_request_artifact_id: StrictStr | None = None
    banking_option_matrix_artifact_id: StrictStr | None = None
    banking_discovery_result_artifact_id: StrictStr | None = None
    banking_option_advice_artifact_id: StrictStr | None = None
    banking_precheck_readiness_artifact_id: StrictStr | None = None
    decision_post_banking_review_artifact_id: StrictStr | None = None
    banking_precheck_proposal_artifact_id: StrictStr | None = None
    banking_precheck_result_set_artifact_id: StrictStr | None = None
    decision_post_precheck_review_artifact_id: StrictStr | None = None
    document_preparation_request_artifact_id: StrictStr | None = None
    document_release_package_artifact_id: StrictStr | None = None

    evaluation_case: EvaluationCase
    finance_facts: FinanceFacts
    finance_assessment: FinanceAssessment
    operations_facts: OperationsFacts
    operations_assessment: OperationsAssessment
    risk_assessment: InitialRiskAssessment
    approval_checkpoints: tuple[ApprovalCheckpointSet, ...] = Field(min_length=1)
    decision_route_plan: DecisionRoutePlan

    banking_discovery_request: BankingDiscoveryRequest | None = None
    banking_option_matrix: BankingOptionMatrix | None = None
    banking_discovery_result: BankingDiscoveryResult | None = None
    banking_option_advice: BankingOptionAdvice | None = None
    banking_precheck_readiness: BankingPrecheckReadiness | None = None
    decision_post_banking_review: DecisionPostBankingReview | None = None
    banking_precheck_proposal: BankingPrecheckSubmissionProposal | None = None
    banking_precheck_result_set: BankingPrecheckResultSet | None = None
    decision_post_precheck_review: DecisionPostPrecheckReview | None = None
    document_preparation_request: DocumentPreparationRequest | None = None
    document_release_package: DocumentReleasePackage | None = None

    source_artifacts: tuple[InternalDecisionSourceArtifactRef, ...] = Field(
        min_length=8
    )
    source_artifact_ids: tuple[StrictStr, ...] = Field(min_length=8)
    governance_references: tuple[InternalDecisionGovernanceReference, ...] = ()
    governance_reference_ids: tuple[StrictStr, ...] = ()
    evidence_ids: tuple[StrictStr, ...]
    missing_data_requests: tuple[MissingDataRequest, ...] = ()

    recommendation_performed: Literal[False] = False
    selection_performed: Literal[False] = False
    approval_requested: Literal[False] = False
    external_action_performed: Literal[False] = False

    @model_validator(mode="after")
    def validate_exact_snapshots(self) -> InternalDecisionPackage:
        """Reject mismatched identities, paths, indexes, and implied decisions."""
        expected_identity = (
            self.evaluation_case_id,
            self.dataset_id,
            self.contract_id,
        )
        identity_models = (
            self.evaluation_case,
            self.finance_facts,
            self.operations_facts,
            self.risk_assessment,
            self.decision_route_plan,
            *self.approval_checkpoints,
        )
        if any(
            (
                item.evaluation_case_id,
                item.dataset_id,
                item.contract_id,
            )
            != expected_identity
            for item in identity_models
        ):
            raise ValueError("Internal Decision snapshots belong to different cases")
        for assessment in (self.finance_assessment, self.operations_assessment):
            if (
                assessment.evaluation_case_id,
                assessment.dataset_id,
                assessment.contract_id,
            ) != expected_identity:
                raise ValueError("Assessment identity differs from the package")

        if self.finance_assessment.fact_ids != tuple(
            item.fact_id for item in self.finance_facts.facts
        ):
            raise ValueError("Finance assessment does not index the exact Finance facts")
        if self.finance_assessment.facts_input_hash != internal_decision_snapshot_hash(
            self.finance_facts
        ):
            raise ValueError("Finance assessment was built from different Finance facts")
        if self.operations_assessment.fact_ids != tuple(
            item.fact_id for item in self.operations_facts.facts
        ):
            raise ValueError(
                "Operations assessment does not index the exact Operations facts"
            )
        if self.operations_assessment.facts_input_hash != internal_decision_snapshot_hash(
            self.operations_facts
        ):
            raise ValueError(
                "Operations assessment was built from different Operations facts"
            )
        if (
            self.risk_assessment.finance_facts_artifact_id
            != self.finance_facts_artifact_id
            or self.risk_assessment.operations_facts_artifact_id
            != self.operations_facts_artifact_id
        ):
            raise ValueError("Risk assessment references different fact artifacts")

        source_ids = tuple(item.artifact_id for item in self.source_artifacts)
        if source_ids != self.source_artifact_ids or len(set(source_ids)) != len(
            source_ids
        ):
            raise ValueError("source_artifact_ids must exactly index unique sources")
        expected_evidence = tuple(
            dict.fromkeys(
                evidence_id
                for artifact in self.source_artifacts
                for evidence_id in artifact.evidence_ids
            )
        )
        if self.evidence_ids != expected_evidence:
            raise ValueError("evidence_ids must exactly index source-envelope evidence")
        if self.governance_reference_ids != tuple(
            item.approval_request_id for item in self.governance_references
        ):
            raise ValueError("governance_reference_ids do not match references")
        if len(set(self.governance_reference_ids)) != len(
            self.governance_reference_ids
        ):
            raise ValueError("governance_reference_ids must be unique")
        known_checkpoint_ids = {
            checkpoint.checkpoint_id
            for checkpoint_set in self.approval_checkpoints
            for checkpoint in checkpoint_set.checkpoints
        }
        known_coverage_ids = {
            coverage.coverage_id
            for checkpoint_set in self.approval_checkpoints
            for coverage in checkpoint_set.policy_coverages
        }
        if any(
            not set(reference.checkpoint_ids).issubset(known_checkpoint_ids)
            or not set(reference.policy_coverage_ids).issubset(
                known_coverage_ids
            )
            for reference in self.governance_references
        ):
            raise ValueError("Governance reference has dangling policy IDs")
        if self.missing_data_requests:
            raise ValueError("A ready Internal Decision Package cannot contain gaps")

        self._validate_artifact_bindings()
        self._validate_path()
        expected_package_id = internal_decision_package_id(
            assembly_path=self.assembly_path,
            source_artifacts=self.source_artifacts,
            governance_references=self.governance_references,
        )
        if self.package_id != expected_package_id:
            raise ValueError("Internal Decision package_id is unstable")
        return self

    def _validate_artifact_bindings(self) -> None:
        refs = {item.artifact_id: item.artifact_type for item in self.source_artifacts}
        bindings: tuple[tuple[str | None, BaseModel | None, ArtifactType], ...] = (
            (
                self.evaluation_case_artifact_id,
                self.evaluation_case,
                ArtifactType.EVALUATION_CASE,
            ),
            (
                self.finance_facts_artifact_id,
                self.finance_facts,
                ArtifactType.FINANCE_FACTS,
            ),
            (
                self.finance_assessment_artifact_id,
                self.finance_assessment,
                ArtifactType.FINANCE_ASSESSMENT,
            ),
            (
                self.operations_facts_artifact_id,
                self.operations_facts,
                ArtifactType.OPERATIONS_FACTS,
            ),
            (
                self.operations_assessment_artifact_id,
                self.operations_assessment,
                ArtifactType.OPERATIONS_ASSESSMENT,
            ),
            (
                self.risk_assessment_artifact_id,
                self.risk_assessment,
                ArtifactType.INITIAL_RISK_ASSESSMENT,
            ),
            (
                self.decision_route_plan_artifact_id,
                self.decision_route_plan,
                ArtifactType.DECISION_ROUTE_PLAN,
            ),
            (
                self.banking_discovery_request_artifact_id,
                self.banking_discovery_request,
                ArtifactType.BANKING_DISCOVERY_REQUEST,
            ),
            (
                self.banking_option_matrix_artifact_id,
                self.banking_option_matrix,
                ArtifactType.BANKING_OPTION_MATRIX,
            ),
            (
                self.banking_discovery_result_artifact_id,
                self.banking_discovery_result,
                ArtifactType.BANKING_DISCOVERY_RESULT,
            ),
            (
                self.banking_option_advice_artifact_id,
                self.banking_option_advice,
                ArtifactType.BANKING_OPTION_ADVICE,
            ),
            (
                self.banking_precheck_readiness_artifact_id,
                self.banking_precheck_readiness,
                ArtifactType.BANKING_PRECHECK_READINESS,
            ),
            (
                self.decision_post_banking_review_artifact_id,
                self.decision_post_banking_review,
                ArtifactType.DECISION_POST_BANKING_REVIEW,
            ),
            (
                self.banking_precheck_proposal_artifact_id,
                self.banking_precheck_proposal,
                ArtifactType.BANKING_PRECHECK_SUBMISSION_PROPOSAL,
            ),
            (
                self.banking_precheck_result_set_artifact_id,
                self.banking_precheck_result_set,
                ArtifactType.BANKING_PRECHECK_RESULT_SET,
            ),
            (
                self.decision_post_precheck_review_artifact_id,
                self.decision_post_precheck_review,
                ArtifactType.DECISION_POST_PRECHECK_REVIEW,
            ),
            (
                self.document_preparation_request_artifact_id,
                self.document_preparation_request,
                ArtifactType.DOCUMENT_PREPARATION_REQUEST,
            ),
            (
                self.document_release_package_artifact_id,
                self.document_release_package,
                ArtifactType.DOCUMENT_RELEASE_PACKAGE,
            ),
        )
        if any(
            artifact_id is not None and refs.get(artifact_id) is not artifact_type
            for artifact_id, _, artifact_type in bindings
        ):
            raise ValueError("A package artifact binding has the wrong source type")
        if any(
            (artifact_id is None) != (snapshot is None)
            for artifact_id, snapshot, _ in bindings
        ):
            raise ValueError("A package snapshot and artifact binding disagree")
        checkpoint_ids = tuple(
            item.artifact_id
            for item in self.source_artifacts
            if item.artifact_type is ArtifactType.APPROVAL_CHECKPOINTS
        )
        if checkpoint_ids != self.approval_checkpoint_artifact_ids:
            raise ValueError("Approval checkpoint artifact index is not exact")
        if len(checkpoint_ids) != len(self.approval_checkpoints):
            raise ValueError("Approval checkpoint snapshots do not match artifacts")
        bound_ids = {
            artifact_id
            for artifact_id, _, _ in bindings
            if artifact_id is not None
        } | set(checkpoint_ids)
        if bound_ids != set(self.source_artifact_ids):
            raise ValueError("Source artifacts are not exactly bound to package snapshots")

    def _validate_path(self) -> None:
        banking_values = (
            self.banking_discovery_request,
            self.banking_option_matrix,
            self.banking_discovery_result,
            self.banking_precheck_readiness,
            self.decision_post_banking_review,
        )
        if self.assembly_path is InternalDecisionAssemblyPath.DIRECT_ROUTE:
            if self.decision_route_plan.route_outcome is not (
                DecisionRouteOutcome.DIRECT_INTERNAL_DECISION
            ):
                raise ValueError("DIRECT_ROUTE requires a direct Decision route")
            if any(item is not None for item in banking_values) or any(
                item is not None
                for item in (
                    self.banking_precheck_proposal,
                    self.banking_precheck_result_set,
                    self.decision_post_precheck_review,
                    self.banking_option_advice,
                    self.document_preparation_request,
                    self.document_release_package,
                )
            ):
                raise ValueError("DIRECT_ROUTE cannot contain Banking or Document outputs")
            if self.governance_references:
                raise ValueError("DIRECT_ROUTE cannot contain a decline reference")
            return

        if self.decision_route_plan.route_outcome is not (
            DecisionRouteOutcome.BANKING_DISCOVERY_REQUIRED
        ):
            raise ValueError("A Banking assembly path requires a Banking route")
        if any(item is None for item in banking_values):
            raise ValueError("A Banking path requires the complete discovery snapshot")

        post_banking = self.decision_post_banking_review
        if post_banking is None:  # pragma: no cover - guarded above
            raise ValueError("Decision post-Banking review is unavailable")
        if self.assembly_path is InternalDecisionAssemblyPath.BANKING_NO_VIABLE_OPTION:
            if post_banking.outcome is not DecisionPostBankingOutcome.NO_VIABLE_OPTION:
                raise ValueError("BANKING_NO_VIABLE_OPTION has a mismatched outcome")
            self._require_no_precheck_or_document()
            return
        if self.assembly_path is InternalDecisionAssemblyPath.BANKING_NO_PRECHECK_PATH:
            if post_banking.outcome is not DecisionPostBankingOutcome.NO_PRECHECK_PATH:
                raise ValueError("BANKING_NO_PRECHECK_PATH has a mismatched outcome")
            self._require_no_precheck_or_document()
            return
        if self.assembly_path is InternalDecisionAssemblyPath.BANKING_PRECHECK_DECLINED:
            if post_banking.outcome is not (
                DecisionPostBankingOutcome.BANKING_PRECHECK_READY
            ):
                raise ValueError(
                    "A declined precheck requires a precheck-ready Banking review"
                )
            if self.banking_precheck_proposal is None:
                raise ValueError("A declined precheck requires its exact proposal")
            if len(self.governance_references) != 1:
                raise ValueError("A declined precheck requires one Governance reference")
            reference = self.governance_references[0]
            if (
                reference.subject_artifact_id
                != self.banking_precheck_proposal_artifact_id
            ):
                raise ValueError("Decline reference does not bind the proposal artifact")
            if any(
                item is not None
                for item in (
                    self.banking_precheck_result_set,
                    self.decision_post_precheck_review,
                    self.document_preparation_request,
                    self.document_release_package,
                )
            ):
                raise ValueError("A declined precheck cannot contain executed results")
            return

        if any(
            item is None
            for item in (
                self.banking_precheck_proposal,
                self.banking_precheck_result_set,
                self.decision_post_precheck_review,
            )
        ):
            raise ValueError("Post-precheck paths require proposal, result, and review")
        post_precheck = self.decision_post_precheck_review
        if post_precheck is None:  # pragma: no cover - guarded above
            raise ValueError("Decision post-precheck review is unavailable")
        if post_banking.outcome is not (
            DecisionPostBankingOutcome.BANKING_PRECHECK_READY
        ):
            raise ValueError(
                "A post-precheck package requires a precheck-ready Banking review"
            )
        if self.assembly_path is InternalDecisionAssemblyPath.BANKING_NON_ACTIONABLE:
            allowed = {
                DecisionPostPrecheckOutcome.ALL_OPTIONS_NOT_ELIGIBLE,
                DecisionPostPrecheckOutcome.NO_PROVIDER_RECOMMENDATION,
                DecisionPostPrecheckOutcome.PRECHECK_SERVICE_UNAVAILABLE,
                DecisionPostPrecheckOutcome.MIXED_NON_ACTIONABLE_RESULTS,
            }
            if post_precheck.outcome not in allowed:
                raise ValueError("BANKING_NON_ACTIONABLE has an actionable outcome")
            if (
                self.document_preparation_request is not None
                or self.document_release_package is not None
            ):
                raise ValueError("A non-actionable Banking path cannot contain documents")
            if self.governance_references:
                raise ValueError("Non-actionable results do not carry a decline reference")
            return
        if self.assembly_path is InternalDecisionAssemblyPath.CONDITIONAL_DOCUMENT_READY:
            if post_precheck.outcome is not (
                DecisionPostPrecheckOutcome.CONDITIONAL_OPTIONS_AVAILABLE
            ):
                raise ValueError("Conditional Document path has a mismatched outcome")
            if (
                self.document_preparation_request is None
                or self.document_release_package is None
            ):
                raise ValueError("Conditional Document path requires an exact package")
            if (
                self.document_release_package.preparation_request_id
                != self.document_preparation_request.request_id
                or self.document_preparation_request.option_id
                not in post_precheck.conditional_option_ids
            ):
                raise ValueError("Document package does not bind a conditional option")
            if self.governance_references:
                raise ValueError("Package readiness cannot contain a send approval")
            return
        raise ValueError("Unsupported Internal Decision assembly path")

    def _require_no_precheck_or_document(self) -> None:
        if any(
            item is not None
            for item in (
                self.banking_precheck_proposal,
                self.banking_precheck_result_set,
                self.decision_post_precheck_review,
                self.document_preparation_request,
                self.document_release_package,
            )
        ) or self.governance_references:
            raise ValueError("Precheck-free Banking path contains downstream state")


class InternalDecisionPackageComponentResult(ComponentResult):
    """Side-effect-free result containing at most one ready package draft."""

    package: InternalDecisionPackage | None = None


class InternalDecisionPackageExecutionResult(BaseModel):
    """Validated package result returned through orchestration boundaries."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: StrictStr = Field(min_length=1)
    package: InternalDecisionPackage | None = None
    generated_artifacts: tuple[ArtifactEnvelope, ...] = ()
    validation_reports: tuple[ValidationReport, ...] = ()
    validation_errors: tuple[StrictStr, ...] = ()
    missing_data_requests: tuple[MissingDataRequest, ...] = ()
    warnings: tuple[StrictStr, ...] = ()
    runtime_events: tuple[dict[str, Any], ...] = ()


def internal_decision_snapshot_hash(snapshot: BaseModel) -> str:
    """Match the deterministic facts hash used by assessment components."""
    encoded = json.dumps(
        json_safe(snapshot.model_dump(mode="json")),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
