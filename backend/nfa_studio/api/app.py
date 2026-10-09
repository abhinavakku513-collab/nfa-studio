"""ASGI entry point: `uvicorn nfa_studio.api.app:app`."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from nfa_studio.api import errors
from nfa_studio.api.routes import api, public

app = FastAPI(title="NFA Studio", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

errors.install(app)
app.include_router(public)
app.include_router(api)
