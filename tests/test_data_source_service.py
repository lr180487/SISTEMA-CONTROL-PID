"""Pruebas unitarias del servicio de selección de fuentes industriales."""
import asyncio
from types import SimpleNamespace

from backend.services.data_sources import DataSourceService


class FakeProcess:
    def __init__(self):
        self.steps = 0
        self.q_feed_current = 0.0
        self.levels_mm = {"C1": 300.0, "C2": 300.0, "C3": 300.0}
        self.pump_rpm_actual = {"C1": 100.0, "C2": 100.0, "C3": 100.0}
        self.pump_rpm_cmd = {"C1": 100.0, "C2": 100.0, "C3": 100.0}
        self.configs = {
            cid: SimpleNamespace(sp=300.0, kp=-5.0, ki=-0.5, kff=1.0,
                                 mode="AUTO", ff_enabled=True, manual_rpm=100.0)
            for cid in ("C1", "C2", "C3")
        }

    def step(self, dt):
        self.steps += 1


class FakeOPCUA:
    def __init__(self):
        self.connected = True
        self.config = SimpleNamespace(active=True, poll_ms=100)
        self.reads = 0
        self.writes = []

    async def read_all(self):
        self.reads += 1
        return {"Q_Feed_LPM": 23.0, "C1_PV_mm": 321.0, "C1_Pump_RPM_PV": 140.0}

    async def write_tag(self, tag, value):
        self.writes.append((tag, value))
        return {"status": "ok"}


class FakePLC:
    pass


def make_service(writes=False):
    process = FakeProcess()
    opcua = FakeOPCUA()
    service = DataSourceService(process, FakePLC(), opcua, lambda: writes, 0.5)
    return service, process, opcua


def test_simulation_is_the_only_source_that_advances_process():
    service, process, opcua = make_service()
    assert asyncio.run(service.advance_active_source("SIMULATION")) is True
    assert process.steps == 1
    assert opcua.reads == 0


def test_opcua_updates_telemetry_without_advancing_simulation():
    service, process, opcua = make_service()
    assert asyncio.run(service.advance_active_source("OPC_UA", now_ms=1000)) is True
    assert process.steps == 0
    assert process.q_feed_current == 23.0
    assert process.levels_mm["C1"] == 321.0
    assert process.pump_rpm_actual["C1"] == 140.0


def test_snap7_mode_does_not_fabricate_telemetry():
    service, process, opcua = make_service()
    assert asyncio.run(service.advance_active_source("PLC_S7_1200", now_ms=1000)) is False
    assert process.steps == 0
    assert opcua.reads == 0


def test_opcua_writes_are_off_unless_explicitly_enabled():
    service, process, opcua = make_service(writes=False)
    assert asyncio.run(service.sync_opcua_to_plc()) == []
    assert opcua.writes == []


def test_opcua_writes_only_setpoints_and_parameters_when_enabled():
    service, process, opcua = make_service(writes=True)
    written = asyncio.run(service.sync_opcua_to_plc())
    assert len(written) == 21
    assert all("_PV" not in tag and "Output" not in tag for tag, _ in opcua.writes)
