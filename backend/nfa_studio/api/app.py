"""ASGI entry point: `uvicorn nfa_studio.api.app:app`."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from nfa_studio.api.routes import router

app = FastAPI(title="NFA Studio", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(router)
