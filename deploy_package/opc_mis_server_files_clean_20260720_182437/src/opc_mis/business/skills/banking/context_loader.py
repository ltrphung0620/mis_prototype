"""Load Banking discovery inputs from explicit, validated artifacts and dataset keys."""

from dataclasses import dataclass

from pydantic import ValidationError

from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.banking_models import (
    BankingDiscoveryRequest,
    BankingInputSupplement,
)
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.dataset import DatasetRecord, DatasetSnapshot
from opc_mis.domain.enums import (
    ArtifactType,
    CurrencyCode,
    DecisionCapability,
    DecisionHandoffMode,
    SourceType,
    ValidationStatus,
)
from opc_mis.domain.planner_models import EvaluationCase
from opc_mis.domain.team_pack import SheetDefinition, SheetRegistry
from opc_mis.ports.artifact_repository import ArtifactRepository
from opc_mis.ports.dataset_port import DatasetNotFoundError, DatasetPort

_REQUIRED_ARTIFACT_TYPES = (
    ArtifactType.EVALUATION_CASE,
    ArtifactType.BANKING_DISCOVERY_REQUEST,
)
_ALLOWED_ARTIFACT_TYPES = {
    *_REQUIRED_ARTIFACT_TYPES,
    ArtifactType.BANKING_INPUT_SUPPLEMENT,
}
_VALID_STATUSES = (ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS)


class BankingDiscoveryContextError(RuntimeError):
    """Raised when Banking receives missing, unvalidated, or inconsistent inputs."""


class BankingDiscoveryRequestMissing(BankingDiscoveryContextError):
    """Raised when Decision has not created the required Banking request yet."""


@dataclass(frozen=True)
class BankingDiscoveryContext:
    """Authoritative Banking inputs with only Planner-selected relationships."""

    dataset: DatasetSnapshot
    evaluation_case_artifact: ArtifactEnvelope
    request_artifact: ArtifactEnvelope
    supplement_artifact: ArtifactEnvelope | None
    evaluation_case: EvaluationCase
    request: BankingDiscoveryRequest
    supplement: BankingInputSupplement | None
    explicit_credit_profiles: tuple[DatasetRecord, ...]

    @property
    def source_artifact_ids(self) -> tuple[str, ...]:
        """Return the explicit upstream artifacts in stable semantic order."""
        return (
            self.evaluation_case_artifact.artifact_id,
            self.request_artifact.artifact_id,
            *(
                (self.supplement_artifact.artifact_id,)
                if self.supplement_artifact is not None
                else ()
            ),
        )

    @property
    def requested_amount(self) -> int | None:
        """Return the Decision request amount, with supplement-only legacy fallback."""
        if self.request.requested_amount is not None:
            return self.request.requested_amount
        return self.supplement.requested_amount if self.supplement is not None else None

    @property
    def requested_amount_currency(self) -> CurrencyCode:
        """Return the currency attached to the authoritative amount source."""
        if self.request.requested_amount is not None:
            return self.request.requested_amount_currency
        if self.supplement is not None:
            return self.supplement.requested_amount_currency
        return self.request.requested_amount_currency


class BankingDiscoveryContextLoader:
    """Resolve Banking context without fuzzy names or descriptive-text matching."""

    def __init__(self, *, datasets: DatasetPort, artifacts: ArtifactRepository) -> None:
        self._datasets = datasets
        self._artifacts = artifacts

    async def load(self, context: ExecutionContext) -> BankingDiscoveryContext:
        """Load exactly one validated case and one validated Banking request."""
        if context.evaluation_case_id is None:
            raise BankingDiscoveryContextError(
                "Banking discovery requires evaluation_case_id."
            )

        upstream: list[ArtifactEnvelope] = []
        for artifact_id in context.input_artifact_ids:
            artifact = await self._artifacts.get(artifact_id)
            if artifact is None:
                raise BankingDiscoveryContextError(
                    f"Banking discovery received an unknown artifact: {artifact_id}."
                )
            if artifact.validation_status not in _VALID_STATUSES:
                raise BankingDiscoveryContextError(
                    f"Banking discovery received an unvalidated artifact: {artifact_id}."
                )
            upstream.append(artifact)

        unexpected = tuple(
            item.artifact_type
            for item in upstream
            if item.artifact_type not in _ALLOWED_ARTIFACT_TYPES
        )
        if unexpected:
            raise BankingDiscoveryContextError(
                "Banking discovery received unexpected artifacts: "
                + ", ".join(item.value for item in unexpected)
            )

        grouped = {
            artifact_type: tuple(
                item for item in upstream if item.artifact_type is artifact_type
            )
            for artifact_type in _REQUIRED_ARTIFACT_TYPES
        }
        if (
            len(grouped[ArtifactType.EVALUATION_CASE]) == 1
            and not grouped[ArtifactType.BANKING_DISCOVERY_REQUEST]
        ):
            raise BankingDiscoveryRequestMissing(
                "Banking discovery is waiting for BANKING_DISCOVERY_REQUEST."
            )
        invalid_counts = tuple(
            artifact_type
            for artifact_type, matches in grouped.items()
            if len(matches) != 1
        )
        if invalid_counts:
            raise BankingDiscoveryContextError(
                "Banking discovery requires exactly one validated artifact of each type: "
                + ", ".join(item.value for item in invalid_counts)
            )

        case_artifact = grouped[ArtifactType.EVALUATION_CASE][0]
        request_artifact = grouped[ArtifactType.BANKING_DISCOVERY_REQUEST][0]
        supplement_artifacts = tuple(
            item
            for item in upstream
            if item.artifact_type is ArtifactType.BANKING_INPUT_SUPPLEMENT
        )
        if len(supplement_artifacts) > 1:
            raise BankingDiscoveryContextError(
                "Banking discovery accepts at most one immutable input supplement."
            )
        supplement_artifact = (
            supplement_artifacts[0] if supplement_artifacts else None
        )
        try:
            evaluation_case = EvaluationCase.model_validate(case_artifact.payload)
            request = BankingDiscoveryRequest.model_validate(request_artifact.payload)
            supplement = (
                BankingInputSupplement.model_validate(supplement_artifact.payload)
                if supplement_artifact is not None
                else None
            )
            dataset = await self._datasets.get_snapshot(context.dataset_id)
        except (ValidationError, DatasetNotFoundError) as exc:
            raise BankingDiscoveryContextError(
                f"Invalid Banking discovery context: {exc}"
            ) from exc

        self._validate_identity(
            context=context,
            dataset=dataset,
            case_artifact=case_artifact,
            request_artifact=request_artifact,
            supplement_artifact=supplement_artifact,
            evaluation_case=evaluation_case,
            request=request,
            supplement=supplement,
        )
        explicit_credit_profiles = tuple(
            self._exact(dataset, SheetRegistry.CREDIT_PROFILES, credit_case_id)
            for credit_case_id in evaluation_case.related_credit_case_ids
        )
        return BankingDiscoveryContext(
            dataset=dataset,
            evaluation_case_artifact=case_artifact,
            request_artifact=request_artifact,
            supplement_artifact=supplement_artifact,
            evaluation_case=evaluation_case,
            request=request,
            supplement=supplement,
            explicit_credit_profiles=explicit_credit_profiles,
        )

    @staticmethod
    def _validate_identity(
        *,
        context: ExecutionContext,
        dataset: DatasetSnapshot,
        case_artifact: ArtifactEnvelope,
        request_artifact: ArtifactEnvelope,
        supplement_artifact: ArtifactEnvelope | None,
        evaluation_case: EvaluationCase,
        request: BankingDiscoveryRequest,
        supplement: BankingInputSupplement | None,
    ) -> None:
        expected = (
            context.evaluation_case_id,
            context.dataset_id,
            evaluation_case.contract_id,
        )
        if (
            evaluation_case.evaluation_case_id,
            evaluation_case.dataset_id,
            evaluation_case.contract_id,
        ) != expected:
            raise BankingDiscoveryContextError(
                "EvaluationCase identity does not match the Banking execution context."
            )
        if (
            request.evaluation_case_id,
            request.dataset_id,
            request.contract_id,
        ) != expected:
            raise BankingDiscoveryContextError(
                "BankingDiscoveryRequest identity does not match EvaluationCase."
            )
        if dataset.dataset_id != context.dataset_id:
            raise BankingDiscoveryContextError(
                "Dataset snapshot identity does not match the Banking execution context."
            )
        if any(
            artifact.evaluation_case_id != context.evaluation_case_id
            for artifact in (
                case_artifact,
                request_artifact,
                *((supplement_artifact,) if supplement_artifact is not None else ()),
            )
        ):
            raise BankingDiscoveryContextError(
                "Banking input envelope belongs to a different evaluation case."
            )
        if request.execution_mode is not DecisionHandoffMode.BANKING_DISCOVERY:
            raise BankingDiscoveryContextError(
                "Banking request has an unsupported execution mode."
            )
        if (
            request.requested_capability
            is not DecisionCapability.BANKING_INTERNAL_DISCOVERY
        ):
            raise BankingDiscoveryContextError(
                "Banking request does not request BANKING_INTERNAL_DISCOVERY."
            )
        if request.source_route_artifact_id not in request.source_artifact_ids:
            raise BankingDiscoveryContextError(
                "Banking request is missing its Decision route lineage."
            )
        request_evidence_ids = {
            item.evidence_id for item in request_artifact.evidence_refs
        }
        if not set(request.evidence_ids).issubset(request_evidence_ids):
            raise BankingDiscoveryContextError(
                "Banking request references evidence absent from its artifact envelope."
            )
        if not set(request.amount_evidence_ids).issubset(request_evidence_ids):
            raise BankingDiscoveryContextError(
                "Banking request amount evidence is absent from its artifact envelope."
            )
        if request.requested_amount is not None:
            amount_evidence = tuple(
                item
                for item in request_artifact.evidence_refs
                if item.evidence_id in request.amount_evidence_ids
            )
            if (
                len(amount_evidence) != 1
                or amount_evidence[0].source_type is not SourceType.TEAM_PACK
                or amount_evidence[0].sheet
                != SheetRegistry.CREDIT_PROFILES.sheet_name
                or amount_evidence[0].record_id != request.credit_case_id
                or amount_evidence[0].field != "requested_amount"
                or amount_evidence[0].display_value != request.requested_amount
            ):
                raise BankingDiscoveryContextError(
                    "Banking request amount must bind to one exact credit-profile "
                    "requested_amount evidence item."
                )
            requirements = tuple(
                item
                for item in evaluation_case.contract_requirements
                if item.requirement_id == request.requirement_id
            )
            if len(requirements) != 1:
                raise BankingDiscoveryContextError(
                    "Banking request amount must reference one exact EvaluationCase "
                    "contract requirement."
                )
            requirement = requirements[0]
            if (
                len(request.need_types) != 1
                or requirement.requirement_type.value
                != request.need_types[0].value
                or requirement.credit_case_id != request.credit_case_id
                or requirement.requested_amount != request.requested_amount
                or requirement.requested_amount_currency
                is not request.requested_amount_currency
                or requirement.amount_semantics is not request.amount_semantics
                or not set(request.amount_evidence_ids).issubset(
                    requirement.evidence_ids
                )
            ):
                raise BankingDiscoveryContextError(
                    "Banking request amount does not match its exact EvaluationCase "
                    "contract requirement."
                )
            case_evidence = {
                item.evidence_id: item for item in case_artifact.evidence_refs
            }
            request_evidence = {
                item.evidence_id: item for item in request_artifact.evidence_refs
            }
            if any(
                case_evidence.get(evidence_id)
                != request_evidence[evidence_id]
                for evidence_id in request.amount_evidence_ids
            ):
                raise BankingDiscoveryContextError(
                    "EvaluationCase artifact does not retain the Banking request amount "
                    "evidence."
                )
        if (
            request.requested_amount is not None
            and request.credit_case_id not in evaluation_case.related_credit_case_ids
        ):
            raise BankingDiscoveryContextError(
                "Banking request amount credit case is not an explicit EvaluationCase "
                "relationship."
            )
        if supplement is not None:
            if (
                supplement.evaluation_case_id,
                supplement.dataset_id,
                supplement.contract_id,
            ) != expected:
                raise BankingDiscoveryContextError(
                    "Banking input supplement identity does not match EvaluationCase."
                )
            if supplement.banking_request_id != request.request_id:
                raise BankingDiscoveryContextError(
                    "Banking input supplement belongs to a different Banking request."
                )
            if case_artifact.artifact_id not in supplement.source_artifact_ids:
                raise BankingDiscoveryContextError(
                    "Banking input supplement is missing EvaluationCase lineage."
                )
            supplement_evidence_ids = {
                item.evidence_id
                for item in supplement_artifact.evidence_refs  # type: ignore[union-attr]
            }
            if not set(supplement.evidence_ids).issubset(supplement_evidence_ids):
                raise BankingDiscoveryContextError(
                    "Banking input supplement references evidence absent from its envelope."
                )
            if request.requested_amount is not None and (
                supplement.requested_amount != request.requested_amount
                or supplement.requested_amount_currency
                is not request.requested_amount_currency
            ):
                raise BankingDiscoveryContextError(
                    "A legacy Banking supplement conflicts with the authoritative "
                    "BankingDiscoveryRequest amount."
                )

    @staticmethod
    def _exact(
        dataset: DatasetSnapshot,
        definition: SheetDefinition,
        record_id: str,
    ) -> DatasetRecord:
        matches = dataset.lookup(definition, record_id)
        if len(matches) != 1:
            raise BankingDiscoveryContextError(
                f"Expected exactly one {record_id} in {definition.sheet_name}; "
                f"found {len(matches)}."
            )
        return matches[0]
