"""Enumerations used by the Planner Skill domain."""

from enum import StrEnum


class SourceType(StrEnum):
    """Origin of a piece of evidence."""

    TEAM_PACK = "TEAM_PACK"
    USER_INPUT = "USER_INPUT"
    DERIVED = "DERIVED"
    POLICY_CONFIG = "POLICY_CONFIG"


class CurrencyCode(StrEnum):
    """Canonical currency used by monetary values in the OPC TeamPack."""

    VND = "VND"


class EvaluationScope(StrEnum):
    """Requested initial assessment scopes."""

    FINANCE = "FINANCE"
    OPERATIONS = "OPERATIONS"
    RISK = "RISK"


class ReadinessStatus(StrEnum):
    """Whether downstream initial assessment can start."""

    READY = "READY"
    READY_WITH_WARNINGS = "READY_WITH_WARNINGS"
    BLOCKED = "BLOCKED"


class CashflowScope(StrEnum):
    """Relationship between cashflow data and an evaluation case."""

    OPC_GLOBAL = "OPC_GLOBAL"
    CASE_SPECIFIC = "CASE_SPECIFIC"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class MissingSeverity(StrEnum):
    """Severity of a missing-data request."""

    BLOCKING = "BLOCKING"


class MissingRequestStatus(StrEnum):
    """Lifecycle state of a missing-data request."""

    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


class ComponentStatus(StrEnum):
    """Allowed status returned by any business component."""

    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    WAITING_FOR_INPUT = "WAITING_FOR_INPUT"
    FAILED_SAFE = "FAILED_SAFE"


class WorkflowStatus(StrEnum):
    """Persisted workflow status owned by the Orchestrator."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    WAITING_FOR_DEPENDENCIES = "WAITING_FOR_DEPENDENCIES"
    WAITING_FOR_INPUT = "WAITING_FOR_INPUT"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    WAITING_FOR_DEMO = "WAITING_FOR_DEMO"
    BLOCKED = "BLOCKED"
    FAILED_SAFE = "FAILED_SAFE"


class WorkflowNodeStatus(StrEnum):
    """Durable execution status of one Master Workflow node."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_FOR_DEPENDENCIES = "WAITING_FOR_DEPENDENCIES"
    WAITING_FOR_INPUT = "WAITING_FOR_INPUT"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    BLOCKED = "BLOCKED"
    FAILED_SAFE = "FAILED_SAFE"


class RunTaskType(StrEnum):
    """Workflow task identifiers used in Planner's initial run plan."""

    FINANCE_ASSESSMENT = "FINANCE_ASSESSMENT"
    OPERATIONS_ASSESSMENT = "OPERATIONS_ASSESSMENT"
    INITIAL_RISK_SCAN = "INITIAL_RISK_SCAN"


class ArtifactType(StrEnum):
    """Artifact types emitted by implemented business components."""

    PLANNER_RESULT = "PLANNER_RESULT"
    EVALUATION_CASE = "EVALUATION_CASE"
    FINANCE_FACTS = "FINANCE_FACTS"
    FINANCE_ASSESSMENT = "FINANCE_ASSESSMENT"
    OPERATIONS_FACTS = "OPERATIONS_FACTS"
    OPERATIONS_ASSESSMENT = "OPERATIONS_ASSESSMENT"
    RISK_PRE_SCAN = "RISK_PRE_SCAN"
    APPROVAL_CHECKPOINTS = "APPROVAL_CHECKPOINTS"
    RISK_RULE_EVALUATION = "RISK_RULE_EVALUATION"
    INITIAL_RISK_ASSESSMENT = "INITIAL_RISK_ASSESSMENT"
    DECISION_ROUTE_PLAN = "DECISION_ROUTE_PLAN"
    BANKING_DISCOVERY_REQUEST = "BANKING_DISCOVERY_REQUEST"
    BANKING_OPTION_MATRIX = "BANKING_OPTION_MATRIX"
    BANKING_DISCOVERY_RESULT = "BANKING_DISCOVERY_RESULT"
    BANKING_OPTION_ADVICE = "BANKING_OPTION_ADVICE"
    BANKING_INPUT_SUPPLEMENT = "BANKING_INPUT_SUPPLEMENT"
    BANKING_PRECHECK_READINESS = "BANKING_PRECHECK_READINESS"
    DECISION_POST_BANKING_REVIEW = "DECISION_POST_BANKING_REVIEW"
    BANKING_PRECHECK_SUBMISSION_PROPOSAL = (
        "BANKING_PRECHECK_SUBMISSION_PROPOSAL"
    )
    BANKING_PRECHECK_RESULT_SET = "BANKING_PRECHECK_RESULT_SET"
    DECISION_POST_PRECHECK_REVIEW = "DECISION_POST_PRECHECK_REVIEW"
    BANKING_PRECHECK_EVIDENCE_SUPPLEMENT = (
        "BANKING_PRECHECK_EVIDENCE_SUPPLEMENT"
    )
    DOCUMENT_PREPARATION_REQUEST = "DOCUMENT_PREPARATION_REQUEST"
    DOCUMENT_CHECKLIST = "DOCUMENT_CHECKLIST"
    DOCUMENT_PACKAGE_DRAFT = "DOCUMENT_PACKAGE_DRAFT"
    DOCUMENT_RELEASE_PACKAGE = "DOCUMENT_RELEASE_PACKAGE"
    DOCUMENT_EVIDENCE_SUPPLEMENT = "DOCUMENT_EVIDENCE_SUPPLEMENT"
    INTERNAL_DECISION_PACKAGE = "INTERNAL_DECISION_PACKAGE"
    FINAL_RISK_ASSESSMENT = "FINAL_RISK_ASSESSMENT"
    AI_DECISION_ANALYSIS = "AI_DECISION_ANALYSIS"
    DECISION_CARD = "DECISION_CARD"
    POST_DECISION_UPDATE = "POST_DECISION_UPDATE"
    NEGOTIATION_OUTCOME = "NEGOTIATION_OUTCOME"
    EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL = (
        "EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL"
    )


class DecisionRouteMode(StrEnum):
    """Workflow-selected execution mode for Decision Route Planning."""

    INITIAL_ROUTE = "INITIAL_ROUTE"


class DecisionHandoffMode(StrEnum):
    """Explicit Decision capability handoff currently supported by Workflow."""

    BANKING_DISCOVERY = "BANKING_DISCOVERY"
    DOCUMENT_PREPARATION = "DOCUMENT_PREPARATION"


class BankingDiscoveryHandoffStatus(StrEnum):
    """Outcome of Decision's deterministic Banking discovery handoff."""

    REQUEST_CREATED = "REQUEST_CREATED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    WAITING_FOR_ROUTE = "WAITING_FOR_ROUTE"
    FAILED_SAFE = "FAILED_SAFE"


class BankingDiscoveryStatus(StrEnum):
    """Outcome of Banking's internal, side-effect-free catalog discovery."""

    OPTIONS_READY = "OPTIONS_READY"
    OPTIONS_READY_WITH_GAPS = "OPTIONS_READY_WITH_GAPS"
    NO_CONFIGURED_OPTIONS = "NO_CONFIGURED_OPTIONS"
    WAITING_FOR_REQUEST = "WAITING_FOR_REQUEST"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    FAILED_SAFE = "FAILED_SAFE"


class BankingCriterionStatus(StrEnum):
    """Deterministic result of one catalog criterion evaluation."""

    PASS = "PASS"
    FAIL = "FAIL"
    NOT_EVALUABLE = "NOT_EVALUABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class BankingCriterionCode(StrEnum):
    """Supported deterministic Banking discovery checks."""

    NEED_TYPE_CONFIGURED = "NEED_TYPE_CONFIGURED"
    MINIMUM_AMOUNT = "MINIMUM_AMOUNT"
    EXPLICIT_CREDIT_PROFILE_RELATIONSHIP = "EXPLICIT_CREDIT_PROFILE_RELATIONSHIP"
    MOCK_PRECHECK_METADATA = "MOCK_PRECHECK_METADATA"


class BankingDataGapCode(StrEnum):
    """Typed evidence gaps that limit a later Banking precheck."""

    REQUESTED_AMOUNT_UNAVAILABLE = "REQUESTED_AMOUNT_UNAVAILABLE"
    REQUESTED_AMOUNT_CURRENCY_UNAVAILABLE = "REQUESTED_AMOUNT_CURRENCY_UNAVAILABLE"
    CREDIT_PROFILE_RELATIONSHIP_UNCONFIRMED = (
        "CREDIT_PROFILE_RELATIONSHIP_UNCONFIRMED"
    )


class BankingPrecheckStatus(StrEnum):
    """Whether mock API metadata exists; execution is outside Phase A."""

    MOCK_AVAILABLE_NOT_EXECUTED = "MOCK_AVAILABLE_NOT_EXECUTED"
    NOT_CONFIGURED = "NOT_CONFIGURED"


class BankingPrecheckFieldSource(StrEnum):
    """Explicit server-policy source for one external-API required field."""

    EVALUATION_CASE = "EVALUATION_CASE"
    BANKING_DISCOVERY_REQUEST = "BANKING_DISCOVERY_REQUEST"
    BANKING_INPUT_SUPPLEMENT = "BANKING_INPUT_SUPPLEMENT"
    OPC_PROFILE = "OPC_PROFILE"


class BankingPrecheckFieldStatus(StrEnum):
    """Resolution state of one explicitly mapped precheck field."""

    RESOLVED = "RESOLVED"
    MISSING_INPUT = "MISSING_INPUT"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    UNMAPPED = "UNMAPPED"


class BankingPrecheckReadinessStatus(StrEnum):
    """Deterministic readiness without executing the configured precheck."""

    READY = "READY"
    PARTIALLY_READY = "PARTIALLY_READY"
    INPUT_REQUIRED = "INPUT_REQUIRED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    UNSUPPORTED_MAPPING = "UNSUPPORTED_MAPPING"
    OPTION_REQUIREMENTS_NOT_MET = "OPTION_REQUIREMENTS_NOT_MET"


class BankingPrecheckExecutionMode(StrEnum):
    """Execution mode supported by the isolated Phase B1 precheck boundary."""

    SIMULATED = "SIMULATED"


class BankingPrecheckOutcome(StrEnum):
    """Non-binding normalized outcomes returned by a precheck provider."""

    CONDITIONAL_PRECHECK = "CONDITIONAL_PRECHECK"
    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    NO_RECOMMENDATION = "NO_RECOMMENDATION"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"


class ProviderEligibilityStatus(StrEnum):
    """Eligibility conclusion carried by a non-binding provider precheck."""

    ELIGIBLE = "ELIGIBLE"
    CONDITIONAL = "CONDITIONAL"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    NOT_EVALUABLE = "NOT_EVALUABLE"


class ProviderGuaranteeDecision(StrEnum):
    """Provider posture for a guarantee request; never a final bank approval."""

    WILLING = "WILLING"
    CONDITIONAL = "CONDITIONAL"
    DECLINED = "DECLINED"
    NO_DECISION = "NO_DECISION"


class BankingPrecheckSupportedAmountStrategy(StrEnum):
    """Server-owned rule used only to produce a simulated supported amount."""

    NONE = "NONE"
    ECHO_REQUESTED_AMOUNT = "ECHO_REQUESTED_AMOUNT"


class BankingPrecheckResultAuthority(StrEnum):
    """Authority boundary of a Phase B1 result set."""

    SIMULATED_NON_BINDING = "SIMULATED_NON_BINDING"


class DecisionPostPrecheckOptionDisposition(StrEnum):
    """Deterministic interpretation of one non-binding precheck result."""

    CONDITIONAL_REVIEW = "CONDITIONAL_REVIEW"
    FOLLOW_UP_EVIDENCE_REQUIRED = "FOLLOW_UP_EVIDENCE_REQUIRED"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    NO_PROVIDER_RECOMMENDATION = "NO_PROVIDER_RECOMMENDATION"
    PRECHECK_UNAVAILABLE = "PRECHECK_UNAVAILABLE"


class DecisionPostPrecheckOutcome(StrEnum):
    """Aggregate Decision route after every precheck candidate is preserved."""

    FOLLOW_UP_EVIDENCE_REQUIRED = "FOLLOW_UP_EVIDENCE_REQUIRED"
    CONDITIONAL_OPTIONS_AVAILABLE = "CONDITIONAL_OPTIONS_AVAILABLE"
    ALL_OPTIONS_NOT_ELIGIBLE = "ALL_OPTIONS_NOT_ELIGIBLE"
    NO_PROVIDER_RECOMMENDATION = "NO_PROVIDER_RECOMMENDATION"
    PRECHECK_SERVICE_UNAVAILABLE = "PRECHECK_SERVICE_UNAVAILABLE"
    MIXED_NON_ACTIONABLE_RESULTS = "MIXED_NON_ACTIONABLE_RESULTS"


class BankingHandlingPolicyEffect(StrEnum):
    """Execution effect of source handling text in the current phase."""

    SOURCE_GUIDANCE_ONLY = "SOURCE_GUIDANCE_ONLY"


class BankingAdviceSource(StrEnum):
    """How optional Banking option prose was produced."""

    OPENAI = "OPENAI"
    DETERMINISTIC_FALLBACK = "DETERMINISTIC_FALLBACK"
    NOT_INVOKED = "NOT_INVOKED"


class BankingAdviceStatus(StrEnum):
    """Authority boundary of the Banking option advisor."""

    ADVISORY_ONLY = "ADVISORY_ONLY"
    NOT_INVOKED = "NOT_INVOKED"


class DecisionRouteOutcome(StrEnum):
    """Business routing outcome; Workflow owns the concrete next node."""

    DIRECT_INTERNAL_DECISION = "DIRECT_INTERNAL_DECISION"
    BANKING_DISCOVERY_REQUIRED = "BANKING_DISCOVERY_REQUIRED"


class DecisionPostBankingOutcome(StrEnum):
    """Decision classification after Banking readiness, before protected actions."""

    BANKING_PRECHECK_READY = "BANKING_PRECHECK_READY"
    BANKING_INPUT_REQUIRED = "BANKING_INPUT_REQUIRED"
    NO_PRECHECK_PATH = "NO_PRECHECK_PATH"
    UNSUPPORTED_PRECHECK_MAPPING = "UNSUPPORTED_PRECHECK_MAPPING"
    NO_VIABLE_OPTION = "NO_VIABLE_OPTION"


class DecisionCapability(StrEnum):
    """Downstream business capability requested by a route plan."""

    INTERNAL_DECISION_PACKAGE = "INTERNAL_DECISION_PACKAGE"
    BANKING_INTERNAL_DISCOVERY = "BANKING_INTERNAL_DISCOVERY"


class BankingNeedType(StrEnum):
    """Typed, evidence-backed banking need supported by Initial Route."""

    PERFORMANCE_BOND = "PERFORMANCE_BOND"


class ContractRequirementType(StrEnum):
    """Typed business requirements observed on one explicit contract case."""

    PERFORMANCE_BOND = "PERFORMANCE_BOND"
    WORKING_CAPITAL = "WORKING_CAPITAL"
    TRADE_FINANCE_LC = "TRADE_FINANCE_LC"


class RequirementCertainty(StrEnum):
    """Whether source wording declares a requirement or only a possibility."""

    REQUIRED = "REQUIRED"
    POSSIBLE = "POSSIBLE"


class RequirementAmountSemantics(StrEnum):
    """Authoritative meaning of an amount attached to a contract requirement."""

    CREDIT_PROFILE_REQUESTED_AMOUNT = "CREDIT_PROFILE_REQUESTED_AMOUNT"


class DecisionRoutingReasonCode(StrEnum):
    """Typed reason codes accepted by the Initial Route policy."""

    PERFORMANCE_BOND_REQUIREMENT = "PERFORMANCE_BOND_REQUIREMENT"


class RiskRunStatus(StrEnum):
    """Persisted pause/resume state of one initial Risk scan."""

    PRE_SCAN_RUNNING = "PRE_SCAN_RUNNING"
    WAITING_FOR_FACTS = "WAITING_FOR_FACTS"
    FINALIZING = "FINALIZING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_LIMITATIONS = "COMPLETED_WITH_LIMITATIONS"
    FAILED_SAFE = "FAILED_SAFE"


class RiskDependency(StrEnum):
    """Authoritative upstream facts required before Risk finalization."""

    FINANCE_FACTS = "FINANCE_FACTS"
    OPERATIONS_FACTS = "OPERATIONS_FACTS"


class RiskExecutionMode(StrEnum):
    """Explicit workflow-selected phase of the Initial Risk component."""

    PRE_SCAN = "PRE_SCAN"
    FINALIZE = "FINALIZE"


class RiskScope(StrEnum):
    """Relationship of a Risk signal to the current evaluation case."""

    CASE_SPECIFIC = "CASE_SPECIFIC"
    OPC_GLOBAL = "OPC_GLOBAL"
    EVENT_SPECIFIC = "EVENT_SPECIFIC"


class RiskSeverity(StrEnum):
    """Severity values accepted from typed TeamPack rules and alerts."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskLevel(StrEnum):
    """Case-level aggregation without inventing a numeric score."""

    NO_CASE_SIGNAL = "NO_CASE_SIGNAL"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RuleEvaluationStatus(StrEnum):
    """Outcome of one safely parsed source rule."""

    TRIGGERED = "TRIGGERED"
    NOT_TRIGGERED = "NOT_TRIGGERED"
    NOT_EVALUABLE = "NOT_EVALUABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class RuleOperator(StrEnum):
    """Whitelisted comparison operators supported by the Risk engine."""

    GREATER_THAN_OR_EQUAL = "GTE"
    LESS_THAN_OR_EQUAL = "LTE"
    GREATER_THAN = "GT"
    LESS_THAN = "LT"
    EQUAL = "EQ"


class RiskAssessmentStatus(StrEnum):
    """Completeness of the finalized initial Risk assessment."""

    COMPLETE = "COMPLETE"
    LIMITED_BY_EVIDENCE = "LIMITED_BY_EVIDENCE"


class FinalRiskAssessmentStatus(StrEnum):
    """Completeness of the final evidence-based Risk check."""

    COMPLETE = "COMPLETE"
    LIMITED_BY_EVIDENCE = "LIMITED_BY_EVIDENCE"


class FinalRiskConclusion(StrEnum):
    """Whether any residual risk, evidence gap, or human gate remains open."""

    SAFE = "SAFE"
    ATTENTION_REQUIRED = "ATTENTION_REQUIRED"


class ResidualRiskStatus(StrEnum):
    """Whether an initial case finding has explicit mitigation evidence."""

    OPEN_UNCHANGED = "OPEN_UNCHANGED"


class MajorExceptionStatus(StrEnum):
    """Conservative major-exception conclusion from explicit final evidence."""

    DETECTED = "DETECTED"
    NOT_DETECTED = "NOT_DETECTED"
    NOT_EVALUABLE = "NOT_EVALUABLE"


class FinalRiskControlCode(StrEnum):
    """Typed controls retained by Final Risk without executing an action."""

    HUMAN_CONFIRMATION_REQUIRED = "HUMAN_CONFIRMATION_REQUIRED"
    EVIDENCE_LIMITATION_MUST_BE_PRESERVED = (
        "EVIDENCE_LIMITATION_MUST_BE_PRESERVED"
    )
    GOVERNANCE_EVALUATION_BEFORE_PROTECTED_ACTION = (
        "GOVERNANCE_EVALUATION_BEFORE_PROTECTED_ACTION"
    )
    GOVERNANCE_REJECTION_MUST_BE_HONORED = (
        "GOVERNANCE_REJECTION_MUST_BE_HONORED"
    )
    SIMULATED_BANKING_RESULT_IS_NON_BINDING = (
        "SIMULATED_BANKING_RESULT_IS_NON_BINDING"
    )
    DOCUMENT_RELEASE_REQUIRES_SEPARATE_AUTHORIZATION = (
        "DOCUMENT_RELEASE_REQUIRES_SEPARATE_AUTHORIZATION"
    )


class ApprovalSignalStatus(StrEnum):
    """Lifecycle state of a side-effect-free approval checkpoint signal."""

    CHECKPOINT_CANDIDATE = "CHECKPOINT_CANDIDATE"


class ApprovalCheckpointStatus(StrEnum):
    """Registration state of a reusable approval policy checkpoint."""

    REGISTERED = "REGISTERED"


class ApprovalRequestStatus(StrEnum):
    """Durable authorization state for one protected-action request."""

    PENDING = "PENDING"
    AUTHORIZED_WITHOUT_HUMAN = "AUTHORIZED_WITHOUT_HUMAN"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ApprovalDecision(StrEnum):
    """Allowed human decisions for an approval request."""

    APPROVE = "APPROVE"
    REJECT = "REJECT"


class ApprovalGateStatus(StrEnum):
    """Deterministic outcome returned by the governance approval gate."""

    AUTHORIZED = "AUTHORIZED"
    WAITING_FOR_INPUT = "WAITING_FOR_INPUT"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ApprovalTriggerEvent(StrEnum):
    """Events that may activate a registered case approval checkpoint."""

    DOCUMENT_EXTERNAL_RELEASE_REQUESTED = "DOCUMENT_EXTERNAL_RELEASE_REQUESTED"
    LARGE_FINANCIAL_DECISION_REQUESTED = "LARGE_FINANCIAL_DECISION_REQUESTED"
    BANKING_PRECHECK_SUBMISSION_REQUESTED = (
        "BANKING_PRECHECK_SUBMISSION_REQUESTED"
    )
    FINAL_CONTRACT_DECISION_CONFIRMATION_REQUESTED = (
        "FINAL_CONTRACT_DECISION_CONFIRMATION_REQUESTED"
    )
    NEGOTIATION_OUTCOME_CONFIRMATION_REQUESTED = (
        "NEGOTIATION_OUTCOME_CONFIRMATION_REQUESTED"
    )


class ProtectedAction(StrEnum):
    """Actions that cannot execute before the governance gate authorizes them."""

    SEND_DOCUMENT_TO_EXTERNAL_PARTNER = "SEND_DOCUMENT_TO_EXTERNAL_PARTNER"
    COMMIT_LARGE_FINANCIAL_DECISION = "COMMIT_LARGE_FINANCIAL_DECISION"
    SUBMIT_BANKING_PRECHECK = "SUBMIT_BANKING_PRECHECK"
    CONFIRM_FINAL_CONTRACT_DECISION = "CONFIRM_FINAL_CONTRACT_DECISION"
    CONFIRM_NEGOTIATION_OUTCOME = "CONFIRM_NEGOTIATION_OUTCOME"


class OperationsAssessmentStatus(StrEnum):
    """Completeness of an Operations assessment without expressing risk."""

    COMPLETE = "COMPLETE"
    LIMITED_BY_EVIDENCE = "LIMITED_BY_EVIDENCE"


class OperationsDataScope(StrEnum):
    """Relationship of an operational fact to the current case."""

    CASE_SPECIFIC = "CASE_SPECIFIC"
    OPC_GLOBAL = "OPC_GLOBAL"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class OperationsFactQuality(StrEnum):
    """Evidence quality of a deterministic operational fact."""

    VERIFIED = "VERIFIED"
    LIMITED_BY_EVIDENCE = "LIMITED_BY_EVIDENCE"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class OperationsUnit(StrEnum):
    """Units allowed in Operations fact values."""

    COUNT = "COUNT"
    DAYS = "DAYS"
    DATE = "DATE"
    BOOLEAN = "BOOLEAN"
    TEXT = "TEXT"
    RATIO = "RATIO"


class OperationsSourceStatusCategory(StrEnum):
    """Neutral classification of exact order status values from TeamPack."""

    COMPLETED_SOURCE_STATUS = "COMPLETED_SOURCE_STATUS"
    ACTIVE_SOURCE_STATUS = "ACTIVE_SOURCE_STATUS"
    PLANNED_SOURCE_STATUS = "PLANNED_SOURCE_STATUS"
    SOURCE_PENDING_STATUS = "SOURCE_PENDING_STATUS"
    SOURCE_FLAGGED_STATUS = "SOURCE_FLAGGED_STATUS"
    UNCLASSIFIED_SOURCE_STATUS = "UNCLASSIFIED_SOURCE_STATUS"


class OperationsMetric(StrEnum):
    """Deterministic metrics produced by Operations."""

    CONTRACT_START_DATE = "CONTRACT_START_DATE"
    CONTRACT_END_DATE = "CONTRACT_END_DATE"
    CONTRACT_DURATION_DAYS = "CONTRACT_DURATION_DAYS"
    RELATED_ORDER_COUNT = "RELATED_ORDER_COUNT"
    EARLIEST_ORDER_DATE = "EARLIEST_ORDER_DATE"
    LATEST_ORDER_DUE_DATE = "LATEST_ORDER_DUE_DATE"
    ORDER_SCHEDULE_SPAN_DAYS = "ORDER_SCHEDULE_SPAN_DAYS"
    ORDER_OUTSIDE_CONTRACT_WINDOW_COUNT = "ORDER_OUTSIDE_CONTRACT_WINDOW_COUNT"
    ORDER_INTERVAL_GAP_COUNT = "ORDER_INTERVAL_GAP_COUNT"
    MAX_ORDER_INTERVAL_GAP_DAYS = "MAX_ORDER_INTERVAL_GAP_DAYS"
    ORDER_INTERVAL_OVERLAP_COUNT = "ORDER_INTERVAL_OVERLAP_COUNT"
    MAX_ORDER_INTERVAL_OVERLAP_DAYS = "MAX_ORDER_INTERVAL_OVERLAP_DAYS"
    SOURCE_COMPLETED_ORDER_COUNT = "SOURCE_COMPLETED_ORDER_COUNT"
    SOURCE_ACTIVE_ORDER_COUNT = "SOURCE_ACTIVE_ORDER_COUNT"
    SOURCE_PLANNED_ORDER_COUNT = "SOURCE_PLANNED_ORDER_COUNT"
    SOURCE_PENDING_ORDER_COUNT = "SOURCE_PENDING_ORDER_COUNT"
    SOURCE_FLAGGED_ORDER_COUNT = "SOURCE_FLAGGED_ORDER_COUNT"
    UNCLASSIFIED_ORDER_STATUS_COUNT = "UNCLASSIFIED_ORDER_STATUS_COUNT"
    OPEN_PAST_DUE_ORDER_COUNT = "OPEN_PAST_DUE_ORDER_COUNT"
    MAX_OPEN_PAST_DUE_DAYS = "MAX_OPEN_PAST_DUE_DAYS"
    SOURCE_DELIVERY_NOTE_COUNT = "SOURCE_DELIVERY_NOTE_COUNT"
    OPC_LATE_DELIVERY_PENALTY_RATE = "OPC_LATE_DELIVERY_PENALTY_RATE"


class OperationsCalculation(StrEnum):
    """Named deterministic calculation attached to operational facts."""

    SOURCE_VALUE = "SOURCE_VALUE"
    COUNT = "COUNT"
    DATE_DIFFERENCE_INCLUSIVE = "DATE_DIFFERENCE_INCLUSIVE"
    MIN_DATE = "MIN_DATE"
    MAX_DATE = "MAX_DATE"
    MAX = "MAX"
    INTERVAL_GAP = "INTERVAL_GAP"
    INTERVAL_OVERLAP = "INTERVAL_OVERLAP"


class OperationsObservationCode(StrEnum):
    """Neutral operational observations forwarded to Risk."""

    SOURCE_FLAGGED_ORDER_STATUS_OBSERVED = "SOURCE_FLAGGED_ORDER_STATUS_OBSERVED"
    SOURCE_PENDING_ORDER_STATUS_OBSERVED = "SOURCE_PENDING_ORDER_STATUS_OBSERVED"
    ORDER_OUTSIDE_CONTRACT_WINDOW = "ORDER_OUTSIDE_CONTRACT_WINDOW"
    OPEN_ORDER_PAST_DUE = "OPEN_ORDER_PAST_DUE"
    ORDER_INTERVAL_GAP_OBSERVED = "ORDER_INTERVAL_GAP_OBSERVED"
    ORDER_INTERVAL_OVERLAP_OBSERVED = "ORDER_INTERVAL_OVERLAP_OBSERVED"
    UNSTRUCTURED_DELIVERY_NOTE_PRESENT = "UNSTRUCTURED_DELIVERY_NOTE_PRESENT"
    NO_RELATED_ORDERS = "NO_RELATED_ORDERS"


class FinanceAssessmentStatus(StrEnum):
    """Completeness of a Finance assessment, without expressing risk."""

    COMPLETE = "COMPLETE"
    LIMITED_BY_EVIDENCE = "LIMITED_BY_EVIDENCE"


class FinanceDataScope(StrEnum):
    """Relationship of a finance fact to the current case."""

    CASE_SPECIFIC = "CASE_SPECIFIC"
    OPC_GLOBAL = "OPC_GLOBAL"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class FinanceFactQuality(StrEnum):
    """Evidence quality of a deterministic finance fact."""

    VERIFIED = "VERIFIED"
    LIMITED_BY_COVERAGE = "LIMITED_BY_COVERAGE"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class FinanceNarrativeSource(StrEnum):
    """How the non-authoritative finance narrative was composed."""

    OPENAI = "OPENAI"
    DETERMINISTIC_FALLBACK = "DETERMINISTIC_FALLBACK"


class FinanceUnit(StrEnum):
    """Units allowed in Finance fact values."""

    VND = "VND"
    RATIO = "RATIO"
    COUNT = "COUNT"
    BOOLEAN = "BOOLEAN"
    TEXT = "TEXT"


class FinanceMetric(StrEnum):
    """Deterministic metrics produced by Finance."""

    CONTRACT_VALUE = "CONTRACT_VALUE"
    CONTRACT_GROSS_MARGIN_SOURCE = "CONTRACT_GROSS_MARGIN_SOURCE"
    OPC_TARGET_GROSS_MARGIN = "OPC_TARGET_GROSS_MARGIN"
    RELATED_ORDER_COUNT = "RELATED_ORDER_COUNT"
    ORDER_REVENUE_TOTAL = "ORDER_REVENUE_TOTAL"
    ORDER_ESTIMATED_COST_TOTAL = "ORDER_ESTIMATED_COST_TOTAL"
    ORDER_GROSS_PROFIT = "ORDER_GROSS_PROFIT"
    ORDER_GROSS_MARGIN = "ORDER_GROSS_MARGIN"
    ORDER_COVERAGE_RATIO = "ORDER_COVERAGE_RATIO"
    UNCOVERED_CONTRACT_VALUE = "UNCOVERED_CONTRACT_VALUE"
    RELATED_INVOICE_COUNT = "RELATED_INVOICE_COUNT"
    INVOICE_TOTAL = "INVOICE_TOTAL"
    PAID_INVOICE_TOTAL = "PAID_INVOICE_TOTAL"
    OPEN_INVOICE_TOTAL = "OPEN_INVOICE_TOTAL"
    NOT_ISSUED_INVOICE_TOTAL = "NOT_ISSUED_INVOICE_TOTAL"
    OUTSTANDING_ISSUED_RECEIVABLE = "OUTSTANDING_ISSUED_RECEIVABLE"
    INVOICE_COVERAGE_RATIO = "INVOICE_COVERAGE_RATIO"
    CASHFLOW_MONTH_COUNT = "CASHFLOW_MONTH_COUNT"
    WORST_RESERVE_GAP = "WORST_RESERVE_GAP"
    WORST_RESERVE_GAP_MONTH = "WORST_RESERVE_GAP_MONTH"
    NEGATIVE_NET_CASHFLOW_MONTH_COUNT = "NEGATIVE_NET_CASHFLOW_MONTH_COUNT"


class FinanceCalculation(StrEnum):
    """Named deterministic calculation attached to derived Finance facts."""

    SOURCE_VALUE = "SOURCE_VALUE"
    COUNT = "COUNT"
    SUM = "SUM"
    DIFFERENCE = "DIFFERENCE"
    SAFE_RATIO = "SAFE_RATIO"
    MAX_NON_NEGATIVE_DIFFERENCE = "MAX_NON_NEGATIVE_DIFFERENCE"
    MINIMUM_BY_VALUE = "MINIMUM_BY_VALUE"


class FinanceObservationCode(StrEnum):
    """Evidence observations forwarded to Risk without activating risk rules."""

    MARGIN_BELOW_OPC_TARGET_OBSERVED = "MARGIN_BELOW_OPC_TARGET_OBSERVED"
    CASH_RESERVE_SHORTFALL_OBSERVED = "CASH_RESERVE_SHORTFALL_OBSERVED"
    NEGATIVE_NET_CASH_MOVEMENT_OBSERVED = "NEGATIVE_NET_CASH_MOVEMENT_OBSERVED"
    ORDER_COVERAGE_INCOMPLETE = "ORDER_COVERAGE_INCOMPLETE"
    RECEIVABLE_EXPOSURE_OBSERVED = "RECEIVABLE_EXPOSURE_OBSERVED"
    PERFORMANCE_BOND_REQUIREMENT_OBSERVED = "PERFORMANCE_BOND_REQUIREMENT_OBSERVED"
    TRANSACTION_LINKAGE_UNAVAILABLE = "TRANSACTION_LINKAGE_UNAVAILABLE"
    CASHFLOW_ONLY_AVAILABLE_AT_OPC_LEVEL = "CASHFLOW_ONLY_AVAILABLE_AT_OPC_LEVEL"


class ArtifactStatus(StrEnum):
    """Persistence state of an artifact envelope."""

    CREATED = "CREATED"


class ValidationStatus(StrEnum):
    """Validation outcome recorded on an artifact."""

    PENDING = "PENDING"
    VALID = "VALID"
    VALID_WITH_WARNINGS = "VALID_WITH_WARNINGS"
    BLOCKED = "BLOCKED"
