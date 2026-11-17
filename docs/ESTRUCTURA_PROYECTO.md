# Estructura del proyecto S_C_PID

```text
flotation-scada/
├── backend/
│   ├── api/
│   │   ├── dependencies.py
│   │   ├── schemas.py
│   │   └── routes/             # REST, WebSocket y dashboard por dominio
│   ├── core/
│   │   └── runtime.py          # composición y ciclo de vida de recursos
│   ├── services/               # lógica de aplicación y fuentes industriales
│   ├── main.py                  # composición FastAPI; sin endpoints de dominio
│   ├── settings.py              # configuración .env
│   ├── models.py                # contratos Pydantic
│   ├── controller.py            # control PI + Feedforward
│   ├── process_model.py         # modelo dinámico y alarmas
│   ├── historian.py             # persistencia SQLite
│   ├── opcua_client.py          # cliente OPC UA
│   └── plc_s7.py                # cliente Snap7 y mapa DB100
├── frontend/                    # HTML, CSS, JavaScript y vendor
├── plc_s7_1200/                 # fuentes SCL para TIA Portal V17
├── tests/                       # pruebas unitarias, integración y contrato
├── tools/                       # sincronización de contrato
├── docs/                         # auditoría, fases y contratos
└── data/                         # histórico SQLite local y certificados
```

## Dependencias de runtime

`backend/core/runtime.py` compone los objetos de proceso, histórico y comunicación.
FastAPI publica esa instancia en `app.state.runtime`. Los routers acceden a ella por
`Depends(get_runtime)` en `backend/api/dependencies.py`; no importan globals de
`backend.main`.

`backend/main.py` registra middleware y routers y controla el lifespan. Los módulos
`backend/api/routes/` conservan los paths públicos del dashboard.

## Fuentes industriales

`SIMULATION` es la única fuente que avanza el modelo local. `OPC_UA` actualiza el
proceso con muestras recibidas del servidor. `PLC_S7_1200` no fabrica telemetría y
permanece pendiente de adquisición cíclica validada.

La documentación de ingeniería y diagramas de la Fase 7 permanece condicionada a la
aprobación técnica de la Fase 6.
