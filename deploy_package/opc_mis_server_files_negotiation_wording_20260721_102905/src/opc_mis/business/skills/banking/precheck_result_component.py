"""Normalize authorized simulated Banking precheck responses without side effects."""

from collections.abc import Iterable

from pydantic import ValidationError

from opc_mis.business.skills.banking.precheck_result_context import (
    BankingPrecheckResultContext,
    BankingPrecheckResultContextError,
    BankingPrecheckResultContextLoader,
)
from opc_mis.domain.artifacts import ArtifactDraft, ArtifactEnvelope
from opc_mis.domain.banking_precheck_execution_models import (
    AuthorizedActionPermit,
    BankingCompanyProfileField,
    BankingPrecheckNormalizedResult,
    BankingPrecheckRawResponse,
    BankingPrecheckRequest,
    BankingPrecheckResultComponentInput,
    BankingPrecheckResultComponentResult,
    BankingPrecheckResultSet,
    banking_precheck_idempotency_key,
)
from opc_mis.domain.banking_precheck_submission_models import (
    BankingPrecheckSubmissionCandidate,
)
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import (
    ArtifactType,
    BankingPrecheckExecutionMode,
    BankingPrecheckFieldSource,
    BankingPrecheckResultAuthority,
    ComponentStatus,
    ProtectedAction,
    SourceType,
)
from opc_mis.domain.events import RuntimeEvent
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.lineage import deterministic_id
from opc_mis.domain.team_pack import SheetRegistry


class BankingPrecheckResultBuildError(RuntimeError):
    """Raised when approved requests and simulated responses do not match exactly."""


class BankingPrecheckResultComponent:
    """Create one non-binding result set from already-returned simulated responses."""

    component_id = "BANKING_PRECHECK_RESULT_COMPONENT"

    def __init__(self, *, context_loader: BankingPrecheckResultContextLoader) -> None:
        self._context_loader = context_loader

    async def execute(
        self,
        context: ExecutionContext,
    ) -> BankingPrecheckResultComponentResult:
        """Normalize raw responses; never invoke an adapter or protected action."""
        try:
            result_context = await self._context_loader.load(context)
            component_input = BankingPrecheckResultComponentInput.model_validate(
                context.component_input
            )
            result_set, evidence_refs = self._build(
                execution=context,
                context=result_context,
                component_input=component_input,
            )
        except ValidationError as exc:
            # Pydantic's rendered error can echo rejected input values. The component
            # input contains the in-memory company profile, so expose only a bounded
            # diagnostic at the workflow boundary.
            message = (
                "Invalid typed Banking precheck result input "
                f"({exc.error_count()} validation error(s))."
            )
            return BankingPrecheckResultComponentResult(
                status=ComponentStatus.FAILED_SAFE,
                runtime_events=(
                    RuntimeEvent(
                        event_type="BANKING_PRECHECK_RESULT_FAILED_SAFE",
                        message=message,
                    ),
                ),
            )
        except (
            BankingPrecheckResultContextError,
            BankingPrecheckResultBuildError,
        ) as exc:
            return BankingPrecheckResultComponentResult(
                status=ComponentStatus.FAILED_SAFE,
                runtime_events=(
                    RuntimeEvent(
                        event_type="BANKING_PRECHECK_RESULT_FAILED_SAFE",
                        message=str(exc),
                    ),
                ),
            )

        draft = ArtifactDraft(
            artifact_type=ArtifactType.BANKING_PRECHECK_RESULT_SET,
            evaluation_case_id=result_set.evaluation_case_id,
            producer=self.component_id,
            payload=result_set.model_dump(mode="json"),
            evidence_refs=evidence_refs,
            identity_inputs={
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
            },
        )
        outcome_warnings = tuple(
            dict.fromkeys(
                f"BANKING_PRECHECK_{item.outcome.value}"
                for item in result_set.results
            )
        )
        warnings = ("BANKING_PRECHECK_SIMULATED_NON_BINDING", *outcome_warnings)
        return BankingPrecheckResultComponentResult(
            status=ComponentStatus.COMPLETED_WITH_WARNINGS,
            result_set=result_set,
            artifacts=(draft,),
            warnings=warnings,
            runtime_events=(
                RuntimeEvent(
                    event_type="BANKING_PRECHECK_RESULTS_NORMALIZED",
                    message=(
                        "Banking normalized an authorized simulated precheck batch; "
                        "the results are non-binding and no option was selected."
                    ),
                    metadata={
                        "result_set_id": result_set.result_set_id,
                        "result_count": len(result_set.results),
                        "execution_mode": result_set.execution_mode.value,
                        "authority": result_set.authority.value,
                    },
                ),
            ),
        )

    def _build(
        self,
        *,
        execution: ExecutionContext,
        context: BankingPrecheckResultContext,
        component_input: BankingPrecheckResultComponentInput,
    ) -> tuple[BankingPrecheckResultSet, tuple[EvidenceRef, ...]]:
        proposal = context.proposal
        permit = component_input.permit
        self._validate_permit(execution, context, permit)
        requests = component_input.requests
        responses = component_input.raw_responses
        if len(requests) != len(proposal.candidates):
            raise BankingPrecheckResultBuildError(
                "Banking precheck requests must exactly cover proposal candidates."
            )
        if len(responses) != len(requests):
            raise BankingPrecheckResultBuildError(
                "Banking precheck responses must exactly cover request order."
            )
        evidence = self._source_evidence(context.source_artifacts)
        approval_evidence = self._approval_evidence(context, permit)
        self._merge_evidence(evidence, (approval_evidence,))
        normalized_results: list[BankingPrecheckNormalizedResult] = []
        for candidate, request, response in zip(
            proposal.candidates,
            requests,
            responses,
            strict=True,
        ):
            self._validate_request(
                context=context,
                permit=permit,
                candidate=candidate,
                request=request,
                evidence=evidence,
            )
            self._validate_response(request=request, response=response)
            policy_evidence = self._scenario_evidence(
                context=context,
                adapter_id=component_input.adapter_id,
                adapter_config_hash=component_input.adapter_config_hash,
                response=response,
            )
            self._merge_evidence(evidence, (policy_evidence,))
            normalized = self._normalized_result(
                context=context,
                candidate=candidate,
                request=request,
                response=response,
                approval_evidence=approval_evidence,
                policy_evidence=policy_evidence,
                evidence=evidence,
            )
            normalized_results.append(normalized)

        normalized_tuple = tuple(normalized_results)
        result_set_id = deterministic_id(
            "BPRS",
            context.proposal_artifact.artifact_id,
            proposal.proposal_id,
            permit.approval_request_id,
            permit.permit_id,
            component_input.adapter_id,
            component_input.adapter_config_hash,
            tuple(item.normalized_result_id for item in normalized_tuple),
            context.source_artifact_ids,
        )
        evidence_refs = tuple(evidence[key] for key in sorted(evidence))
        result_set = BankingPrecheckResultSet(
            result_set_id=result_set_id,
            evaluation_case_id=proposal.evaluation_case_id,
            dataset_id=proposal.dataset_id,
            contract_id=proposal.contract_id,
            proposal_artifact_id=context.proposal_artifact.artifact_id,
            proposal_id=proposal.proposal_id,
            approval_request_id=permit.approval_request_id,
            permit_id=permit.permit_id,
            execution_mode=BankingPrecheckExecutionMode.SIMULATED,
            authority=BankingPrecheckResultAuthority.SIMULATED_NON_BINDING,
            adapter_id=component_input.adapter_id,
            adapter_config_hash=component_input.adapter_config_hash,
            candidate_option_ids=proposal.candidate_option_ids,
            results=normalized_tuple,
            source_artifact_ids=context.source_artifact_ids,
            evidence_ids=tuple(item.evidence_id for item in evidence_refs),
            adapter_invoked=True,
            external_bank_submission=False,
            bank_approval_obtained=False,
            selection_performed=False,
            ranking_performed=False,
            documents_prepared=False,
        )
        return result_set, evidence_refs

    @staticmethod
    def _validate_permit(
        execution: ExecutionContext,
        context: BankingPrecheckResultContext,
        permit: AuthorizedActionPermit,
    ) -> None:
        artifact = context.proposal_artifact
        if permit.workflow_run_id != execution.workflow_run_id:
            raise BankingPrecheckResultBuildError(
                "Authorized permit belongs to another workflow run."
            )
        if permit.evaluation_case_id != context.proposal.evaluation_case_id:
            raise BankingPrecheckResultBuildError(
                "Authorized permit belongs to another evaluation case."
            )
        if permit.protected_action is not ProtectedAction.SUBMIT_BANKING_PRECHECK:
            raise BankingPrecheckResultBuildError(
                "Authorized permit does not cover Banking precheck submission."
            )
        if (
            permit.subject_artifact_id != artifact.artifact_id
            or permit.subject_artifact_version != artifact.version
            or permit.subject_input_hash != artifact.input_hash
        ):
            raise BankingPrecheckResultBuildError(
                "Authorized permit does not bind the exact proposal envelope."
            )

    def _validate_request(
        self,
        *,
        context: BankingPrecheckResultContext,
        permit: AuthorizedActionPermit,
        candidate: BankingPrecheckSubmissionCandidate,
        request: BankingPrecheckRequest,
        evidence: dict[str, EvidenceRef],
    ) -> None:
        proposal = context.proposal
        expected_identity = (
            proposal.dataset_id,
            proposal.evaluation_case_id,
            proposal.contract_id,
            context.proposal_artifact.artifact_id,
            proposal.proposal_id,
            candidate.proposal_item_id,
            candidate.option_id,
            candidate.bank_product_id,
            candidate.api_id,
            candidate.api_provider,
            candidate.api_method,
            candidate.api_endpoint,
            proposal.requested_amount,
            proposal.requested_amount_currency,
        )
        actual_identity = (
            request.dataset_id,
            request.evaluation_case_id,
            request.contract_id,
            request.proposal_artifact_id,
            request.proposal_id,
            request.proposal_item_id,
            request.option_id,
            request.bank_product_id,
            request.api_id,
            request.api_provider,
            request.api_method,
            request.api_endpoint,
            request.requested_amount,
            request.requested_amount_currency,
        )
        if actual_identity != expected_identity:
            raise BankingPrecheckResultBuildError(
                f"Request {request.request_id} does not match proposal item "
                f"{candidate.proposal_item_id}."
            )
        expected_idempotency = banking_precheck_idempotency_key(
            permit_id=permit.permit_id,
            proposal_artifact_id=context.proposal_artifact.artifact_id,
            proposal_item_id=candidate.proposal_item_id,
            request_hash=request.request_hash,
        )
        if request.idempotency_key != expected_idempotency:
            raise BankingPrecheckResultBuildError(
                f"Request {request.request_id} has an invalid idempotency key."
            )
        expected_profile = self._company_profile(
            context=context,
            candidate=candidate,
            evidence=evidence,
        )
        if request.company_profile != expected_profile:
            raise BankingPrecheckResultBuildError(
                f"Request {request.request_id} company profile is not evidence-bound."
            )

    @staticmethod
    def _validate_response(
        *,
        request: BankingPrecheckRequest,
        response: BankingPrecheckRawResponse,
    ) -> None:
        if (
            response.request_id != request.request_id
            or response.idempotency_key != request.idempotency_key
            or response.api_id != request.api_id
            or response.api_provider != request.api_provider
            or response.requested_amount != request.requested_amount
            or response.currency is not request.requested_amount_currency
            or response.authority
            is not BankingPrecheckResultAuthority.SIMULATED_NON_BINDING
        ):
            raise BankingPrecheckResultBuildError(
                f"Raw response does not match request {request.request_id}."
            )

    @staticmethod
    def _company_profile(
        *,
        context: BankingPrecheckResultContext,
        candidate: BankingPrecheckSubmissionCandidate,
        evidence: dict[str, EvidenceRef],
    ) -> tuple[BankingCompanyProfileField, ...]:
        bindings = tuple(
            item
            for item in candidate.field_bindings
            if item.source is BankingPrecheckFieldSource.OPC_PROFILE
        )
        if len(bindings) != 1:
            raise BankingPrecheckResultBuildError(
                f"Proposal item {candidate.proposal_item_id} requires exactly one "
                "OPC_PROFILE binding."
            )
        fields: list[BankingCompanyProfileField] = []
        for record_id in bindings[0].source_record_ids:
            field_matches = tuple(
                item
                for item in evidence.values()
                if item.source_type is SourceType.TEAM_PACK
                and item.sheet == SheetRegistry.OPC_PROFILE.sheet_name
                and item.record_id == record_id
                and item.field == "field"
            )
            value_matches = tuple(
                item
                for item in evidence.values()
                if item.source_type is SourceType.TEAM_PACK
                and item.sheet == SheetRegistry.OPC_PROFILE.sheet_name
                and item.record_id == record_id
                and item.field == "value"
            )
            if (
                len(field_matches) != 1
                or len(value_matches) != 1
                or field_matches[0].display_value != record_id
            ):
                raise BankingPrecheckResultBuildError(
                    f"OPC profile record {record_id} lacks exact field/value evidence."
                )
            try:
                fields.append(
                    BankingCompanyProfileField(
                        field=record_id,
                        value=value_matches[0].display_value,
                    )
                )
            except ValidationError as exc:
                raise BankingPrecheckResultBuildError(
                    f"OPC profile record {record_id} is not a JSON-safe scalar."
                ) from exc
        return tuple(fields)

    def _normalized_result(
        self,
        *,
        context: BankingPrecheckResultContext,
        candidate: BankingPrecheckSubmissionCandidate,
        request: BankingPrecheckRequest,
        response: BankingPrecheckRawResponse,
        approval_evidence: EvidenceRef,
        policy_evidence: EvidenceRef,
        evidence: dict[str, EvidenceRef],
    ) -> BankingPrecheckNormalizedResult:
        missing_candidate_evidence = tuple(
            item for item in candidate.evidence_ids if item not in evidence
        )
        if missing_candidate_evidence:
            raise BankingPrecheckResultBuildError(
                f"Proposal item {candidate.proposal_item_id} references unavailable "
                "evidence."
            )
        supporting = (
            *(evidence[item] for item in candidate.evidence_ids),
            approval_evidence,
            policy_evidence,
        )
        normalized_result_id = deterministic_id(
            "BPNR",
            context.proposal_artifact.artifact_id,
            candidate.proposal_item_id,
            request.request_id,
            request.request_hash,
            response.response_hash,
        )
        display = {
            "option_id": candidate.option_id,
            "outcome": response.outcome.value,
            "eligibility_status": response.eligibility_status.value,
            "guarantee_decision": response.guarantee_decision.value,
            "requested_amount": response.requested_amount,
            "supported_amount": response.supported_amount,
            "currency": response.currency.value,
            "required_documents": list(response.required_documents),
            "approval_conditions": list(response.approval_conditions),
            "execution_mode": response.execution_mode.value,
            "authority": response.authority.value,
            "non_binding": True,
        }
        derived = EvidenceRef(
            evidence_id=deterministic_id(
                "EVD",
                context.proposal.dataset_id,
                SourceType.DERIVED,
                "BANKING_PRECHECK_RESULT_SET",
                normalized_result_id,
                display,
                tuple(item.evidence_id for item in supporting),
            ),
            source_type=SourceType.DERIVED,
            sheet="BANKING_PRECHECK_RESULT_SET",
            row_number=0,
            record_id=normalized_result_id,
            field="normalized_result",
            display_value=display,
            source_evidence_ids=tuple(item.evidence_id for item in supporting),
        )
        self._merge_evidence(evidence, (derived,))
        result_evidence_ids = tuple(
            dict.fromkeys(
                (
                    *candidate.evidence_ids,
                    approval_evidence.evidence_id,
                    policy_evidence.evidence_id,
                    derived.evidence_id,
                )
            )
        )
        return BankingPrecheckNormalizedResult(
            normalized_result_id=normalized_result_id,
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            proposal_item_id=candidate.proposal_item_id,
            option_id=candidate.option_id,
            bank_product_id=candidate.bank_product_id,
            api_id=response.api_id,
            api_provider=response.api_provider,
            execution_mode=response.execution_mode,
            provider_reference=response.provider_reference,
            scenario_id=response.scenario_id,
            scenario_version=response.scenario_version,
            scenario_hash=response.scenario_hash,
            outcome=response.outcome,
            message=response.message,
            reason_codes=response.reason_codes,
            required_follow_up_fields=response.required_follow_up_fields,
            requested_amount=response.requested_amount,
            supported_amount=response.supported_amount,
            currency=response.currency,
            eligibility_status=response.eligibility_status,
            guarantee_decision=response.guarantee_decision,
            required_documents=response.required_documents,
            approval_conditions=response.approval_conditions,
            request_hash=request.request_hash,
            response_hash=response.response_hash,
            authority=BankingPrecheckResultAuthority.SIMULATED_NON_BINDING,
            non_binding=True,
            evidence_ids=result_evidence_ids,
        )

    @staticmethod
    def _approval_evidence(
        context: BankingPrecheckResultContext,
        permit: AuthorizedActionPermit,
    ) -> EvidenceRef:
        display = {
            "permit_id": permit.permit_id,
            "approval_request_id": permit.approval_request_id,
            "protected_action": permit.protected_action.value,
            "subject_artifact_id": permit.subject_artifact_id,
            "subject_artifact_version": permit.subject_artifact_version,
            "subject_input_hash": permit.subject_input_hash,
            "authorized_by": permit.authorized_by,
            "authorized_at": permit.authorized_at.isoformat(),
        }
        return EvidenceRef(
            evidence_id=deterministic_id(
                "EVD",
                context.proposal.dataset_id,
                SourceType.USER_INPUT,
                "APPROVAL_AUTHORIZATION",
                permit.approval_request_id,
                display,
            ),
            source_type=SourceType.USER_INPUT,
            sheet="APPROVAL_AUTHORIZATION",
            row_number=0,
            record_id=permit.approval_request_id,
            field="authorized_action_permit",
            display_value=display,
        )

    @staticmethod
    def _scenario_evidence(
        *,
        context: BankingPrecheckResultContext,
        adapter_id: str,
        adapter_config_hash: str,
        response: BankingPrecheckRawResponse,
    ) -> EvidenceRef:
        display = {
            "adapter_id": adapter_id,
            "adapter_config_hash": adapter_config_hash,
            "api_id": response.api_id,
            "api_provider": response.api_provider,
            "provider_reference": response.provider_reference,
            "scenario_id": response.scenario_id,
            "scenario_version": response.scenario_version,
            "scenario_hash": response.scenario_hash,
            "outcome": response.outcome.value,
            "message": response.message,
            "reason_codes": list(response.reason_codes),
            "required_follow_up_fields": list(
                response.required_follow_up_fields
            ),
            "requested_amount": response.requested_amount,
            "supported_amount": response.supported_amount,
            "currency": response.currency.value,
            "eligibility_status": response.eligibility_status.value,
            "guarantee_decision": response.guarantee_decision.value,
            "required_documents": list(response.required_documents),
            "approval_conditions": list(response.approval_conditions),
            "authority": response.authority.value,
            "non_binding": response.non_binding,
        }
        return EvidenceRef(
            evidence_id=deterministic_id(
                "EVD",
                context.proposal.dataset_id,
                SourceType.POLICY_CONFIG,
                "BANKING_PRECHECK_SIMULATION_POLICY",
                response.scenario_id,
                display,
            ),
            source_type=SourceType.POLICY_CONFIG,
            sheet="BANKING_PRECHECK_SIMULATION_POLICY",
            row_number=0,
            record_id=response.scenario_id,
            field="scenario",
            display_value=display,
        )

    @staticmethod
    def _source_evidence(
        artifacts: Iterable[ArtifactEnvelope],
    ) -> dict[str, EvidenceRef]:
        evidence: dict[str, EvidenceRef] = {}
        for artifact in artifacts:
            for item in artifact.evidence_refs:
                existing = evidence.get(item.evidence_id)
                if existing is not None and existing != item:
                    raise BankingPrecheckResultBuildError(
                        f"Conflicting evidence payload for {item.evidence_id}."
                    )
                evidence[item.evidence_id] = item
        if not evidence:
            raise BankingPrecheckResultBuildError(
                "Banking precheck result requires proposal evidence."
            )
        return evidence

    @staticmethod
    def _merge_evidence(
        target: dict[str, EvidenceRef],
        source: Iterable[EvidenceRef],
    ) -> None:
        for item in source:
            existing = target.get(item.evidence_id)
            if existing is not None and existing != item:
                raise BankingPrecheckResultBuildError(
                    f"Conflicting evidence payload for {item.evidence_id}."
                )
            target[item.evidence_id] = item
