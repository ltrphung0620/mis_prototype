"""Apply valid data patches to an isolated in-memory dataset copy."""

from __future__ import annotations

import json
from copy import deepcopy

from opc_mis.domain.dataset import DatasetSnapshot
from opc_mis.domain.evidence import DataPatch
from opc_mis.domain.lineage import LineageFactory
from opc_mis.domain.team_pack import SheetRegistry
from opc_mis.infrastructure.excel.normalizers import display_value, normalize_value
from opc_mis.infrastructure.excel.validators import validate_record_types
from opc_mis.infrastructure.excel.workbook_loader import WorkbookLoader


class PatchApplicationError(ValueError):
    """Raised when a data patch cannot target one exact workbook record field."""


class OverlayStore:
    """Create an isolated in-memory overlay without saving the TeamPack."""

    def __init__(self, registry: type[SheetRegistry] = SheetRegistry) -> None:
        self._registry = registry

    def apply(
        self,
        dataset: DatasetSnapshot,
        patches: tuple[DataPatch, ...],
        lineage: LineageFactory,
    ) -> DatasetSnapshot:
        """Return a patched dataset copy; the original dataset and workbook remain unchanged."""
        if not patches:
            return dataset
        result = deepcopy(dataset)
        for patch in patches:
            target = patch.target_sheet or patch.canonical_entity_type
            if target is None:
                raise PatchApplicationError(f"Patch {patch.patch_id} has no target")
            definition = self._registry.resolve_target(target)
            if definition is None:
                raise PatchApplicationError(
                    f"Patch {patch.patch_id} targets unknown sheet/entity {target}"
                )
            if patch.field not in result.headers.get(definition.sheet_name, ()):
                raise PatchApplicationError(
                    f"Patch {patch.patch_id} targets unknown field {patch.field} "
                    f"on {definition.sheet_name}"
                )
            if patch.field == definition.primary_key:
                raise PatchApplicationError(
                    f"Patch {patch.patch_id} cannot change primary key {patch.field}"
                )
            normalized_target = normalize_value(definition.primary_key or "", patch.target_record)
            matches = result.lookup(definition, normalized_target)
            if len(matches) != 1:
                raise PatchApplicationError(
                    f"Patch {patch.patch_id} expected one target record; found {len(matches)}"
                )
            record = matches[0]
            safe_patch_value = display_value(patch.value)
            try:
                json.dumps(safe_patch_value, allow_nan=False)
            except (TypeError, ValueError) as exc:
                raise PatchApplicationError(
                    f"Patch {patch.patch_id} value is not JSON-safe: {exc}"
                ) from exc
            normalized_value = normalize_value(patch.field, safe_patch_value)
            candidate_values = {**record.values, patch.field: normalized_value}
            patch_issues = [
                issue
                for issue in validate_record_types(
                    definition.sheet_name, record.record_id, candidate_values
                )
                if issue.field == patch.field
            ]
            if patch_issues:
                raise PatchApplicationError(
                    f"Patch {patch.patch_id} is invalid: {patch_issues[0].reason}"
                )
            record.values[patch.field] = normalized_value
            record.display_values[patch.field] = safe_patch_value
            record.patched_evidence[patch.field] = lineage.patch(patch, definition.sheet_name)
        missing_key_issues = [
            issue for issue in dataset.validation_issues if issue.code == "MISSING_PRIMARY_KEY"
        ]
        result.validation_issues = missing_key_issues + [
            issue
            for records in result.sheets.values()
            for record in records
            for issue in validate_record_types(record.sheet, record.record_id, record.values)
        ]
        result.validation_issues.extend(WorkbookLoader.foreign_key_issues(result.sheets))
        return result
