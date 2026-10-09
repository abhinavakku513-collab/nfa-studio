"""HTTP routes for API v1 (spec §11)."""

from typing import Final, Literal

from fastapi import APIRouter
from pydantic import BaseModel

from nfa_studio.ir.limits import LIMITS, Limits
from nfa_studio.ir.schema import IR_VERSION, NODE_TYPES

API_VERSION: Final = "v1"

router = APIRouter(prefix=f"/{API_VERSION}")


class Health(BaseModel):
    status: Literal["ok"]


class Capabilities(BaseModel):
    api_version: Literal["v1"]
    ir_version: Literal["1.0"]
    node_types: list[str]
    limits: Limits


@router.get("/health")
def health() -> Health:
    """Liveness and readiness."""
    return Health(status="ok")


@router.get("/capabilities")
def capabilities() -> Capabilities:
    """Supported node types, limits and versions."""
    return Capabilities(
        api_version=API_VERSION,
        ir_version=IR_VERSION,
        node_types=list(NODE_TYPES),
        limits=LIMITS,
    )
