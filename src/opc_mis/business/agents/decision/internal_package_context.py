"""Load exact validated inputs for Internal Decision Package assembly."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from opc_mis.domain.approvals import ApprovalCheckpointSet, ApprovalRequest
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
from opc_mis.domain.components import ExecutionContext
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
    DecisionPostBankingOutcome,
    DecisionPostPrecheckOutcome,
    DecisionRouteOutcome,
    ProtectedAction,
    ValidationStatus,
)
from opc_mis.domain.finance_models import FinanceAssessment, FinanceFacts
from opc_mis.domain.internal_decision_package_models import (
    InternalDecisionAssemblyPath,
    InternalDecisionAssemblyRequest,
    InternalDecisionGovernanceReference,
    InternalDecisionSourceArtifactRef,
)
from opc_mis.domain.operations_models import OperationsAssessment, OperationsFacts
from opc_mis.domain.planner_models import EvaluationCase
from opc_mis.domain.risk_models import InitialRiskAssessment
from opc_mis.ports.approval_request_repository import ApprovalRequestRepository
from opc_mis.ports.artifact_repository import ArtifactRepository

_VALID_STATUSES = {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}
_COMMON_TYPES = (
    ArtifactType.EVALUATION_CASE,
    ArtifactType.FINANCE_FACTS,
    ArtifactType.FINANCE_ASSESSMENT,
    ArtifactType.OPERATIONS_FACTS,
    ArtifactType.OPERATIONS_ASSESSMENT,
    ArtifactType.INITIAL_RISK_ASSESSMENT,
    ArtifactType.APPROVAL_CHECKPOINTS,
    ArtifactType.DECISION_ROUTE_PLAN,
)
_BANKING_TYPES = (
    ArtifactType.BANKING_DISCOVERY_REQUEST,
    ArtifactType.BANKING_OPTION_MATRIX,
    ArtifactType.BANKING_DISCOVERY_RESULT,
    ArtifactType.BANKING_PRECHECK_READINESS,
    ArtifactType.DECISION_POST_BANKING_REVIEW,
)
_POST_PRECHECK_TYPES = (
    ArtifactType.BANKING_PRECHECK_SUBMISSION_PROPOSAL,
    ArtifactType.BANKING_PRECHECK_RESULT_SET,
    ArtifactType.DECISION_POST_PRECHECK_REVIEW,
)


class InternalDecisionPackageContextError(RuntimeError):
    """Raised when supplied artifacts cannot establish exact valid lineage."""


@dataclass(frozen=True)
class InternalDecisionMissingInput:
    """One blocking assembly prerequisite translated into a MissingDataRequest."""

    requirement_code: str
    target_record: str
    field: str
    expected_type: str
    reason: str


class InternalDecisionPackageMissingInputs(RuntimeError):
    """Raised when assembly must wait for explicit upstream inputs."""

    def __init__(self, missing: tuple[InternalDecisionMissingInput, ...]) -> None:
        self.missing = missing
        super().__init__("Internal Decision Package is waiting for required inputs.")


@dataclass(frozen=True)
class InternalDecisionPackageContext:
    """Parsed immutable snapshots and their exact source envelopes."""

    request: InternalDecisionAssemblyRequest
    source_artifacts: tuple[ArtifactEnvelope, ...]
    source_artifact_refs: tuple[InternalDecisionSourceArtifactRef, ...]
    evaluation_case_artifact: ArtifactEnvelope
    finance_facts_artifact: ArtifactEnvelope
    finance_assessment_artifact: ArtifactEnvelope
    operations_facts_artifact: ArtifactEnvelope
    operations_assessment_artifact: ArtifactEnvelope
    risk_assessment_artifact: ArtifactEnvelope
    approval_checkpoint_artifacts: tuple[ArtifactEnvelope, ...]
    decision_route_plan_artifact: ArtifactEnvelope
    evaluation_case: EvaluationCase
    finance_facts: FinanceFacts
    finance_assessment: FinanceAssessment
    operations_facts: OperationsFacts
    operations_assessment: OperationsAssessment
    risk_assessment: InitialRiskAssessment
    approval_checkpoints: tuple[ApprovalCheckpointSet, ...]
    decision_route_plan: DecisionRoutePlan
    banking_discovery_request_artifact: ArtifactEnvelope | None = None
    banking_option_matrix_artifact: ArtifactEnvelope | None = None
    banking_discovery_result_artifact: ArtifactEnvelope | None = None
    banking_option_advice_artifact: ArtifactEnvelope | None = None
    banking_precheck_readiness_artifact: ArtifactEnvelope | None = None
    decision_post_banking_review_artifact: ArtifactEnvelope | None = None
    banking_precheck_proposal_artifact: ArtifactEnvelope | None = None
    banking_precheck_result_set_artifact: ArtifactEnvelope | None = None
    decision_post_precheck_review_artifact: ArtifactEnvelope | None = None
    document_preparation_request_artifact: ArtifactEnvelope | None = None
    document_release_package_artifact: ArtifactEnvelope | None = None
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
    governance_references: tuple[InternalDecisionGovernanceReference, ...] = ()

    @property
    def source_artifact_ids(self) -> tuple[str, ...]:
        """Preserve the Workflow-provided input order exactly."""
        return tuple(item.artifact_id for item in self.source_artifacts)


ModelT = TypeVar("ModelT", bound=BaseModel)


class InternalDecisionPackageContextLoader:
    """Resolve authoritative artifacts without persistence or source-data reads."""

    def __init__(
        self,
        *,
        artifacts: ArtifactRepository,
        approvals: ApprovalRequestRepository,
    ) -> None:
        self._artifacts = artifacts
        self._approvals = approvals

    async def load(
        self,
        context: ExecutionContext,
        request: InternalDecisionAssemblyRequest,
    ) -> InternalDecisionPackageContext:
        if context.evaluation_case_id is None:
            raise InternalDecisionPackageContextError(
                "Internal Decision Package requires evaluation_case_id."
            )
        if len(set(context.input_artifact_ids)) != len(context.input_artifact_ids):
            raise InternalDecisionPackageContextError(
                "Internal Decision Package received duplicate artifact IDs."
            )
        loaded = await self._load_exact_artifacts(context)
        grouped = self._group(loaded)
        required = self._required_types(request.assembly_path)
        allowed = set(required)
        if request.assembly_path is not InternalDecisionAssemblyPath.DIRECT_ROUTE:
            allowed.add(ArtifactType.BANKING_OPTION_ADVICE)
        unexpected = tuple(
            item.artifact_type for item in loaded if item.artifact_type not in allowed
        )
        if unexpected:
            raise InternalDecisionPackageContextError(
                "Internal Decision Package received artifact types outside the selected "
                "assembly path: " + ", ".join(item.value for item in unexpected)
            )
        duplicates = tuple(
            artifact_type
            for artifact_type, matches in grouped.items()
            if len(matches) > 1 and artifact_type is not ArtifactType.APPROVAL_CHECKPOINTS
        )
        if duplicates:
            raise InternalDecisionPackageContextError(
                "Internal Decision Package received duplicate artifact types: "
                + ", ".join(item.value for item in duplicates)
            )
        route_matches = grouped.get(ArtifactType.DECISION_ROUTE_PLAN, ())
        if len(route_matches) == 1:
            try:
                route_for_path = self._parse(route_matches[0], DecisionRoutePlan)
            except ValidationError as exc:
                raise InternalDecisionPackageContextError(
                    f"Invalid Decision Route Plan input schema: {exc}"
                ) from exc
            direct_requested = (
                request.assembly_path is InternalDecisionAssemblyPath.DIRECT_ROUTE
            )
            direct_actual = route_for_path.route_outcome is (
                DecisionRouteOutcome.DIRECT_INTERNAL_DECISION
            )
            if direct_requested != direct_actual:
                raise InternalDecisionPackageContextError(
                    "Internal Decision assembly path contradicts the available "
                    "Decision Route Plan."
                )
        self._validate_available_branch_outcomes(request=request, grouped=grouped)
        missing = tuple(
            InternalDecisionMissingInput(
                requirement_code=f"{artifact_type.value}_REQUIRED",
                target_record=context.evaluation_case_id,
                field="input_artifact_ids",
                expected_type=artifact_type.value,
                reason=(
                    "Internal Decision Package assembly requires one validated "
                    f"{artifact_type.value} artifact for this path."
                ),
            )
            for artifact_type in required
            if not grouped.get(artifact_type)
        )
        if missing:
            raise InternalDecisionPackageMissingInputs(missing)

        case_artifact = self._one(grouped, ArtifactType.EVALUATION_CASE)
        finance_facts_artifact = self._one(grouped, ArtifactType.FINANCE_FACTS)
        finance_assessment_artifact = self._one(
            grouped, ArtifactType.FINANCE_ASSESSMENT
        )
        operations_facts_artifact = self._one(grouped, ArtifactType.OPERATIONS_FACTS)
        operations_assessment_artifact = self._one(
            grouped, ArtifactType.OPERATIONS_ASSESSMENT
        )
        risk_artifact = self._one(grouped, ArtifactType.INITIAL_RISK_ASSESSMENT)
        checkpoint_artifacts = grouped[ArtifactType.APPROVAL_CHECKPOINTS]
        route_artifact = self._one(grouped, ArtifactType.DECISION_ROUTE_PLAN)

        try:
            evaluation_case = self._parse(case_artifact, EvaluationCase)
            finance_facts = self._parse(finance_facts_artifact, FinanceFacts)
            finance_assessment = self._parse(
                finance_assessment_artifact, FinanceAssessment
            )
            operations_facts = self._parse(operations_facts_artifact, OperationsFacts)
            operations_assessment = self._parse(
                operations_assessment_artifact, OperationsAssessment
            )
            risk_assessment = self._parse(risk_artifact, InitialRiskAssessment)
            approval_checkpoints = tuple(
                self._parse(item, ApprovalCheckpointSet)
                for item in checkpoint_artifacts
            )
            route_plan = self._parse(route_artifact, DecisionRoutePlan)
            parsed = self._parse_optional(grouped)
        except ValidationError as exc:
            raise InternalDecisionPackageContextError(
                f"Invalid Internal Decision Package input schema: {exc}"
            ) from exc

        self._validate_identity(
            context=context,
            contract_id=evaluation_case.contract_id,
            models=(
                evaluation_case,
                finance_facts,
                finance_assessment,
                operations_facts,
                operations_assessment,
                risk_assessment,
                *approval_checkpoints,
                route_plan,
                *(item for item in parsed.values() if item is not None),
            ),
        )
        self._validate_common_lineage(
            finance_facts_artifact=finance_facts_artifact,
            finance_assessment_artifact=finance_assessment_artifact,
            operations_facts_artifact=operations_facts_artifact,
            operations_assessment_artifact=operations_assessment_artifact,
            risk_assessment=risk_assessment,
            risk_artifact=risk_artifact,
            route_plan=route_plan,
            route_artifact=route_artifact,
            evaluation_case_artifact=case_artifact,
            checkpoint_artifacts=checkpoint_artifacts,
        )
        self._validate_path_lineage(grouped=grouped, parsed=parsed)
        governance_references = await self._governance_references(
            context=context,
            request=request,
            grouped=grouped,
        )
        refs = tuple(self._source_ref(item) for item in loaded)
        return InternalDecisionPackageContext(
            request=request,
            source_artifacts=loaded,
            source_artifact_refs=refs,
            evaluation_case_artifact=case_artifact,
            finance_facts_artifact=finance_facts_artifact,
            finance_assessment_artifact=finance_assessment_artifact,
            operations_facts_artifact=operations_facts_artifact,
            operations_assessment_artifact=operations_assessment_artifact,
            risk_assessment_artifact=risk_artifact,
            approval_checkpoint_artifacts=checkpoint_artifacts,
            decision_route_plan_artifact=route_artifact,
            evaluation_case=evaluation_case,
            finance_facts=finance_facts,
            finance_assessment=finance_assessment,
            operations_facts=operations_facts,
            operations_assessment=operations_assessment,
            risk_assessment=risk_assessment,
            approval_checkpoints=approval_checkpoints,
            decision_route_plan=route_plan,
            governance_references=governance_references,
            **self._context_kwargs(grouped, parsed),
        )

    async def _load_exact_artifacts(
        self, context: ExecutionContext
    ) -> tuple[ArtifactEnvelope, ...]:
        loaded: list[ArtifactEnvelope] = []
        for artifact_id in context.input_artifact_ids:
            artifact = await self._artifacts.get(artifact_id)
            if artifact is None:
                raise InternalDecisionPackageContextError(
                    f"Internal Decision Package received unknown artifact: {artifact_id}."
                )
            if artifact.validation_status not in _VALID_STATUSES:
                raise InternalDecisionPackageContextError(
                    "Internal Decision Package received an unvalidated artifact: "
                    f"{artifact_id}."
                )
            if artifact.evaluation_case_id != context.evaluation_case_id:
                raise InternalDecisionPackageContextError(
                    "An Internal Decision Package source belongs to another case."
                )
            loaded.append(artifact)
        return tuple(loaded)

    @staticmethod
    def _required_types(
        path: InternalDecisionAssemblyPath,
    ) -> tuple[ArtifactType, ...]:
        required = list(_COMMON_TYPES)
        if path is InternalDecisionAssemblyPath.DIRECT_ROUTE:
            return tuple(required)
        required.extend(_BANKING_TYPES)
        if path is InternalDecisionAssemblyPath.BANKING_PRECHECK_DECLINED:
            required.append(ArtifactType.BANKING_PRECHECK_SUBMISSION_PROPOSAL)
        elif path in {
            InternalDecisionAssemblyPath.BANKING_NON_ACTIONABLE,
            InternalDecisionAssemblyPath.CONDITIONAL_DOCUMENT_READY,
        }:
            required.extend(_POST_PRECHECK_TYPES)
        if path is InternalDecisionAssemblyPath.CONDITIONAL_DOCUMENT_READY:
            required.extend(
                (
                    ArtifactType.DOCUMENT_PREPARATION_REQUEST,
                    ArtifactType.DOCUMENT_RELEASE_PACKAGE,
                )
            )
        return tuple(required)

    @staticmethod
    def _group(
        artifacts: tuple[ArtifactEnvelope, ...],
    ) -> dict[ArtifactType, tuple[ArtifactEnvelope, ...]]:
        return {
            artifact_type: tuple(
                item for item in artifacts if item.artifact_type is artifact_type
            )
            for artifact_type in ArtifactType
        }

    def _validate_available_branch_outcomes(
        self,
        *,
        request: InternalDecisionAssemblyRequest,
        grouped: dict[ArtifactType, tuple[ArtifactEnvelope, ...]],
    ) -> None:
        """Reject a contradictory path before diagnosing downstream inputs as missing."""
        post_banking_matches = grouped.get(
            ArtifactType.DECISION_POST_BANKING_REVIEW, ()
        )
        if len(post_banking_matches) == 1:
            try:
                post_banking = self._parse(
                    post_banking_matches[0], DecisionPostBankingReview
                )
            except ValidationError as exc:
                raise InternalDecisionPackageContextError(
                    f"Invalid Decision post-Banking review input schema: {exc}"
                ) from exc
            expected_post_banking = {
                InternalDecisionAssemblyPath.BANKING_NO_VIABLE_OPTION: (
                    DecisionPostBankingOutcome.NO_VIABLE_OPTION
                ),
                InternalDecisionAssemblyPath.BANKING_NO_PRECHECK_PATH: (
                    DecisionPostBankingOutcome.NO_PRECHECK_PATH
                ),
                InternalDecisionAssemblyPath.BANKING_PRECHECK_DECLINED: (
                    DecisionPostBankingOutcome.BANKING_PRECHECK_READY
                ),
                InternalDecisionAssemblyPath.BANKING_NON_ACTIONABLE: (
                    DecisionPostBankingOutcome.BANKING_PRECHECK_READY
                ),
                InternalDecisionAssemblyPath.CONDITIONAL_DOCUMENT_READY: (
                    DecisionPostBankingOutcome.BANKING_PRECHECK_READY
                ),
            }.get(request.assembly_path)
            if (
                expected_post_banking is not None
                and post_banking.outcome is not expected_post_banking
            ):
                raise InternalDecisionPackageContextError(
                    "Internal Decision assembly path contradicts the available "
                    "Decision post-Banking review."
                )

        post_precheck_matches = grouped.get(
            ArtifactType.DECISION_POST_PRECHECK_REVIEW, ()
        )
        if len(post_precheck_matches) != 1:
            return
        try:
            post_precheck = self._parse(
                post_precheck_matches[0], DecisionPostPrecheckReview
            )
        except ValidationError as exc:
            raise InternalDecisionPackageContextError(
                f"Invalid Decision post-precheck review input schema: {exc}"
            ) from exc
        non_actionable_outcomes = {
            DecisionPostPrecheckOutcome.ALL_OPTIONS_NOT_ELIGIBLE,
            DecisionPostPrecheckOutcome.NO_PROVIDER_RECOMMENDATION,
            DecisionPostPrecheckOutcome.PRECHECK_SERVICE_UNAVAILABLE,
            DecisionPostPrecheckOutcome.MIXED_NON_ACTIONABLE_RESULTS,
        }
        path_matches = (
            request.assembly_path
            is InternalDecisionAssemblyPath.BANKING_NON_ACTIONABLE
            and post_precheck.outcome in non_actionable_outcomes
        ) or (
            request.assembly_path
            is InternalDecisionAssemblyPath.CONDITIONAL_DOCUMENT_READY
            and post_precheck.outcome
            is DecisionPostPrecheckOutcome.CONDITIONAL_OPTIONS_AVAILABLE
        )
        if request.assembly_path in {
            InternalDecisionAssemblyPath.BANKING_NON_ACTIONABLE,
            InternalDecisionAssemblyPath.CONDITIONAL_DOCUMENT_READY,
        } and not path_matches:
            raise InternalDecisionPackageContextError(
                "Internal Decision assembly path contradicts the available "
                "Decision post-precheck review."
            )

    @staticmethod
    def _one(
        grouped: dict[ArtifactType, tuple[ArtifactEnvelope, ...]],
        artifact_type: ArtifactType,
    ) -> ArtifactEnvelope:
        matches = grouped.get(artifact_type, ())
        if len(matches) != 1:
            raise InternalDecisionPackageContextError(
                f"Expected exactly one {artifact_type.value} artifact."
            )
        return matches[0]

    @staticmethod
    def _parse(envelope: ArtifactEnvelope, model: type[ModelT]) -> ModelT:
        return model.model_validate(envelope.payload)

    def _parse_optional(
        self, grouped: dict[ArtifactType, tuple[ArtifactEnvelope, ...]]
    ) -> dict[ArtifactType, BaseModel | None]:
        model_types: tuple[tuple[ArtifactType, type[BaseModel]], ...] = (
            (ArtifactType.BANKING_DISCOVERY_REQUEST, BankingDiscoveryRequest),
            (ArtifactType.BANKING_OPTION_MATRIX, BankingOptionMatrix),
            (ArtifactType.BANKING_DISCOVERY_RESULT, BankingDiscoveryResult),
            (ArtifactType.BANKING_OPTION_ADVICE, BankingOptionAdvice),
            (ArtifactType.BANKING_PRECHECK_READINESS, BankingPrecheckReadiness),
            (ArtifactType.DECISION_POST_BANKING_REVIEW, DecisionPostBankingReview),
            (
                ArtifactType.BANKING_PRECHECK_SUBMISSION_PROPOSAL,
                BankingPrecheckSubmissionProposal,
            ),
            (ArtifactType.BANKING_PRECHECK_RESULT_SET, BankingPrecheckResultSet),
            (
                ArtifactType.DECISION_POST_PRECHECK_REVIEW,
                DecisionPostPrecheckReview,
            ),
            (
                ArtifactType.DOCUMENT_PREPARATION_REQUEST,
                DocumentPreparationRequest,
            ),
            (ArtifactType.DOCUMENT_RELEASE_PACKAGE, DocumentReleasePackage),
        )
        result: dict[ArtifactType, BaseModel | None] = {}
        for artifact_type, model_type in model_types:
            matches = grouped.get(artifact_type, ())
            result[artifact_type] = (
                self._parse(matches[0], model_type) if len(matches) == 1 else None
            )
        return result

    @staticmethod
    def _validate_identity(
        *,
        context: ExecutionContext,
        contract_id: str,
        models: tuple[BaseModel, ...],
    ) -> None:
        expected = {
            "evaluation_case_id": context.evaluation_case_id,
            "dataset_id": context.dataset_id,
            "contract_id": contract_id,
        }
        for model in models:
            mismatched = tuple(
                field_name
                for field_name, expected_value in expected.items()
                if field_name in type(model).model_fields
                and getattr(model, field_name) != expected_value
            )
            if mismatched:
                raise InternalDecisionPackageContextError(
                    f"{model.__class__.__name__} identity differs from the execution "
                    f"case: {', '.join(mismatched)}."
                )

    @staticmethod
    def _validate_common_lineage(
        *,
        finance_facts_artifact: ArtifactEnvelope,
        finance_assessment_artifact: ArtifactEnvelope,
        operations_facts_artifact: ArtifactEnvelope,
        operations_assessment_artifact: ArtifactEnvelope,
        risk_assessment: InitialRiskAssessment,
        risk_artifact: ArtifactEnvelope,
        route_plan: DecisionRoutePlan,
        route_artifact: ArtifactEnvelope,
        evaluation_case_artifact: ArtifactEnvelope,
        checkpoint_artifacts: tuple[ArtifactEnvelope, ...],
    ) -> None:
        expected_finance_inputs = (
            *finance_facts_artifact.input_artifact_ids,
            finance_facts_artifact.artifact_id,
        )
        if finance_assessment_artifact.input_artifact_ids != expected_finance_inputs:
            raise InternalDecisionPackageContextError(
                "Finance Assessment envelope does not bind the selected Finance Facts."
            )
        expected_operations_inputs = (
            *operations_facts_artifact.input_artifact_ids,
            operations_facts_artifact.artifact_id,
        )
        if (
            operations_assessment_artifact.input_artifact_ids
            != expected_operations_inputs
        ):
            raise InternalDecisionPackageContextError(
                "Operations Assessment envelope does not bind the selected "
                "Operations Facts."
            )
        if (
            risk_assessment.finance_facts_artifact_id
            != finance_facts_artifact.artifact_id
            or risk_assessment.operations_facts_artifact_id
            != operations_facts_artifact.artifact_id
        ):
            raise InternalDecisionPackageContextError(
                "Initial Risk Assessment references different fact artifacts."
            )
        risk_fact_ids = {
            finance_facts_artifact.artifact_id,
            operations_facts_artifact.artifact_id,
        }
        if not risk_fact_ids.issubset(set(risk_artifact.input_artifact_ids)):
            raise InternalDecisionPackageContextError(
                "Initial Risk Assessment envelope omits its selected fact artifacts."
            )
        # Route Planning has a fixed semantic lineage: case, Finance facts,
        # Operations facts, Risk assessment, then one checkpoint registry.
        if len(route_plan.source_artifact_ids) != 5:
            raise InternalDecisionPackageContextError(
                "Decision Route Plan has an unexpected source lineage shape."
            )
        expected_prefix = (
            evaluation_case_artifact.artifact_id,
            finance_facts_artifact.artifact_id,
            operations_facts_artifact.artifact_id,
            risk_artifact.artifact_id,
        )
        if route_plan.source_artifact_ids[:4] != expected_prefix:
            raise InternalDecisionPackageContextError(
                "Decision Route Plan source order is invalid."
            )
        if route_artifact.input_artifact_ids != route_plan.source_artifact_ids:
            raise InternalDecisionPackageContextError(
                "Decision Route Plan payload and envelope lineage differ."
            )
        if route_plan.source_artifact_ids[4] not in {
            item.artifact_id for item in checkpoint_artifacts
        }:
            raise InternalDecisionPackageContextError(
                "Decision Route Plan references a different checkpoint registry."
            )

    def _validate_path_lineage(
        self,
        *,
        grouped: dict[ArtifactType, tuple[ArtifactEnvelope, ...]],
        parsed: dict[ArtifactType, BaseModel | None],
    ) -> None:
        request = parsed[ArtifactType.BANKING_DISCOVERY_REQUEST]
        if request is None:
            return
        assert isinstance(request, BankingDiscoveryRequest)
        route_artifact = self._one(grouped, ArtifactType.DECISION_ROUTE_PLAN)
        request_artifact = self._one(
            grouped, ArtifactType.BANKING_DISCOVERY_REQUEST
        )
        route = self._parse(route_artifact, DecisionRoutePlan)
        if (
            request.source_route_artifact_id != route_artifact.artifact_id
            or request.source_route_plan_id != route.route_plan_id
            or request_artifact.input_artifact_ids != (route_artifact.artifact_id,)
        ):
            raise InternalDecisionPackageContextError(
                "Banking request does not bind the exact Decision Route Plan."
            )
        matrix = parsed[ArtifactType.BANKING_OPTION_MATRIX]
        result = parsed[ArtifactType.BANKING_DISCOVERY_RESULT]
        readiness = parsed[ArtifactType.BANKING_PRECHECK_READINESS]
        post_banking = parsed[ArtifactType.DECISION_POST_BANKING_REVIEW]
        assert isinstance(matrix, BankingOptionMatrix)
        assert isinstance(result, BankingDiscoveryResult)
        assert isinstance(readiness, BankingPrecheckReadiness)
        assert isinstance(post_banking, DecisionPostBankingReview)
        matrix_artifact = self._one(grouped, ArtifactType.BANKING_OPTION_MATRIX)
        result_artifact = self._one(grouped, ArtifactType.BANKING_DISCOVERY_RESULT)
        readiness_artifact = self._one(
            grouped, ArtifactType.BANKING_PRECHECK_READINESS
        )
        post_banking_artifact = self._one(
            grouped, ArtifactType.DECISION_POST_BANKING_REVIEW
        )
        if matrix.request_id != request.request_id or (
            request_artifact.artifact_id not in matrix.source_artifact_ids
        ) or matrix.source_artifact_ids != matrix_artifact.input_artifact_ids:
            raise InternalDecisionPackageContextError(
                "Banking matrix does not bind the exact discovery request."
            )
        if (
            request_artifact.artifact_id not in result_artifact.input_artifact_ids
            or not result_artifact.input_artifact_ids
            or result_artifact.input_artifact_ids[-1] != matrix_artifact.artifact_id
        ):
            raise InternalDecisionPackageContextError(
                "Banking discovery result envelope does not bind the exact matrix."
            )
        if (
            result.request_id != request.request_id
            or result.matrix_id != matrix.matrix_id
            or readiness.matrix_id != matrix.matrix_id
            or matrix_artifact.artifact_id not in readiness.source_artifact_ids
            or readiness.source_artifact_ids
            != readiness_artifact.input_artifact_ids
        ):
            raise InternalDecisionPackageContextError(
                "Banking discovery outputs do not bind the exact option matrix."
            )
        if (
            post_banking.matrix_id != matrix.matrix_id
            or post_banking.banking_request_id != request.request_id
            or post_banking.readiness_id != readiness.readiness_id
            or post_banking.source_artifact_ids
            != (matrix_artifact.artifact_id, readiness_artifact.artifact_id)
            or post_banking.source_artifact_ids
            != post_banking_artifact.input_artifact_ids
        ):
            raise InternalDecisionPackageContextError(
                "Decision post-Banking review has different Banking lineage."
            )
        advice = parsed[ArtifactType.BANKING_OPTION_ADVICE]
        if advice is not None:
            advice_artifact = self._one(grouped, ArtifactType.BANKING_OPTION_ADVICE)
            if (
                getattr(advice, "matrix_id", None) != matrix.matrix_id
                or advice_artifact.input_artifact_ids
                != (matrix_artifact.artifact_id,)
            ):
                raise InternalDecisionPackageContextError(
                    "Banking advice references a different matrix."
                )
        proposal = parsed[ArtifactType.BANKING_PRECHECK_SUBMISSION_PROPOSAL]
        if proposal is None:
            return
        assert isinstance(proposal, BankingPrecheckSubmissionProposal)
        proposal_artifact = self._one(
            grouped, ArtifactType.BANKING_PRECHECK_SUBMISSION_PROPOSAL
        )
        if (
            proposal.banking_request_id != request.request_id
            or proposal.matrix_id != matrix.matrix_id
            or proposal.readiness_id != readiness.readiness_id
            or proposal.review_id != post_banking.review_id
            or post_banking_artifact.artifact_id not in proposal.source_artifact_ids
            or proposal.source_artifact_ids != proposal_artifact.input_artifact_ids
        ):
            raise InternalDecisionPackageContextError(
                "Banking precheck proposal has different readiness lineage."
            )
        result_set = parsed[ArtifactType.BANKING_PRECHECK_RESULT_SET]
        post_precheck = parsed[ArtifactType.DECISION_POST_PRECHECK_REVIEW]
        if result_set is None and post_precheck is None:
            return
        assert isinstance(result_set, BankingPrecheckResultSet)
        assert isinstance(post_precheck, DecisionPostPrecheckReview)
        result_artifact = self._one(grouped, ArtifactType.BANKING_PRECHECK_RESULT_SET)
        post_precheck_artifact = self._one(
            grouped, ArtifactType.DECISION_POST_PRECHECK_REVIEW
        )
        if (
            result_set.proposal_artifact_id != proposal_artifact.artifact_id
            or result_set.proposal_id != proposal.proposal_id
            or result_set.source_artifact_ids != result_artifact.input_artifact_ids
            or proposal_artifact.artifact_id not in result_set.source_artifact_ids
            or post_precheck.result_set_artifact_id != result_artifact.artifact_id
            or post_precheck.result_set_id != result_set.result_set_id
            or post_precheck.proposal_artifact_id != proposal_artifact.artifact_id
            or post_precheck.proposal_id != proposal.proposal_id
            or post_precheck.source_artifact_ids
            != (result_artifact.artifact_id, proposal_artifact.artifact_id)
            or post_precheck.source_artifact_ids
            != post_precheck_artifact.input_artifact_ids
        ):
            raise InternalDecisionPackageContextError(
                "Post-precheck outputs have different proposal or result lineage."
            )
        document_request = parsed[ArtifactType.DOCUMENT_PREPARATION_REQUEST]
        release = parsed[ArtifactType.DOCUMENT_RELEASE_PACKAGE]
        if document_request is None and release is None:
            return
        assert isinstance(document_request, DocumentPreparationRequest)
        assert isinstance(release, DocumentReleasePackage)
        document_request_artifact = self._one(
            grouped, ArtifactType.DOCUMENT_PREPARATION_REQUEST
        )
        release_artifact = self._one(grouped, ArtifactType.DOCUMENT_RELEASE_PACKAGE)
        if (
            document_request.option_id not in post_precheck.conditional_option_ids
            or document_request.source_artifact_ids
            != (post_precheck_artifact.artifact_id, result_artifact.artifact_id)
            or document_request.source_artifact_ids
            != document_request_artifact.input_artifact_ids
            or release.preparation_request_id != document_request.request_id
            or len(release.source_artifact_ids) < 2
            or release.source_artifact_ids[1] != document_request_artifact.artifact_id
            or release.source_artifact_ids != release_artifact.input_artifact_ids
        ):
            raise InternalDecisionPackageContextError(
                "Document release package does not bind the conditional review request."
            )

    async def _governance_references(
        self,
        *,
        context: ExecutionContext,
        request: InternalDecisionAssemblyRequest,
        grouped: dict[ArtifactType, tuple[ArtifactEnvelope, ...]],
    ) -> tuple[InternalDecisionGovernanceReference, ...]:
        if request.assembly_path is not (
            InternalDecisionAssemblyPath.BANKING_PRECHECK_DECLINED
        ):
            return ()
        approval_id = request.approval_request_id
        if approval_id is None:  # pragma: no cover - request model guards this
            raise InternalDecisionPackageContextError(
                "Declined precheck path has no approval request ID."
            )
        approval = await self._approvals.get(approval_id)
        if approval is None:
            raise InternalDecisionPackageMissingInputs(
                (
                    InternalDecisionMissingInput(
                        requirement_code="REJECTED_PRECHECK_APPROVAL_REQUIRED",
                        target_record=context.evaluation_case_id or "UNKNOWN_CASE",
                        field="approval_request_id",
                        expected_type="ApprovalRequest(status=REJECTED)",
                        reason=(
                            "The declined precheck path requires its exact persisted "
                            "Founder decision."
                        ),
                    ),
                )
            )
        proposal_artifact = self._one(
            grouped, ArtifactType.BANKING_PRECHECK_SUBMISSION_PROPOSAL
        )
        self._validate_rejected_approval(context, approval, proposal_artifact, grouped)
        decision = approval.decision_record
        if decision is None:  # pragma: no cover - ApprovalRequest guards this
            raise InternalDecisionPackageContextError(
                "Rejected approval has no decision record."
            )
        return (
            InternalDecisionGovernanceReference(
                approval_request_id=approval.request_id,
                workflow_run_id=approval.workflow_run_id,
                status=approval.status,
                action=approval.command.action_type,
                subject_artifact_id=approval.subject_artifact_id,
                subject_artifact_version=approval.subject_artifact_version,
                subject_input_hash=approval.subject_input_hash,
                checkpoint_ids=approval.checkpoint_ids,
                policy_artifact_id=approval.policy_artifact_id or "",
                policy_artifact_version=approval.policy_artifact_version or 0,
                policy_input_hash=approval.policy_input_hash or "",
                policy_coverage_ids=approval.policy_coverage_ids,
                decision=decision.decision,
                decided_by=decision.decided_by,
                decision_reason=decision.reason,
                decided_at=decision.decided_at,
            ),
        )

    @staticmethod
    def _validate_rejected_approval(
        context: ExecutionContext,
        approval: ApprovalRequest,
        proposal_artifact: ArtifactEnvelope,
        grouped: dict[ArtifactType, tuple[ArtifactEnvelope, ...]],
    ) -> None:
        decision = approval.decision_record
        if (
            approval.workflow_run_id != context.workflow_run_id
            or approval.evaluation_case_id != context.evaluation_case_id
            or approval.dataset_id != context.dataset_id
            or approval.status is not ApprovalRequestStatus.REJECTED
            or approval.command.action_type
            is not ProtectedAction.SUBMIT_BANKING_PRECHECK
            or approval.command.evaluation_case_id != context.evaluation_case_id
            or approval.command.payload_artifact_id != proposal_artifact.artifact_id
            or approval.subject_artifact_id != proposal_artifact.artifact_id
            or approval.subject_artifact_version != proposal_artifact.version
            or approval.subject_input_hash != proposal_artifact.input_hash
            or decision is None
            or decision.decision is not ApprovalDecision.REJECT
        ):
            raise InternalDecisionPackageContextError(
                "Approval request is not the exact rejected precheck decision."
            )
        policies = grouped.get(ArtifactType.APPROVAL_CHECKPOINTS, ())
        matching_policy = tuple(
            item
            for item in policies
            if item.artifact_id == approval.policy_artifact_id
            and item.version == approval.policy_artifact_version
            and item.input_hash == approval.policy_input_hash
        )
        if len(matching_policy) != 1:
            raise InternalDecisionPackageContextError(
                "Rejected precheck decision is missing its exact policy artifact."
            )
        try:
            policy = ApprovalCheckpointSet.model_validate(
                matching_policy[0].payload
            )
        except ValidationError as exc:  # pragma: no cover - validated envelope guard
            raise InternalDecisionPackageContextError(
                f"Rejected precheck policy artifact is invalid: {exc}"
            ) from exc
        checkpoints_by_id = {
            item.checkpoint_id: item for item in policy.checkpoints
        }
        coverages_by_id = {
            item.coverage_id: item for item in policy.policy_coverages
        }
        if not set(approval.checkpoint_ids).issubset(checkpoints_by_id) or not set(
            approval.policy_coverage_ids
        ).issubset(coverages_by_id):
            raise InternalDecisionPackageContextError(
                "Rejected precheck decision has dangling policy references."
            )
        if any(
            checkpoints_by_id[item].protected_action
            is not ProtectedAction.SUBMIT_BANKING_PRECHECK
            for item in approval.checkpoint_ids
        ) or any(
            coverages_by_id[item].protected_action
            is not ProtectedAction.SUBMIT_BANKING_PRECHECK
            or coverages_by_id[item].subject_artifact_id
            != proposal_artifact.artifact_id
            for item in approval.policy_coverage_ids
        ):
            raise InternalDecisionPackageContextError(
                "Rejected precheck policy references a different protected action."
            )

    @staticmethod
    def _source_ref(envelope: ArtifactEnvelope) -> InternalDecisionSourceArtifactRef:
        return InternalDecisionSourceArtifactRef(
            artifact_id=envelope.artifact_id,
            artifact_type=envelope.artifact_type,
            version=envelope.version,
            input_hash=envelope.input_hash,
            validation_status=envelope.validation_status,
            evidence_ids=tuple(
                dict.fromkeys(item.evidence_id for item in envelope.evidence_refs)
            ),
        )

    @staticmethod
    def _context_kwargs(
        grouped: dict[ArtifactType, tuple[ArtifactEnvelope, ...]],
        parsed: dict[ArtifactType, BaseModel | None],
    ) -> dict[str, object]:
        bindings = (
            (
                "banking_discovery_request",
                "banking_discovery_request_artifact",
                ArtifactType.BANKING_DISCOVERY_REQUEST,
            ),
            (
                "banking_option_matrix",
                "banking_option_matrix_artifact",
                ArtifactType.BANKING_OPTION_MATRIX,
            ),
            (
                "banking_discovery_result",
                "banking_discovery_result_artifact",
                ArtifactType.BANKING_DISCOVERY_RESULT,
            ),
            (
                "banking_option_advice",
                "banking_option_advice_artifact",
                ArtifactType.BANKING_OPTION_ADVICE,
            ),
            (
                "banking_precheck_readiness",
                "banking_precheck_readiness_artifact",
                ArtifactType.BANKING_PRECHECK_READINESS,
            ),
            (
                "decision_post_banking_review",
                "decision_post_banking_review_artifact",
                ArtifactType.DECISION_POST_BANKING_REVIEW,
            ),
            (
                "banking_precheck_proposal",
                "banking_precheck_proposal_artifact",
                ArtifactType.BANKING_PRECHECK_SUBMISSION_PROPOSAL,
            ),
            (
                "banking_precheck_result_set",
                "banking_precheck_result_set_artifact",
                ArtifactType.BANKING_PRECHECK_RESULT_SET,
            ),
            (
                "decision_post_precheck_review",
                "decision_post_precheck_review_artifact",
                ArtifactType.DECISION_POST_PRECHECK_REVIEW,
            ),
            (
                "document_preparation_request",
                "document_preparation_request_artifact",
                ArtifactType.DOCUMENT_PREPARATION_REQUEST,
            ),
            (
                "document_release_package",
                "document_release_package_artifact",
                ArtifactType.DOCUMENT_RELEASE_PACKAGE,
            ),
        )
        result: dict[str, object] = {}
        for model_name, artifact_name, artifact_type in bindings:
            result[model_name] = parsed[artifact_type]
            matches = grouped.get(artifact_type, ())
            result[artifact_name] = matches[0] if len(matches) == 1 else None
        return result
