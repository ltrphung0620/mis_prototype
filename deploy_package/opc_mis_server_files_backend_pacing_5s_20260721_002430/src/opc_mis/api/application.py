"""FastAPI application factory and lifespan composition."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from opc_mis.api.routes import router
from opc_mis.config import AppSettings
from opc_mis.runtime import PlannerRuntime

DASHBOARD_DIR = Path(__file__).resolve().parent / "static" / "react"


def create_app(
    *,
    workbook_path: Path | None = None,
    dataset_id: str | None = None,
    database_path: Path | str | None = None,
) -> FastAPI:
    """Create a testable API app using explicit or environment-backed settings."""
    settings = AppSettings.from_environment()
    runtime = PlannerRuntime(
        workbook_path=workbook_path or settings.team_pack_path,
        dataset_id=dataset_id or settings.dataset_id,
        settings=settings,
        database_path=(
            database_path
            if database_path is not None
            else ":memory:"
            if workbook_path is not None or dataset_id is not None
            else settings.database_path
        ),
        workflow_step_delay_seconds=(
            0.0
            if workbook_path is not None or dataset_id is not None
            else settings.workflow_step_delay_seconds
        ),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await runtime.startup(start_runner=True)
        app.state.planner_runtime = runtime
        yield
        await runtime.shutdown()

    app = FastAPI(
        title="OPC MIS Agentic AI",
        description=(
            "Read-only TeamPack API for Planner Intake plus deterministic Finance, Operations, "
            "and pause/resume initial Risk assessment. A durable Master Workflow runs the full "
            "Initial Assessment, deterministic Decision Initial Route, and applicable internal "
            "Banking catalog discovery, precheck-readiness review, and typed amount-input "
            "pause/resume automatically. For a ready Banking route, the workflow creates a "
            "reference-only submission proposal and pauses at WAITING_FOR_APPROVAL for the "
            "protected SUBMIT_BANKING_PRECHECK action. After approval, the workflow invokes a "
            "server-configured simulator and persists a clearly non-binding precheck result set; "
            "Decision then preserves and classifies every option/product result without "
            "selection. A single conditional result routes to a masked internal Document "
            "dossier. Missing provider documents pause through a metadata-only reference "
            "endpoint. A ready DOCUMENT_RELEASE_PACKAGE flows into a neutral Internal Decision "
            "Package and then a deterministic Final Risk Check. A bounded Decision composer "
            "creates an evidence-validated Decision Card for Founder review. Governance pauses "
            "the workflow for the exact protected action, and Post-decision Update records the "
            "Founder outcome. An accepted route may create a separate external-document "
            "submission proposal and approval gate, but the prototype stops at "
            "READY_FOR_EXTERNAL_SUBMISSION and has no external send connector. "
            "The system does not call the TeamPack endpoint or claim a bank approval. Governance "
            "registers checkpoints and gates protected actions; Risk "
            "does not approve, bank, prepare documents, or make decisions."
        ),
        version="0.16.0",
        lifespan=lifespan,
    )
    app.include_router(router)
    app.mount(
        "/dashboard-assets",
        StaticFiles(directory=DASHBOARD_DIR),
        name="dashboard-assets",
    )

    @app.exception_handler(RequestValidationError)
    async def request_validation_error(
        _request: Request,
        _error: RequestValidationError,
    ) -> JSONResponse:
        """Reject invalid public input without reflecting its raw value."""
        return JSONResponse(
            status_code=422,
            content={"detail": "Request validation failed."},
        )

    @app.get("/health", tags=["System"], summary="Check API health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "dataset_id": runtime.dataset_id}

    @app.get(
        "/api/system/capabilities",
        tags=["System"],
        summary="Inspect safe dashboard runtime capabilities",
    )
    async def system_capabilities() -> dict[str, object]:
        """Expose feature flags and model identity without returning secret material."""

        openai_active = bool(settings.openai_enabled and settings.openai_api_key)
        return {
            "dataset_id": runtime.dataset_id,
            "snapshot_hash": runtime.snapshot_hash,
            "dataset_source": "SERVER_CONFIGURED_TEAM_PACK",
            "openai_enabled": openai_active,
            "openai_model": settings.openai_model if openai_active else None,
            "openai_components": (
                ["FINANCE_NARRATIVE", "BANKING_OPTION_ADVISOR", "DECISION_ANALYSIS"]
                if openai_active
                else []
            ),
            "workflow_transport": "POLLING",
            "recommended_poll_interval_ms": 1500,
            "document_input_mode": "OPAQUE_REFERENCE_METADATA",
        }

    @app.get("/dashboard", include_in_schema=False)
    async def dashboard() -> FileResponse:
        """Serve the Founder dashboard shell; all business data comes from APIs."""

        return FileResponse(DASHBOARD_DIR / "index.html")

    @app.get("/", include_in_schema=False)
    async def dashboard_redirect() -> RedirectResponse:
        return RedirectResponse(url="/dashboard")

    return app
