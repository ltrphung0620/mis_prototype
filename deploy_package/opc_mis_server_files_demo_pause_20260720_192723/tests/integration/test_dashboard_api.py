"""Founder dashboard shell and safe capability-boundary integration tests."""

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opc_mis.api.application import create_app

TEAM_PACK = Path("data/input/MISTalent2026_OPC_AgenticAI_TeamPack_v3.xlsx").resolve()
TEST_HMAC_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="


@pytest.fixture(scope="module")
def dashboard_client() -> Iterator[TestClient]:
    app = create_app(
        workbook_path=TEAM_PACK,
        dataset_id="DASHBOARD_TEST_DATASET",
        database_path=":memory:",
    )
    with TestClient(app) as client:
        yield client


def test_root_redirects_to_founder_dashboard(dashboard_client: TestClient) -> None:
    response = dashboard_client.get("/", follow_redirects=False)

    assert response.status_code in {302, 307}
    assert response.headers["location"] == "/dashboard"


def test_dashboard_serves_react_shell_without_demo_contract(
    dashboard_client: TestClient,
) -> None:
    response = dashboard_client.get("/dashboard")

    assert response.status_code == 200
    assert '<html lang="vi">' in response.text
    assert '<div id="root"></div>' in response.text
    assert "/dashboard-assets/assets/" in response.text
    assert "CON-004" not in response.text


def _dashboard_asset_text(
    dashboard_client: TestClient,
) -> tuple[str, str]:
    shell = dashboard_client.get("/dashboard")
    urls = re.findall(r'(?:src|href)="([^"]+)"', shell.text)
    javascript_url = next(item for item in urls if item.endswith(".js"))
    stylesheet_url = next(item for item in urls if item.endswith(".css"))
    javascript = dashboard_client.get(javascript_url)
    stylesheet = dashboard_client.get(stylesheet_url)
    assert javascript.status_code == 200
    assert stylesheet.status_code == 200
    return javascript.text, stylesheet.text


def test_dashboard_bundle_connects_only_to_real_backend_workflow_apis(
    dashboard_client: TestClient,
) -> None:
    script, stylesheet = _dashboard_asset_text(dashboard_client)

    for endpoint in (
        "/api/cases/run",
        "/api/workflows/",
        "/dashboard",
        "/approval-requests/",
        "/documents/evidence-supplements",
        "/banking/precheck-evidence-supplements",
    ):
        assert endpoint in script
    assert "Chọn hợp đồng" in script
    assert "Tiến trình xử lý" in script
    assert "Decision Dashboard" in script
    assert "decision-dashboard" in stylesheet
    assert "tiền kiểm" not in script.lower()
    assert "Đây là kiểm tra mức sẵn sàng dữ liệu" not in script
    assert "Khảo sát này chưa gọi tiền kiểm" not in script
    assert "api.openai.com" not in script
    assert "/v1/responses" not in script
    assert "CON-004" not in script


def test_dashboard_bundle_does_not_render_lineage_or_model_metadata(
    dashboard_client: TestClient,
) -> None:
    script, _stylesheet = _dashboard_asset_text(dashboard_client)

    assert "JSON.stringify(artifact" not in script
    assert "verification_evidence_types" not in script
    assert "Nội dung do OpenAI tạo" in script
    assert "composer_model" not in script
    assert "source_evidence" not in script


def test_dashboard_does_not_invent_decision_card_readiness_in_browser(
    dashboard_client: TestClient,
) -> None:
    script, _stylesheet = _dashboard_asset_text(dashboard_client)

    assert "Decision Card của lượt chạy hiện tại chưa sẵn sàng" in script
    assert "internal_decision_package_ready" not in script
    assert "hasArtifact" not in script


def test_capabilities_never_expose_openai_secret(dashboard_client: TestClient) -> None:
    response = dashboard_client.get("/api/system/capabilities")

    assert response.status_code == 200
    payload = response.json()
    assert payload["dataset_id"] == "DASHBOARD_TEST_DATASET"
    assert payload["workflow_transport"] == "POLLING"
    assert payload["document_input_mode"] == "OPAQUE_REFERENCE_METADATA"
    assert "api_key" not in response.text.lower()
    assert "secret" not in response.text.lower()


def test_capabilities_report_configured_openai_without_key_material(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-used")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.6-terra")
    monkeypatch.setenv("OPC_MIS_MASKING_HMAC_KEY_BASE64", TEST_HMAC_KEY)
    app = create_app(
        workbook_path=TEAM_PACK,
        dataset_id="DASHBOARD_OPENAI_TEST",
        database_path=":memory:",
    )

    with TestClient(app) as client:
        response = client.get("/api/system/capabilities")

    payload = response.json()
    assert payload["openai_enabled"] is True
    assert payload["openai_model"] == "gpt-5.6-terra"
    assert payload["openai_components"] == [
        "FINANCE_NARRATIVE",
        "BANKING_OPTION_ADVISOR",
        "DECISION_ANALYSIS",
    ]
    assert "test-key-not-used" not in response.text
