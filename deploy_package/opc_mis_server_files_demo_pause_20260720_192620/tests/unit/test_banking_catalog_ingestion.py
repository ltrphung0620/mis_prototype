"""Banking catalog ingestion and server-owned mapping policy tests."""

import json
from pathlib import Path

import pytest

from opc_mis.domain.enums import BankingNeedType
from opc_mis.domain.team_pack import SheetRegistry
from opc_mis.infrastructure.config.banking_catalog_policy import (
    BankingCatalogPolicyError,
    BankingCatalogPolicyLoader,
)
from opc_mis.infrastructure.excel.workbook_loader import WorkbookLoader

POLICY_PATH = Path("config/banking/catalog_mappings.json")


def test_loader_ingests_banking_catalog_sheets_by_exact_names(
    team_pack_path: Path,
) -> None:
    dataset = WorkbookLoader().load("DATASET", team_pack_path)

    expected = (
        SheetRegistry.BANK_PRODUCTS,
        SheetRegistry.API_CATALOG,
        SheetRegistry.API_HANDLING_RULES,
    )
    for definition in expected:
        assert definition.sheet_name in dataset.sheets
        assert dataset.headers[definition.sheet_name] == definition.required_headers
        assert dataset.sheets[definition.sheet_name]
        assert definition.sheet_name not in dataset.duplicate_ids

    banking_sheets = {definition.sheet_name for definition in expected}
    assert not [
        issue for issue in dataset.validation_issues if issue.sheet in banking_sheets
    ]


def test_new_catalog_sheets_are_optional() -> None:
    assert SheetRegistry.BANK_PRODUCTS.mandatory is False
    assert SheetRegistry.API_CATALOG.mandatory is False
    assert SheetRegistry.API_HANDLING_RULES.mandatory is False


def test_policy_loader_returns_typed_policy_with_canonical_hash() -> None:
    policy = BankingCatalogPolicyLoader().load(POLICY_PATH)

    assert policy.policy_id == "OPC_BANKING_CATALOG_MAPPING"
    assert policy.bindings[0].need_type is BankingNeedType.PERFORMANCE_BOND
    assert policy.bindings[0].precheck_api_by_product
    assert len(policy.policy_hash) == 64
    assert int(policy.policy_hash, 16) >= 0


def test_server_policy_references_explicit_catalog_ids(team_pack_path: Path) -> None:
    dataset = WorkbookLoader().load("DATASET", team_pack_path)
    policy = BankingCatalogPolicyLoader().load(POLICY_PATH)
    product_ids = set(dataset.indexes[SheetRegistry.BANK_PRODUCTS.sheet_name])
    api_ids = set(dataset.indexes[SheetRegistry.API_CATALOG.sheet_name])
    handling_rule_ids = set(
        dataset.indexes[SheetRegistry.API_HANDLING_RULES.sheet_name]
    )

    for binding in policy.bindings:
        assert set(binding.bank_product_ids).issubset(product_ids)
        assert set(binding.precheck_api_by_product.values()).issubset(api_ids)
        assert set(binding.handling_rule_ids).issubset(handling_rule_ids)


def test_policy_hash_is_independent_of_json_formatting(tmp_path: Path) -> None:
    source = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    reformatted = tmp_path / "reformatted.json"
    reformatted.write_text(
        json.dumps(source, ensure_ascii=False, indent=7, sort_keys=True),
        encoding="utf-8",
    )

    loader = BankingCatalogPolicyLoader()

    assert loader.load(reformatted).policy_hash == loader.load(POLICY_PATH).policy_hash


def test_policy_loader_rejects_implicit_product_mapping(tmp_path: Path) -> None:
    source = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    source["bindings"][0]["precheck_api_by_product"] = {
        "UNDECLARED-PRODUCT": "API-002"
    }
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(source), encoding="utf-8")

    with pytest.raises(BankingCatalogPolicyError, match="unknown bank_product_id"):
        BankingCatalogPolicyLoader().load(invalid)


def test_policy_loader_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(BankingCatalogPolicyError, match="does not exist"):
        BankingCatalogPolicyLoader().load(tmp_path / "missing.json")
