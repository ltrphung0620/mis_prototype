"""Domain contracts for authorized, simulated Banking precheck execution results."""

from __future__ import annotations

from datetime import datetime
from math import isfinite
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.components import ComponentResult
from opc_mis.domain.enums import (
    BankingPrecheckExecutionMode,
    BankingPrecheckOutcome,
    BankingPrecheckResultAuthority,
    BankingPrecheckSupportedAmountStrategy,
    ComponentStatus,
    CurrencyCode,
    ProtectedAction,
    ProviderEligibilityStatus,
    ProviderGuaranteeDecision,
    WorkflowStatus,
)
from opc_mis.domain.lineage import deterministic_id
from opc_mis.domain.missing_data import MissingDataRequest
from opc_mis.domain.validation_reports import ValidationReport

BankingCompanyProfileValue = (
    StrictBool | StrictInt | StrictFloat | StrictStr | None
)


class AuthorizedActionPermit(BaseModel):
    """Typed proof that Governance authorized one exact proposal artifact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    permit_id: StrictStr = Field(min_length=1)
    workflow_run_id: StrictStr = Field(min_length=1)
    evaluation_case_id: StrictStr = Field(min_length=1)
    approval_request_id: StrictStr = Field(min_length=1)
    protected_action: ProtectedAction = ProtectedAction.SUBMIT_BANKING_PRECHECK
    subject_artifact_id: StrictStr = Field(min_length=1)
    subject_artifact_version: StrictInt = Field(ge=1)
    subject_input_hash: StrictStr = Field(min_length=1)
    authorized_by: StrictStr = Field(min_length=1)
    authorized_at: datetime

    @model_validator(mode="after")
    def validate_authorization(self) -> AuthorizedActionPermit:
        """Require the exact protected action and an auditable timestamp."""
        if self.protected_action is not ProtectedAction.SUBMIT_BANKING_PRECHECK:
            raise ValueError("permit action must be SUBMIT_BANKING_PRECHECK")
        if self.authorized_at.tzinfo is None:
            raise ValueError("authorized_at must be timezone-aware")
        return self


class BankingCompanyProfileField(BaseModel):
    """One exact OPC profile field carried only inside the adapter request."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    field: StrictStr = Field(min_length=1)
    value: BankingCompanyProfileValue = Field(repr=False)

    @field_validator("value")
    @classmethod
    def require_finite_json_scalar(
        cls,
        value: BankingCompanyProfileValue,
    ) -> BankingCompanyProfileValue:
        """Reject non-finite numbers while retaining explicit null values."""
        if isinstance(value, float) and not isfinite(value):
            raise ValueError("company profile values must be finite JSON scalars")
        return value


def banking_precheck_request_hash(
    *,
    dataset_id: str,
    evaluation_case_id: str,
    contract_id: str,
    proposal_artifact_id: str,
    proposal_id: str,
    proposal_item_id: str,
    option_id: str,
    bank_product_id: str,
    api_id: str,
    api_provider: str,
    api_method: str,
    api_endpoint: str,
    requested_amount: int,
    requested_amount_currency: CurrencyCode,
    company_profile: tuple[BankingCompanyProfileField, ...],
) -> str:
    """Hash the exact request business payload in one shared canonical order."""
    return deterministic_id(
        "BPRH",
        dataset_id,
        evaluation_case_id,
        contract_id,
        proposal_artifact_id,
        proposal_id,
        proposal_item_id,
        option_id,
        bank_product_id,
        api_id,
        api_provider,
        api_method,
        api_endpoint,
        requested_amount,
        requested_amount_currency,
        tuple((item.field, item.value) for item in company_profile),
    )


def banking_precheck_idempotency_key(
    *,
    permit_id: str,
    proposal_artifact_id: str,
    proposal_item_id: str,
    request_hash: str,
) -> str:
    """Bind idempotency to authorization, proposal envelope, item, and request."""
    return deterministic_id(
        "BPIK",
        permit_id,
        proposal_artifact_id,
        proposal_item_id,
        request_hash,
    )


def banking_precheck_response_hash(
    *,
    request_id: str,
    idempotency_key: str,
    api_id: str,
    api_provider: str,
    execution_mode: BankingPrecheckExecutionMode,
    provider_reference: str,
    scenario_id: str,
    scenario_version: str,
    scenario_hash: str,
    outcome: BankingPrecheckOutcome,
    message: str,
    reason_codes: tuple[str, ...],
    required_follow_up_fields: tuple[str, ...],
    requested_amount: int,
    supported_amount: int | None,
    currency: CurrencyCode,
    eligibility_status: ProviderEligibilityStatus,
    guarantee_decision: ProviderGuaranteeDecision,
    required_documents: tuple[str, ...],
    approval_conditions: tuple[str, ...],
    authority: BankingPrecheckResultAuthority,
    non_binding: bool,
) -> str:
    """Hash one raw simulated response using the shared provider contract."""
    return deterministic_id(
        "BPRSH",
        request_id,
        idempotency_key,
        api_id,
        api_provider,
        execution_mode,
        provider_reference,
        scenario_id,
        scenario_version,
        scenario_hash,
        outcome,
        message,
        reason_codes,
        required_follow_up_fields,
        requested_amount,
        supported_amount,
        currency,
        eligibility_status,
        guarantee_decision,
        required_documents,
        approval_conditions,
        authority,
        non_binding,
    )


def _validate_provider_conclusion(
    *,
    outcome: BankingPrecheckOutcome,
    requested_amount: int,
    supported_amount: int | None,
    currency: CurrencyCode,
    eligibility_status: ProviderEligibilityStatus,
    guarantee_decision: ProviderGuaranteeDecision,
    required_documents: tuple[str, ...],
    approval_conditions: tuple[str, ...],
) -> None:
    """Reject internally inconsistent simulated provider conclusions."""
    for field_name, values in (
        ("required_documents", required_documents),
        ("approval_conditions", approval_conditions),
    ):
        if any(not value.strip() or value != value.strip() for value in values):
            raise ValueError(f"{field_name} must contain non-empty canonical codes")
    if currency is not CurrencyCode.VND:
        raise ValueError("Banking precheck provider amounts must use VND")
    if supported_amount is not None and supported_amount > requested_amount:
        raise ValueError("supported_amount cannot exceed requested_amount")
    if outcome is BankingPrecheckOutcome.CONDITIONAL_PRECHECK:
        if eligibility_status not in {
            ProviderEligibilityStatus.ELIGIBLE,
            ProviderEligibilityStatus.CONDITIONAL,
        }:
            raise ValueError(
                "CONDITIONAL_PRECHECK requires an eligible provider posture"
            )
        if guarantee_decision not in {
            ProviderGuaranteeDecision.WILLING,
            ProviderGuaranteeDecision.CONDITIONAL,
        }:
            raise ValueError(
                "CONDITIONAL_PRECHECK requires a willing or conditional guarantee posture"
            )
        if supported_amount != requested_amount:
            raise ValueError(
                "prototype CONDITIONAL_PRECHECK must echo the requested amount"
            )
        if not required_documents:
            raise ValueError(
                "CONDITIONAL_PRECHECK requires provider document requirements"
            )
        if not approval_conditions:
            raise ValueError(
                "CONDITIONAL_PRECHECK requires provider approval conditions"
            )
        return
    if outcome is BankingPrecheckOutcome.NOT_ELIGIBLE:
        if (
            eligibility_status is not ProviderEligibilityStatus.NOT_ELIGIBLE
            or guarantee_decision is not ProviderGuaranteeDecision.DECLINED
            or supported_amount is not None
            or required_documents
            or approval_conditions
        ):
            raise ValueError(
                "NOT_ELIGIBLE requires a declined provider posture without amount, "
                "document, or approval-condition claims"
            )
        return
    if (
        eligibility_status is not ProviderEligibilityStatus.NOT_EVALUABLE
        or guarantee_decision is not ProviderGuaranteeDecision.NO_DECISION
        or supported_amount is not None
        or required_documents
        or approval_conditions
    ):
        raise ValueError(
            f"{outcome.value} cannot carry an eligibility, guarantee, amount, "
            "document, or approval conclusion"
        )


class BankingPrecheckRequest(BaseModel):
    """Exact simulated-adapter request for one proposal candidate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: StrictStr = Field(min_length=1)
    dataset_id: StrictStr = Field(min_length=1)
    evaluation_case_id: StrictStr = Field(min_length=1)
    contract_id: StrictStr = Field(min_length=1)
    proposal_artifact_id: StrictStr = Field(min_length=1)
    proposal_id: StrictStr = Field(min_length=1)
    proposal_item_id: StrictStr = Field(min_length=1)
    option_id: StrictStr = Field(min_length=1)
    bank_product_id: StrictStr = Field(min_length=1)
    api_id: StrictStr = Field(min_length=1)
    api_provider: StrictStr = Field(min_length=1)
    api_method: StrictStr = Field(min_length=1)
    api_endpoint: StrictStr = Field(min_length=1)
    requested_amount: StrictInt = Field(gt=0)
    requested_amount_currency: CurrencyCode = CurrencyCode.VND
    company_profile: tuple[BankingCompanyProfileField, ...] = Field(
        min_length=1,
        repr=False,
    )
    request_hash: StrictStr = Field(min_length=1)
    idempotency_key: StrictStr = Field(min_length=1)

    @model_validator(mode="after")
    def validate_request(self) -> BankingPrecheckRequest:
        """Require exact profile and request-hash identity without logging values."""
        fields = tuple(item.field for item in self.company_profile)
        if len(set(fields)) != len(fields):
            raise ValueError("company_profile fields must be unique")
        if self.requested_amount_currency is not CurrencyCode.VND:
            raise ValueError("Banking precheck request amount must use VND")
        expected_hash = banking_precheck_request_hash(
            dataset_id=self.dataset_id,
            evaluation_case_id=self.evaluation_case_id,
            contract_id=self.contract_id,
            proposal_artifact_id=self.proposal_artifact_id,
            proposal_id=self.proposal_id,
            proposal_item_id=self.proposal_item_id,
            option_id=self.option_id,
            bank_product_id=self.bank_product_id,
            api_id=self.api_id,
            api_provider=self.api_provider,
            api_method=self.api_method,
            api_endpoint=self.api_endpoint,
            requested_amount=self.requested_amount,
            requested_amount_currency=self.requested_amount_currency,
            company_profile=self.company_profile,
        )
        if self.request_hash != expected_hash:
            raise ValueError("request_hash does not match the canonical request payload")
        return self


class BankingPrecheckRawResponse(BaseModel):
    """Typed raw response returned only by the simulated precheck adapter."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: StrictStr = Field(min_length=1)
    idempotency_key: StrictStr = Field(min_length=1)
    api_id: StrictStr = Field(min_length=1)
    api_provider: StrictStr = Field(min_length=1)
    execution_mode: BankingPrecheckExecutionMode = (
        BankingPrecheckExecutionMode.SIMULATED
    )
    provider_reference: StrictStr = Field(min_length=1)
    scenario_id: StrictStr = Field(min_length=1)
    scenario_version: StrictStr = Field(min_length=1)
    scenario_hash: StrictStr = Field(min_length=1)
    outcome: BankingPrecheckOutcome
    message: StrictStr = Field(min_length=1)
    reason_codes: tuple[StrictStr, ...] = ()
    required_follow_up_fields: tuple[StrictStr, ...] = ()
    requested_amount: StrictInt = Field(gt=0)
    supported_amount: StrictInt | None = Field(default=None, gt=0)
    currency: CurrencyCode = CurrencyCode.VND
    eligibility_status: ProviderEligibilityStatus = (
        ProviderEligibilityStatus.NOT_EVALUABLE
    )
    guarantee_decision: ProviderGuaranteeDecision = (
        ProviderGuaranteeDecision.NO_DECISION
    )
    required_documents: tuple[StrictStr, ...] = ()
    approval_conditions: tuple[StrictStr, ...] = ()
    authority: BankingPrecheckResultAuthority = (
        BankingPrecheckResultAuthority.SIMULATED_NON_BINDING
    )
    response_hash: StrictStr = Field(min_length=1)
    non_binding: Literal[True] = True

    @model_validator(mode="after")
    def validate_response(self) -> BankingPrecheckRawResponse:
        """Enforce simulated authority, unique codes, and canonical response hash."""
        if self.execution_mode is not BankingPrecheckExecutionMode.SIMULATED:
            raise ValueError("Banking precheck raw response must be SIMULATED")
        if self.authority is not BankingPrecheckResultAuthority.SIMULATED_NON_BINDING:
            raise ValueError("Banking precheck raw response must be non-binding")
        for field_name, values in (
            ("reason_codes", self.reason_codes),
            ("required_follow_up_fields", self.required_follow_up_fields),
            ("required_documents", self.required_documents),
            ("approval_conditions", self.approval_conditions),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} must be unique")
        _validate_provider_conclusion(
            outcome=self.outcome,
            requested_amount=self.requested_amount,
            supported_amount=self.supported_amount,
            currency=self.currency,
            eligibility_status=self.eligibility_status,
            guarantee_decision=self.guarantee_decision,
            required_documents=self.required_documents,
            approval_conditions=self.approval_conditions,
        )
        expected_hash = banking_precheck_response_hash(
            request_id=self.request_id,
            idempotency_key=self.idempotency_key,
            api_id=self.api_id,
            api_provider=self.api_provider,
            execution_mode=self.execution_mode,
            provider_reference=self.provider_reference,
            scenario_id=self.scenario_id,
            scenario_version=self.scenario_version,
            scenario_hash=self.scenario_hash,
            outcome=self.outcome,
            message=self.message,
            reason_codes=self.reason_codes,
            required_follow_up_fields=self.required_follow_up_fields,
            requested_amount=self.requested_amount,
            supported_amount=self.supported_amount,
            currency=self.currency,
            eligibility_status=self.eligibility_status,
            guarantee_decision=self.guarantee_decision,
            required_documents=self.required_documents,
            approval_conditions=self.approval_conditions,
            authority=self.authority,
            non_binding=self.non_binding,
        )
        if self.response_hash != expected_hash:
            raise ValueError("response_hash does not match the canonical raw response")
        return self


class BankingPrecheckNormalizedResult(BaseModel):
    """One non-binding normalized result tied to an exact proposal candidate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    normalized_result_id: StrictStr = Field(min_length=1)
    request_id: StrictStr = Field(min_length=1)
    idempotency_key: StrictStr = Field(min_length=1)
    proposal_item_id: StrictStr = Field(min_length=1)
    option_id: StrictStr = Field(min_length=1)
    bank_product_id: StrictStr = Field(min_length=1)
    api_id: StrictStr = Field(min_length=1)
    api_provider: StrictStr = Field(min_length=1)
    execution_mode: BankingPrecheckExecutionMode
    provider_reference: StrictStr = Field(min_length=1)
    scenario_id: StrictStr = Field(min_length=1)
    scenario_version: StrictStr = Field(min_length=1)
    scenario_hash: StrictStr = Field(min_length=1)
    outcome: BankingPrecheckOutcome
    message: StrictStr = Field(min_length=1)
    reason_codes: tuple[StrictStr, ...] = ()
    required_follow_up_fields: tuple[StrictStr, ...] = ()
    requested_amount: StrictInt = Field(gt=0)
    supported_amount: StrictInt | None = Field(default=None, gt=0)
    currency: CurrencyCode = CurrencyCode.VND
    eligibility_status: ProviderEligibilityStatus = (
        ProviderEligibilityStatus.NOT_EVALUABLE
    )
    guarantee_decision: ProviderGuaranteeDecision = (
        ProviderGuaranteeDecision.NO_DECISION
    )
    required_documents: tuple[StrictStr, ...] = ()
    approval_conditions: tuple[StrictStr, ...] = ()
    request_hash: StrictStr = Field(min_length=1)
    response_hash: StrictStr = Field(min_length=1)
    authority: BankingPrecheckResultAuthority = (
        BankingPrecheckResultAuthority.SIMULATED_NON_BINDING
    )
    non_binding: Literal[True] = True
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_normalized_result(self) -> BankingPrecheckNormalizedResult:
        """Keep normalized authority and reference indexes exact."""
        if self.execution_mode is not BankingPrecheckExecutionMode.SIMULATED:
            raise ValueError("normalized result must be SIMULATED")
        if self.authority is not BankingPrecheckResultAuthority.SIMULATED_NON_BINDING:
            raise ValueError("normalized result authority must be non-binding")
        for field_name, values in (
            ("reason_codes", self.reason_codes),
            ("required_follow_up_fields", self.required_follow_up_fields),
            ("required_documents", self.required_documents),
            ("approval_conditions", self.approval_conditions),
            ("evidence_ids", self.evidence_ids),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} must be unique")
        _validate_provider_conclusion(
            outcome=self.outcome,
            requested_amount=self.requested_amount,
            supported_amount=self.supported_amount,
            currency=self.currency,
            eligibility_status=self.eligibility_status,
            guarantee_decision=self.guarantee_decision,
            required_documents=self.required_documents,
            approval_conditions=self.approval_conditions,
        )
        return self


class BankingPrecheckResultSet(BaseModel):
    """Complete simulated result batch without selection or bank authority."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    result_set_id: StrictStr = Field(min_length=1)
    evaluation_case_id: StrictStr = Field(min_length=1)
    dataset_id: StrictStr = Field(min_length=1)
    contract_id: StrictStr = Field(min_length=1)
    proposal_artifact_id: StrictStr = Field(min_length=1)
    proposal_id: StrictStr = Field(min_length=1)
    approval_request_id: StrictStr = Field(min_length=1)
    permit_id: StrictStr = Field(min_length=1)
    execution_mode: BankingPrecheckExecutionMode = (
        BankingPrecheckExecutionMode.SIMULATED
    )
    authority: BankingPrecheckResultAuthority = (
        BankingPrecheckResultAuthority.SIMULATED_NON_BINDING
    )
    adapter_id: StrictStr = Field(min_length=1)
    adapter_config_hash: StrictStr = Field(min_length=1)
    candidate_option_ids: tuple[StrictStr, ...] = Field(min_length=1)
    results: tuple[BankingPrecheckNormalizedResult, ...] = Field(min_length=1)
    source_artifact_ids: tuple[StrictStr, ...] = Field(min_length=1)
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)
    adapter_invoked: Literal[True] = True
    external_bank_submission: Literal[False] = False
    bank_approval_obtained: Literal[False] = False
    selection_performed: Literal[False] = False
    ranking_performed: Literal[False] = False
    documents_prepared: Literal[False] = False

    @model_validator(mode="after")
    def validate_result_batch(self) -> BankingPrecheckResultSet:
        """Require one result per candidate in exact order and non-binding authority."""
        result_option_ids = tuple(item.option_id for item in self.results)
        if result_option_ids != self.candidate_option_ids:
            raise ValueError(
                "candidate_option_ids must exactly match normalized result order"
            )
        for field_name, values in (
            ("candidate_option_ids", self.candidate_option_ids),
            (
                "proposal_item_ids",
                tuple(item.proposal_item_id for item in self.results),
            ),
            ("request_ids", tuple(item.request_id for item in self.results)),
            (
                "idempotency_keys",
                tuple(item.idempotency_key for item in self.results),
            ),
            ("source_artifact_ids", self.source_artifact_ids),
            ("evidence_ids", self.evidence_ids),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} must be unique")
        if any(
            item.execution_mode is not self.execution_mode
            or item.authority is not self.authority
            or not item.non_binding
            for item in self.results
        ):
            raise ValueError("all normalized results must share result-set authority")
        return self


class BankingPrecheckSimulationScenario(BaseModel):
    """One server-owned deterministic simulated-provider scenario."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scenario_id: StrictStr = Field(min_length=1)
    api_id: StrictStr = Field(min_length=1)
    api_provider: StrictStr = Field(min_length=1)
    outcome: BankingPrecheckOutcome
    message: StrictStr = Field(min_length=1)
    reason_codes: tuple[StrictStr, ...] = ()
    required_follow_up_fields: tuple[StrictStr, ...] = ()
    eligibility_status: ProviderEligibilityStatus = (
        ProviderEligibilityStatus.NOT_EVALUABLE
    )
    guarantee_decision: ProviderGuaranteeDecision = (
        ProviderGuaranteeDecision.NO_DECISION
    )
    supported_amount_strategy: BankingPrecheckSupportedAmountStrategy = (
        BankingPrecheckSupportedAmountStrategy.NONE
    )
    currency: CurrencyCode = CurrencyCode.VND
    required_documents: tuple[StrictStr, ...] = ()
    approval_conditions: tuple[StrictStr, ...] = ()
    non_binding: Literal[True] = True

    @model_validator(mode="after")
    def validate_scenario(self) -> BankingPrecheckSimulationScenario:
        """Reject duplicate reason and follow-up declarations."""
        for field_name, values in (
            ("reason_codes", self.reason_codes),
            ("required_follow_up_fields", self.required_follow_up_fields),
            ("required_documents", self.required_documents),
            ("approval_conditions", self.approval_conditions),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"scenario {field_name} must be unique")
        if self.currency is not CurrencyCode.VND:
            raise ValueError("simulation scenarios must use VND")
        if self.outcome is BankingPrecheckOutcome.CONDITIONAL_PRECHECK:
            if (
                self.supported_amount_strategy
                is not BankingPrecheckSupportedAmountStrategy.ECHO_REQUESTED_AMOUNT
            ):
                raise ValueError(
                    "CONDITIONAL_PRECHECK requires ECHO_REQUESTED_AMOUNT in this prototype"
                )
            _validate_provider_conclusion(
                outcome=self.outcome,
                requested_amount=1,
                supported_amount=1,
                currency=self.currency,
                eligibility_status=self.eligibility_status,
                guarantee_decision=self.guarantee_decision,
                required_documents=self.required_documents,
                approval_conditions=self.approval_conditions,
            )
            return self
        if (
            self.supported_amount_strategy
            is not BankingPrecheckSupportedAmountStrategy.NONE
        ):
            raise ValueError(
                "non-conditional scenarios cannot produce a supported amount"
            )
        _validate_provider_conclusion(
            outcome=self.outcome,
            requested_amount=1,
            supported_amount=None,
            currency=self.currency,
            eligibility_status=self.eligibility_status,
            guarantee_decision=self.guarantee_decision,
            required_documents=self.required_documents,
            approval_conditions=self.approval_conditions,
        )
        return self


class BankingPrecheckSimulationPolicyDocument(BaseModel):
    """Validated content of the server-owned simulation scenario document."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    configuration_id: StrictStr = Field(min_length=1)
    configuration_version: StrictStr = Field(min_length=1)
    scenarios: tuple[BankingPrecheckSimulationScenario, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_scenarios(self) -> BankingPrecheckSimulationPolicyDocument:
        """Require one unambiguous scenario per configured API/provider pair."""
        scenario_ids = tuple(item.scenario_id for item in self.scenarios)
        api_keys = tuple((item.api_id, item.api_provider) for item in self.scenarios)
        if len(set(scenario_ids)) != len(scenario_ids):
            raise ValueError("simulation scenario IDs must be unique")
        if len(set(api_keys)) != len(api_keys):
            raise ValueError("simulation APIs/providers must map to one scenario")
        return self


class BankingPrecheckSimulationPolicy(BankingPrecheckSimulationPolicyDocument):
    """Runtime scenario policy with a canonical configuration hash."""

    configuration_hash: StrictStr = Field(min_length=1)


class BankingPrecheckResultComponentInput(BaseModel):
    """Workflow-enriched input after permit issuance and simulated adapter execution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    permit: AuthorizedActionPermit
    requests: tuple[BankingPrecheckRequest, ...] = Field(min_length=1)
    raw_responses: tuple[BankingPrecheckRawResponse, ...] = Field(min_length=1)
    adapter_id: StrictStr = Field(min_length=1)
    adapter_config_hash: StrictStr = Field(min_length=1)


class BankingPrecheckResultComponentResult(ComponentResult):
    """Side-effect-free normalized output returned by the Banking component."""

    result_set: BankingPrecheckResultSet | None = None


class BankingPrecheckResultExecutionResult(BaseModel):
    """Validated and persisted Phase B1 result returned by workflow boundaries."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: str
    result_set: BankingPrecheckResultSet | None = None
    generated_artifacts: tuple[ArtifactEnvelope, ...] = ()
    validation_reports: tuple[ValidationReport, ...] = ()
    validation_errors: tuple[str, ...] = ()
    missing_data_requests: tuple[MissingDataRequest, ...] = ()
    warnings: tuple[str, ...] = ()
    runtime_events: tuple[dict[str, Any], ...] = ()
