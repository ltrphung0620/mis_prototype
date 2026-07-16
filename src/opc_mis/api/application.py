"""FastAPI application factory and lifespan composition."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from opc_mis.api.routes import router
from opc_mis.config import AppSettings
from opc_mis.runtime import PlannerRuntime


def create_app(
    *,
    workbook_path: Path | None = None,
    dataset_id: str | None = None,
) -> FastAPI:
    """Create a testable API app using explicit or environment-backed settings."""
    settings = AppSettings.from_environment()
    runtime = PlannerRuntime(
        workbook_path=workbook_path or settings.team_pack_path,
        dataset_id=dataset_id or settings.dataset_id,
        settings=settings,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await runtime.startup()
        app.state.planner_runtime = runtime
        yield

    app = FastAPI(
        title="OPC MIS Agentic AI",
        description=(
            "Read-only TeamPack API for Planner Intake plus deterministic Finance and "
            "Operations assessments. Components emit facts and neutral observations; they do not "
            "execute Risk, Approval, Banking, Document, or Decision responsibilities."
        ),
        version="0.4.0",
        lifespan=lifespan,
    )
    app.include_router(router)

    @app.get("/health", tags=["System"], summary="Check API health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "dataset_id": runtime.dataset_id}

    return app
