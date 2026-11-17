"""Configuración y conexión complementaria Snap7."""
from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from ...core.runtime import Runtime
from ...models import PLCConnectionConfig
from ...settings import settings
from ..dependencies import get_runtime

router = APIRouter(tags=["plc-snap7"])


@router.get("/api/plc/status")
async def get_plc_status(rt: Runtime = Depends(get_runtime)):
    return rt.plc_client.get_status()


@router.post("/api/plc/config")
async def update_plc_config(cfg: PLCConnectionConfig, rt: Runtime = Depends(get_runtime)):
    return rt.plc_client.update_config(cfg)


@router.post("/api/plc/connect")
async def connect_plc(cfg: PLCConnectionConfig, rt: Runtime = Depends(get_runtime)):
    rt.plc_client.update_config(cfg)
    return rt.plc_client.test_and_connect()


@router.post("/api/plc/disconnect")
async def disconnect_plc(rt: Runtime = Depends(get_runtime)):
    return rt.plc_client.disconnect()


@router.get("/api/plc/scl", response_class=PlainTextResponse)
async def get_tia_portal_scl():
    if settings.scl_file.exists():
        return settings.scl_file.read_text(encoding="utf-8")
    return "// Archivo SCL no encontrado"
