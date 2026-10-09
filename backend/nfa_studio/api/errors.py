"""Error codes, HTTP statuses and the JSON error body (spec §11.2, §12.2).

Every error answers with {"error": {"code", "message", "detail"}}; the message names
the reason and the next action.
"""

import logging
from collections.abc import Mapping
from typing import Any, Final

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from nfa_studio.core.simulate import InputTooLong, SymbolNotInAlphabet
from nfa_studio.interpret.nonregular import NonRegularRequest
from nfa_studio.interpret.rule_parser import AlphabetMissing, UnsupportedRequest
from nfa_studio.ir.limits import StateLimitExceeded, TimeBudgetExceeded
from nfa_studio.ir.normalize import IRInvalid
from nfa_studio.render import RenderMismatch
from nfa_studio.session.clarify import UnknownAnswer
from nfa_studio.verify.ladder import VerificationFailed

logger = logging.getLogger("nfa_studio.api")

STATUS: Final = {
    "E_SCHEMA_INVALID": 422,
    "E_ALPHABET_MISSING": 422,
    "E_NEEDS_CLARIFICATION": 200,
    "E_UNSUPPORTED_NONREGULAR": 422,
    "E_UNSUPPORTED_FEATURE": 422,
    "E_SYMBOL_NOT_IN_ALPHABET": 422,
    "E_INPUT_TOO_LONG": 413,
    "E_STATE_LIMIT": 422,
    "E_TIMEOUT": 504,
    "E_VERIFY_FAILED": 500,
    "E_AUTOMATON_NOT_FOUND": 404,
    "E_RATE_LIMITED": 429,
    # Not in §11.2: an expired clarification session, and faults of the server itself.
    "E_SESSION_NOT_FOUND": 404,
    "E_INTERNAL": 500,
}


class ApiError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        detail: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = dict(detail or {})
        self.headers = dict(headers or {})


def to_api_error(exc: Exception) -> ApiError:
    """The API form of an error raised by the interpreter, compiler, verifier or renderer."""
    match exc:
        case ApiError():
            return exc
        case SymbolNotInAlphabet():
            return ApiError(exc.code, str(exc), {"symbol": exc.symbol, "position": exc.position})
        case InputTooLong():
            return ApiError(exc.code, str(exc), {"length": exc.length, "limit": exc.limit})
        case StateLimitExceeded():
            return ApiError(exc.code, str(exc), {"size": exc.size, "limit": exc.limit})
        case TimeBudgetExceeded():
            return ApiError(exc.code, str(exc), {"seconds": exc.seconds})
        case VerificationFailed():
            return ApiError(
                exc.code,
                f"{exc} The automaton is not shown. Rephrase or simplify the description; "
                "the specification has been logged for the developers.",
                {"level": exc.level, "counterexample": exc.counterexample},
            )
        case RenderMismatch():
            return ApiError(
                "E_VERIFY_FAILED",
                "A view was not built from the verified automaton, so it is not shown. "
                "Build the automaton again.",
                {"level": "V0", "counterexample": None},
            )
        case IRInvalid():
            return ApiError(
                exc.code,
                f"{exc}. Correct these fields and send the specification again.",
                {"errors": list(exc.errors)},
            )
        case UnknownAnswer():
            return ApiError("E_SCHEMA_INVALID", str(exc), {"errors": [str(exc)]})
        case NonRegularRequest():
            alternative = {"text": exc.alternative.text, "ir": exc.alternative.ir}
            return ApiError(
                exc.code,
                str(exc),
                {"reason": exc.reason, "why": exc.why, "alternative": alternative},
            )
        case UnsupportedRequest():
            return ApiError(
                exc.code,
                str(exc),
                {"reason": exc.reason, "examples": list(exc.examples), "alternative": None},
            )
        case AlphabetMissing():
            return ApiError(exc.code, str(exc))
    logger.exception("unexpected error", exc_info=exc)
    return ApiError(
        "E_INTERNAL",
        "The server failed unexpectedly. Try again; if it keeps failing, report it.",
    )


def error_response(error: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=STATUS[error.code],
        content={"error": {"code": error.code, "message": error.message, "detail": error.detail}},
        headers=error.headers,
    )


def install(app: FastAPI) -> None:
    async def domain(request: Request, exc: Exception) -> JSONResponse:
        return error_response(to_api_error(exc))

    async def invalid_request(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, RequestValidationError)
        errors = [f"{'.'.join(str(part) for part in e['loc'])}: {e['msg']}" for e in exc.errors()]
        return error_response(
            ApiError(
                "E_SCHEMA_INVALID",
                "The request is invalid: " + "; ".join(errors) + ". Correct it and send it again.",
                {"errors": errors},
            )
        )

    app.add_exception_handler(RequestValidationError, invalid_request)
    # Each expected error gets its own handler. A handler for Exception alone would run
    # as Starlette's server-error handler, which re-raises after answering.
    for expected in _EXPECTED:
        app.add_exception_handler(expected, domain)
    app.add_exception_handler(Exception, domain)


_EXPECTED: Final = (
    ApiError,
    SymbolNotInAlphabet,
    InputTooLong,
    StateLimitExceeded,
    TimeBudgetExceeded,
    VerificationFailed,
    RenderMismatch,
    IRInvalid,
    UnknownAnswer,
    NonRegularRequest,
    UnsupportedRequest,
    AlphabetMissing,
)
