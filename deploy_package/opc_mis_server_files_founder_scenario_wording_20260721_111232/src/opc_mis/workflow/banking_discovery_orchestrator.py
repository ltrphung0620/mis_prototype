"""Workflow-owned validation and persistence for Banking Phase A."""

from opc_mis.business.skills.banking.advisor_component import (
    BankingOptionAdvisorSkill,
)
from opc_mis.business.skills.banking.component import BankingDiscoverySkill
from opc_mis.domain.artifacts import ArtifactDraft, ArtifactEnvelope
from opc_mis.domain.banking_models import (
    BankingCatalogPolicy,
    BankingDiscoveryExecutionResult,
    BankingDiscoveryResult,
    BankingOptionAdvice,
    BankingOptionMatrix,
)
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import (
    ArtifactType,
    BankingDiscoveryStatus,
    ComponentStatus,
    ValidationStatus,
    WorkflowStatus,
)
from opc_mis.domain.validation_reports import ValidationReport
from opc_mis.domain.workflow import WorkflowNode
from opc_mis.governance.evidence_validator import EvidenceValidator
from opc_mis.ports.artifact_repository import ArtifactRepository
from opc_mis.workflow.artifact_factory import ArtifactFactory, artifact_input_hash


class BankingDiscoveryOrchestrator:
    """Persist deterministic options first, then bounded advisory prose."""

    def __init__(
        self,
        *,
        discovery: BankingDiscoverySkill,
        advisor: BankingOptionAdvisorSkill,
        artifacts: ArtifactRepository,
        policy: BankingCatalogPolicy,
        advisor_configuration_hash: str,
        artifact_factory: ArtifactFactory | None = None,
    ) -> None:
        self._discovery = discovery
        self._advisor = advisor
        self._artifacts = artifacts
        self._validator = EvidenceValidator(banking_policy=policy)
        self._advisor_configuration_hash = advisor_configuration_hash
        self._artifact_factory = artifact_factory or ArtifactFactory()

    async def run(self, context: ExecutionContext) -> BankingDiscoveryExecutionResult:
        """Validate all deterministic drafts before any Phase A persistence."""
        result = await self._discovery.execute(context)
        if result.status is ComponentStatus.FAILED_SAFE:
            return BankingDiscoveryExecutionResult(
                status=WorkflowStatus.FAILED_SAFE,
                component_status=result.status,
                current_node=WorkflowNode.BANKING_INTERNAL_DISCOVERY.value,
                discovery_status=result.discovery_status,
                validation_errors=tuple(
                    item.message for item in result.runtime_events
                ),
                warnings=result.warnings,
                runtime_events=tuple(
                    item.model_dump(mode="json") for item in result.runtime_events
                ),
            )
        if result.status is ComponentStatus.WAITING_FOR_INPUT:
            return BankingDiscoveryExecutionResult(
                status=WorkflowStatus.WAITING_FOR_INPUT,
                component_status=result.status,
                current_node=WorkflowNode.BANKING_INTERNAL_DISCOVERY.value,
                discovery_status=result.discovery_status,
                missing_data_requests=result.missing_data_requests,
                warnings=result.warnings,
                runtime_events=tuple(
                    item.model_dump(mode="json") for item in result.runtime_events
                ),
            )

        contract_errors = self._validate_discovery_contract(result)
        if contract_errors:
            return self._failed_validation(
                result.discovery_status,
                contract_errors,
                result.warnings,
            )
        matrix = result.option_matrix
        discovery_result = result.discovery_result
        if matrix is None or discovery_result is None:  # guarded above
            return self._failed_validation(
                BankingDiscoveryStatus.FAILED_SAFE,
                ("Banking discovery returned no typed outputs.",),
                result.warnings,
            )
        drafts = {item.artifact_type: item for item in result.artifacts}
        deterministic_drafts = (
            drafts[ArtifactType.BANKING_OPTION_MATRIX],
            drafts[ArtifactType.BANKING_DISCOVERY_RESULT],
        )
        reports = tuple(
            [await self._validator.validate(item) for item in deterministic_drafts]
        )
        blocked = tuple(
            error
            for report in reports
            if report.status is ValidationStatus.BLOCKED
            for error in report.blocking_errors
        )
        if blocked:
            return self._failed_validation(
                matrix.discovery_status,
                blocked,
                result.warnings,
                reports=reports,
                matrix=matrix,
                discovery_result=discovery_result,
            )

        matrix_envelope = await self._persist_or_reuse(
            deterministic_drafts[0], context, reports[0]
        )
        result_context = context.model_copy(
            update={
                "input_artifact_ids": (
                    *context.input_artifact_ids,
                    matrix_envelope.artifact_id,
                )
            }
        )
        result_envelope = await self._persist_or_reuse(
            deterministic_drafts[1], result_context, reports[1]
        )

        advice_context = context.model_copy(
            update={
                "input_artifact_ids": (matrix_envelope.artifact_id,),
                "component_input": {
                    "matrix_id": matrix.matrix_id,
                    "advisor_configuration_hash": self._advisor_configuration_hash,
                },
            }
        )
        advice, advice_envelope, advice_report, advice_warnings, advice_events = (
            await self._advice(advice_context, matrix_envelope, matrix)
        )
        if advice is None or advice_envelope is None:
            return self._failed_validation(
                matrix.discovery_status,
                ("Banking option advice failed safe after matrix persistence.",),
                (*result.warnings, *advice_warnings),
                reports=reports,
                matrix=matrix,
                discovery_result=discovery_result,
                generated=(matrix_envelope, result_envelope),
            )

        all_warnings = tuple(dict.fromkeys((*result.warnings, *advice_warnings)))
        component_status = (
            ComponentStatus.COMPLETED_WITH_WARNINGS
            if all_warnings
            else ComponentStatus.COMPLETED
        )
        return BankingDiscoveryExecutionResult(
            status=WorkflowStatus.COMPLETED,
            component_status=component_status,
            current_node=WorkflowNode.BANKING_INTERNAL_OPTIONS_READY.value,
            discovery_status=matrix.discovery_status,
            option_matrix=matrix,
            discovery_result=discovery_result,
            option_advice=advice,
            generated_artifacts=(
                matrix_envelope,
                result_envelope,
                advice_envelope,
            ),
            validation_reports=(
                *reports,
                *((advice_report,) if advice_report is not None else ()),
            ),
            warnings=all_warnings,
            runtime_events=(
                *(item.model_dump(mode="json") for item in result.runtime_events),
                *advice_events,
            ),
        )

    async def _advice(
        self,
        context: ExecutionContext,
        matrix_envelope: ArtifactEnvelope,
        matrix: BankingOptionMatrix,
    ) -> tuple[
        BankingOptionAdvice | None,
        ArtifactEnvelope | None,
        ValidationReport | None,
        tuple[str, ...],
        tuple[dict[str, object], ...],
    ]:
        existing = await self._artifacts.list_by_case(matrix.evaluation_case_id)
        reusable = next(
            (
                item
                for item in existing
                if item.artifact_type is ArtifactType.BANKING_OPTION_ADVICE
                and item.input_artifact_ids == (matrix_envelope.artifact_id,)
                and BankingOptionAdvice.model_validate(
                    item.payload
                ).advisor_configuration_hash
                == self._advisor_configuration_hash
                and item.validation_status
                in {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}
            ),
            None,
        )
        if reusable is not None:
            return (
                BankingOptionAdvice.model_validate(reusable.payload),
                reusable,
                None,
                (),
                (),
            )

        result = await self._advisor.execute(context)
        if result.status is ComponentStatus.FAILED_SAFE or result.option_advice is None:
            return (
                None,
                None,
                None,
                result.warnings,
                tuple(item.model_dump(mode="json") for item in result.runtime_events),
            )
        if len(result.artifacts) != 1 or (
            result.artifacts[0].artifact_type is not ArtifactType.BANKING_OPTION_ADVICE
        ):
            return None, None, None, ("BANKING_ADVICE_CONTRACT_INVALID",), ()
        advice = result.option_advice
        cross_errors = self._validate_advice_against_matrix(advice, matrix)
        if cross_errors:
            return None, None, None, cross_errors, ()
        draft = result.artifacts[0]
        report = await self._validator.validate(draft)
        if report.status is ValidationStatus.BLOCKED:
            return None, None, report, report.blocking_errors, ()
        envelope = await self._persist_or_reuse(draft, context, report)
        return (
            BankingOptionAdvice.model_validate(envelope.payload),
            envelope,
            report,
            result.warnings,
            tuple(item.model_dump(mode="json") for item in result.runtime_events),
        )

    @staticmethod
    def _validate_discovery_contract(result: object) -> tuple[str, ...]:
        if not hasattr(result, "artifacts"):
            return ("Banking discovery returned an invalid component result.",)
        typed = result
        matrix = getattr(typed, "option_matrix", None)
        discovery_result = getattr(typed, "discovery_result", None)
        artifacts = getattr(typed, "artifacts", ())
        if matrix is None or discovery_result is None:
            return ("Banking discovery must return matrix and result objects.",)
        artifact_types = tuple(item.artifact_type for item in artifacts)
        if len(artifacts) != 2 or set(artifact_types) != {
            ArtifactType.BANKING_OPTION_MATRIX,
            ArtifactType.BANKING_DISCOVERY_RESULT,
        }:
            return ("Banking discovery must return exactly two deterministic drafts.",)
        if (
            discovery_result.matrix_id != matrix.matrix_id
            or discovery_result.discovery_status is not matrix.discovery_status
            or discovery_result.candidate_option_ids
            != tuple(item.option_id for item in matrix.candidates)
            or discovery_result.data_gap_ids
            != tuple(item.gap_id for item in matrix.data_gaps)
            or discovery_result.mapping_version != matrix.mapping_version
            or discovery_result.mapping_hash != matrix.mapping_hash
        ):
            return ("Banking discovery result does not match its option matrix.",)
        payload_by_type = {item.artifact_type: item.payload for item in artifacts}
        if payload_by_type[ArtifactType.BANKING_OPTION_MATRIX] != matrix.model_dump(
            mode="json"
        ) or payload_by_type[
            ArtifactType.BANKING_DISCOVERY_RESULT
        ] != discovery_result.model_dump(mode="json"):
            return ("Banking typed outputs and artifact drafts disagree.",)
        return ()

    @staticmethod
    def _validate_advice_against_matrix(
        advice: BankingOptionAdvice,
        matrix: BankingOptionMatrix,
    ) -> tuple[str, ...]:
        errors: list[str] = []
        if advice.matrix_id != matrix.matrix_id:
            errors.append("Banking advice references a different option matrix.")
        known = {item.option_id for item in matrix.candidates}
        allowed = {tuple(sorted(item)) for item in matrix.allowed_option_combinations}
        for suggestion in advice.suggestions:
            if not set(suggestion.option_ids).issubset(known):
                errors.append("Banking advice references an unknown option ID.")
            if len(suggestion.option_ids) > 1 and tuple(
                sorted(suggestion.option_ids)
            ) not in allowed:
                errors.append("Banking advice uses an unconfigured option combination.")
        return tuple(dict.fromkeys(errors))

    def _failed_validation(
        self,
        discovery_status: BankingDiscoveryStatus,
        errors: tuple[str, ...],
        warnings: tuple[str, ...],
        *,
        reports: tuple[ValidationReport, ...] = (),
        matrix: BankingOptionMatrix | None = None,
        discovery_result: BankingDiscoveryResult | None = None,
        generated: tuple[ArtifactEnvelope, ...] = (),
    ) -> BankingDiscoveryExecutionResult:
        return BankingDiscoveryExecutionResult(
            status=WorkflowStatus.FAILED_SAFE,
            component_status=ComponentStatus.FAILED_SAFE,
            current_node=WorkflowNode.BANKING_INTERNAL_DISCOVERY.value,
            discovery_status=discovery_status,
            option_matrix=matrix,
            discovery_result=discovery_result,
            generated_artifacts=generated,
            validation_reports=reports,
            validation_errors=errors,
            warnings=warnings,
        )

    async def _persist_or_reuse(
        self,
        draft: ArtifactDraft,
        context: ExecutionContext,
        report: ValidationReport,
    ) -> ArtifactEnvelope:
        existing = await self._artifacts.list_by_case(draft.evaluation_case_id)
        input_hash = artifact_input_hash(draft, context)
        current = next(
            (
                item
                for item in existing
                if item.artifact_type is draft.artifact_type
                and item.input_hash == input_hash
            ),
            None,
        )
        if current is not None:
            return current
        version = 1 + max(
            (
                item.version
                for item in existing
                if item.artifact_type is draft.artifact_type
            ),
            default=0,
        )
        envelope = self._artifact_factory.create(
            draft=draft,
            context=context,
            validation_report=report,
            version=version,
        )
        await self._artifacts.save(envelope)
        return envelope
