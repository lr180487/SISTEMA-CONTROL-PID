"""Endpoints de estado, salud y configuración general."""
import time
from fastapi import APIRouter, Depends, HTTPException, Request

from ...models import (SCHEMA_VERSION, ConfigSnapshot, ConfigUpdateRequest,
                       ConfigUpdateResponse, HealthStatus)
from ..dependencies import get_runtime
from ...core.runtime import Runtime
from ...settings import settings

router = APIRouter(tags=["system"])


@router.get("/api/state")
async def get_state(rt: Runtime = Depends(get_runtime)):
    return rt.telemetry()


@router.get("/api/health", response_model=HealthStatus)
async def health(rt: Runtime = Depends(get_runtime)):
    telemetry = rt.telemetry()
    return HealthStatus(
        status="ok" if rt.process.running else "degraded",
        app_version=settings.app_version,
        schema_version=SCHEMA_VERSION,
        uptime_sec=round(time.time() - rt.started_at, 1),
        server_time=telemetry.timestamp,
        simulation_running=rt.process.running,
        simulation_hz=round(1.0 / settings.simulation_dt, 2),
        ws_clients=len(rt.ws_clients),
        historian_rows=rt.historian.get_count(),
        plc_mode=rt.plc_client.config.mode,
        plc_connected=rt.plc_client.connected,
        opcua_connected=rt.opcua_client.connected,
        opcua_endpoint=rt.opcua_client.config.endpoint,
        data_source=rt.plc_client.config.mode,
    )


@router.get("/api/config", response_model=ConfigSnapshot)
async def get_config(rt: Runtime = Depends(get_runtime)):
    return rt.config_snapshot()


@router.patch("/api/config", response_model=ConfigUpdateResponse)
async def patch_config(req: ConfigUpdateRequest, rt: Runtime = Depends(get_runtime)):
    applied: list[str] = []
    warnings: list[str] = []
    if req.feed is not None:
        if req.feed.profile != rt.process.feed_cfg.profile:
            rt.process.profile_start_sec = rt.process.elapsed_sec
        rt.process.feed_cfg = req.feed
    for cid, upd in (req.cells or {}).items():
        cfg = rt.process.configs[cid]
        data = upd.model_dump(exclude_unset=True, exclude_none=True)
        for key, value in data.items():
            setattr(cfg, key, value)
        if cfg.alarm_low >= cfg.alarm_high - 20.0:
            cfg.alarm_low = cfg.alarm_high - 25.0
            warnings.append(f"{cid}: alarm_low ajustado a {cfg.alarm_low:.1f} mm por coherencia con alarm_high")
        applied.append(cid)
    return ConfigUpdateResponse(
        applied_cells=applied,
        feed_applied=req.feed is not None,
        warnings=warnings,
        config=rt.config_snapshot(),
    )


@router.get("/api/meta")
async def api_meta(request: Request):
    return {
        "app_version": settings.app_version,
        "schema_version": SCHEMA_VERSION,
        "simulation_hz": round(1.0 / settings.simulation_dt, 2),
        "cell_ids": ["C1", "C2", "C3"],
        "ws_path": "/ws",
        "endpoints": [r.path for r in request.app.routes if getattr(r, "path", "").startswith("/api")],
    }
