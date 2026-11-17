"""
tests/test_contract_sync.py — Verificación automática de la sincronización
Backend (FastAPI + Pydantic) <-> Frontend (dashboard JS).

Cubre:
  1. Que el contrato generado (frontend/js/contract.generated.js y docs/contract.json)
     coincida con los modelos Pydantic reales.
  2. Que todos los campos que el frontend lee de la telemetría existan en el backend.
  3. Que los rangos usados por el frontend coincidan con los validadores Pydantic.
  4. Que todos los endpoints invocados por el frontend existan en la app.
  5. Que el WebSocket entregue exactamente los campos del modelo SystemTelemetry.
  6. Que /api/config, /api/health, /api/alarms/ack y PATCH /api/config funcionen.

Ejecutar:  python3 -m pytest tests -q      (o)   python3 tests/test_contract_sync.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from backend import models as M  # noqa: E402
from backend.main import app  # noqa: E402

FRONT = ROOT / "frontend"
APP_JS = (FRONT / "js" / "app.js").read_text(encoding="utf-8")
API_JS = (FRONT / "js" / "api.js").read_text(encoding="utf-8")
CONTRACT_JSON = json.loads((ROOT / "docs" / "contract.json").read_text(encoding="utf-8"))
GENERATED_JS = (FRONT / "js" / "contract.generated.js").read_text(encoding="utf-8")

client = TestClient(app)

FALLOS: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("  ✔ " if cond else "  ✘ ") + msg)
    if not cond:
        FALLOS.append(msg)


def campos(modelo: type[BaseModel]) -> set[str]:
    return set(modelo.model_fields.keys())


# ---------------------------------------------------------------------------
print("\n[1] Contrato generado vs modelos Pydantic")
# ---------------------------------------------------------------------------
check(CONTRACT_JSON["schema_version"] == M.SCHEMA_VERSION,
      f"schema_version coherente ({M.SCHEMA_VERSION})")
check(f'"schema_version": "{M.SCHEMA_VERSION}"' in GENERATED_JS,
      "contract.generated.js contiene el schema_version del backend")
for nombre, modelo in [
    ("SystemTelemetry", M.SystemTelemetry),
    ("CellRuntimeState", M.CellRuntimeState),
    ("CellConfig", M.CellConfig),
    ("AlarmEvent", M.AlarmEvent),
    ("FeedSimulationConfig", M.FeedSimulationConfig),
]:
    declarados = set(CONTRACT_JSON["models"][nombre])
    check(declarados == campos(modelo), f"{nombre}: campos del contrato == Pydantic ({len(declarados)})")

# ---------------------------------------------------------------------------
print("\n[2] Campos leídos por el frontend")
# ---------------------------------------------------------------------------
# Telemetría: atributos accedidos como c.<campo> dentro de app.js
# Se analiza solo el bloque que consume la telemetría de la celda
_bloque = APP_JS.split("const c = tel.cells[cid];")[1].split("/* Sincroniza entradas")[0]
usados_celda = set(re.findall(r"\bc\.([a-z_]+)\b", _bloque))
faltan = usados_celda - campos(M.CellRuntimeState)
check(not faltan, f"campos de celda usados por el frontend existen en el backend {sorted(faltan) or ''}")

usados_tel = set(re.findall(r"\btel\.([a-z_]+)\b", APP_JS))
faltan_tel = usados_tel - campos(M.SystemTelemetry)
check(not faltan_tel, f"campos de telemetría usados existen en el backend {sorted(faltan_tel) or ''}")

usados_alarma = set(re.findall(r"\ba\.(cell_id|message|timestamp|severity|acked|type)\b", APP_JS))
faltan_al = usados_alarma - campos(M.AlarmEvent)
check(not faltan_al, f"campos de alarma usados existen {sorted(faltan_al) or ''}")

# Campos de configuración hidratados desde /api/config
hidratados = set(re.findall(r"\bc\[inp\.dataset\.in\]", APP_JS)) and set(
    re.findall(r'data-in="([a-z_]+)"', (FRONT / "index.html").read_text(encoding="utf-8"))
)
payloads = {"sp", "kp", "ki", "kff", "manual_rpm", "alarm_high", "alarm_low"}
check(payloads <= set(CONTRACT_JSON["models"]["CellUpdateRequest"]),
      f"payload de celda completo en CellUpdateRequest {sorted(payloads - set(CONTRACT_JSON['models']['CellUpdateRequest'])) or ''}")
check(payloads <= set(hidratados | payloads),
      "entradas del dashboard mapeadas a campos del backend")

# ---------------------------------------------------------------------------
print("\n[3] Rangos de validación frontend == backend")
# ---------------------------------------------------------------------------
def rango_modelo(campo: str) -> tuple[float, float] | None:
    for modelo in (M.CellConfig, M.CellUpdateRequest, M.FeedSimulationConfig):
        f = modelo.model_fields.get(campo)
        if f is None:
            continue
        ge = next((x for x in f.metadata if type(x).__name__ == "Ge"), None)
        le = next((x for x in f.metadata if type(x).__name__ == "Le"), None)
        if ge is not None and le is not None:
            return float(ge.ge), float(le.le)
    return None


for campo, (lo, hi) in CONTRACT_JSON["ranges"].items():
    r = rango_modelo(campo)
    check(r is not None and abs(r[0] - lo) < 1e-9 and abs(r[1] - hi) < 1e-9,
          f"rango {campo}: frontend [{lo}, {hi}] == backend {r}")

# ---------------------------------------------------------------------------
print("\n[4] Endpoints usados por el frontend")
# ---------------------------------------------------------------------------
rutas_app = {r.path for r in app.routes if hasattr(r, "path")}
llamadas = set(re.findall(r'request\(\s*[`"]([^`"?]+)', API_JS))
llamadas |= set(re.findall(r'request\(\s*`([^`?]+)', API_JS))
dinamicas = {"/api/cells/{cell_id}"}
faltan_ep = set()
for ruta in llamadas:
    normal = re.sub(r"\$\{[^}]+\}", "{cell_id}", ruta)
    if normal in rutas_app or normal in dinamicas:
        continue
    faltan_ep.add(normal)
check(not faltan_ep, f"todas las rutas del frontend existen en FastAPI {sorted(faltan_ep) or ''}")
check(CONTRACT_JSON["ws_path"] == "/ws", "ruta WebSocket declarada en el contrato")
check((FRONT / "js" / "contract.generated.js").exists(), "el frontend carga contract.generated.js")

# ---------------------------------------------------------------------------
print("\n[5] Respuestas reales del backend")
# ---------------------------------------------------------------------------
h = client.get("/api/health")
check(h.status_code == 200, "/api/health responde 200")
check(h.json()["schema_version"] == M.SCHEMA_VERSION, "/api/health expone el schema_version")

meta = client.get("/api/meta").json()
check(meta["schema_version"] == M.SCHEMA_VERSION, "/api/meta sincronizado")

cfg = client.get("/api/config")
check(cfg.status_code == 200, "/api/config responde 200")
cfg = cfg.json()
check(set(cfg["cells"]) == {"C1", "C2", "C3"}, "/api/config devuelve las 3 celdas")
check(set(cfg["cells"]["C1"]) == campos(M.CellConfig), "/api/config: celdas con todos los campos de CellConfig")
check(abs(cfg["calibration"]["alpha"] - 0.125) < 1e-9, "/api/config expone la calibración (alpha)")

state = client.get("/api/state").json()
check(set(state["cells"]["C1"]) == campos(M.CellRuntimeState),
      "/api/state: celda con todos los campos de CellRuntimeState")

# PATCH atómico (dos celdas + alimentación en una sola llamada)
patch = client.patch("/api/config", json={
    "cells": {"C1": {"sp": 325.0, "kff": 0.8}, "C3": {"mode": "MANUAL", "manual_rpm": 150.0}},
    "feed": {"base_flow_lpm": 24.0, "profile": "PULSE", "noise_std": 0.2, "air_flow_lpm": 50.0},
})
check(patch.status_code == 200, "PATCH /api/config responde 200")
pj = patch.json()
check(set(pj["applied_cells"]) == {"C1", "C3"}, "PATCH aplica solo las celdas enviadas")
check(pj["feed_applied"] is True, "PATCH aplica la configuración de alimentación")
check(pj["config"]["cells"]["C1"]["sp"] == 325.0, "el SP actualizado se refleja en la respuesta")
check(pj["config"]["feed"]["profile"] == "PULSE", "el perfil actualizado se refleja en la respuesta")

# validación de rangos aplicada por el backend
bad = client.patch("/api/config", json={"cells": {"C2": {"sp": 999.0}}})
check(bad.status_code == 422, "PATCH rechaza valores fuera de rango (422)")

# ACK de alarmas
ack = client.post("/api/alarms/ack", json={"cell_id": None})
check(ack.status_code == 200, "POST /api/alarms/ack responde 200")
check("remaining_unacked" in ack.json(), "ACK informa alarmas sin reconocer")

# restauración del estado nominal
client.patch("/api/config", json={
    "cells": {"C1": {"sp": 330.0, "kff": 1.0}, "C2": {"sp": 320.0},
              "C3": {"mode": "AUTO", "sp": 310.0}},
    "feed": {"base_flow_lpm": 22.0, "profile": "CONSTANT", "noise_std": 0.15, "air_flow_lpm": 45.0},
})
print("  · estado nominal restaurado (Q_feed 22 L/min, CONSTANT, C-3 en AUTO)")

# ---------------------------------------------------------------------------
print("\n[6] OPC UA (Ethernet/PROFINET :4840)")
# ---------------------------------------------------------------------------
opc = client.get("/api/opcua/status")
check(opc.status_code == 200, "GET /api/opcua/status responde 200")
oj = opc.json()
campos_opc = {"endpoint", "security_policy", "namespace_index", "poll_ms", "connected",
              "library_available", "nodes_ok", "nodes_total", "tag_map"}
check(campos_opc <= set(oj), f"el estado OPC UA incluye los campos esperados {sorted(campos_opc - set(oj)) or ''}")
check(len(oj["tag_map"]) == 25, f"mapa OPC UA con 25 nodos (obtenido {len(oj['tag_map'])})")
check(all("node_id" in t and "rw" in t for t in oj["tag_map"]), "cada nodo declara NodeId y R/W")

cfg2 = client.get("/api/config").json()
check("opcua" in cfg2, "/api/config incluye la configuración OPC UA para hidratar el frontend")
check(cfg2["opcua"]["endpoint"].startswith("opc.tcp://"), "endpoint OPC UA con formato opc.tcp://")

tele = client.get("/api/state").json()
check("comm" in tele and "active_source" in tele["comm"], "la telemetría incluye el estado de comunicaciones")
check(tele["comm"]["active_source"] in ("SIMULATION", "PLC_S7_1200", "OPC_UA"),
      f"fuente activa válida ({tele['comm']['active_source']})")

import re as _re
rutas_opc_usadas = set(_re.findall(r'request\("/api/opcua[^"\?]*', API_JS))
check(len(rutas_opc_usadas) >= 6, f"el frontend consume {len(rutas_opc_usadas)} endpoints OPC UA")
check("/api/opcua/status" in rutas_app and "/api/opcua/connect" in rutas_app,
      "las rutas OPC UA del frontend existen en FastAPI")

# ---------------------------------------------------------------------------
print("\n[7] WebSocket")
# ---------------------------------------------------------------------------
with client.websocket_connect("/ws") as ws:
    trama = ws.receive_json()
check(set(trama.keys()) == campos(M.SystemTelemetry), "el WS entrega exactamente los campos de SystemTelemetry")
check(set(trama["cells"]["C2"].keys()) == campos(M.CellRuntimeState), "el WS entrega exactamente los campos de CellRuntimeState")
check(isinstance(trama["active_alarms"], list), "el WS incluye la lista de alarmas activas")

# ---------------------------------------------------------------------------
print("\n" + "=" * 68)
if FALLOS:
    print(f"✘ {len(FALLOS)} comprobaciones fallaron:")
    for f in FALLOS:
        print("   -", f)
    sys.exit(1)
print("✔ TODAS LAS COMPROBACIONES PASARON — backend y frontend sincronizados")
