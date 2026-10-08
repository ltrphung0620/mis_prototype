"""Assess transaction linkage from headers only; never parse descriptions as keys."""

from opc_mis.domain.dataset import DatasetSnapshot
from opc_mis.domain.team_pack import SheetRegistry


def has_explicit_case_transaction_link(dataset: DatasetSnapshot) -> bool:
    """Return true only if a supported structured relationship column exists."""
    headers = set(dataset.headers.get(SheetRegistry.BANK_TRANSACTIONS.sheet_name, ()))
    return bool(headers.intersection({"contract_id", "order_id", "invoice_id"}))
