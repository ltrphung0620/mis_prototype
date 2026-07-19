"""FastAPI application factory and lifespan composition."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from opc_mis.api.routes import router
from opc_mis.config import AppSettings
from opc_mis.runtime import PlannerRuntime


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
            "endpoint; a ready DOCUMENT_RELEASE_PACKAGE is stored as input for a future "
            "Internal Decision Package. Package readiness does not trigger Founder approval "
            "or SEND_DOCUMENT_TO_EXTERNAL_PARTNER. That checkpoint remains dormant until a "
            "future evidence-bound Decision proposal exists; the recommendation/proposal and "
            "external send are not implemented in this phase. "
            "The system does not call the TeamPack endpoint or claim a bank approval. Governance "
            "registers checkpoints and gates protected actions; Risk "
            "does not approve, bank, prepare documents, or make decisions."
        ),
        version="0.15.0",
        lifespan=lifespan,
    )
    app.include_router(router)

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

    return app
