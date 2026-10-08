"""Read-only TeamPack loader using actual sheet names and headers."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path
from zipfile import BadZipFile

import pandas as pd
from openpyxl.utils.exceptions import InvalidFileException

from opc_mis.domain.dataset import (
    DatasetRecord as WorkbookRecord,
)
from opc_mis.domain.dataset import (
    DatasetSnapshot as WorkbookDataset,
)
from opc_mis.domain.team_pack import SheetRegistry
from opc_mis.infrastructure.excel.normalizers import display_value, normalize_value
from opc_mis.infrastructure.excel.validators import (
    ValidationIssue,
    validate_foreign_key_values,
    validate_record_types,
)


class WorkbookError(RuntimeError):
    """Base class for typed TeamPack workbook failures."""


class WorkbookReadError(WorkbookError):
    """Raised when the workbook path cannot be read."""


class WorkbookIntegrityError(WorkbookError):
    """Raised when the source workbook changes during execution."""


def compute_sha256(path: Path) -> str:
    """Compute the SHA-256 hash of a file without modifying it."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class WorkbookLoader:
    """Load the Planner projection of the TeamPack without saving the workbook."""

    def __init__(self, registry: type[SheetRegistry] = SheetRegistry) -> None:
        self._registry = registry

    def load(self, dataset_id: str, workbook_path: Path) -> WorkbookDataset:
        """Read actual sheets, normalize values, build indexes, and verify immutability."""
        path = workbook_path.resolve()
        if not path.is_file():
            raise WorkbookReadError(f"Workbook does not exist: {path}")

        try:
            before_hash = compute_sha256(path)
            excel_file = pd.ExcelFile(path, engine="openpyxl")
        except (OSError, ValueError, ImportError, BadZipFile, InvalidFileException) as exc:
            raise WorkbookReadError(f"Unable to open workbook {path}: {exc}") from exc

        available = set(excel_file.sheet_names)
        sheets: dict[str, list[WorkbookRecord]] = {}
        headers: dict[str, tuple[str, ...]] = {}
        indexes: dict[str, dict[str, list[WorkbookRecord]]] = {}
        duplicate_ids: dict[str, tuple[str, ...]] = {}
        validation_issues: list[ValidationIssue] = []
        missing_sheets = tuple(
            definition.sheet_name
            for definition in self._registry.DEFINITIONS
            if definition.mandatory and definition.sheet_name not in available
        )
        missing_headers: dict[str, tuple[str, ...]] = {}

        for definition in self._registry.DEFINITIONS:
            if definition.sheet_name not in available:
                continue
            try:
                frame = pd.read_excel(excel_file, sheet_name=definition.sheet_name, dtype=object)
            except (
                OSError,
                ValueError,
                TypeError,
                ImportError,
                BadZipFile,
                InvalidFileException,
            ) as exc:
                excel_file.close()
                raise WorkbookReadError(
                    f"Unable to read sheet {definition.sheet_name}: {exc}"
                ) from exc
            actual_headers = tuple(str(column).strip() for column in frame.columns)
            headers[definition.sheet_name] = actual_headers
            absent = tuple(
                header for header in definition.required_headers if header not in actual_headers
            )
            if absent:
                missing_headers[definition.sheet_name] = absent

            records: list[WorkbookRecord] = []
            index: defaultdict[str, list[WorkbookRecord]] = defaultdict(list)
            for frame_index, row in frame.iterrows():
                original = {header: row.get(header) for header in actual_headers}
                normalized = {
                    header: normalize_value(header, value) for header, value in original.items()
                }
                if all(value is None for value in normalized.values()):
                    continue
                primary_key = definition.primary_key
                raw_id = normalized.get(primary_key) if primary_key else None
                record_id = str(raw_id) if raw_id is not None else f"ROW-{int(frame_index) + 2}"
                if primary_key and raw_id is None:
                    validation_issues.append(
                        ValidationIssue(
                            code="MISSING_PRIMARY_KEY",
                            sheet=definition.sheet_name,
                            record_id=record_id,
                            field=primary_key,
                            reason="Primary-key value is missing.",
                        )
                    )
                record = WorkbookRecord(
                    sheet=definition.sheet_name,
                    row_number=int(frame_index) + 2,
                    record_id=record_id,
                    values=normalized,
                    display_values={
                        header: display_value(value) for header, value in original.items()
                    },
                )
                records.append(record)
                if primary_key and raw_id is not None:
                    index[record_id].append(record)
                validation_issues.extend(
                    validate_record_types(definition.sheet_name, record_id, normalized)
                )
            sheets[definition.sheet_name] = records
            indexes[definition.sheet_name] = dict(index)
            duplicates = tuple(sorted(key for key, matches in index.items() if len(matches) > 1))
            if duplicates:
                duplicate_ids[definition.sheet_name] = duplicates

        excel_file.close()
        after_hash = compute_sha256(path)
        if after_hash != before_hash:
            raise WorkbookIntegrityError(f"Workbook changed while being read: {path}")

        validation_issues.extend(self.foreign_key_issues(sheets))

        return WorkbookDataset(
            dataset_id=dataset_id,
            source_locator=str(path),
            source_hash=before_hash,
            snapshot_hash=before_hash,
            sheets=sheets,
            headers=headers,
            indexes=indexes,
            duplicate_ids=duplicate_ids,
            validation_issues=validation_issues,
            missing_sheets=missing_sheets,
            missing_headers=missing_headers,
        )

    @staticmethod
    def foreign_key_issues(
        sheets: dict[str, list[WorkbookRecord]],
    ) -> list[ValidationIssue]:
        """Validate every explicit Planner relationship in an in-memory dataset."""
        relationships = (
            (SheetRegistry.CONTRACTS, "customer_id", SheetRegistry.CUSTOMERS),
            (SheetRegistry.ORDERS, "contract_id", SheetRegistry.CONTRACTS),
            (SheetRegistry.ORDERS, "customer_id", SheetRegistry.CUSTOMERS),
            (SheetRegistry.ORDERS, "service_id", SheetRegistry.PRODUCTS),
            (SheetRegistry.INVOICES, "order_id", SheetRegistry.ORDERS),
            (SheetRegistry.INVOICES, "customer_id", SheetRegistry.CUSTOMERS),
        )
        issues: list[ValidationIssue] = []
        for child, child_field, parent in relationships:
            child_records = sheets.get(child.sheet_name, [])
            parent_records = sheets.get(parent.sheet_name, [])
            if not child_records or not parent_records:
                continue
            parent_values = {record.record_id for record in parent_records}
            issues.extend(
                validate_foreign_key_values(
                    child_sheet=child.sheet_name,
                    child_rows=[(record.record_id, record.values) for record in child_records],
                    child_field=child_field,
                    parent_sheet=parent.sheet_name,
                    parent_values=parent_values,
                )
            )
        return issues

    @staticmethod
    def verify_unchanged(dataset: WorkbookDataset) -> None:
        """Raise when the source hash differs from the hash captured on load."""
        source_path = Path(dataset.source_locator)
        current_hash = compute_sha256(source_path)
        if current_hash != dataset.workbook_hash:
            raise WorkbookIntegrityError(
                f"Workbook hash changed after dataset ingestion: {source_path}"
            )
