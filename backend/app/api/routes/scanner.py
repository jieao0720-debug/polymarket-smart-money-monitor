from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import Container, get_container
from app.core.errors import NotFoundError
from app.schemas.api import ScanRunRequest, ScanStatusResponse
from app.services.scan_registry import ScanState

router = APIRouter(prefix="/api/scanner", tags=["scanner"])


def _to_response(state: ScanState | None) -> ScanStatusResponse:
    if state is None:
        return ScanStatusResponse(scan_id=None, status="idle")
    return ScanStatusResponse(
        scan_id=state.scan_id, status=state.status, started_at=state.started_at,
        finished_at=state.finished_at, markets_found=state.markets_found,
        markets_analyzed=state.markets_analyzed, signals_generated=state.signals_generated,
        errors=state.errors, current_step=state.current_step)


@router.post("/run", response_model=ScanStatusResponse)
async def run_scan(body: ScanRunRequest | None = None,
                   container: Container = Depends(get_container)) -> ScanStatusResponse:
    state = await container.registry.start()  # raises 409 if a scan is already running
    max_markets = body.max_markets if body else None
    container.spawn(container.scanner.run_scan(state.scan_id, max_markets=max_markets))
    return _to_response(state)


@router.get("/status/{scan_id}", response_model=ScanStatusResponse)
async def scan_status(scan_id: str,
                      container: Container = Depends(get_container)) -> ScanStatusResponse:
    state = container.registry.get(scan_id)
    if state is None:
        raise NotFoundError(f"scan {scan_id} not found")
    return _to_response(state)


@router.get("/latest", response_model=ScanStatusResponse)
async def scan_latest(container: Container = Depends(get_container)) -> ScanStatusResponse:
    return _to_response(container.registry.latest())
