"""Base async HTTP client: timeout, bounded retries with backoff, concurrency cap,
and api_fetch_logs recording via an injected async sink.

Rules (development-rules.md #14): idempotent GETs retry up to N times; POSTs never
auto-retry. Request params are sanitized before logging.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.core.errors import UpstreamError

logger = logging.getLogger("app.clients")

LogSink = Callable[[dict[str, Any]], Awaitable[None]]

_SENSITIVE_PARAM_KEYS = {"signature", "secret", "passphrase", "api_key", "apikey",
                         "authorization", "private_key", "poly_signature", "poly_passphrase"}

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def sanitize_params(params: dict[str, Any] | None) -> dict[str, Any] | None:
    if not params:
        return params
    return {k: ("[REDACTED]" if k.lower() in _SENSITIVE_PARAM_KEYS else v)
            for k, v in params.items()}


class BaseHTTPClient:
    source = "base"

    def __init__(self, base_url: str, *, timeout: float = 15.0, retries: int = 3,
                 semaphore: asyncio.Semaphore | None = None, log_sink: LogSink | None = None,
                 client: httpx.AsyncClient | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = max(1, retries)
        self.semaphore = semaphore or asyncio.Semaphore(8)
        self.log_sink = log_sink
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            headers={"User-Agent": "polymarket-smart-money-monitor/0.1 (analysis tool)"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _log(self, *, endpoint: str, status: str, http_status: int | None,
                   params: dict[str, Any] | None, summary: str | None,
                   error: str | None, duration_ms: int) -> None:
        if self.log_sink is None:
            return
        try:
            await self.log_sink({
                "source": self.source, "endpoint": endpoint, "status": status,
                "http_status": http_status, "request_params": sanitize_params(params),
                "response_summary": (summary or "")[:500] or None,
                "error_message": (error or "")[:500] or None, "duration_ms": duration_ms,
            })
        except Exception:  # pragma: no cover — logging must never break data flow
            logger.warning("fetch-log sink failed for %s", endpoint)

    async def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET with bounded retries. Raises UpstreamError after exhausting retries."""
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        last_error: str | None = None
        last_status: int | None = None
        start = time.monotonic()
        for attempt in range(self.retries):
            try:
                async with self.semaphore:
                    resp = await self._client.get(url, params=params)
                last_status = resp.status_code
                if resp.status_code in _RETRYABLE_STATUS:
                    last_error = f"HTTP {resp.status_code}"
                elif resp.status_code >= 400:
                    last_error = f"HTTP {resp.status_code}"
                    break  # non-retryable client error
                else:
                    data = resp.json()
                    await self._log(endpoint=url, status="ok", http_status=resp.status_code,
                                    params=params, summary=str(data)[:200], error=None,
                                    duration_ms=int((time.monotonic() - start) * 1000))
                    return data
            except httpx.TimeoutException:
                last_error = "timeout"
            except httpx.HTTPError as exc:
                last_error = f"transport: {type(exc).__name__}"
            except ValueError:
                last_error = "invalid JSON response"
                break
            if attempt < self.retries - 1:
                await asyncio.sleep(0.5 * (2 ** attempt) + random.random() * 0.25)
        duration_ms = int((time.monotonic() - start) * 1000)
        status = "timeout" if last_error == "timeout" else "error"
        await self._log(endpoint=url, status=status, http_status=last_status, params=params,
                        summary=None, error=last_error, duration_ms=duration_ms)
        raise UpstreamError(f"{self.source} request failed: {last_error}",
                            details={"endpoint": url, "source": self.source})

    async def post_json(self, path: str, *, json_body: Any,
                        headers: dict[str, str] | None = None) -> Any:
        """POST without auto-retry (order safety: development-rules.md #14)."""
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        start = time.monotonic()
        try:
            async with self.semaphore:
                resp = await self._client.post(url, json=json_body, headers=headers)
            duration_ms = int((time.monotonic() - start) * 1000)
            # Never log the body (may contain signed order payloads).
            await self._log(endpoint=url, status="ok" if resp.status_code < 400 else "error",
                            http_status=resp.status_code, params=None,
                            summary=f"POST status={resp.status_code}",
                            error=None if resp.status_code < 400 else f"HTTP {resp.status_code}",
                            duration_ms=duration_ms)
            try:
                data = resp.json()
            except ValueError:
                data = {"raw": resp.text[:500]}
            return resp.status_code, data
        except httpx.HTTPError as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            await self._log(endpoint=url, status="error", http_status=None, params=None,
                            summary=None, error=f"transport: {type(exc).__name__}",
                            duration_ms=duration_ms)
            raise UpstreamError(f"{self.source} POST failed: {type(exc).__name__}",
                                details={"endpoint": url}) from exc
