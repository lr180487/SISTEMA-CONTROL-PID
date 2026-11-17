"""Punto de composición FastAPI del SCADA.

Los endpoints viven en backend.api.routes y el estado operativo se inyecta
mediante Runtime. Este módulo conserva aliases de compatibilidad para pruebas
históricas y consumidores internos; no contiene lógica de negocio HTTP.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api.routes import (cells as cells_routes, dashboard as dashboard_routes,
                         historian as historian_routes, opcua as opcua_routes,
                         plc as plc_routes, system as system_routes,
                         websocket as websocket_routes)
from .core.runtime import Runtime, create_runtime
from .opcua_client import ASYNCUA_AVAILABLE
from .settings import settings

runtime: Runtime = create_runtime()

# Aliases de compatibilidad: las rutas nuevas nunca importan estos globals.
process = runtime.process
historian_db = runtime.historian
historian = runtime.historian
plc_client = runtime.plc_client
opcua_client = runtime.opcua_client
source_service = runtime.source_service
ws_clients = runtime.ws_clients
APP_VERSION = settings.app_version
SIM_DT = settings.simulation_dt
FRONTEND_DIR = settings.frontend_dir
SCL_FILE = settings.scl_file
_last_opc_poll = 0.0


def _control_writes_enabled() -> bool:
    return settings.control_writes_enabled


def apply_opcua_values(values: dict) -> None:
    runtime.source_service.apply_opcua_values(values)


async def sync_opcua_to_plc() -> list[str]:
    return await runtime.source_service.sync_opcua_to_plc()


async def advance_active_source(mode: str, now_ms: float | None = None) -> bool:
    global _last_opc_poll
    runtime.source_service.last_opc_poll = _last_opc_poll
    fresh = await runtime.source_service.advance_active_source(mode, now_ms=now_ms)
    _last_opc_poll = runtime.source_service.last_opc_poll
    return fresh


async def simulation_loop() -> None:
    await runtime.simulation_loop()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.runtime = runtime
    runtime.simulation_task = asyncio.create_task(runtime.simulation_loop())
    try:
        yield
    finally:
        await runtime.shutdown()


app = FastAPI(
    title="SCADA Flotación 3 Celdas - Control PI + Feedforward (Siemens S7-1200)",
    description="Implementación basada en Quintanilla et al. (2023), MethodsX 10, 102081.",
    version=APP_VERSION,
    lifespan=lifespan,
)
app.state.runtime = runtime
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)

# Routers por dominio: las rutas públicas y sus métodos se conservan.
app.include_router(system_routes.router)
app.include_router(cells_routes.router)
app.include_router(historian_routes.router)
app.include_router(plc_routes.router)
app.include_router(opcua_routes.router)
app.include_router(websocket_routes.router)
app.include_router(dashboard_routes.router)
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
