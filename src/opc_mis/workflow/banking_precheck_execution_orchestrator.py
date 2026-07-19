"""Governed Phase B1 execution and persistence for simulated Banking prechecks."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictStr,
    ValidationError,
)

from opc_mis.business.skills.banking.precheck_request_resolver import (
    BankingPrecheckRequestResolutionError,
    BankingPrecheckRequestResolver,
)
from opc_mis.business.skills.banking.precheck_result_component import (
    BankingPrecheckResultComponent,
)
from opc_mis.domain.artifacts import ArtifactDraft, ArtifactEnvelope
from opc_mis.domain.banking_models import BankingInputSupplement
from opc_mis.domain.banking_precheck_execution_models import (
    BankingPrecheckResultComponentInput,
    BankingPrecheckResultExecutionResult,
    BankingPrecheckResultSet,
)
from opc_mis.domain.banking_precheck_submission_models import (
    BankingPrecheckSubmissionProposal,
)
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import (
    ArtifactType,
    ComponentStatus,
    ValidationStatus,
    WorkflowStatus,
)
from opc_mis.domain.planner_models import EvaluationCase
from opc_mis.domain.team_pack import SheetRegistry
from opc_mis.domain.validation_reports import ValidationReport
from opc_mis.domain.workflow import WorkflowNode
from opc_mis.governance.authorized_action import (
    AuthorizationPermitError,
    AuthorizedActionPermitIssuer,
)
from opc_mis.governance.evidence_validator import EvidenceValidator
from opc_mis.ports.artifact_repository import ArtifactRepository
from opc_mis.ports.banking_precheck_adapter import BankingPrecheckAdapter
from opc_mis.ports.dataset_port import DatasetPort
from opc_mis.workflow.artifact_factory import ArtifactFactory, artifact_input_hash

_VALID_ARTIFACT_STATUSES = {
    ValidationStatus.VALID,
    ValidationStatus.VALID_WITH_WARNINGS,
}
_AUTHORIZATION_FAILURE = (
    "Banking precheck authorization could not be verified safely."
)
_INPUT_VALIDATION_FAILURE = (
    "Banking precheck execution inputs could not be validated safely."
)
_REQUEST_RESOLUTION_FAILURE = (
    "Banking precheck request references could not be resolved safely."
)
_UNEXPECTED_EXECUTION_FAILURE = (
    "Banking precheck execution failed safely; internal provider and "
    "infrastructure details were withheld."
)
_MISSING_REUSABLE_RESULT = (
    "Completed Banking precheck execution has no exact validated persisted result."
)


class BankingPrecheckExecutionCommand(BaseModel):
    """Workflow-only pointer to the persisted human approval request."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    approval_request_id: StrictStr = Field(min_length=1)
    reuse_existing_only: StrictBool = False


class BankingPrecheckExecutionOrchestrator:
    """Issue a permit, invoke the adapter, then validate and persist one result set."""

    def __init__(
        self,
        *,
        result_component: BankingPrecheckResultComponent,
        request_resolver: BankingPrecheckRequestResolver,
        permit_issuer: AuthorizedActionPermitIssuer,
        adapter: BankingPrecheckAdapter,
        datasets: DatasetPort,
        artifacts: ArtifactRepository,
        evidence_validator: EvidenceValidator | None = None,
        artifact_factory: ArtifactFactory | None = None,
    ) -> None:
        self._result_component = result_component
        self._request_resolver = request_resolver
        self._permit_issuer = permit_issuer
        self._adapter = adapter
        self._datasets = datasets
        self._artifacts = artifacts
        self._validator = evidence_validator or EvidenceValidator()
        self._artifact_factory = artifact_factory or ArtifactFactory()

    async def run(
        self,
        context: ExecutionContext,
    ) -> BankingPrecheckResultExecutionResult:
        """Run only after exact Governance authorization; never select an option."""
        try:
            command = BankingPrecheckExecutionCommand.model_validate(
                context.component_input
            )
            (
                proposal_artifact,
                evaluation_case_artifact,
                supplement_artifact,
                proposal,
                evaluation_case,
                supplement,
            ) = await self._load_inputs(context)
            permit = await self._permit_issuer.issue(
                approval_request_id=command.approval_request_id,
                workflow_run_id=context.workflow_run_id,
                evaluation_case_id=proposal.evaluation_case_id,
                expected_subject_artifact_id=proposal_artifact.artifact_id,
            )
            existing = await self._existing_result(
                context=context,
                proposal=proposal,
                proposal_artifact=proposal_artifact,
                approval_request_id=command.approval_request_id,
                permit_id=permit.permit_id,
            )
            if existing is not None:
                return existing
            if command.reuse_existing_only:
                return self._failed((_MISSING_REUSABLE_RESULT,))
            snapshot = await self._datasets.get_snapshot(context.dataset_id)
            requests = self._request_resolver.resolve(
                proposal_artifact=proposal_artifact,
                evaluation_case_artifact=evaluation_case_artifact,
                supplement_artifact=supplement_artifact,
                proposal=proposal,
                evaluation_case=evaluation_case,
                supplement=supplement,
                opc_profile_records=tuple(snapshot.records(SheetRegistry.OPC_PROFILE)),
                authorization=permit,
            )
            raw_responses = tuple(
                [
                    await self._adapter.submit(request, permit)
                    for request in requests
                ]
            )
            component_input = BankingPrecheckResultComponentInput(
                permit=permit,
                requests=requests,
                raw_responses=raw_responses,
                adapter_id=self._adapter.adapter_id,
                adapter_config_hash=self._adapter.configuration_hash,
            )
            result_context = context.model_copy(
                update={"component_input": component_input.model_dump(mode="json")}
            )
            result = await self._result_component.execute(result_context)
        except AuthorizationPermitError:
            return self._failed((_AUTHORIZATION_FAILURE,))
        except BankingPrecheckRequestResolutionError:
            return self._failed((_REQUEST_RESOLUTION_FAILURE,))
        except (ValidationError, ValueError):
            return self._failed((_INPUT_VALIDATION_FAILURE,))
        except Exception:
            # Adapter/infrastructure failures cross a fail-safe workflow boundary. They
            # are never converted into a fabricated response or exposed to callers.
            return self._failed((_UNEXPECTED_EXECUTION_FAILURE,))

        events = tuple(item.model_dump(mode="json") for item in result.runtime_events)
        if result.status is ComponentStatus.FAILED_SAFE:
            errors = tuple(item.message for item in result.runtime_events) or (
                "Banking precheck result component failed safely.",
            )
            return self._failed(errors, warnings=result.warnings, events=events)
        errors = self._contract_errors(result)
        if errors:
            return self._failed(errors, warnings=result.warnings, events=events)
        result_set = result.result_set
        draft = result.artifacts[0]
        if result_set is None:  # pragma: no cover - guarded by contract validation
            return self._failed(
                ("Banking precheck execution returned no typed result set.",),
                warnings=result.warnings,
                events=events,
            )
        try:
            report = await self._validator.validate(draft)
            if report.status is ValidationStatus.BLOCKED:
                return self._failed(
                    report.blocking_errors,
                    warnings=result.warnings,
                    events=events,
                    reports=(report,),
                    result_set=result_set,
                )
            envelope = await self._persist_or_reuse(draft, result_context, report)
            persisted = BankingPrecheckResultSet.model_validate(envelope.payload)
        except Exception:
            return self._failed(
                (_UNEXPECTED_EXECUTION_FAILURE,),
                warnings=result.warnings,
                events=events,
                result_set=result_set,
            )
        return BankingPrecheckResultExecutionResult(
            status=WorkflowStatus.COMPLETED,
            component_status=result.status,
            current_node=WorkflowNode.BANKING_PRECHECK_EXECUTION.value,
            result_set=persisted,
            generated_artifacts=(envelope,),
            validation_reports=(report,),
            warnings=result.warnings,
            runtime_events=events,
        )

    async def _load_inputs(
        self,
        context: ExecutionContext,
    ) -> tuple[
        ArtifactEnvelope,
        ArtifactEnvelope,
        ArtifactEnvelope,
        BankingPrecheckSubmissionProposal,
        EvaluationCase,
        BankingInputSupplement,
    ]:
        if context.evaluation_case_id is None or not context.input_artifact_ids:
            raise ValueError("Banking precheck execution requires a case and proposal lineage.")
        supplied: list[ArtifactEnvelope] = []
        for artifact_id in context.input_artifact_ids:
            artifact = await self._artifacts.get(artifact_id)
            if artifact is None or artifact.validation_status not in _VALID_ARTIFACT_STATUSES:
                raise ValueError(
                    f"Banking precheck execution input is unknown or invalid: {artifact_id}."
                )
            if artifact.evaluation_case_id != context.evaluation_case_id:
                raise ValueError("A Banking precheck execution input belongs to another case.")
            supplied.append(artifact)
        supplied_tuple = tuple(supplied)
        proposal_artifact = self._one(
            supplied_tuple,
            ArtifactType.BANKING_PRECHECK_SUBMISSION_PROPOSAL,
        )
        if supplied_tuple[0] != proposal_artifact:
            raise ValueError("The approved proposal must be the first execution input.")
        proposal = BankingPrecheckSubmissionProposal.model_validate(
            proposal_artifact.payload
        )
        if context.input_artifact_ids != (
            proposal_artifact.artifact_id,
            *proposal.source_artifact_ids,
        ):
            raise ValueError(
                "Banking precheck execution inputs do not match exact proposal lineage."
            )
        evaluation_case_artifact = self._one(
            supplied_tuple,
            ArtifactType.EVALUATION_CASE,
        )
        supplement_artifact = self._one(
            supplied_tuple,
            ArtifactType.BANKING_INPUT_SUPPLEMENT,
        )
        evaluation_case = EvaluationCase.model_validate(
            evaluation_case_artifact.payload
        )
        supplement = BankingInputSupplement.model_validate(
            supplement_artifact.payload
        )
        return (
            proposal_artifact,
            evaluation_case_artifact,
            supplement_artifact,
            proposal,
            evaluation_case,
            supplement,
        )

    async def _existing_result(
        self,
        *,
        context: ExecutionContext,
        proposal: BankingPrecheckSubmissionProposal,
        proposal_artifact: ArtifactEnvelope,
        approval_request_id: str,
        permit_id: str,
    ) -> BankingPrecheckResultExecutionResult | None:
        artifacts = await self._artifacts.list_by_case(proposal.evaluation_case_id)
        matches: list[tuple[ArtifactEnvelope, BankingPrecheckResultSet]] = []
        for artifact in artifacts:
            if (
                artifact.artifact_type is not ArtifactType.BANKING_PRECHECK_RESULT_SET
                or artifact.validation_status not in _VALID_ARTIFACT_STATUSES
            ):
                continue
            result_set = BankingPrecheckResultSet.model_validate(artifact.payload)
            if (
                result_set.proposal_artifact_id == proposal_artifact.artifact_id
                and result_set.proposal_id == proposal.proposal_id
                and result_set.approval_request_id == approval_request_id
                and result_set.permit_id == permit_id
                and result_set.adapter_id == self._adapter.adapter_id
                and result_set.adapter_config_hash == self._adapter.configuration_hash
                and result_set.candidate_option_ids == proposal.candidate_option_ids
                and result_set.source_artifact_ids == context.input_artifact_ids
                and artifact.input_artifact_ids == context.input_artifact_ids
            ):
                report = await self._validator.validate(
                    ArtifactDraft(
                        artifact_type=artifact.artifact_type,
                        evaluation_case_id=artifact.evaluation_case_id,
                        producer=artifact.producer,
                        payload=artifact.payload,
                        evidence_refs=artifact.evidence_refs,
                        identity_inputs=self._result_identity_inputs(result_set),
                    )
                )
                if report.status is ValidationStatus.BLOCKED:
                    raise ValueError(
                        "Persisted Banking precheck result failed current evidence "
                        "revalidation."
                    )
                matches.append((artifact, result_set))
        if not matches:
            return None
        if len(matches) != 1:
            raise ValueError("Authorized Banking precheck has ambiguous persisted results.")
        artifact, result_set = matches[0]
        warnings = (
            "BANKING_PRECHECK_SIMULATED_NON_BINDING",
            *(f"BANKING_PRECHECK_{item.outcome.value}" for item in result_set.results),
        )
        return BankingPrecheckResultExecutionResult(
            status=WorkflowStatus.COMPLETED,
            component_status=ComponentStatus.COMPLETED_WITH_WARNINGS,
            current_node=WorkflowNode.BANKING_PRECHECK_EXECUTION.value,
            result_set=result_set,
            generated_artifacts=(artifact,),
            warnings=tuple(dict.fromkeys(warnings)),
        )

    @staticmethod
    def _result_identity_inputs(
        result_set: BankingPrecheckResultSet,
    ) -> dict[str, object]:
        """Reconstruct the exact business identity used by the result component."""
        return {
            "source_artifact_ids": result_set.source_artifact_ids,
            "proposal_artifact_id": result_set.proposal_artifact_id,
            "proposal_id": result_set.proposal_id,
            "approval_request_id": result_set.approval_request_id,
            "permit_id": result_set.permit_id,
            "adapter_id": result_set.adapter_id,
            "adapter_config_hash": result_set.adapter_config_hash,
            "candidate_option_ids": result_set.candidate_option_ids,
            "request_hashes": tuple(
                item.request_hash for item in result_set.results
            ),
            "response_hashes": tuple(
                item.response_hash for item in result_set.results
            ),
            "execution_mode": result_set.execution_mode,
            "authority": result_set.authority,
        }

    @staticmethod
    def _one(
        artifacts: tuple[ArtifactEnvelope, ...],
        artifact_type: ArtifactType,
    ) -> ArtifactEnvelope:
        matches = tuple(
            item for item in artifacts if item.artifact_type is artifact_type
        )
        if len(matches) != 1:
            raise ValueError(
                f"Banking precheck execution requires one {artifact_type.value} artifact."
            )
        return matches[0]

    @staticmethod
    def _contract_errors(result: object) -> tuple[str, ...]:
        result_set = getattr(result, "result_set", None)
        artifacts = getattr(result, "artifacts", ())
        if result_set is None:
            return ("Banking precheck result component must return a typed result set.",)
        if len(artifacts) != 1 or (
            artifacts[0].artifact_type is not ArtifactType.BANKING_PRECHECK_RESULT_SET
        ):
            return ("Banking precheck result must return exactly one result-set draft.",)
        if artifacts[0].payload != result_set.model_dump(mode="json"):
            return ("Banking precheck result set and artifact draft disagree.",)
        if getattr(result, "approval_signals", ()) or getattr(
            result, "action_commands", ()
        ):
            return (
                "Banking precheck result cannot emit approvals or protected actions.",
            )
        if getattr(result, "missing_data_requests", ()):
            return ("Executed Banking precheck result cannot request workflow input.",)
        if (
            result_set.external_bank_submission
            or result_set.bank_approval_obtained
            or result_set.selection_performed
            or result_set.ranking_performed
            or result_set.documents_prepared
        ):
            return ("Banking precheck result exceeded the Phase B1 boundary.",)
        return ()

    async def _persist_or_reuse(
        self,
        draft: ArtifactDraft,
        context: ExecutionContext,
        report: ValidationReport,
    ) -> ArtifactEnvelope:
        existing = await self._artifacts.list_by_case(draft.evaluation_case_id)
        input_hash = artifact_input_hash(draft, context)
        same_input = tuple(
            item
            for item in existing
            if item.artifact_type is draft.artifact_type
            and item.input_hash == input_hash
        )
        if len(same_input) > 1:
            raise ValueError(
                "Banking precheck result identity has ambiguous persisted artifacts."
            )
        if same_input:
            current = same_input[0]
            exact_reuse = (
                current.validation_status in _VALID_ARTIFACT_STATUSES
                and current.payload == draft.payload
                and current.evidence_refs == draft.evidence_refs
                and current.input_artifact_ids == context.input_artifact_ids
            )
            if exact_reuse:
                return current
            raise ValueError(
                "Persisted Banking precheck result conflicts with its exact payload "
                "or lineage."
            )
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

    @staticmethod
    def _failed(
        errors: tuple[str, ...],
        *,
        warnings: tuple[str, ...] = (),
        events: tuple[dict[str, object], ...] = (),
        reports: tuple[ValidationReport, ...] = (),
        result_set: BankingPrecheckResultSet | None = None,
    ) -> BankingPrecheckResultExecutionResult:
        return BankingPrecheckResultExecutionResult(
            status=WorkflowStatus.FAILED_SAFE,
            component_status=ComponentStatus.FAILED_SAFE,
            current_node=WorkflowNode.BANKING_PRECHECK_EXECUTION.value,
            result_set=result_set,
            validation_reports=reports,
            validation_errors=errors,
            warnings=warnings,
            runtime_events=events,
        )
