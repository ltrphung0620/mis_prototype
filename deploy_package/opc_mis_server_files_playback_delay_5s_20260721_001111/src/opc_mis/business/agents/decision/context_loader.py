"""Load Decision Initial Route inputs from explicit validated artifacts."""

from dataclasses import dataclass

from pydantic import ValidationError

from opc_mis.domain.approvals import ApprovalCheckpointSet
from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import ArtifactType, ValidationStatus
from opc_mis.domain.finance_models import FinanceFacts
from opc_mis.domain.operations_models import OperationsFacts
from opc_mis.domain.planner_models import EvaluationCase
from opc_mis.domain.risk_models import InitialRiskAssessment
from opc_mis.ports.artifact_repository import ArtifactRepository

_REQUIRED_TYPES = (
    ArtifactType.EVALUATION_CASE,
    ArtifactType.FINANCE_FACTS,
    ArtifactType.OPERATIONS_FACTS,
    ArtifactType.INITIAL_RISK_ASSESSMENT,
    ArtifactType.APPROVAL_CHECKPOINTS,
)


class DecisionRouteContextError(RuntimeError):
    """Raised when explicit Decision inputs are invalid or inconsistent."""


class DecisionRouteMissingArtifacts(RuntimeError):
    """Raised when Initial Route is invoked before required artifacts exist."""

    def __init__(self, missing: tuple[ArtifactType, ...]) -> None:
        self.missing = missing
        super().__init__(
            "Decision Initial Route is waiting for: "
            + ", ".join(item.value for item in missing)
        )


@dataclass(frozen=True)
class DecisionInitialRouteContext:
    """Validated authoritative inputs used by deterministic route policy."""

    evaluation_case_artifact: ArtifactEnvelope
    finance_facts_artifact: ArtifactEnvelope
    operations_facts_artifact: ArtifactEnvelope
    risk_assessment_artifact: ArtifactEnvelope
    approval_checkpoints_artifact: ArtifactEnvelope
    evaluation_case: EvaluationCase
    finance_facts: FinanceFacts
    operations_facts: OperationsFacts
    risk_assessment: InitialRiskAssessment
    approval_checkpoints: ApprovalCheckpointSet

    @property
    def source_artifact_ids(self) -> tuple[str, ...]:
        return (
            self.evaluation_case_artifact.artifact_id,
            self.finance_facts_artifact.artifact_id,
            self.operations_facts_artifact.artifact_id,
            self.risk_assessment_artifact.artifact_id,
            self.approval_checkpoints_artifact.artifact_id,
        )


class DecisionRouteContextLoader:
    """Resolve only explicit case artifacts; never read Excel or infer relationships."""

    def __init__(self, *, artifacts: ArtifactRepository) -> None:
        self._artifacts = artifacts

    async def load(self, context: ExecutionContext) -> DecisionInitialRouteContext:
        if context.evaluation_case_id is None:
            raise DecisionRouteContextError("Decision Initial Route requires evaluation_case_id.")
        upstream: list[ArtifactEnvelope] = []
        for artifact_id in context.input_artifact_ids:
            artifact = await self._artifacts.get(artifact_id)
            if artifact is None:
                raise DecisionRouteContextError(
                    f"Decision received an unknown upstream artifact: {artifact_id}."
                )
            if artifact.validation_status not in {
                ValidationStatus.VALID,
                ValidationStatus.VALID_WITH_WARNINGS,
            }:
                raise DecisionRouteContextError(
                    f"Decision received an unvalidated artifact: {artifact_id}."
                )
            upstream.append(artifact)
        grouped = {
            artifact_type: tuple(
                item for item in upstream if item.artifact_type is artifact_type
            )
            for artifact_type in _REQUIRED_TYPES
        }
        duplicates = tuple(
            artifact_type
            for artifact_type, matches in grouped.items()
            if len(matches) > 1
        )
        if duplicates:
            raise DecisionRouteContextError(
                "Decision received duplicate upstream artifacts: "
                + ", ".join(item.value for item in duplicates)
            )
        missing = tuple(
            artifact_type
            for artifact_type, matches in grouped.items()
            if not matches
        )
        if missing:
            raise DecisionRouteMissingArtifacts(missing)
        case_artifact = grouped[ArtifactType.EVALUATION_CASE][0]
        finance_artifact = grouped[ArtifactType.FINANCE_FACTS][0]
        operations_artifact = grouped[ArtifactType.OPERATIONS_FACTS][0]
        risk_artifact = grouped[ArtifactType.INITIAL_RISK_ASSESSMENT][0]
        checkpoints_artifact = grouped[ArtifactType.APPROVAL_CHECKPOINTS][0]
        try:
            case = EvaluationCase.model_validate(case_artifact.payload)
            finance = FinanceFacts.model_validate(finance_artifact.payload)
            operations = OperationsFacts.model_validate(operations_artifact.payload)
            risk = InitialRiskAssessment.model_validate(risk_artifact.payload)
            checkpoints = ApprovalCheckpointSet.model_validate(
                checkpoints_artifact.payload
            )
        except ValidationError as exc:
            raise DecisionRouteContextError(
                f"Invalid Decision Initial Route input schema: {exc}"
            ) from exc
        self._validate_identity(context, case, finance, operations, risk, checkpoints)
        self._validate_risk_upstream_lineage(
            risk=risk,
            finance_artifact=finance_artifact,
            operations_artifact=operations_artifact,
        )
        return DecisionInitialRouteContext(
            evaluation_case_artifact=case_artifact,
            finance_facts_artifact=finance_artifact,
            operations_facts_artifact=operations_artifact,
            risk_assessment_artifact=risk_artifact,
            approval_checkpoints_artifact=checkpoints_artifact,
            evaluation_case=case,
            finance_facts=finance,
            operations_facts=operations,
            risk_assessment=risk,
            approval_checkpoints=checkpoints,
        )

    @staticmethod
    def _validate_identity(
        execution: ExecutionContext,
        case: EvaluationCase,
        finance: FinanceFacts,
        operations: OperationsFacts,
        risk: InitialRiskAssessment,
        checkpoints: ApprovalCheckpointSet,
    ) -> None:
        expected = (
            execution.evaluation_case_id,
            execution.dataset_id,
            case.contract_id,
        )
        for label, actual in (
            ("EvaluationCase", (case.evaluation_case_id, case.dataset_id, case.contract_id)),
            ("FinanceFacts", (finance.evaluation_case_id, finance.dataset_id, finance.contract_id)),
            (
                "OperationsFacts",
                (operations.evaluation_case_id, operations.dataset_id, operations.contract_id),
            ),
            (
                "InitialRiskAssessment",
                (risk.evaluation_case_id, risk.dataset_id, risk.contract_id),
            ),
            (
                "ApprovalCheckpointSet",
                (
                    checkpoints.evaluation_case_id,
                    checkpoints.dataset_id,
                    checkpoints.contract_id,
                ),
            ),
        ):
            if actual != expected:
                raise DecisionRouteContextError(
                    f"{label} identity does not match the Decision execution context."
                )

    @staticmethod
    def _validate_risk_upstream_lineage(
        *,
        risk: InitialRiskAssessment,
        finance_artifact: ArtifactEnvelope,
        operations_artifact: ArtifactEnvelope,
    ) -> None:
        """Reject a Risk assessment finalized from different fact artifacts."""
        if risk.finance_facts_artifact_id != finance_artifact.artifact_id:
            raise DecisionRouteContextError(
                "InitialRiskAssessment references a different FinanceFacts artifact."
            )
        if risk.operations_facts_artifact_id != operations_artifact.artifact_id:
            raise DecisionRouteContextError(
                "InitialRiskAssessment references a different OperationsFacts artifact."
            )
