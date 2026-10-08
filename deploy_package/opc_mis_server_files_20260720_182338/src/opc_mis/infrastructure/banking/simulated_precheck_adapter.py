"""Deterministic, non-binding Banking precheck simulation adapter."""

from opc_mis.domain.banking_precheck_execution_models import (
    AuthorizedActionPermit,
    BankingPrecheckRawResponse,
    BankingPrecheckRequest,
    BankingPrecheckSimulationPolicy,
    BankingPrecheckSimulationScenario,
    banking_precheck_idempotency_key,
    banking_precheck_request_hash,
    banking_precheck_response_hash,
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
from opc_mis.domain.lineage import deterministic_id

_UNCONFIGURED_SCENARIO_ID = "SIMULATION-SCENARIO-NOT-CONFIGURED"
_UNCONFIGURED_REASON_CODE = "SIMULATION_SCENARIO_NOT_CONFIGURED"
_UNCONFIGURED_MESSAGE = (
    "Simulated precheck service is unavailable because no server scenario matches "
    "this API/provider; no provider decision was made."
)
_ADAPTER_ID = "SIMULATED_BANKING_PRECHECK_ADAPTER_V1"


class BankingPrecheckAuthorizationError(PermissionError):
    """Raised when a request is not bound to the supplied Governance permit."""


class BankingPrecheckRequestIntegrityError(ValueError):
    """Raised when canonical request or idempotency identity does not match."""


class SimulatedBankingPrecheckAdapter:
    """Return stateless simulated results without contacting a Banking provider."""

    __slots__ = ("_policy", "_scenarios")

    def __init__(self, *, policy: BankingPrecheckSimulationPolicy) -> None:
        self._policy = policy
        self._scenarios = {
            (item.api_id, item.api_provider): item for item in policy.scenarios
        }

    @property
    def adapter_id(self) -> str:
        """Return the stable simulated adapter identifier."""
        return _ADAPTER_ID

    @property
    def configuration_hash(self) -> str:
        """Return the canonical identity of the server-owned scenario policy."""
        return self._policy.configuration_hash

    async def submit(
        self,
        request: BankingPrecheckRequest,
        authorization: AuthorizedActionPermit,
    ) -> BankingPrecheckRawResponse:
        """Return one deterministic simulated response after exact permit checks."""
        self._validate_authorization(request, authorization)
        self._validate_request_identity(request, authorization)
        scenario = self._scenarios.get((request.api_id, request.api_provider))
        if scenario is None:
            return self._unconfigured_response(request)
        return self._scenario_response(request, scenario)

    @staticmethod
    def _validate_authorization(
        request: BankingPrecheckRequest,
        authorization: AuthorizedActionPermit,
    ) -> None:
        if (
            authorization.protected_action
            is not ProtectedAction.SUBMIT_BANKING_PRECHECK
            or authorization.evaluation_case_id != request.evaluation_case_id
            or authorization.subject_artifact_id != request.proposal_artifact_id
        ):
            raise BankingPrecheckAuthorizationError(
                "Banking precheck request is not bound to the supplied authorization."
            )

    @staticmethod
    def _validate_request_identity(
        request: BankingPrecheckRequest,
        authorization: AuthorizedActionPermit,
    ) -> None:
        expected_hash = banking_precheck_request_hash(
            dataset_id=request.dataset_id,
            evaluation_case_id=request.evaluation_case_id,
            contract_id=request.contract_id,
            proposal_artifact_id=request.proposal_artifact_id,
            proposal_id=request.proposal_id,
            proposal_item_id=request.proposal_item_id,
            option_id=request.option_id,
            bank_product_id=request.bank_product_id,
            api_id=request.api_id,
            api_provider=request.api_provider,
            api_method=request.api_method,
            api_endpoint=request.api_endpoint,
            requested_amount=request.requested_amount,
            requested_amount_currency=request.requested_amount_currency,
            company_profile=request.company_profile,
        )
        expected_idempotency_key = banking_precheck_idempotency_key(
            permit_id=authorization.permit_id,
            proposal_artifact_id=request.proposal_artifact_id,
            proposal_item_id=request.proposal_item_id,
            request_hash=expected_hash,
        )
        if (
            request.request_hash != expected_hash
            or request.idempotency_key != expected_idempotency_key
        ):
            raise BankingPrecheckRequestIntegrityError(
                "Banking precheck request identity is invalid."
            )

    def _scenario_response(
        self,
        request: BankingPrecheckRequest,
        scenario: BankingPrecheckSimulationScenario,
    ) -> BankingPrecheckRawResponse:
        scenario_hash = deterministic_id(
            "BPSCNH",
            self.configuration_hash,
            scenario.model_dump(mode="json"),
        )
        return self._response(
            request=request,
            scenario_id=scenario.scenario_id,
            scenario_hash=scenario_hash,
            outcome=scenario.outcome,
            message=scenario.message,
            reason_codes=scenario.reason_codes,
            required_follow_up_fields=scenario.required_follow_up_fields,
            supported_amount=(
                request.requested_amount
                if scenario.supported_amount_strategy
                is BankingPrecheckSupportedAmountStrategy.ECHO_REQUESTED_AMOUNT
                else None
            ),
            currency=scenario.currency,
            eligibility_status=scenario.eligibility_status,
            guarantee_decision=scenario.guarantee_decision,
            required_documents=scenario.required_documents,
            approval_conditions=scenario.approval_conditions,
        )

    def _unconfigured_response(
        self,
        request: BankingPrecheckRequest,
    ) -> BankingPrecheckRawResponse:
        scenario_hash = deterministic_id(
            "BPSCNH",
            self.configuration_hash,
            _UNCONFIGURED_SCENARIO_ID,
            request.api_id,
            request.api_provider,
        )
        return self._response(
            request=request,
            scenario_id=_UNCONFIGURED_SCENARIO_ID,
            scenario_hash=scenario_hash,
            outcome=BankingPrecheckOutcome.SERVICE_UNAVAILABLE,
            message=_UNCONFIGURED_MESSAGE,
            reason_codes=(_UNCONFIGURED_REASON_CODE,),
            required_follow_up_fields=(),
            supported_amount=None,
            currency=request.requested_amount_currency,
            eligibility_status=ProviderEligibilityStatus.NOT_EVALUABLE,
            guarantee_decision=ProviderGuaranteeDecision.NO_DECISION,
            required_documents=(),
            approval_conditions=(),
        )

    def _response(
        self,
        *,
        request: BankingPrecheckRequest,
        scenario_id: str,
        scenario_hash: str,
        outcome: BankingPrecheckOutcome,
        message: str,
        reason_codes: tuple[str, ...],
        required_follow_up_fields: tuple[str, ...],
        supported_amount: int | None,
        currency: CurrencyCode,
        eligibility_status: ProviderEligibilityStatus,
        guarantee_decision: ProviderGuaranteeDecision,
        required_documents: tuple[str, ...],
        approval_conditions: tuple[str, ...],
    ) -> BankingPrecheckRawResponse:
        execution_mode = BankingPrecheckExecutionMode.SIMULATED
        authority = BankingPrecheckResultAuthority.SIMULATED_NON_BINDING
        provider_reference = deterministic_id(
            "SIMREF",
            self.configuration_hash,
            scenario_id,
            request.request_hash,
        )
        response_hash = banking_precheck_response_hash(
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            api_id=request.api_id,
            api_provider=request.api_provider,
            execution_mode=execution_mode,
            provider_reference=provider_reference,
            scenario_id=scenario_id,
            scenario_version=self._policy.configuration_version,
            scenario_hash=scenario_hash,
            outcome=outcome,
            message=message,
            reason_codes=reason_codes,
            required_follow_up_fields=required_follow_up_fields,
            requested_amount=request.requested_amount,
            supported_amount=supported_amount,
            currency=currency,
            eligibility_status=eligibility_status,
            guarantee_decision=guarantee_decision,
            required_documents=required_documents,
            approval_conditions=approval_conditions,
            authority=authority,
            non_binding=True,
        )
        return BankingPrecheckRawResponse(
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            api_id=request.api_id,
            api_provider=request.api_provider,
            execution_mode=execution_mode,
            provider_reference=provider_reference,
            scenario_id=scenario_id,
            scenario_version=self._policy.configuration_version,
            scenario_hash=scenario_hash,
            outcome=outcome,
            message=message,
            reason_codes=reason_codes,
            required_follow_up_fields=required_follow_up_fields,
            requested_amount=request.requested_amount,
            supported_amount=supported_amount,
            currency=currency,
            eligibility_status=eligibility_status,
            guarantee_decision=guarantee_decision,
            required_documents=required_documents,
            approval_conditions=approval_conditions,
            authority=authority,
            response_hash=response_hash,
            non_binding=True,
        )
