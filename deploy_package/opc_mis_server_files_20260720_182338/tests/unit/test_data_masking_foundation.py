"""Security and correctness tests for classification and masking foundations."""

import json
import logging
from pathlib import Path

import pytest

from opc_mis.domain.data_classification_models import (
    DataClassification,
    DataClassificationRule,
)
from opc_mis.domain.masking_models import (
    MaskingAction,
    MaskingAlgorithmId,
    MaskingPolicyDocument,
    MaskingRule,
    TokenizationContext,
    masking_policy_document_sha256,
)
from opc_mis.domain.team_pack import SheetRegistry
from opc_mis.governance.data_classification_policy import (
    DataClassificationPolicy,
    UnclassifiedFieldError,
)
from opc_mis.governance.masking_policy import (
    DataMinimizationError,
    MaskingPolicy,
    UnsafeMaskingInputError,
)
from opc_mis.infrastructure.excel.workbook_loader import WorkbookLoader
from opc_mis.infrastructure.security.free_text_redactor import (
    DeterministicFreeTextRedactor,
)
from opc_mis.infrastructure.security.hmac_tokenizer import (
    HmacContextualTokenizer,
    TokenizationError,
)
from opc_mis.ports.masking_service import MaskingService
from opc_mis.ports.text_redaction_service import TextRedactionService
from opc_mis.ports.tokenization_service import TokenizationService

POLICY_PATH = Path("config/data_protection/masking_policy.json")
TOKENIZATION_SECRET = b"unit-test-only-tokenization-key-material-32bytes"
RAW_COMPANY_ID = "OPC-001"
RAW_SECRET = "do-not-persist-this-access-token"
PURPOSE = "PERFORMANCE_BOND_DOCUMENT_RELEASE"


def _sources(payload: dict[str, object]) -> dict[str, tuple[str, ...]]:
    return {field: (f"EVD-EXACT-{field.upper()}",) for field in payload}


def _document() -> MaskingPolicyDocument:
    return MaskingPolicyDocument.model_validate(
        json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    )


def _policy(document: MaskingPolicyDocument | None = None) -> MaskingPolicy:
    tokenizer: TokenizationService = HmacContextualTokenizer(
        secret_key=TOKENIZATION_SECRET,
        token_bytes=16,
    )
    redactor: TextRedactionService = DeterministicFreeTextRedactor()
    return MaskingPolicy(
        document=document or _document(),
        tokenizer=tokenizer,
        redactor=redactor,
    )


def test_masking_examples_sheet_is_ingested_by_exact_name_and_headers(
    team_pack_path: Path,
) -> None:
    dataset = WorkbookLoader().load("DATASET", team_pack_path)
    definition = SheetRegistry.MASKING_EXAMPLES

    assert definition.sheet_name == "21_MASKING_EXAMPLES"
    assert dataset.headers[definition.sheet_name] == definition.required_headers
    assert dataset.sheets[definition.sheet_name]
    assert definition.sheet_name not in dataset.duplicate_ids
    assert not [
        issue
        for issue in dataset.validation_issues
        if issue.sheet == definition.sheet_name
    ]


def test_policy_document_has_exact_complete_rules_and_no_secret_material() -> None:
    source = POLICY_PATH.read_text(encoding="utf-8")
    document = _document()

    assert document.fail_closed is True
    assert document.allowed_recipients == ("VietinBank", "SecureConnector")
    assert "*" not in document.allowed_recipients
    assert len(document.classification_rules) == len(document.masking_rules)
    assert all(rule.token_bytes >= 16 for rule in document.masking_rules)
    assert "secret_key" not in source
    assert RAW_SECRET not in source


def test_classification_is_exact_stable_and_fails_closed() -> None:
    document = _document()
    policy = DataClassificationPolicy(
        policy_id=document.policy_id,
        policy_version=document.policy_version,
        rules=document.classification_rules,
    )

    first = policy.classify("customer_id")
    second = policy.classify("customer_id")

    assert first == second
    assert first.classification is DataClassification.RESTRICTED
    assert first.decision_id.startswith("CLASS-")
    with pytest.raises(UnclassifiedFieldError, match="Customer_ID"):
        policy.classify("Customer_ID")


def test_contextual_hmac_tokens_are_deterministic_and_namespace_separated() -> None:
    tokenizer = HmacContextualTokenizer(
        secret_key=TOKENIZATION_SECRET,
        token_bytes=16,
    )
    base = TokenizationContext(
        provider="VietinBank",
        purpose=PURPOSE,
        field_type="customer_id",
        key_version="v1",
    )

    token = tokenizer.tokenize("CUS-005", base)

    assert token == tokenizer.tokenize("CUS-005", base)
    assert token != tokenizer.tokenize(
        "CUS-005", base.model_copy(update={"provider": "OtherBank"})
    )
    assert token != tokenizer.tokenize(
        "CUS-005", base.model_copy(update={"purpose": "ANOTHER_PURPOSE"})
    )
    assert token != tokenizer.tokenize(
        "CUS-005", base.model_copy(update={"field_type": "company_id"})
    )
    assert token != tokenizer.tokenize(
        "CUS-005", base.model_copy(update={"key_version": "v2"})
    )
    assert len(token.rsplit("-", 1)[-1]) == 26


def test_tokenizer_unicode_canonicalization_and_secret_safe_repr(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    tokenizer = HmacContextualTokenizer(
        secret_key=TOKENIZATION_SECRET,
        token_bytes=16,
    )
    context = TokenizationContext(
        provider="VietinBank",
        purpose=PURPOSE,
        field_type="company_name",
        key_version="v1",
    )

    composed = tokenizer.tokenize("Caf\u00e9", context)
    decomposed = tokenizer.tokenize("Cafe\u0301", context)

    assert composed == decomposed
    assert TOKENIZATION_SECRET.decode() not in repr(tokenizer)
    assert TOKENIZATION_SECRET.decode() not in caplog.text
    with pytest.raises(TokenizationError, match="at least 32 bytes"):
        HmacContextualTokenizer(secret_key=b"short")
    with pytest.raises(TokenizationError, match="between 16 and 32"):
        HmacContextualTokenizer(secret_key=TOKENIZATION_SECRET, token_bytes=15)


def test_mask_payload_minimizes_tokenizes_generalizes_and_redacts() -> None:
    policy: MaskingService = _policy()
    raw_note = (
        f"Use contract CON-004 for {RAW_COMPANY_ID}; "
        f"access_token={RAW_SECRET} and contact ops@example.com"
    )
    payload = {
        "contract_id": "CON-004",
        "company_id": RAW_COMPANY_ID,
        "requested_amount": 420_000_000,
        "contract_value": 4_200_000_000,
        "governance_rule": "internal-only approval text",
        "access_token": RAW_SECRET,
        "contract_note": raw_note,
    }

    result = policy.mask_payload(
        payload,
        recipient="VietinBank",
        purpose=PURPOSE,
        required_fields=set(payload),
        source_evidence_ids_by_field=_sources(payload),
    )
    serialized = result.model_dump_json()

    assert result.values["contract_id"].startswith("TOK-CONTRACT-ID-V1-")
    assert result.values["company_id"].startswith("TOK-COMPANY-ID-V1-")
    assert result.values["requested_amount"] == 420_000_000
    assert result.values["contract_value"] == "4B-5B VND"
    assert "governance_rule" not in result.values
    assert "access_token" not in result.values
    assert result.values["contract_note"] == (
        "Use contract [CONTRACT_ID_REDACTED] for [COMPANY_ID_REDACTED]; "
        "[SECRET_REDACTED] and contact [EMAIL_REDACTED]"
    )
    assert RAW_COMPANY_ID not in serialized
    assert RAW_SECRET not in serialized
    assert raw_note not in serialized
    assert result.manifest.manifest_id.startswith("MASK-")
    assert result.manifest.policy_document_sha256 == masking_policy_document_sha256(
        _document()
    )
    assert all(item.source_evidence_ids for item in result.manifest.items)
    assert all(not item.policy_evidence_ids for item in result.manifest.items)
    assert all(
        item.policy_reference.startswith("SERVER_POLICY:")
        for item in result.manifest.items
    )
    assert all(item.raw_value_persisted is False for item in result.manifest.items)
    assert tuple(
        decision.decision_id for decision in result.classification_decisions
    ) == tuple(
        item.classification_decision_id for item in result.manifest.items
    )


def test_team_pack_policy_claim_requires_exact_policy_evidence() -> None:
    with pytest.raises(ValueError, match="exact source_evidence_ids"):
        DataClassificationRule(
            rule_id="CLASS-UNSUBSTANTIATED",
            field_name="field_name",
            classification=DataClassification.INTERNAL,
            policy_reference="TEAM_PACK:20_DATA_CLASS/Internal operating data",
        )


def test_required_fields_are_explicit_and_context_mismatch_omits() -> None:
    policy = _policy()
    payload = {
        "requested_amount": 420_000_000,
        "contract_value": 4_200_000_000,
    }

    with pytest.raises(DataMinimizationError, match="required_fields"):
        policy.mask_payload(
            payload,
            recipient="VietinBank",
            purpose=PURPOSE,
            required_fields=(),
            source_evidence_ids_by_field=_sources(payload),
        )

    with pytest.raises(DataMinimizationError, match="requested_amount"):
        incomplete = {"contract_value": 4_200_000_000}
        policy.mask_payload(
            incomplete,
            recipient="VietinBank",
            purpose=PURPOSE,
            required_fields={"contract_value", "requested_amount"},
            source_evidence_ids_by_field=_sources(incomplete),
        )

    with pytest.raises(DataMinimizationError, match="not authorized"):
        policy.mask_payload(
            payload,
            recipient="OtherBank",
            purpose=PURPOSE,
            required_fields=set(payload),
            source_evidence_ids_by_field=_sources(payload),
        )

    minimized = policy.mask_payload(
        payload,
        recipient="VietinBank",
        purpose=PURPOSE,
        required_fields={"requested_amount"},
        source_evidence_ids_by_field=_sources(payload),
    )
    wrong_context = policy.mask_payload(
        payload,
        recipient="VietinBank",
        purpose="UNDECLARED_PURPOSE",
        required_fields=set(payload),
        source_evidence_ids_by_field=_sources(payload),
    )

    assert minimized.values == {"requested_amount": 420_000_000}
    assert wrong_context.values == {}
    assert all(
        item.action is MaskingAction.OMIT for item in wrong_context.manifest.items
    )


def test_unknown_non_scalar_and_vault_raw_values_fail_without_echoing_values() -> None:
    policy = _policy()

    with pytest.raises(UnclassifiedFieldError) as unknown:
        unknown_payload = {"unknown_field": RAW_SECRET}
        policy.mask_payload(
            unknown_payload,
            recipient="VietinBank",
            purpose=PURPOSE,
            required_fields={"unknown_field"},
            source_evidence_ids_by_field=_sources(unknown_payload),
        )
    assert RAW_SECRET not in str(unknown.value)

    with pytest.raises(UnsafeMaskingInputError) as nested:
        nested_payload = {"company_id": {"raw": RAW_SECRET}}
        policy.mask_payload(
            nested_payload,  # type: ignore[arg-type]
            recipient="VietinBank",
            purpose=PURPOSE,
            required_fields={"company_id"},
            source_evidence_ids_by_field=_sources(nested_payload),
        )
    assert RAW_SECRET not in str(nested.value)

    with pytest.raises(UnsafeMaskingInputError) as raw_vault:
        raw_vault_payload = {"connector_credential_reference": RAW_SECRET}
        policy.mask_payload(
            raw_vault_payload,
            recipient="SecureConnector",
            purpose="SECURE_CONNECTOR_EXECUTION",
            required_fields={"connector_credential_reference"},
            source_evidence_ids_by_field=_sources(raw_vault_payload),
        )
    assert RAW_SECRET not in str(raw_vault.value)

    vault_payload = {"connector_credential_reference": "vault://banking/api-002"}
    vault = policy.mask_payload(
        vault_payload,
        recipient="SecureConnector",
        purpose="SECURE_CONNECTOR_EXECUTION",
        required_fields={"connector_credential_reference"},
        source_evidence_ids_by_field=_sources(vault_payload),
    )
    assert vault.values == {
        "connector_credential_reference": "vault://banking/api-002"
    }


def test_partial_mask_action_is_display_only_and_supported() -> None:
    base = _document()
    classification = DataClassificationRule(
        rule_id="CLASS-DISPLAY-ID",
        field_name="display_id",
        classification=DataClassification.INTERNAL,
        policy_reference="TEST_POLICY",
    )
    masking = MaskingRule(
        rule_id="MASK-DISPLAY-ID",
        field_name="display_id",
        action=MaskingAction.PARTIAL_MASK,
        algorithm_id=MaskingAlgorithmId.PARTIAL_MASK_DISPLAY,
        algorithm_version="v1",
        allowed_purposes=(PURPOSE,),
        allowed_recipients=("VietinBank",),
        visible_prefix_characters=2,
        visible_suffix_characters=2,
    )
    document = MaskingPolicyDocument(
        policy_id="TEST_PARTIAL_MASK",
        policy_version="1",
        allowed_recipients=base.allowed_recipients,
        classification_rules=(classification,),
        masking_rules=(masking,),
        vnd_generalization=base.vnd_generalization,
    )

    partial_payload = {"display_id": "AB123456"}
    result = _policy(document).mask_payload(
        partial_payload,
        recipient="VietinBank",
        purpose=PURPOSE,
        required_fields={"display_id"},
        source_evidence_ids_by_field=_sources(partial_payload),
    )

    assert result.values == {"display_id": "AB***56"}


def test_free_text_redactor_returns_counts_not_matched_values() -> None:
    text = f"Customer CUS-005 email test@example.com access_token={RAW_SECRET}"
    result = DeterministicFreeTextRedactor().redact(
        text,
        exact_identifiers={"customer_id": "CUS-005"},
    )
    serialized = result.model_dump_json()

    assert result.text == (
        "Customer [CUSTOMER_ID_REDACTED] email [EMAIL_REDACTED] [SECRET_REDACTED]"
    )
    assert {item.category for item in result.findings} == {
        "EMAIL",
        "EXACT_CUSTOMER_ID",
        "SECRET",
    }
    assert "CUS-005" not in serialized
    assert RAW_SECRET not in serialized
