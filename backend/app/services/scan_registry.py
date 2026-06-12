"""In-process scan status registry (ASSUMPTION-A13: single-process deployment)."""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass
class ScanState:
    scan_id: str
    status: str = "running"  # running / completed / failed
    started_at: datetime = field(default_factory=_utcnow)
    finished_at: datetime | None = None
    markets_found: int = 0
    markets_analyzed: int = 0
    signals_generated: int = 0
    errors: list[str] = field(default_factory=list)
    current_step: str = "starting"


class ScanRegistry:
    def __init__(self) -> None:
        self._scans: dict[str, ScanState] = {}
        self._order: list[str] = []
        self._lock = asyncio.Lock()

    async def start(self) -> ScanState:
        async with self._lock:
            if any(s.status == "running" for s in self._scans.values()):
                from app.core.errors import ScanAlreadyRunningError
                raise ScanAlreadyRunningError("A scan is already running")
            state = ScanState(scan_id=uuid.uuid4().hex)
            self._scans[state.scan_id] = state
            self._order.append(state.scan_id)
            return state

    def get(self, scan_id: str) -> ScanState | None:
        return self._scans.get(scan_id)

    def latest(self) -> ScanState | None:
        return self._scans[self._order[-1]] if self._order else None

    def finish(self, scan_id: str, *, failed: bool = False) -> None:
        state = self._scans.get(scan_id)
        if state:
            state.status = "failed" if failed else "completed"
            state.finished_at = _utcnow()
            state.current_step = "done"
