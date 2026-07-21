"""Tests for canonical server-owned masking-policy loading."""

import json
from pathlib import Path

import pytest

from opc_mis.infrastructure.config.masking_policy_loader import (
    MaskingPolicyConfigurationError,
    MaskingPolicyLoader,
    canonical_masking_policy_hash,
)


def test_loader_returns_canonical_non_secret_identity() -> None:
    loaded = MaskingPolicyLoader().load(
        Path("config/data_protection/masking_policy.json")
    )

    assert loaded.document.fail_closed is True
    assert loaded.configuration_hash == canonical_masking_policy_hash(
        loaded.document
    )
    assert len(loaded.configuration_hash) == 64


def test_loader_rejects_unknown_policy_fields_without_echoing_values(
    tmp_path: Path,
) -> None:
    source = json.loads(
        Path("config/data_protection/masking_policy.json").read_text(
            encoding="utf-8"
        )
    )
    source["secret_key"] = "must-not-be-echoed"
    path = tmp_path / "invalid-masking-policy.json"
    path.write_text(json.dumps(source), encoding="utf-8")

    with pytest.raises(MaskingPolicyConfigurationError) as captured:
        MaskingPolicyLoader().load(path)

    assert "must-not-be-echoed" not in str(captured.value)
