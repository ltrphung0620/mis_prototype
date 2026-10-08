"""ASGI entry point for Uvicorn."""

from pathlib import Path

from dotenv import load_dotenv

from opc_mis.api.application import create_app

# Local development loads server-side settings from ``.env`` before the
# application factory reads them.  The API capability endpoint exposes only
# safe booleans/model identity; secret material never leaves this process.
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

app = create_app()
