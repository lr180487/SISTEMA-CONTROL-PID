"""Pruebas de regresión y seguridad para el ciclo SCADA y OPC UA."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend import opcua_client as opcua_module


def test_opcua_mode_never_advances_simulation(monkeypatch):
    calls = {"step": 0, "read": 0, "write": 0}

    def fake_step(dt):
        calls["step"] += 1

    async def fake_read():
        calls["read"] += 1
        return {"C1_PV_mm": 321.0}

    async def fake_sync():
        calls["write"] += 1
        return []

    monkeypatch.setattr(main.process, "step", fake_step)
    monkeypatch.setattr(main.opcua_client, "connected", True)
    monkeypatch.setattr(main.opcua_client.config, "active", True)
    monkeypatch.setattr(main.opcua_client.config, "poll_ms", 100)
    monkeypatch.setattr(main.opcua_client, "read_all", fake_read)
    monkeypatch.setattr(main, "sync_opcua_to_plc", fake_sync)
    monkeypatch.delenv("SCADA_ENABLE_CONTROL_WRITES", raising=False)
    monkeypatch.setattr(main, "_last_opc_poll", 0.0)

    fresh = asyncio.run(main.advance_active_source("OPC_UA", now_ms=1000.0))

    assert fresh is True
    assert calls["step"] == 0
    assert calls["read"] == 1
    assert calls["write"] == 0


def test_simulation_mode_advances_model(monkeypatch):
    calls = {"step": 0}

    def fake_step(dt):
        calls["step"] += 1

    monkeypatch.setattr(main.process, "step", fake_step)
    assert asyncio.run(main.advance_active_source("SIMULATION")) is True
    assert calls["step"] == 1


def test_snap7_mode_does_not_falsely_simulate(monkeypatch):
    calls = {"step": 0}

    def fake_step(dt):
        calls["step"] += 1

    monkeypatch.setattr(main.process, "step", fake_step)
    assert asyncio.run(main.advance_active_source("PLC_S7_1200")) is False
    assert calls["step"] == 0


def test_opcua_write_endpoint_denied_by_default(monkeypatch):
    monkeypatch.delenv("SCADA_ENABLE_CONTROL_WRITES", raising=False)
    client = TestClient(main.app)
    response = client.post(
        "/api/opcua/write",
        json={"tag": "C1_SP_mm", "value": 325.0},
    )
    assert response.status_code == 403


def test_opcua_write_validation_rejects_out_of_range_without_io(monkeypatch):
    class FakeNode:
        async def write_value(self, value):
            raise AssertionError("No debe llegar a escribir")

    class FakeClient:
        def get_node(self, node_id):
            return FakeNode()

    fake_ua = SimpleNamespace(
        Variant=lambda value, kind: (value, kind),
        VariantType=SimpleNamespace(Boolean="Boolean", Float="Float"),
        NodeId=lambda identifier, namespace: (identifier, namespace),
    )
    monkeypatch.setattr(opcua_module, "ua", fake_ua)
    opcua_module.opcua_client.connected = True
    opcua_module.opcua_client.client = FakeClient()
    result = asyncio.run(opcua_module.opcua_client.write_tag("C1_SP_mm", 999.0))
    assert result["status"] == "error"
    assert "fuera de rango" in result["detail"]


def test_opcua_write_validation_rejects_string_boolean(monkeypatch):
    class FakeNode:
        async def write_value(self, value):
            raise AssertionError("No debe llegar a escribir")

    class FakeClient:
        def get_node(self, node_id):
            return FakeNode()

    fake_ua = SimpleNamespace(
        Variant=lambda value, kind: (value, kind),
        VariantType=SimpleNamespace(Boolean="Boolean", Float="Float"),
        NodeId=lambda identifier, namespace: (identifier, namespace),
    )
    monkeypatch.setattr(opcua_module, "ua", fake_ua)
    opcua_module.opcua_client.connected = True
    opcua_module.opcua_client.client = FakeClient()
    result = asyncio.run(opcua_module.opcua_client.write_tag("C1_AutoMode", "false"))
    assert result["status"] == "error"
    assert "Boolean" in result["detail"]


def test_opcua_endpoint_parser_rejects_invalid_scheme():
    with pytest.raises(ValueError):
        opcua_module.opcua_client._parse_endpoint("http://127.0.0.1:4840")


def test_opcua_test_server_reports_missing_dependency(monkeypatch):
    monkeypatch.setattr(main.runtime, "asyncua_available", False)
    client = TestClient(main.app)
    response = client.post("/api/opcua/test-server/start", json={"port": 4840})
    assert response.status_code == 503
