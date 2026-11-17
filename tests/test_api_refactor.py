"""Pruebas de regresión de la segunda iteración de arquitectura API."""
from fastapi.testclient import TestClient

from backend.main import app, runtime


def test_routes_are_registered_by_domain_and_keep_public_paths():
    paths = {route.path for route in app.routes if hasattr(route, "path")}
    expected = {
        "/api/state", "/api/health", "/api/config", "/api/cells/{cell_id}",
        "/api/feed", "/api/alarms", "/api/historian/recent", "/api/plc/status",
        "/api/opcua/status", "/api/opcua/write", "/api/meta", "/ws", "/",
    }
    assert expected <= paths


def test_runtime_is_attached_to_application_and_dependencies_are_used():
    assert app.state.runtime is runtime
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["app_version"]


def test_dashboard_static_entrypoint_is_preserved():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_opcua_test_server_status_uses_runtime_state():
    client = TestClient(app)
    response = client.get("/api/opcua/test-server/status")
    assert response.status_code == 200
    assert response.json() == {"running": False, "endpoint": None}


def test_websocket_route_remains_available():
    client = TestClient(app)
    with client.websocket_connect("/ws") as websocket:
        payload = websocket.receive_json()
        assert "cells" in payload


def test_runtime_factory_creates_isolated_process_and_protocol_clients():
    from backend.core.runtime import create_runtime

    other = create_runtime()
    assert other is not runtime
    assert other.process is not runtime.process
    assert other.plc_client is not runtime.plc_client
    assert other.opcua_client is not runtime.opcua_client
    assert other.source_service.process is other.process
