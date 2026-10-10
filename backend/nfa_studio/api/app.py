"""ASGI entry point: `uvicorn nfa_studio.api.app:app`."""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from nfa_studio.api import errors
from nfa_studio.api.routes import api, public

DEV_ORIGIN = "http://localhost:3000"


def cors_origins(value: str | None) -> list[str]:
    """Origins allowed to call the API, from a comma-separated list such as NFA_CORS_ORIGINS.

    A trailing slash is dropped, since a browser's Origin header never has one.
    """
    origins = [o.strip().rstrip("/") for o in (value or "").split(",")]
    return [o for o in origins if o] or [DEV_ORIGIN]


app = FastAPI(title="NFA Studio", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(os.environ.get("NFA_CORS_ORIGINS")),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

errors.install(app)
app.include_router(public)
app.include_router(api)
