"""ASGI entry point for Uvicorn."""

from opc_mis.api.application import create_app

app = create_app()
