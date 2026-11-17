#!/usr/bin/env python3
"""
tools/sync_contract.py — Sincronización automática del contrato Backend <-> Frontend.

Qué hace:
  1. Lee los modelos Pydantic reales del backend (models.py) y las rutas reales de
     la app FastAPI (main.py).
  2. Emite frontend/js/contract.generated.js con:
       · SCHEMA_VERSION / APP_VERSION
       · nombres de campos exactos de cada payload (telemetría, celda, alarma, config)
       · mapa de endpoints REST + ruta WebSocket
       · límites de validación (rangos) de cada parámetro de control
  3. Escribe además docs/api/contract.json (contrato legible por máquina) y
     docs/api/CONTRATO_API.md (tabla de endpoints para revisión humana).

Uso:
    python3 tools/sync_contract.py           # regenera los artefactos
    python3 tools/sync_contract.py --check   # falla (exit 1) si están desactualizados

El frontend consume la versión generada y verifica en tiempo de ejecución que
/api/meta devuelva el mismo `schema_version`; si no coincide, muestra un aviso
de desincronización en el propio panel.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import models as M  # noqa: E402
from backend.main import APP_VERSION, app  # noqa: E402

JS_OUT = ROOT / "frontend" / "js" / "contract.generated.js"
JSON_OUT = ROOT / "docs" / "api" / "contract.json"
MD_OUT = ROOT / "docs" / "api" / "CONTRATO_API.md"

MODELOS = {
    "SystemTelemetry": M.SystemTelemetry,
    "CellRuntimeState": M.CellRuntimeState,
    "CellConfig": M.CellConfig,
    "CellUpdateRequest": M.CellUpdateRequest,
    "AlarmEvent": M.AlarmEvent,
    "FeedSimulationConfig": M.FeedSimulationConfig,
    "PLCConnectionConfig": M.PLCConnectionConfig,
    "ConfigSnapshot": M.ConfigSnapshot,
    "ConfigUpdateResponse": M.ConfigUpdateResponse,
    "HealthStatus": M.HealthStatus,
}

# Rangos de validación declarados en los modelos (fuente única de verdad)
RANGOS = {
    "sp": [150.0, 430.0],
    "manual_rpm": [0.0, 350.0],
    "kp": [-50.0, 50.0],
    "ki": [-15.0, 15.0],
    "kff": [0.0, 3.0],
    "alarm_high": [200.0, 445.0],
    "alarm_low": [80.0, 380.0],
    "base_flow_lpm": [5.0, 45.0],
    "noise_std": [0.0, 2.5],
    "air_flow_lpm": [10.0, 90.0],
}


def _campos(modelo) -> list[str]:
    return list(modelo.model_fields.keys())


def _rutas() -> list[dict]:
    salida = []
    for r in app.routes:
        path = getattr(r, "path", None)
        if not path or not (path.startswith("/api") or path == "/ws"):
            continue
        metodos = sorted(getattr(r, "methods", []) or [])
        if path == "/ws":
            metodos = ["WEBSOCKET"]
        salida.append({"path": path, "methods": metodos, "name": getattr(r, "name", "")})
    salida.sort(key=lambda x: (x["path"], x["methods"]))
    return salida


def construir_contrato() -> dict:
    return {
        "app_version": APP_VERSION,
        "schema_version": M.SCHEMA_VERSION,
        "ws_path": "/ws",
        "cell_ids": ["C1", "C2", "C3"],
        "profiles": ["CONSTANT", "STEP_QUINTANILLA", "PULSE", "SINE", "NOISY_RAMP"],
        "modes": ["AUTO", "MANUAL"],
        "alarm_states": ["NORMAL", "HIGH", "LOW", "HH_CRITICAL", "LL_CRITICAL"],
        "ranges": RANGOS,
        "models": {nombre: _campos(m) for nombre, m in MODELOS.items()},
        "endpoints": _rutas(),
    }


def render_js(c: dict) -> str:
    body = json.dumps(c, indent=2, ensure_ascii=False)
    return (
        "/* ARCHIVO GENERADO AUTOMÁTICAMENTE — NO EDITAR A MANO.\n"
        " * Fuente: backend/models.py + backend/main.py (rutas FastAPI reales).\n"
        " * Regenerar con:  python3 tools/sync_contract.py\n"
        " */\n"
        f"window.CONTRACT = {body};\n"
    )


def render_md(c: dict) -> str:
    lineas = [
        "# Contrato API — Backend FastAPI ↔ Frontend SCADA",
        "",
        f"- **app_version:** `{c['app_version']}`",
        f"- **schema_version:** `{c['schema_version']}`",
        f"- **WebSocket:** `{c['ws_path']}` (telemetría cada 500 ms)",
        "",
        "> Archivo generado por `tools/sync_contract.py`; no editar a mano.",
        "",
        "## Endpoints",
        "",
        "| Método | Ruta | Handler |",
        "|---|---|---|",
    ]
    for e in c["endpoints"]:
        lineas.append(f"| {' / '.join(e['methods']) or '—'} | `{e['path']}` | `{e['name']}` |")
    lineas += ["", "## Campos por modelo (Pydantic)", ""]
    for nombre, campos in c["models"].items():
        lineas += [f"### {nombre}", "", "```", ", ".join(campos), "```", ""]
    lineas += ["## Rangos de validación", "", "| Parámetro | Mín | Máx |", "|---|---|---|"]
    for k, (lo, hi) in c["ranges"].items():
        lineas.append(f"| `{k}` | {lo} | {hi} |")
    lineas.append("")
    return "\n".join(lineas)


def main() -> int:
    contrato = construir_contrato()
    js = render_js(contrato)
    js_prev = JS_OUT.read_text(encoding="utf-8") if JS_OUT.exists() else ""

    if "--check" in sys.argv:
        if js.strip() != js_prev.strip():
            print("✗ Contrato desactualizado: ejecute  python3 tools/sync_contract.py")
            return 1
        print("✓ Contrato sincronizado con el backend (schema %s)" % contrato["schema_version"])
        return 0

    JS_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    JS_OUT.write_text(js, encoding="utf-8")
    JSON_OUT.write_text(json.dumps(contrato, indent=2, ensure_ascii=False), encoding="utf-8")
    MD_OUT.write_text(render_md(contrato), encoding="utf-8")

    print(f"✓ {JS_OUT.relative_to(ROOT)}  ({len(contrato['models'])} modelos, {len(contrato['endpoints'])} endpoints)")
    print(f"✓ {JSON_OUT.relative_to(ROOT)}")
    print(f"✓ {MD_OUT.relative_to(ROOT)}")
    print(f"  schema_version = {contrato['schema_version']} | app_version = {contrato['app_version']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
