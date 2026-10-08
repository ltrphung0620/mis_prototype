"""Regression tests for fail-closed Phase B1 result-set validation."""

import asyncio
from collections.abc import Callable

import pytest

from opc_mis.domain.artifacts import ArtifactDraft
from opc_mis.domain.banking_precheck_execution_models import (
    BankingPrecheckRawResponse,
    BankingPrecheckSimulationPolicy,
    BankingPrecheckSimulationPolicyDocument,
    BankingPrecheckSimulationScenario,
    banking_precheck_response_hash,
)
from opc_mis.domain.enums import (
    BankingPrecheckExecutionMode,
    BankingPrecheckOutcome,
    BankingPrecheckResultAuthority,
    ProviderEligibilityStatus,
    ProviderGuaranteeDecision,
    SourceType,
    ValidationStatus,
)
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.lineage import deterministic_id
from opc_mis.governance.evidence_validator import EvidenceValidator
from opc_mis.infrastructure.config.banking_precheck_simulation_policy import (
    canonical_simulation_policy_hash,
)
from tests.unit.test_banking_precheck_result_component import _setup


def _policy(
    *,
    api_id: str,
    api_provider: str,
) -> BankingPrecheckSimulationPolicy:
    scenario = BankingPrecheckSimulationScenario(
        scenario_id="SCENARIO-VALIDATOR-EXACT",
        api_id=api_id,
        api_provider=api_provider,
        outcome=BankingPrecheckOutcome.NO_RECOMMENDATION,
        message="Exact non-binding simulated outcome from server policy.",
        reason_codes=("SIMULATED_NO_PROVIDER_DECISION",),
    )
    document = BankingPrecheckSimulationPolicyDocument(
        configuration_id="BANKING-PRECHECK-VALIDATOR-TEST",
        configuration_version="validator-test-v1",
        scenarios=(scenario,),
    )
    return BankingPrecheckSimulationPolicy(
        **document.model_dump(mode="python"),
        configuration_hash=canonical_simulation_policy_hash(document),
    )


async def _draft_and_policy() -> tuple[
    ArtifactDraft,
    BankingPrecheckSimulationPolicy,
]:
    repository, component, execution, component_input = await _setup(
        candidate_count=1
    )
    proposal_artifact = await repository.get(execution.input_artifact_ids[0])
    assert proposal_artifact is not None
    amount_evidence = next(
        item
        for item in proposal_artifact.evidence_refs
        if item.sheet == "BANKING_INPUT_SUPPLEMENT"
        and item.field == "requested_amount"
    )
    currency_evidence = EvidenceRef(
        evidence_id=deterministic_id(
            "EVD",
            proposal_artifact.payload["dataset_id"],
            SourceType.USER_INPUT,
            amount_evidence.record_id,
            "requested_amount_currency",
            "VND",
        ),
        source_type=SourceType.USER_INPUT,
        sheet="BANKING_INPUT_SUPPLEMENT",
        row_number=0,
        record_id=amount_evidence.record_id,
        field="requested_amount_currency",
        display_value="VND",
    )
    for artifact in await repository.list_by_case(
        proposal_artifact.evaluation_case_id
    ):
        if not any(
            item.sheet == "BANKING_PRECHECK_READINESS"
            and item.field == "amount"
            for item in artifact.evidence_refs
        ):
            continue
        enriched_evidence = (
            *(
                item.model_copy(
                    update={
                        "source_evidence_ids": (
                            *item.source_evidence_ids,
                            currency_evidence.evidence_id,
                        )
                    }
                )
                if item.sheet == "BANKING_PRECHECK_READINESS"
                and item.field == "amount"
                else item
                for item in artifact.evidence_refs
            ),
            currency_evidence,
        )
        payload = dict(artifact.payload)
        if artifact.artifact_id == proposal_artifact.artifact_id:
            payload["evidence_ids"] = [
                *payload["evidence_ids"],
                currency_evidence.evidence_id,
            ]
        await repository.save(
            artifact.model_copy(
                update={
                    "payload": payload,
                    "evidence_refs": enriched_evidence,
                }
            )
        )
    request = component_input.requests[0]
    policy = _policy(api_id=request.api_id, api_provider=request.api_provider)
    scenario = policy.scenarios[0]
    provider_reference = deterministic_id(
        "SIMREF",
        policy.configuration_hash,
        scenario.scenario_id,
        request.request_hash,
    )
    scenario_hash = deterministic_id(
        "BPSCNH",
        policy.configuration_hash,
        scenario.model_dump(mode="json"),
    )
    response_fields = {
        "request_id": request.request_id,
        "idempotency_key": request.idempotency_key,
        "api_id": request.api_id,
        "api_provider": request.api_provider,
        "execution_mode": BankingPrecheckExecutionMode.SIMULATED,
        "provider_reference": provider_reference,
        "scenario_id": scenario.scenario_id,
        "scenario_version": policy.configuration_version,
        "scenario_hash": scenario_hash,
        "outcome": scenario.outcome,
        "message": scenario.message,
        "reason_codes": scenario.reason_codes,
        "required_follow_up_fields": scenario.required_follow_up_fields,
        "requested_amount": request.requested_amount,
        "supported_amount": None,
        "currency": request.requested_amount_currency,
        "eligibility_status": ProviderEligibilityStatus.NOT_EVALUABLE,
        "guarantee_decision": ProviderGuaranteeDecision.NO_DECISION,
        "required_documents": (),
        "approval_conditions": (),
        "authority": BankingPrecheckResultAuthority.SIMULATED_NON_BINDING,
        "non_binding": True,
    }
    response = BankingPrecheckRawResponse(
        **response_fields,
        response_hash=banking_precheck_response_hash(**response_fields),
    )
    exact_input = component_input.model_copy(
        update={
            "raw_responses": (response,),
            "adapter_config_hash": policy.configuration_hash,
        }
    )
    result = await component.execute(
        execution.model_copy(
            update={"component_input": exact_input.model_dump(mode="json")}
        )
    )
    assert len(result.artifacts) == 1
    return result.artifacts[0], policy


def _replace_first_result(
    draft: ArtifactDraft,
    update: dict[str, object],
) -> ArtifactDraft:
    payload = dict(draft.payload)
    first = dict(payload["results"][0])
    first.update(update)
    payload["results"] = [first]
    return draft.model_copy(update={"payload": payload})


def test_exact_result_set_passes_only_with_server_simulation_policy() -> None:
    async def scenario() -> None:
        draft, policy = await _draft_and_policy()

        exact = await EvidenceValidator(
            banking_precheck_simulation_policy=policy
        ).validate(draft)
        without_policy = await EvidenceValidator().validate(draft)

        assert exact.status is ValidationStatus.VALID
        assert "BANKING_PRECHECK_RESULT_SET_BOUNDARY_VALID" in exact.checks
        assert without_policy.status is ValidationStatus.BLOCKED
        assert any(
            "requires the server simulation policy" in item
            for item in without_policy.blocking_errors
        )

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "mutate",
    (
        lambda draft: _replace_first_result(
            draft, {"request_id": "BPRQ-FORGED-BUT-PREFIXED"}
        ),
        lambda draft: _replace_first_result(
            draft, {"request_hash": "BPRH-FORGED-BUT-PREFIXED"}
        ),
        lambda draft: _replace_first_result(
            draft, {"idempotency_key": "BPIK-FORGED-BUT-PREFIXED"}
        ),
        lambda draft: _replace_first_result(
            draft, {"response_hash": "BPRSH-FORGED-BUT-PREFIXED"}
        ),
        lambda draft: _replace_first_result(
            draft, {"provider_reference": "SIMREF-FORGED-BUT-PREFIXED"}
        ),
        lambda draft: _replace_first_result(
            draft, {"normalized_result_id": "BPNR-FORGED-BUT-PREFIXED"}
        ),
        lambda draft: draft.model_copy(
            update={
                "payload": {
                    **draft.payload,
                    "result_set_id": "BPRS-FORGED-BUT-PREFIXED",
                }
            }
        ),
    ),
)
def test_prefixed_but_noncanonical_identity_is_blocked(
    mutate: Callable[[ArtifactDraft], ArtifactDraft],
) -> None:
    async def scenario() -> None:
        draft, policy = await _draft_and_policy()

        report = await EvidenceValidator(
            banking_precheck_simulation_policy=policy
        ).validate(mutate(draft))

        assert report.status is ValidationStatus.BLOCKED

    asyncio.run(scenario())


def test_self_consistent_but_unconfigured_provider_scenario_is_blocked() -> None:
    async def scenario() -> None:
        _, component, execution, component_input = await _setup(candidate_count=1)
        request = component_input.requests[0]
        policy = _policy(api_id=request.api_id, api_provider=request.api_provider)
        invented = {
            "request_id": request.request_id,
            "idempotency_key": request.idempotency_key,
            "api_id": request.api_id,
            "api_provider": request.api_provider,
            "execution_mode": BankingPrecheckExecutionMode.SIMULATED,
            "provider_reference": deterministic_id(
                "SIMREF",
                policy.configuration_hash,
                "INVENTED-SCENARIO",
                request.request_hash,
            ),
            "scenario_id": "INVENTED-SCENARIO",
            "scenario_version": policy.configuration_version,
            "scenario_hash": "BPSCNH-INVENTED-BUT-PREFIXED",
            "outcome": BankingPrecheckOutcome.CONDITIONAL_PRECHECK,
            "message": "Invented provider conclusion.",
            "reason_codes": ("INVENTED",),
            "required_follow_up_fields": (),
            "requested_amount": request.requested_amount,
            "supported_amount": request.requested_amount,
            "currency": request.requested_amount_currency,
            "eligibility_status": ProviderEligibilityStatus.ELIGIBLE,
            "guarantee_decision": ProviderGuaranteeDecision.CONDITIONAL,
            "required_documents": ("SIGNED_CONTRACT",),
            "approval_conditions": ("CONTRACT_SIGNED",),
            "authority": BankingPrecheckResultAuthority.SIMULATED_NON_BINDING,
            "non_binding": True,
        }
        response = BankingPrecheckRawResponse(
            **invented,
            response_hash=banking_precheck_response_hash(**invented),
        )
        changed = component_input.model_copy(
            update={
                "raw_responses": (response,),
                "adapter_config_hash": policy.configuration_hash,
            }
        )
        result = await component.execute(
            execution.model_copy(
                update={"component_input": changed.model_dump(mode="json")}
            )
        )
        assert len(result.artifacts) == 1

        report = await EvidenceValidator(
            banking_precheck_simulation_policy=policy
        ).validate(result.artifacts[0])

        assert report.status is ValidationStatus.BLOCKED
        assert any(
            "server simulation scenario" in item
            or "scenario evidence is stale" in item
            for item in report.blocking_errors
        )

    asyncio.run(scenario())


def test_contract_binding_must_name_the_result_set_contract() -> None:
    async def scenario() -> None:
        draft, policy = await _draft_and_policy()
        changed_evidence = tuple(
            evidence.model_copy(
                update={
                    "record_id": "CON-OTHER",
                    "display_value": "CON-OTHER",
                }
            )
            if evidence.sheet == "EVALUATION_CASE"
            and evidence.field == "contract_id"
            else evidence
            for evidence in draft.evidence_refs
        )
        forged = draft.model_copy(update={"evidence_refs": changed_evidence})

        report = await EvidenceValidator(
            banking_precheck_simulation_policy=policy
        ).validate(forged)

        assert report.status is ValidationStatus.BLOCKED
        assert any(
            "contract is not evidence-bound" in item
            for item in report.blocking_errors
        )

    asyncio.run(scenario())


def test_tampered_approval_display_is_blocked_even_when_ids_are_unchanged() -> None:
    async def scenario() -> None:
        draft, policy = await _draft_and_policy()
        changed_evidence = []
        for evidence in draft.evidence_refs:
            if (
                evidence.source_type is SourceType.USER_INPUT
                and evidence.sheet == "APPROVAL_AUTHORIZATION"
            ):
                display = dict(evidence.display_value)
                display["authorized_by"] = "ATTACKER"
                display["subject_input_hash"] = "TAMPERED-SUBJECT-HASH"
                evidence = evidence.model_copy(update={"display_value": display})
            changed_evidence.append(evidence)
        forged = draft.model_copy(
            update={"evidence_refs": tuple(changed_evidence)}
        )

        report = await EvidenceValidator(
            banking_precheck_simulation_policy=policy
        ).validate(forged)

        assert report.status is ValidationStatus.BLOCKED
        assert any(
            "approval evidence identity is invalid" in item
            for item in report.blocking_errors
        )

    asyncio.run(scenario())


def test_tampered_derived_display_and_sources_are_blocked() -> None:
    async def scenario() -> None:
        draft, policy = await _draft_and_policy()
        changed_evidence = []
        for evidence in draft.evidence_refs:
            if (
                evidence.source_type is SourceType.DERIVED
                and evidence.sheet == "BANKING_PRECHECK_RESULT_SET"
            ):
                evidence = evidence.model_copy(
                    update={
                        "display_value": {"outcome": "FORGED"},
                        "source_evidence_ids": (),
                    }
                )
            changed_evidence.append(evidence)
        forged = draft.model_copy(
            update={"evidence_refs": tuple(changed_evidence)}
        )

        report = await EvidenceValidator(
            banking_precheck_simulation_policy=policy
        ).validate(forged)

        assert report.status is ValidationStatus.BLOCKED
        assert any(
            "normalized lineage is invalid" in item
            for item in report.blocking_errors
        )

    asyncio.run(scenario())
