"""Canonical TeamPack entities used by ingestion and Planner resolution."""

from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class SheetDefinition:
    """Schema information for one supported TeamPack entity."""

    canonical_entity: str
    sheet_name: str
    primary_key: str | None
    required_headers: tuple[str, ...]
    mandatory: bool = False


class SheetRegistry:
    """Single source of truth for workbook names used by the Planner intake domain."""

    OPC_PROFILE = SheetDefinition("OPC_PROFILE", "02_OPC_PROFILE", "field", ("field", "value"))
    CUSTOMERS = SheetDefinition(
        "CUSTOMER",
        "03_CUSTOMERS",
        "customer_id",
        (
            "customer_id",
            "customer_name",
            "customer_type",
            "province",
            "industry",
            "strategic_value",
            "revenue_model",
            "payment_reliability",
            "banking_fit_hint",
        ),
        mandatory=True,
    )
    CONTRACTS = SheetDefinition(
        "CONTRACT",
        "04_CONTRACTS",
        "contract_id",
        (
            "contract_id",
            "customer_id",
            "start_date",
            "end_date",
            "status",
            "description",
            "contract_value",
            "gross_margin",
            "payment_terms",
        ),
        mandatory=True,
    )
    PRODUCTS = SheetDefinition(
        "SERVICE",
        "05_PRODUCTS",
        "service_id",
        (
            "service_id",
            "service_name",
            "pricing_model",
            "list_price",
            "target_margin",
            "target_segment",
        ),
        mandatory=True,
    )
    ORDERS = SheetDefinition(
        "ORDER",
        "06_ORDERS",
        "order_id",
        (
            "order_id",
            "contract_id",
            "customer_id",
            "order_date",
            "due_date",
            "status",
            "service_id",
            "order_revenue",
            "estimated_cost",
            "delivery_note",
        ),
        mandatory=True,
    )
    INVOICES = SheetDefinition(
        "INVOICE",
        "07_INVOICES",
        "invoice_id",
        (
            "invoice_id",
            "order_id",
            "customer_id",
            "issue_date",
            "due_date",
            "status",
            "invoice_amount",
            "paid_date",
        ),
        mandatory=True,
    )
    BANK_TRANSACTIONS = SheetDefinition(
        "BANK_TRANSACTION",
        "08_BANK_TXN",
        "txn_id",
        (
            "txn_id",
            "txn_date",
            "bank",
            "account_id",
            "direction",
            "description",
            "amount",
            "counterparty_id",
            "txn_status",
            "transaction_risk_score",
        ),
    )
    CASHFLOW = SheetDefinition(
        "CASHFLOW",
        "09_CASHFLOW",
        "month",
        (
            "month",
            "expected_cash_in",
            "expected_cash_out",
            "direct_cost",
            "opex",
            "cash_reserve_minimum",
            "projected_closing_cash",
            "management_note",
        ),
    )
    CREDIT_PROFILES = SheetDefinition(
        "CREDIT_PROFILE",
        "10_CREDIT_PROFILE",
        "credit_case_id",
        (
            "credit_case_id",
            "company_id",
            "request_type",
            "requested_amount",
            "tenor",
            "collateral_or_basis",
            "eligibility_score",
            "precheck_note",
            "approval_status",
        ),
    )
    BANK_PRODUCTS = SheetDefinition(
        "BANK_PRODUCT",
        "11_BANK_PRODUCTS",
        "bank_product_id",
        (
            "bank_product_id",
            "bank",
            "product_name",
            "target_segment",
            "description",
            "annual_rate_or_fee",
            "processing_fee_rate",
            "collateral_ratio",
            "minimum_amount",
            "automation_level",
            "fit_note",
        ),
    )
    API_CATALOG = SheetDefinition(
        "API_CATALOG",
        "12_API_CATALOG",
        "api_id",
        (
            "api_id",
            "provider",
            "method",
            "endpoint",
            "description",
            "required_fields",
            "payload_example",
            "recommended_core_role",
            "catalog_status",
            "extension_rule",
        ),
    )
    RISK_RULES = SheetDefinition(
        "RISK_RULE",
        "13_RISK_RULES",
        "rule_id",
        (
            "rule_id",
            "risk_type",
            "trigger_condition",
            "severity",
            "required_action",
            "owner_agent",
        ),
    )
    ALERTS = SheetDefinition(
        "ALERT",
        "14_ALERTS",
        "alert_id",
        (
            "alert_id",
            "alert_date",
            "alert_type",
            "related_record",
            "severity",
            "risk_score",
            "description",
            "recommended_action",
        ),
    )
    DATA_CLASS = SheetDefinition(
        "DATA_CLASS",
        "20_DATA_CLASS",
        "data_pattern",
        (
            "data_pattern",
            "example_field",
            "classification",
            "external_api_rule",
            "masking_or_tokenization",
            "logging_rule",
        ),
    )
    MASKING_EXAMPLES = SheetDefinition(
        "MASKING_EXAMPLE",
        "21_MASKING_EXAMPLES",
        "source_field",
        (
            "source_field",
            "raw_example",
            "masked_example",
            "tokenized_example",
            "allowed_for_partner_api",
            "reason",
        ),
    )
    API_HANDLING_RULES = SheetDefinition(
        "API_HANDLING_RULE",
        "22_API_HANDLING_RULES",
        "rule_id",
        (
            "rule_id",
            "applies_to",
            "possible_issue",
            "team_visible_meaning",
            "required_handling",
            "requires_human_approval",
            "sensitive_fields",
            "note",
        ),
    )

    DEFINITIONS = (
        OPC_PROFILE,
        CUSTOMERS,
        CONTRACTS,
        PRODUCTS,
        ORDERS,
        INVOICES,
        BANK_TRANSACTIONS,
        CASHFLOW,
        CREDIT_PROFILES,
        BANK_PRODUCTS,
        API_CATALOG,
        RISK_RULES,
        ALERTS,
        DATA_CLASS,
        MASKING_EXAMPLES,
        API_HANDLING_RULES,
    )
    BY_SHEET: ClassVar[dict[str, SheetDefinition]] = {
        definition.sheet_name: definition for definition in DEFINITIONS
    }
    BY_ENTITY: ClassVar[dict[str, SheetDefinition]] = {
        definition.canonical_entity: definition for definition in DEFINITIONS
    }

    @classmethod
    def resolve_target(cls, target: str) -> SheetDefinition | None:
        """Resolve an exact sheet name or canonical entity name."""
        return cls.BY_SHEET.get(target) or cls.BY_ENTITY.get(target.upper())
