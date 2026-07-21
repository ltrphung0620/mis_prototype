"""Unit tests for the pure Phase B1 Banking precheck result component."""

import asyncio
import json
from datetime import UTC, datetime

from opc_mis.business.skills.banking.precheck_result_component import (
    BankingPrecheckResultComponent,
)
from opc_mis.business.skills.banking.precheck_result_context import (
    BankingPrecheckResultContextLoader,
)
from opc_mis.domain.banking_precheck_execution_models import (
    AuthorizedActionPermit,
    BankingCompanyProfileField,
    BankingPrecheckRawResponse,
    BankingPrecheckRequest,
    BankingPrecheckResultComponentInput,
    banking_precheck_idempotency_key,
    banking_precheck_request_hash,
    banking_precheck_response_hash,
)
from opc_mis.domain.banking_precheck_submission_models import (
    BankingPrecheckSubmissionCandidate,
    BankingPrecheckSubmissionProposal,
)
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import (
    ArtifactType,
    BankingPrecheckExecutionMode,
    BankingPrecheckOutcome,
    BankingPrecheckResultAuthority,
    ComponentStatus,
    ProtectedAction,
    ProviderEligibilityStatus,
    ProviderGuaranteeDecision,
    SourceType,
)
from opc_mis.domain.lineage import deterministic_id
from opc_mis.infrastructure.persistence.memory_artifact_repository import (
    InMemoryArtifactRepository,
)
from tests.unit.test_banking_precheck_submission_proposal import (
    CASE_ID,
    DATASET_ID,
    _envelope,
)
from tests.unit.test_banking_precheck_submission_proposal import (
    _setup as _proposal_setup,
)

PROPOSAL_ARTIFACT_ID = "ART-PROPOSAL-PHASE-B1"
WORKFLOW_RUN_ID = "WORKFLOW-PHASE-B1"
APPROVAL_REQUEST_ID = "APPROVAL-PHASE-B1"
PERMIT_ID = "PERMIT-PHASE-B1"
ADAPTER_ID = "SIMULATED-BANKING-PRECHECK-ADAPTER"
ADAPTER_CONFIG_HASH = "SIMULATION-CONFIG-HASH"


def _profile() -> tuple[BankingCompanyProfileField, ...]:
    return (
        BankingCompanyProfileField(
            field="company_id",
            value="OPC-PRECHECK-PROPOSAL",
        ),
        BankingCompanyProfileField(
            field="business_model",
            value="B2B",
        ),
    )


def _permit(*, subject_input_hash: str) -> AuthorizedActionPermit:
    return AuthorizedActionPermit(
        permit_id=PERMIT_ID,
        workflow_run_id=WORKFLOW_RUN_ID,
        evaluation_case_id=CASE_ID,
        approval_request_id=APPROVAL_REQUEST_ID,
        protected_action=ProtectedAction.SUBMIT_BANKING_PRECHECK,
        subject_artifact_id=PROPOSAL_ARTIFACT_ID,
        subject_artifact_version=1,
        subject_input_hash=subject_input_hash,
        authorized_by="FOUNDER",
        authorized_at=datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
    )


def _request(
    *,
    proposal: BankingPrecheckSubmissionProposal,
    candidate: BankingPrecheckSubmissionCandidate,
    permit: AuthorizedActionPermit,
    company_profile: tuple[BankingCompanyProfileField, ...] | None = None,
) -> BankingPrecheckRequest:
    profile = company_profile or _profile()
    request_hash = banking_precheck_request_hash(
        dataset_id=proposal.dataset_id,
        evaluation_case_id=proposal.evaluation_case_id,
        contract_id=proposal.contract_id,
        proposal_artifact_id=PROPOSAL_ARTIFACT_ID,
        proposal_id=proposal.proposal_id,
        proposal_item_id=candidate.proposal_item_id,
        option_id=candidate.option_id,
        bank_product_id=candidate.bank_product_id,
        api_id=candidate.api_id,
        api_provider=candidate.api_provider,
        api_method=candidate.api_method,
        api_endpoint=candidate.api_endpoint,
        requested_amount=proposal.requested_amount,
        requested_amount_currency=proposal.requested_amount_currency,
        company_profile=profile,
    )
    return BankingPrecheckRequest(
        request_id=deterministic_id(
            "BPRQ",
            PROPOSAL_ARTIFACT_ID,
            candidate.proposal_item_id,
            request_hash,
        ),
        dataset_id=proposal.dataset_id,
        evaluation_case_id=proposal.evaluation_case_id,
        contract_id=proposal.contract_id,
        proposal_artifact_id=PROPOSAL_ARTIFACT_ID,
        proposal_id=proposal.proposal_id,
        proposal_item_id=candidate.proposal_item_id,
        option_id=candidate.option_id,
        bank_product_id=candidate.bank_product_id,
        api_id=candidate.api_id,
        api_provider=candidate.api_provider,
        api_method=candidate.api_method,
        api_endpoint=candidate.api_endpoint,
        requested_amount=proposal.requested_amount,
        requested_amount_currency=proposal.requested_amount_currency,
        company_profile=profile,
        request_hash=request_hash,
        idempotency_key=banking_precheck_idempotency_key(
            permit_id=permit.permit_id,
            proposal_artifact_id=PROPOSAL_ARTIFACT_ID,
            proposal_item_id=candidate.proposal_item_id,
            request_hash=request_hash,
        ),
    )


def _response(
    request: BankingPrecheckRequest,
    *,
    index: int,
    outcome: BankingPrecheckOutcome,
) -> BankingPrecheckRawResponse:
    is_conditional = outcome is BankingPrecheckOutcome.CONDITIONAL_PRECHECK
    is_not_eligible = outcome is BankingPrecheckOutcome.NOT_ELIGIBLE
    eligibility_status = (
        ProviderEligibilityStatus.ELIGIBLE
        if is_conditional
        else ProviderEligibilityStatus.NOT_ELIGIBLE
        if is_not_eligible
        else ProviderEligibilityStatus.NOT_EVALUABLE
    )
    guarantee_decision = (
        ProviderGuaranteeDecision.CONDITIONAL
        if is_conditional
        else ProviderGuaranteeDecision.DECLINED
        if is_not_eligible
        else ProviderGuaranteeDecision.NO_DECISION
    )
    provider_reference = deterministic_id(
        "SIMREF",
        request.idempotency_key,
        index,
    )
    scenario_id = f"SIM-SCENARIO-{index}"
    scenario_version = "1"
    scenario_hash = deterministic_id(
        "SIMSCN",
        scenario_id,
        outcome,
    )
    message = (
        "Simulated provider returned a non-binding conditional precheck."
        if is_conditional
        else "Simulated provider returned no binding recommendation."
    )
    reason_codes = (
        ("SIMULATED_CONDITIONAL_PRECHECK",)
        if is_conditional
        else ("SIMULATED_NO_PROVIDER_DECISION",)
    )
    follow_up = (
        ("supporting_document_reference",)
        if outcome is BankingPrecheckOutcome.MISSING_EVIDENCE
        else ()
    )
    response_hash = banking_precheck_response_hash(
        request_id=request.request_id,
        idempotency_key=request.idempotency_key,
        api_id=request.api_id,
        api_provider=request.api_provider,
        execution_mode=BankingPrecheckExecutionMode.SIMULATED,
        provider_reference=provider_reference,
        scenario_id=scenario_id,
        scenario_version=scenario_version,
        scenario_hash=scenario_hash,
        outcome=outcome,
        message=message,
        reason_codes=reason_codes,
        required_follow_up_fields=follow_up,
        requested_amount=request.requested_amount,
        supported_amount=request.requested_amount if is_conditional else None,
        currency=request.requested_amount_currency,
        eligibility_status=eligibility_status,
        guarantee_decision=guarantee_decision,
        required_documents=(
            ("SIGNED_CONTRACT", "COMPANY_PROFILE") if is_conditional else ()
        ),
        approval_conditions=(
            ("CONTRACT_SIGNED",) if is_conditional else ()
        ),
        authority=BankingPrecheckResultAuthority.SIMULATED_NON_BINDING,
        non_binding=True,
    )
    return BankingPrecheckRawResponse(
        request_id=request.request_id,
        idempotency_key=request.idempotency_key,
        api_id=request.api_id,
        api_provider=request.api_provider,
        execution_mode=BankingPrecheckExecutionMode.SIMULATED,
        provider_reference=provider_reference,
        scenario_id=scenario_id,
        scenario_version=scenario_version,
        scenario_hash=scenario_hash,
        outcome=outcome,
        message=message,
        reason_codes=reason_codes,
        required_follow_up_fields=follow_up,
        requested_amount=request.requested_amount,
        supported_amount=request.requested_amount if is_conditional else None,
        currency=request.requested_amount_currency,
        eligibility_status=eligibility_status,
        guarantee_decision=guarantee_decision,
        required_documents=(
            ("SIGNED_CONTRACT", "COMPANY_PROFILE") if is_conditional else ()
        ),
        approval_conditions=(
            ("CONTRACT_SIGNED",) if is_conditional else ()
        ),
        authority=BankingPrecheckResultAuthority.SIMULATED_NON_BINDING,
        response_hash=response_hash,
        non_binding=True,
    )


async def _setup(
    *,
    candidate_count: int = 2,
) -> tuple[
    InMemoryArtifactRepository,
    BankingPrecheckResultComponent,
    ExecutionContext,
    BankingPrecheckResultComponentInput,
]:
    repository, proposal_skill, proposal_execution = await _proposal_setup(
        ready_count=candidate_count
    )
    proposal_result = await proposal_skill.execute(proposal_execution)
    assert proposal_result.proposal is not None
    proposal_draft = proposal_result.artifacts[0]
    proposal_artifact = _envelope(
        artifact_id=PROPOSAL_ARTIFACT_ID,
        artifact_type=ArtifactType.BANKING_PRECHECK_SUBMISSION_PROPOSAL,
        payload=proposal_result.proposal.model_dump(mode="json"),
        evidence_refs=proposal_draft.evidence_refs,
    )
    await repository.save(proposal_artifact)
    permit = _permit(subject_input_hash=proposal_artifact.input_hash)
    requests = tuple(
        _request(
            proposal=proposal_result.proposal,
            candidate=candidate,
            permit=permit,
        )
        for candidate in proposal_result.proposal.candidates
    )
    responses = tuple(
        _response(
            request,
            index=index,
            outcome=(
                BankingPrecheckOutcome.NO_RECOMMENDATION
                if index == 1
                else BankingPrecheckOutcome.MISSING_EVIDENCE
            ),
        )
        for index, request in enumerate(requests, start=1)
    )
    component_input = BankingPrecheckResultComponentInput(
        permit=permit,
        requests=requests,
        raw_responses=responses,
        adapter_id=ADAPTER_ID,
        adapter_config_hash=ADAPTER_CONFIG_HASH,
    )
    execution = ExecutionContext(
        evaluation_case_id=CASE_ID,
        dataset_id=DATASET_ID,
        workflow_run_id=WORKFLOW_RUN_ID,
        input_artifact_ids=(
            proposal_artifact.artifact_id,
            *proposal_result.proposal.source_artifact_ids,
        ),
        requested_scope=proposal_execution.requested_scope,
        component_input=component_input.model_dump(mode="json"),
        current_node="BANKING_PRECHECK_RESULT_SET",
    )
    return (
        repository,
        BankingPrecheckResultComponent(
            context_loader=BankingPrecheckResultContextLoader(
                artifacts=repository
            )
        ),
        execution,
        component_input,
    )


def test_component_normalizes_exact_batch_without_selection_or_side_effects() -> None:
    async def scenario() -> None:
        repository, component, execution, component_input = await _setup()
        before = await repository.list_by_case(CASE_ID)

        result = await component.execute(execution)

        assert result.status is ComponentStatus.COMPLETED_WITH_WARNINGS
        assert result.result_set is not None
        result_set = result.result_set
        assert result_set.proposal_artifact_id == PROPOSAL_ARTIFACT_ID
        assert result_set.approval_request_id == APPROVAL_REQUEST_ID
        assert result_set.permit_id == PERMIT_ID
        assert result_set.execution_mode is BankingPrecheckExecutionMode.SIMULATED
        assert result_set.authority is (
            BankingPrecheckResultAuthority.SIMULATED_NON_BINDING
        )
        assert result_set.candidate_option_ids == tuple(
            item.option_id for item in component_input.requests
        )
        assert tuple(item.request_id for item in result_set.results) == tuple(
            item.request_id for item in component_input.requests
        )
        assert tuple(item.outcome for item in result_set.results) == (
            BankingPrecheckOutcome.NO_RECOMMENDATION,
            BankingPrecheckOutcome.MISSING_EVIDENCE,
        )
        assert result_set.adapter_invoked is True
        assert result_set.external_bank_submission is False
        assert result_set.bank_approval_obtained is False
        assert result_set.selection_performed is False
        assert result_set.ranking_performed is False
        assert result_set.documents_prepared is False
        assert len(result.artifacts) == 1
        assert result.artifacts[0].artifact_type is (
            ArtifactType.BANKING_PRECHECK_RESULT_SET
        )
        evidence_types = {
            item.source_type for item in result.artifacts[0].evidence_refs
        }
        assert {
            SourceType.TEAM_PACK,
            SourceType.USER_INPUT,
            SourceType.POLICY_CONFIG,
            SourceType.DERIVED,
        }.issubset(evidence_types)
        assert set(result_set.evidence_ids) == {
            item.evidence_id for item in result.artifacts[0].evidence_refs
        }
        assert result.approval_signals == ()
        assert result.action_commands == ()
        assert result.missing_data_requests == ()
        assert await repository.list_by_case(CASE_ID) == before
        serialized = json.dumps(result.artifacts[0].payload, sort_keys=True)
        assert '"company_profile":' not in serialized
        assert "OPC-PRECHECK-PROPOSAL" not in serialized
        assert "selected_option" not in serialized

    asyncio.run(scenario())


def test_result_identity_is_stable_for_identical_business_inputs() -> None:
    async def scenario() -> None:
        _, component, execution, _ = await _setup(candidate_count=1)

        first = await component.execute(execution)
        retried = await component.execute(execution)

        assert first.result_set is not None
        assert retried.result_set is not None
        assert first.result_set.result_set_id == retried.result_set.result_set_id
        assert first.result_set.results[0].normalized_result_id == (
            retried.result_set.results[0].normalized_result_id
        )
        assert first.artifacts[0].identity_inputs == retried.artifacts[0].identity_inputs
        assert first.artifacts[0].evidence_refs == retried.artifacts[0].evidence_refs

    asyncio.run(scenario())


def test_component_preserves_conditional_provider_terms_and_lineage() -> None:
    async def scenario() -> None:
        _, component, execution, component_input = await _setup(candidate_count=1)
        request = component_input.requests[0]
        response = _response(
            request,
            index=1,
            outcome=BankingPrecheckOutcome.CONDITIONAL_PRECHECK,
        )
        changed = component_input.model_copy(update={"raw_responses": (response,)})

        result = await component.execute(
            execution.model_copy(
                update={"component_input": changed.model_dump(mode="json")}
            )
        )

        assert result.result_set is not None
        normalized = result.result_set.results[0]
        assert normalized.outcome is BankingPrecheckOutcome.CONDITIONAL_PRECHECK
        assert normalized.requested_amount == request.requested_amount
        assert normalized.supported_amount == request.requested_amount
        assert normalized.eligibility_status is ProviderEligibilityStatus.ELIGIBLE
        assert (
            normalized.guarantee_decision
            is ProviderGuaranteeDecision.CONDITIONAL
        )
        assert normalized.required_documents == (
            "SIGNED_CONTRACT",
            "COMPANY_PROFILE",
        )
        assert normalized.approval_conditions == ("CONTRACT_SIGNED",)
        derived = next(
            item
            for item in result.artifacts[0].evidence_refs
            if item.sheet == "BANKING_PRECHECK_RESULT_SET"
            and item.record_id == normalized.normalized_result_id
        )
        assert derived.display_value["requested_amount"] == request.requested_amount
        assert derived.display_value["supported_amount"] == request.requested_amount
        assert derived.display_value["required_documents"] == [
            "SIGNED_CONTRACT",
            "COMPANY_PROFILE",
        ]

    asyncio.run(scenario())


def test_component_rejects_a_permit_for_another_proposal_envelope() -> None:
    async def scenario() -> None:
        _, component, execution, component_input = await _setup(candidate_count=1)
        wrong_permit = component_input.permit.model_copy(
            update={"subject_input_hash": "ANOTHER-SUBJECT-HASH"}
        )
        changed = component_input.model_copy(update={"permit": wrong_permit})

        result = await component.execute(
            execution.model_copy(
                update={"component_input": changed.model_dump(mode="json")}
            )
        )

        assert result.status is ComponentStatus.FAILED_SAFE
        assert result.result_set is None
        assert result.artifacts == ()
        assert "exact proposal envelope" in result.runtime_events[0].message

    asyncio.run(scenario())


def test_component_rejects_missing_or_reordered_candidate_responses() -> None:
    async def scenario() -> None:
        _, component, execution, component_input = await _setup()
        reversed_input = component_input.model_copy(
            update={
                "raw_responses": tuple(reversed(component_input.raw_responses))
            }
        )

        result = await component.execute(
            execution.model_copy(
                update={
                    "component_input": reversed_input.model_dump(mode="json")
                }
            )
        )

        assert result.status is ComponentStatus.FAILED_SAFE
        assert result.result_set is None
        assert "does not match request" in result.runtime_events[0].message

    asyncio.run(scenario())


def test_component_rejects_profile_values_not_bound_to_proposal_evidence() -> None:
    async def scenario() -> None:
        _, component, execution, component_input = await _setup(candidate_count=1)
        proposal_request = component_input.requests[0]
        changed_profile = (
            BankingCompanyProfileField(field="company_id", value="INVENTED"),
            BankingCompanyProfileField(field="business_model", value="B2B"),
        )
        request_hash = banking_precheck_request_hash(
            dataset_id=proposal_request.dataset_id,
            evaluation_case_id=proposal_request.evaluation_case_id,
            contract_id=proposal_request.contract_id,
            proposal_artifact_id=proposal_request.proposal_artifact_id,
            proposal_id=proposal_request.proposal_id,
            proposal_item_id=proposal_request.proposal_item_id,
            option_id=proposal_request.option_id,
            bank_product_id=proposal_request.bank_product_id,
            api_id=proposal_request.api_id,
            api_provider=proposal_request.api_provider,
            api_method=proposal_request.api_method,
            api_endpoint=proposal_request.api_endpoint,
            requested_amount=proposal_request.requested_amount,
            requested_amount_currency=proposal_request.requested_amount_currency,
            company_profile=changed_profile,
        )
        changed_request = proposal_request.model_copy(
            update={
                "company_profile": changed_profile,
                "request_hash": request_hash,
                "idempotency_key": banking_precheck_idempotency_key(
                    permit_id=component_input.permit.permit_id,
                    proposal_artifact_id=proposal_request.proposal_artifact_id,
                    proposal_item_id=proposal_request.proposal_item_id,
                    request_hash=request_hash,
                ),
            }
        )
        changed = component_input.model_copy(
            update={"requests": (changed_request,)}
        )

        result = await component.execute(
            execution.model_copy(
                update={"component_input": changed.model_dump(mode="json")}
            )
        )

        assert result.status is ComponentStatus.FAILED_SAFE
        assert result.result_set is None
        assert "company profile is not evidence-bound" in (
            result.runtime_events[0].message
        )

    asyncio.run(scenario())


def test_sensitive_company_profile_values_are_hidden_from_repr() -> None:
    async def scenario() -> None:
        _, _, _, component_input = await _setup(candidate_count=1)

        assert "OPC-PRECHECK-PROPOSAL" not in repr(_profile()[0])
        assert "OPC-PRECHECK-PROPOSAL" not in repr(component_input.requests[0])

    asyncio.run(scenario())


def test_invalid_typed_input_does_not_echo_company_profile_values() -> None:
    async def scenario() -> None:
        _, component, execution, component_input = await _setup(candidate_count=1)
        raw_input = component_input.model_dump(mode="json")
        secret = "PRIVATE-PROFILE-VALUE-DO-NOT-ECHO"
        raw_input["requests"][0]["company_profile"][0]["value"] = [secret]

        result = await component.execute(
            execution.model_copy(update={"component_input": raw_input})
        )

        assert result.status is ComponentStatus.FAILED_SAFE
        assert result.result_set is None
        assert secret not in result.runtime_events[0].message
        assert "Invalid typed Banking precheck result input" in (
            result.runtime_events[0].message
        )

    asyncio.run(scenario())
