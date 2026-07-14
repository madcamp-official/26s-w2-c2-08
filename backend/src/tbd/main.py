"""ASGI entry point used by Uvicorn."""

from tbd.app import create_app

app = create_app()
