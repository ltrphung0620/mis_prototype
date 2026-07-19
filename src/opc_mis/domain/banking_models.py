"""Domain contracts for Decision-managed Banking discovery."""

from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.components import ComponentResult
from opc_mis.domain.enums import (
    BankingAdviceSource,
    BankingAdviceStatus,
    BankingCriterionCode,
    BankingCriterionStatus,
    BankingDataGapCode,
    BankingDiscoveryHandoffStatus,
    BankingDiscoveryStatus,
    BankingHandlingPolicyEffect,
    BankingNeedType,
    BankingPrecheckFieldSource,
    BankingPrecheckFieldStatus,
    BankingPrecheckReadinessStatus,
    BankingPrecheckStatus,
    ComponentStatus,
    CurrencyCode,
    DecisionCapability,
    DecisionHandoffMode,
    WorkflowStatus,
)
from opc_mis.domain.missing_data import MissingDataRequest
from opc_mis.domain.validation_reports import ValidationReport

BankingCatalogNumber = StrictInt | StrictFloat | None


class BankingNeedBinding(BaseModel):
    """Explicit policy mapping from a typed need to catalog record IDs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    binding_id: str
    need_type: BankingNeedType
    bank_product_ids: tuple[str, ...] = Field(min_length=1)
    precheck_api_by_product: dict[str, str] = Field(default_factory=dict)
    precheck_field_sources_by_api: dict[
        str, dict[str, BankingPrecheckFieldSource]
    ] = Field(default_factory=dict)
    handling_rule_ids: tuple[str, ...] = ()
    allowed_product_combinations: tuple[tuple[str, ...], ...] = ()

    @model_validator(mode="after")
    def validate_explicit_ids(self) -> "BankingNeedBinding":
        """Reject duplicate, unknown, or singleton combination declarations."""
        products = set(self.bank_product_ids)
        if len(products) != len(self.bank_product_ids):
            raise ValueError("bank_product_ids must be unique")
        if not set(self.precheck_api_by_product).issubset(products):
            raise ValueError("precheck API mapping contains an unknown bank_product_id")
        configured_api_ids = set(self.precheck_api_by_product.values())
        if set(self.precheck_field_sources_by_api) != configured_api_ids:
            raise ValueError(
                "precheck field-source mappings must exactly cover configured API IDs"
            )
        for api_id, field_sources in self.precheck_field_sources_by_api.items():
            if not field_sources:
                raise ValueError(
                    f"precheck field-source mapping for {api_id} must not be empty"
                )
            if any(not field.strip() for field in field_sources):
                raise ValueError("precheck required-field names must not be blank")
        if len(set(self.handling_rule_ids)) != len(self.handling_rule_ids):
            raise ValueError("handling_rule_ids must be unique")
        seen: set[tuple[str, ...]] = set()
        for combination in self.allowed_product_combinations:
            if len(combination) < 2:
                raise ValueError("allowed product combinations require at least two products")
            if len(set(combination)) != len(combination):
                raise ValueError("allowed product combinations cannot contain duplicates")
            if not set(combination).issubset(products):
                raise ValueError("allowed product combination contains an unknown product")
            canonical = tuple(sorted(combination))
            if canonical in seen:
                raise ValueError("allowed product combinations must be unique")
            seen.add(canonical)
        return self


class BankingCatalogPolicyDocument(BaseModel):
    """Validated content stored in the server-owned Banking mapping file."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_id: str
    mapping_version: str
    bindings: tuple[BankingNeedBinding, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_bindings(self) -> "BankingCatalogPolicyDocument":
        """Require one unambiguous binding per supported need type."""
        binding_ids = [item.binding_id for item in self.bindings]
        need_types = [item.need_type for item in self.bindings]
        if len(set(binding_ids)) != len(binding_ids):
            raise ValueError("binding_id values must be unique")
        if len(set(need_types)) != len(need_types):
            raise ValueError("need_type values must have exactly one binding")
        return self


class BankingCatalogPolicy(BankingCatalogPolicyDocument):
    """Runtime policy plus a hash that participates in artifact identity."""

    policy_hash: str


class BankingDiscoveryRequest(BaseModel):
    """Evidence-backed internal work request from Decision to Banking Skill."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str
    evaluation_case_id: str
    dataset_id: str
    contract_id: str
    execution_mode: DecisionHandoffMode
    requested_capability: DecisionCapability
    need_types: tuple[BankingNeedType, ...] = Field(min_length=1)
    requested_amount: None = None
    requested_amount_currency: CurrencyCode = CurrencyCode.VND
    constraints: tuple[str, ...] = Field(default=(), max_length=0)
    source_route_artifact_id: str
    source_route_plan_id: str
    source_artifact_ids: tuple[str, ...] = Field(min_length=1)
    evidence_ids: tuple[str, ...] = Field(min_length=1)

    @field_validator("requested_amount_currency", mode="before")
    @classmethod
    def default_request_currency(cls, value: object) -> object:
        """Read legacy null artifacts using the canonical VND convention."""
        return CurrencyCode.VND if value is None else value


class BankingInputSupplement(BaseModel):
    """Immutable, evidence-backed human input used only for Banking readiness."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    supplement_id: str
    evaluation_case_id: str
    dataset_id: str
    contract_id: str
    banking_request_id: str
    requested_amount: StrictInt = Field(gt=0)
    requested_amount_currency: CurrencyCode = CurrencyCode.VND
    provider: StrictStr = Field(min_length=1)
    note: StrictStr = Field(min_length=1)
    resolved_request_ids: tuple[str, ...] = Field(min_length=1)
    source_artifact_ids: tuple[str, ...] = Field(min_length=2)
    evidence_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_provenance(self) -> "BankingInputSupplement":
        """Reject ambiguous or duplicate supplement provenance."""
        if not self.provider.strip() or not self.note.strip():
            raise ValueError("provider and note must not be blank")
        if len(set(self.resolved_request_ids)) != len(self.resolved_request_ids):
            raise ValueError("resolved_request_ids must be unique")
        if len(set(self.source_artifact_ids)) != len(self.source_artifact_ids):
            raise ValueError("source_artifact_ids must be unique")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("evidence_ids must be unique")
        return self


class BankingCriterion(BaseModel):
    """One deterministic catalog check with explicit evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    criterion_id: str
    code: BankingCriterionCode
    status: BankingCriterionStatus
    detail: str
    evidence_ids: tuple[str, ...] = ()


class BankingDataGap(BaseModel):
    """Non-blocking discovery gap that blocks only a later external precheck."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    gap_id: str
    code: BankingDataGapCode
    detail: str
    blocking_for_precheck: bool = True
    evidence_ids: tuple[str, ...] = ()


class BankingPrecheckReference(BaseModel):
    """Mock API catalog metadata; Phase A never invokes the endpoint."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    api_id: str
    provider: str
    method: str
    endpoint: str
    description: str
    required_fields: tuple[str, ...]
    catalog_status: str
    extension_rule: str
    status: BankingPrecheckStatus
    precheck_executed: Literal[False] = False
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class BankingHandlingGuidance(BaseModel):
    """Source guidance retained as text, never promoted to Governance policy."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id: str
    applies_to: str
    possible_issue: str
    team_visible_meaning: str
    required_handling: str
    source_requires_human_approval_text: str
    sensitive_fields: str
    note: str
    policy_effect: BankingHandlingPolicyEffect = (
        BankingHandlingPolicyEffect.SOURCE_GUIDANCE_ONLY
    )
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class BankingOptionCandidate(BaseModel):
    """One configured catalog option; it is not a recommendation or selection."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    option_id: str
    need_type: BankingNeedType
    bank_product_id: str
    provider: str
    product_name: str
    target_segment: str
    description: str
    annual_rate_or_fee: BankingCatalogNumber
    processing_fee_rate: BankingCatalogNumber
    collateral_ratio: BankingCatalogNumber
    minimum_amount: BankingCatalogNumber
    minimum_amount_currency: CurrencyCode = CurrencyCode.VND
    automation_level: str
    fit_note: str
    criteria: tuple[BankingCriterion, ...]
    precheck: BankingPrecheckReference | None = None
    handling_guidance: tuple[BankingHandlingGuidance, ...] = ()
    evidence_ids: tuple[str, ...] = Field(min_length=1)

    @field_validator("minimum_amount_currency", mode="before")
    @classmethod
    def default_minimum_currency(cls, value: object) -> object:
        """Read legacy null catalog artifacts using the canonical VND convention."""
        return CurrencyCode.VND if value is None else value


class BankingOptionMatrix(BaseModel):
    """Authoritative deterministic internal discovery output."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    matrix_id: str
    evaluation_case_id: str
    dataset_id: str
    contract_id: str
    request_id: str
    mapping_policy_id: str
    mapping_version: str
    mapping_hash: str
    discovery_status: BankingDiscoveryStatus
    requested_need_types: tuple[BankingNeedType, ...] = Field(min_length=1)
    requested_amount: StrictInt | None = None
    requested_amount_currency: CurrencyCode = CurrencyCode.VND
    explicit_credit_case_ids: tuple[str, ...] = ()
    candidates: tuple[BankingOptionCandidate, ...] = ()
    data_gaps: tuple[BankingDataGap, ...] = ()
    allowed_option_combinations: tuple[tuple[str, ...], ...] = ()
    precheck_executed: Literal[False] = False
    source_artifact_ids: tuple[str, ...] = Field(min_length=2)
    evidence_ids: tuple[str, ...] = Field(min_length=1)

    @field_validator("requested_amount_currency", mode="before")
    @classmethod
    def default_matrix_currency(cls, value: object) -> object:
        """Read legacy null artifacts using the canonical VND convention."""
        return CurrencyCode.VND if value is None else value


class BankingDiscoveryResult(BaseModel):
    """Compact result pointing to the deterministic matrix artifact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    result_id: str
    evaluation_case_id: str
    dataset_id: str
    contract_id: str
    request_id: str
    matrix_id: str
    discovery_status: BankingDiscoveryStatus
    candidate_option_ids: tuple[str, ...] = ()
    data_gap_ids: tuple[str, ...] = ()
    mapping_version: str
    mapping_hash: str


class BankingPrecheckFieldResolution(BaseModel):
    """Resolution of one exact API required field under server-owned policy."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    required_field: str
    status: BankingPrecheckFieldStatus
    source: BankingPrecheckFieldSource | None = None
    source_reference: str | None = None
    source_artifact_id: str | None = None
    source_record_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_resolution(self) -> "BankingPrecheckFieldResolution":
        """Keep unmapped fields distinct from mapped-but-unavailable sources."""
        if self.status is BankingPrecheckFieldStatus.UNMAPPED:
            if self.source is not None or self.source_reference is not None:
                raise ValueError("unmapped fields cannot claim a source")
        elif self.source is None or self.source_reference is None:
            raise ValueError("mapped fields require source and source_reference")
        if (
            self.status is BankingPrecheckFieldStatus.RESOLVED
            and not self.source_record_ids
        ):
            raise ValueError("resolved fields require at least one source reference ID")
        return self


class BankingOptionPrecheckReadiness(BaseModel):
    """Readiness assessment for one option without invoking its precheck."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    option_readiness_id: str
    option_id: str
    bank_product_id: str
    api_id: str | None = None
    status: BankingPrecheckReadinessStatus
    required_fields: tuple[str, ...] = ()
    field_resolutions: tuple[BankingPrecheckFieldResolution, ...] = ()
    requirement_checks: tuple[BankingCriterion, ...] = ()
    failed_requirement_codes: tuple[BankingCriterionCode, ...] = ()
    missing_fields: tuple[str, ...] = ()
    unmapped_fields: tuple[str, ...] = ()
    unexpected_policy_fields: tuple[str, ...] = ()
    precheck_executed: Literal[False] = False
    evidence_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_field_index(self) -> "BankingOptionPrecheckReadiness":
        """Require a one-to-one field index whenever an API is configured."""
        fields = tuple(item.required_field for item in self.field_resolutions)
        if len(set(fields)) != len(fields):
            raise ValueError("precheck field resolutions must be unique")
        if self.api_id is None:
            if self.status is not BankingPrecheckReadinessStatus.NOT_CONFIGURED:
                raise ValueError("an option without API metadata must be NOT_CONFIGURED")
            if self.required_fields or self.field_resolutions:
                raise ValueError("an option without API metadata cannot resolve fields")
        elif fields != self.required_fields:
            raise ValueError("field resolutions must preserve exact API required-field order")
        check_codes = tuple(item.code for item in self.requirement_checks)
        if len(set(check_codes)) != len(check_codes):
            raise ValueError("precheck requirement checks must use unique codes")
        if not set(self.failed_requirement_codes).issubset(set(check_codes)):
            raise ValueError("failed requirement codes must reference a requirement check")
        return self


class BankingPrecheckReadiness(BaseModel):
    """Aggregate deterministic assessment; it never executes an external call."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    readiness_id: str
    evaluation_case_id: str
    dataset_id: str
    contract_id: str
    matrix_id: str
    supplement_id: str | None = None
    requested_amount_currency: CurrencyCode = CurrencyCode.VND
    status: BankingPrecheckReadinessStatus
    option_readiness: tuple[BankingOptionPrecheckReadiness, ...]
    ready_option_ids: tuple[str, ...] = ()
    pending_option_ids: tuple[str, ...] = ()
    source_artifact_ids: tuple[str, ...] = Field(min_length=2)
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    precheck_executed: Literal[False] = False

    @model_validator(mode="after")
    def validate_option_indexes(self) -> "BankingPrecheckReadiness":
        """Require ready/pending indexes to partition all assessed options."""
        option_ids = tuple(item.option_id for item in self.option_readiness)
        if len(set(option_ids)) != len(option_ids):
            raise ValueError("option readiness entries must be unique")
        if set(self.ready_option_ids) & set(self.pending_option_ids):
            raise ValueError("ready and pending option indexes must be disjoint")
        if set(option_ids) != set(self.ready_option_ids) | set(self.pending_option_ids):
            raise ValueError("ready and pending option indexes must cover assessed options")
        return self


class BankingAdvisorOption(BaseModel):
    """Sanitized candidate facts allowed through the option-advisor port."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    option_id: str
    need_type: BankingNeedType
    provider: str
    product_name: str
    criterion_statuses: tuple[str, ...]
    limitation_codes: tuple[BankingDataGapCode, ...] = ()


class BankingAdvisorInput(BaseModel):
    """Identifier-free, numeric-free context supplied to optional OpenAI prose."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    matrix_id: str
    options: tuple[BankingAdvisorOption, ...]
    allowed_option_combinations: tuple[tuple[str, ...], ...] = ()


class BankingOptionSuggestionDraft(BaseModel):
    """Structured, untrusted advisor output before deterministic guarding."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    option_ids: tuple[str, ...] = Field(min_length=1)
    rationale: StrictStr


class BankingOptionAdviceDraft(BaseModel):
    """Structured OpenAI response before stable IDs and lineage are attached."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    overview: StrictStr
    suggestions: tuple[BankingOptionSuggestionDraft, ...]


class BankingAdviceComposition(BaseModel):
    """Port result with safe runtime provenance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    advice: BankingOptionAdviceDraft
    source: BankingAdviceSource
    model: str
    prompt_version: str
    fallback_reason: str | None = None


class BankingOptionSuggestion(BaseModel):
    """Guarded advisory suggestion tied only to deterministic option IDs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    suggestion_id: str
    option_ids: tuple[str, ...] = Field(min_length=1)
    rationale: str


class BankingOptionAdvice(BaseModel):
    """Non-authoritative prose that cannot select or execute an option."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    advice_id: str
    evaluation_case_id: str
    matrix_id: str
    advisor_configuration_hash: str = "UNSPECIFIED"
    status: BankingAdviceStatus
    source: BankingAdviceSource
    overview: str
    suggestions: tuple[BankingOptionSuggestion, ...]
    model: str
    prompt_version: str
    fallback_reason: str | None = None


class BankingDiscoveryHandoffComponentResult(ComponentResult):
    """Side-effect-free Decision result; it never invokes a Banking adapter."""

    handoff_status: BankingDiscoveryHandoffStatus
    banking_discovery_request: BankingDiscoveryRequest | None = None


class BankingDiscoveryComponentResult(ComponentResult):
    """Typed output of deterministic internal Banking catalog discovery."""

    discovery_status: BankingDiscoveryStatus
    option_matrix: BankingOptionMatrix | None = None
    discovery_result: BankingDiscoveryResult | None = None


class BankingAdviceComponentResult(ComponentResult):
    """Typed output of the optional, bounded option-advisor component."""

    option_advice: BankingOptionAdvice | None = None


class BankingPrecheckReadinessComponentResult(ComponentResult):
    """Typed result of side-effect-free precheck readiness assessment."""

    readiness: BankingPrecheckReadiness | None = None


class BankingDiscoveryHandoffExecutionResult(BaseModel):
    """Validated handoff result returned through the application boundary."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: str
    handoff_status: BankingDiscoveryHandoffStatus
    banking_discovery_request: BankingDiscoveryRequest | None = None
    generated_artifacts: tuple[ArtifactEnvelope, ...] = ()
    validation_reports: tuple[ValidationReport, ...] = ()
    validation_errors: tuple[str, ...] = ()
    missing_data_requests: tuple[MissingDataRequest, ...] = ()
    warnings: tuple[str, ...] = ()
    runtime_events: tuple[dict[str, Any], ...] = ()


class BankingDiscoveryExecutionResult(BaseModel):
    """Validated Banking Phase A result returned through API and Workflow."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: str
    discovery_status: BankingDiscoveryStatus
    option_matrix: BankingOptionMatrix | None = None
    discovery_result: BankingDiscoveryResult | None = None
    option_advice: BankingOptionAdvice | None = None
    generated_artifacts: tuple[ArtifactEnvelope, ...] = ()
    validation_reports: tuple[ValidationReport, ...] = ()
    validation_errors: tuple[str, ...] = ()
    missing_data_requests: tuple[MissingDataRequest, ...] = ()
    warnings: tuple[str, ...] = ()
    runtime_events: tuple[dict[str, Any], ...] = ()


class BankingPrecheckReadinessExecutionResult(BaseModel):
    """Validated readiness result returned through the application boundary."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: str
    readiness: BankingPrecheckReadiness | None = None
    generated_artifacts: tuple[ArtifactEnvelope, ...] = ()
    validation_reports: tuple[ValidationReport, ...] = ()
    validation_errors: tuple[str, ...] = ()
    missing_data_requests: tuple[MissingDataRequest, ...] = ()
    warnings: tuple[str, ...] = ()
    runtime_events: tuple[dict[str, Any], ...] = ()
