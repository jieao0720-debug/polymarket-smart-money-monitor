"""Unified error envelope: {"error": {"code", "message", "details"}}.

Never leak stack traces to clients (development-rules.md #6, security audit #7).
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.errors")


class AppError(Exception):
    status_code = 400
    code = "APP_ERROR"

    def __init__(self, message: str, *, code: str | None = None,
                 status_code: int | None = None, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.details = details or {}


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"


class ValidationFailed(AppError):
    status_code = 422
    code = "VALIDATION_ERROR"


class GeoblockedError(AppError):
    status_code = 403
    code = "GEOBLOCKED"


class CloseOnlyRegionError(AppError):
    status_code = 403
    code = "CLOSE_ONLY_REGION"


class LiveTradingDisabledError(AppError):
    status_code = 403
    code = "LIVE_TRADING_DISABLED"


class RiskCheckFailedError(AppError):
    status_code = 400
    code = "RISK_CHECK_FAILED"


class MarketNotTradableError(AppError):
    status_code = 400
    code = "MARKET_NOT_TRADABLE"


class UpstreamError(AppError):
    status_code = 502
    code = "UPSTREAM_ERROR"


class ScanAlreadyRunningError(AppError):
    status_code = 409
    code = "SCAN_ALREADY_RUNNING"


def _envelope(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code,
                            content=_envelope(exc.code, exc.message, exc.details))

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_envelope("VALIDATION_ERROR", "Request validation failed",
                              {"errors": exc.errors()}),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exc_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(status_code=exc.status_code,
                            content=_envelope(code, str(exc.detail)))

    @app.exception_handler(Exception)
    async def unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
        # Log server-side with traceback; client gets an opaque envelope only.
        logger.exception("Unhandled error: %s", type(exc).__name__)
        return JSONResponse(status_code=500,
                            content=_envelope("INTERNAL_ERROR", "Internal server error"))
