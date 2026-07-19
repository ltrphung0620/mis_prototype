"""Deterministic and fail-closed tests for the simulated precheck adapter."""

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from opc_mis.domain.banking_precheck_execution_models import (
    AuthorizedActionPermit,
    BankingCompanyProfileField,
    BankingPrecheckRequest,
    banking_precheck_idempotency_key,
    banking_precheck_request_hash,
)
from opc_mis.domain.enums import (
    BankingPrecheckExecutionMode,
    BankingPrecheckOutcome,
    BankingPrecheckResultAuthority,
    BankingPrecheckSupportedAmountStrategy,
    CurrencyCode,
    ProtectedAction,
    ProviderEligibilityStatus,
    ProviderGuaranteeDecision,
)
from opc_mis.infrastructure.banking.simulated_precheck_adapter import (
    BankingPrecheckAuthorizationError,
    BankingPrecheckRequestIntegrityError,
    SimulatedBankingPrecheckAdapter,
)
from opc_mis.infrastructure.config.banking_precheck_simulation_policy import (
    BankingPrecheckSimulationPolicyError,
    BankingPrecheckSimulationPolicyLoader,
)
from opc_mis.ports.banking_precheck_adapter import BankingPrecheckAdapter

POLICY_PATH = Path("config/banking/precheck_simulation_scenarios.json")
CASE_ID = "CASE-SIMULATED-PRECHECK"
PROPOSAL_ARTIFACT_ID = "ART-SIMULATED-PRECHECK-PROPOSAL"
PROFILE_SECRET = "sensitive-company-registration-value"


def _permit(
    *,
    evaluation_case_id: str = CASE_ID,
    subject_artifact_id: str = PROPOSAL_ARTIFACT_ID,
) -> AuthorizedActionPermit:
    return AuthorizedActionPermit(
        permit_id="PERMIT-SIMULATED-PRECHECK",
        workflow_run_id="WORKFLOW-SIMULATED-PRECHECK",
        evaluation_case_id=evaluation_case_id,
        approval_request_id="APPROVAL-SIMULATED-PRECHECK",
        protected_action=ProtectedAction.SUBMIT_BANKING_PRECHECK,
        subject_artifact_id=subject_artifact_id,
        subject_artifact_version=1,
        subject_input_hash="PROPOSAL-INPUT-HASH",
        authorized_by="FOUNDER",
        authorized_at=datetime(2026, 7, 18, 10, 0, tzinfo=UTC),
    )


def _request(
    authorization: AuthorizedActionPermit,
    *,
    api_id: str = "API-002",
    api_provider: str = "VietinBank",
) -> BankingPrecheckRequest:
    profile = (
        BankingCompanyProfileField(
            field="company_registration",
            value=PROFILE_SECRET,
        ),
        BankingCompanyProfileField(field="years_operating", value=8),
    )
    fields = {
        "dataset_id": "DATASET-SIMULATED-PRECHECK",
        "evaluation_case_id": CASE_ID,
        "contract_id": "CONTRACT-SIMULATED-PRECHECK",
        "proposal_artifact_id": PROPOSAL_ARTIFACT_ID,
        "proposal_id": "PROPOSAL-SIMULATED-PRECHECK",
        "proposal_item_id": "PROPOSAL-ITEM-SIMULATED-PRECHECK",
        "option_id": "OPTION-SIMULATED-PRECHECK",
        "bank_product_id": "BANKPROD-002",
        "api_id": api_id,
        "api_provider": api_provider,
        "api_method": "POST",
        "api_endpoint": "/openapi/v1/guarantee/precheck",
        "requested_amount": 350_000_000,
        "requested_amount_currency": CurrencyCode.VND,
        "company_profile": profile,
    }
    request_hash = banking_precheck_request_hash(**fields)
    idempotency_key = banking_precheck_idempotency_key(
        permit_id=authorization.permit_id,
        proposal_artifact_id=PROPOSAL_ARTIFACT_ID,
        proposal_item_id="PROPOSAL-ITEM-SIMULATED-PRECHECK",
        request_hash=request_hash,
    )
    return BankingPrecheckRequest(
        request_id="REQUEST-SIMULATED-PRECHECK",
        **fields,
        request_hash=request_hash,
        idempotency_key=idempotency_key,
    )


def _adapter() -> SimulatedBankingPrecheckAdapter:
    policy = BankingPrecheckSimulationPolicyLoader().load(POLICY_PATH)
    return SimulatedBankingPrecheckAdapter(policy=policy)


def test_policy_loader_returns_typed_canonical_configuration(tmp_path: Path) -> None:
    loader = BankingPrecheckSimulationPolicyLoader()
    policy = loader.load(POLICY_PATH)
    source = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    reformatted = tmp_path / "reformatted.json"
    reformatted.write_text(
        json.dumps(source, ensure_ascii=False, indent=6, sort_keys=True),
        encoding="utf-8",
    )

    scenario = policy.scenarios[0]
    assert policy.configuration_id == "OPC_BANKING_PRECHECK_SIMULATION"
    assert len(policy.configuration_hash) == 64
    assert loader.load(reformatted).configuration_hash == policy.configuration_hash
    assert scenario.api_id == "API-002"
    assert scenario.api_provider == "VietinBank"
    assert scenario.outcome is BankingPrecheckOutcome.CONDITIONAL_PRECHECK
    assert scenario.reason_codes == ("SIMULATED_CONDITIONAL_PRECHECK",)
    assert scenario.eligibility_status is ProviderEligibilityStatus.ELIGIBLE
    assert scenario.guarantee_decision is ProviderGuaranteeDecision.CONDITIONAL
    assert (
        scenario.supported_amount_strategy
        is BankingPrecheckSupportedAmountStrategy.ECHO_REQUESTED_AMOUNT
    )
    assert scenario.required_documents == (
        "SIGNED_CONTRACT",
        "COMPANY_PROFILE",
        "PERFORMANCE_BOND_REQUEST_FORM",
        "CASHFLOW_BUFFER_EVIDENCE",
    )
    assert scenario.approval_conditions == (
        "CONTRACT_SIGNED",
        "CASHFLOW_BUFFER_CONFIRMED",
    )
    assert scenario.non_binding is True


def test_policy_loader_rejects_missing_and_invalid_configuration(
    tmp_path: Path,
) -> None:
    loader = BankingPrecheckSimulationPolicyLoader()
    with pytest.raises(BankingPrecheckSimulationPolicyError, match="does not exist"):
        loader.load(tmp_path / "missing.json")

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}", encoding="utf-8")
    with pytest.raises(BankingPrecheckSimulationPolicyError, match="Invalid"):
        loader.load(invalid)

    inconsistent = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    inconsistent["scenarios"][0]["supported_amount_strategy"] = "NONE"
    inconsistent_path = tmp_path / "inconsistent.json"
    inconsistent_path.write_text(
        json.dumps(inconsistent, ensure_ascii=False),
        encoding="utf-8",
    )
    with pytest.raises(
        BankingPrecheckSimulationPolicyError,
        match="ECHO_REQUESTED_AMOUNT",
    ):
        loader.load(inconsistent_path)


def test_submit_is_deterministic_idempotent_and_never_claims_bank_approval() -> None:
    adapter: BankingPrecheckAdapter = _adapter()
    authorization = _permit()
    request = _request(authorization)

    first = asyncio.run(adapter.submit(request, authorization))
    second = asyncio.run(adapter.submit(request, authorization))

    assert first == second
    assert first.idempotency_key == request.idempotency_key
    assert first.execution_mode is BankingPrecheckExecutionMode.SIMULATED
    assert first.outcome is BankingPrecheckOutcome.CONDITIONAL_PRECHECK
    assert first.reason_codes == ("SIMULATED_CONDITIONAL_PRECHECK",)
    assert first.requested_amount == request.requested_amount
    assert first.supported_amount == request.requested_amount
    assert first.currency is CurrencyCode.VND
    assert first.eligibility_status is ProviderEligibilityStatus.ELIGIBLE
    assert first.guarantee_decision is ProviderGuaranteeDecision.CONDITIONAL
    assert first.required_documents == (
        "SIGNED_CONTRACT",
        "COMPANY_PROFILE",
        "PERFORMANCE_BOND_REQUEST_FORM",
        "CASHFLOW_BUFFER_EVIDENCE",
    )
    assert first.approval_conditions == (
        "CONTRACT_SIGNED",
        "CASHFLOW_BUFFER_CONFIRMED",
    )
    assert first.authority is BankingPrecheckResultAuthority.SIMULATED_NON_BINDING
    assert first.non_binding is True
    assert first.provider_reference.startswith("SIMREF-")
    assert first.response_hash.startswith("BPRSH-")
    assert adapter.adapter_id == "SIMULATED_BANKING_PRECHECK_ADAPTER_V1"
    assert len(adapter.configuration_hash) == 64
    assert "not a vietinbank approval" in first.message.lower()


def test_adapter_does_not_log_or_retain_sensitive_company_profile(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    adapter = _adapter()
    authorization = _permit()
    request = _request(authorization)

    response = asyncio.run(adapter.submit(request, authorization))

    assert PROFILE_SECRET not in repr(request)
    assert PROFILE_SECRET not in repr(adapter)
    assert PROFILE_SECRET not in repr(response)
    assert PROFILE_SECRET not in caplog.text
    assert not hasattr(adapter, "__dict__")


def test_unknown_api_returns_safe_non_binding_service_unavailable() -> None:
    adapter = _adapter()
    authorization = _permit()
    request = _request(
        authorization,
        api_id="API-NOT-CONFIGURED",
        api_provider="Unknown Provider",
    )

    response = asyncio.run(adapter.submit(request, authorization))

    assert response.outcome is BankingPrecheckOutcome.SERVICE_UNAVAILABLE
    assert response.reason_codes == ("SIMULATION_SCENARIO_NOT_CONFIGURED",)
    assert response.non_binding is True
    assert "no provider decision" in response.message.lower()
    assert response == asyncio.run(adapter.submit(request, authorization))


@pytest.mark.parametrize(
    ("authorization"),
    (
        _permit(evaluation_case_id="CASE-OTHER"),
        _permit(subject_artifact_id="ART-OTHER-PROPOSAL"),
    ),
)
def test_invalid_permit_is_rejected_without_exposing_profile(
    authorization: AuthorizedActionPermit,
) -> None:
    adapter = _adapter()
    request = _request(_permit())

    with pytest.raises(BankingPrecheckAuthorizationError) as raised:
        asyncio.run(adapter.submit(request, authorization))

    assert PROFILE_SECRET not in str(raised.value)


def test_invalid_idempotency_key_is_rejected_without_adapter_state() -> None:
    adapter = _adapter()
    authorization = _permit()
    request = _request(authorization).model_copy(
        update={"idempotency_key": "BPIK-TAMPERED"}
    )

    with pytest.raises(BankingPrecheckRequestIntegrityError):
        asyncio.run(adapter.submit(request, authorization))
