"""Composición y ciclo de vida de los recursos del SCADA."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from ..historian import HistorianDB
from ..models import OPCUAConnectionConfig
from ..opcua_client import ASYNCUA_AVAILABLE, SiemensOPCUAClient
from ..plc_s7 import SiemensS71200Client
from ..process_model import ThreeCellFlotationProcess
from ..services.data_sources import DataSourceService
from ..settings import settings

logger = logging.getLogger("scada")


class WebSocketHub:
    """Gestiona conexiones WebSocket sin acoplarlas a los routers."""

    def __init__(self) -> None:
        self.clients: set[Any] = set()

    async def connect(self, websocket: Any) -> None:
        await websocket.accept()
        self.clients.add(websocket)

    def disconnect(self, websocket: Any) -> None:
        self.clients.discard(websocket)

    async def broadcast(self, payload: dict) -> None:
        stale = []
        for websocket in tuple(self.clients):
            try:
                await websocket.send_json(payload)
            except Exception:
                stale.append(websocket)
        for websocket in stale:
            self.disconnect(websocket)

    async def close_all(self) -> None:
        for websocket in tuple(self.clients):
            try:
                await websocket.close(code=1001)
            except Exception:
                pass
            self.disconnect(websocket)


@dataclass
class Runtime:
    process: ThreeCellFlotationProcess
    historian: HistorianDB
    plc_client: SiemensS71200Client
    opcua_client: Any
    source_service: DataSourceService
    ws_hub: WebSocketHub = field(default_factory=WebSocketHub)
    started_at: float = field(default_factory=time.time)
    asyncua_available: bool = ASYNCUA_AVAILABLE
    opcua_test_server: Any | None = None
    opcua_test_endpoint: str | None = None
    simulation_task: asyncio.Task | None = None

    @property
    def ws_clients(self) -> set[Any]:
        return self.ws_hub.clients

    @property
    def simulation_dt(self) -> float:
        return settings.simulation_dt

    @property
    def control_writes_enabled(self) -> bool:
        return settings.control_writes_enabled

    def telemetry(self):
        return self.process.build_telemetry(
            self.plc_client.get_status(), self.opcua_client.get_status()
        )

    def config_snapshot(self):
        return self.process.build_config_snapshot(
            self.plc_client.config, self.opcua_client.config
        )

    async def advance_active_source(self, mode: str, now_ms: float | None = None) -> bool:
        self.source_service.last_opc_poll = getattr(self, "last_opc_poll", 0.0)
        fresh = await self.source_service.advance_active_source(mode, now_ms=now_ms)
        self.last_opc_poll = self.source_service.last_opc_poll
        return fresh

    async def simulation_loop(self) -> None:
        while True:
            try:
                mode = self.plc_client.config.mode
                fresh_sample = await self.advance_active_source(mode)
                telemetry = self.telemetry()
                if fresh_sample:
                    self.historian.record_telemetry(telemetry, every_n_ticks=2)
                if self.ws_clients:
                    await self.ws_hub.broadcast(telemetry.model_dump())
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Fallo en el ciclo principal SCADA")
            await asyncio.sleep(self.simulation_dt)

    async def shutdown(self) -> None:
        if self.simulation_task and not self.simulation_task.done():
            self.simulation_task.cancel()
            try:
                await self.simulation_task
            except asyncio.CancelledError:
                pass
        await self.ws_hub.close_all()
        if self.opcua_client.connected:
            await self.opcua_client.disconnect()
        try:
            self.plc_client.disconnect()
        except Exception:
            logger.exception("No se pudo cerrar la sesión Snap7 durante shutdown")
        if self.opcua_test_server is not None:
            try:
                await self.opcua_test_server.stop()
            finally:
                self.opcua_test_server = None
                self.opcua_test_endpoint = None


def create_runtime() -> Runtime:
    """Construye las dependencias de una instancia SCADA."""
    process = ThreeCellFlotationProcess()
    historian = HistorianDB()
    plc_client = SiemensS71200Client()
    # El cliente OPC UA existente conserva su API pública; su configuración se
    # aplica al componer Runtime y no desde los módulos de rutas.
    opcua_client = SiemensOPCUAClient()
    opcua_client.update_config(
        OPCUAConnectionConfig(
            endpoint=settings.opcua_endpoint,
            security_policy=settings.opcua_security_policy,
            username=settings.opcua_username,
            password=settings.opcua_password,
            namespace_index=settings.opcua_namespace_index,
            poll_ms=settings.opcua_poll_ms,
            timeout_s=settings.opcua_timeout_s,
            active=settings.opcua_active,
        )
    )
    source_service = DataSourceService(
        process=process,
        plc_client=plc_client,
        opcua_client=opcua_client,
        control_writes_enabled=lambda: settings.control_writes_enabled,
        simulation_dt=settings.simulation_dt,
    )
    return Runtime(
        process=process,
        historian=historian,
        plc_client=plc_client,
        opcua_client=opcua_client,
        source_service=source_service,
    )
