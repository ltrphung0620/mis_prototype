"""Secret-safe environment parsing for document masking configuration."""

import base64

import pytest

from opc_mis.config import AppSettings


def test_masking_hmac_key_is_optional_and_hidden_from_repr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = b"document-masking-test-key-material-32-bytes"
    monkeypatch.setenv(
        "OPC_MIS_MASKING_HMAC_KEY_BASE64",
        base64.b64encode(secret).decode("ascii"),
    )
    openai_secret = "test-only-openai-secret-must-not-appear"
    monkeypatch.setenv("OPENAI_API_KEY", openai_secret)

    settings = AppSettings.from_environment()

    assert settings.masking_hmac_key == secret
    assert secret.decode("ascii") not in repr(settings)
    assert settings.openai_api_key == openai_secret
    assert openai_secret not in repr(settings)


@pytest.mark.parametrize("encoded", ("not base64", base64.b64encode(b"short").decode()))
def test_invalid_masking_key_fails_without_echoing_value(
    monkeypatch: pytest.MonkeyPatch,
    encoded: str,
) -> None:
    monkeypatch.setenv("OPC_MIS_MASKING_HMAC_KEY_BASE64", encoded)

    with pytest.raises(ValueError) as captured:
        AppSettings.from_environment()

    assert encoded not in str(captured.value)
