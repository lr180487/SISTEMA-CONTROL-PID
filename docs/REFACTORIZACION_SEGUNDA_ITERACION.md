# Refactorización S_C_PID — Segunda iteración

## Objetivo

Separar los endpoints REST y WebSocket por dominio, centralizar las dependencias
operativas en `Runtime` y reducir `backend/main.py` a punto de composición FastAPI.
Se conserva el contrato público del dashboard, la versión de esquema `1.2.0`, los
paths REST y el WebSocket `/ws`.

## Nueva organización

```text
backend/
├── api/
│   ├── dependencies.py
│   ├── schemas.py
│   └── routes/
│       ├── system.py
│       ├── cells.py
│       ├── historian.py
│       ├── plc.py
│       ├── opcua.py
│       ├── websocket.py
│       └── dashboard.py
├── core/
│   └── runtime.py
├── services/
│   └── data_sources.py
├── main.py
├── settings.py
├── models.py
├── controller.py
├── process_model.py
├── historian.py
├── opcua_client.py
└── plc_s7.py
```

## Responsabilidades

- `main.py`: crea FastAPI, instala middleware, incluye routers y gestiona lifespan.
- `core/runtime.py`: compone proceso, histórico, clientes industriales, servicio de
  fuentes y concentrador WebSocket; inicia y cierra recursos.
- `api/dependencies.py`: proporciona `Runtime` desde `app.state` mediante Depends.
- `api/schemas.py`: modelos HTTP auxiliares que no pertenecen al contrato del dashboard.
- `api/routes/system.py`: `/api/state`, `/api/health`, `/api/config`, `/api/meta`.
- `api/routes/cells.py`: celdas, alimentación, acciones y alarmas.
- `api/routes/historian.py`: consulta, borrado y exportación CSV.
- `api/routes/plc.py`: estado/configuración/conexión Snap7 y descarga SCL.
- `api/routes/opcua.py`: conexión, tags, browse, escritura protegida y servidor de prueba.
- `api/routes/websocket.py`: `/ws` y gestión de conexiones mediante `WebSocketHub`.
- `api/routes/dashboard.py`: página de entrada del dashboard.

## Compatibilidad

Las rutas y métodos HTTP se mantienen. `SCHEMA_VERSION` permanece en `1.2.0`.
`main.py` conserva aliases de compatibilidad para las pruebas históricas, pero los
routers no importan estado desde `main.py`: reciben `Runtime` por inyección de
 dependencias.

La fábrica `create_runtime()` permite construir instancias con proceso y clientes
OPC UA/Snap7 independientes. La instancia asociada a la aplicación se publica en
`app.state.runtime`.

## Seguridad y límites

- Las escrituras OPC UA siguen deshabilitadas por defecto.
- El servidor OPC UA de prueba conserva el binding a `127.0.0.1`.
- La fuente `SIMULATION` es la única que ejecuta `process.step()`.
- OPC UA consume lecturas reales recibidas; Snap7 no se declara fuente cíclica hasta
  implementar y validar el polling industrial.
- La refactorización no certifica comunicación con CPU 1214C ni PLCSIM estándar.

## Validación reproducible

```powershell
python -m compileall -q backend tests tools
python -m pytest -q
python tools/sync_contract.py --check
python tests/contract_sync_check.py
node --check frontend/js/api.js
node --check frontend/js/app.js
node --check frontend/js/charts.js
node --check frontend/js/contract.generated.js
```

Las 28 pruebas preexistentes se mantienen y se agregan pruebas de arquitectura para
routers, runtime, dashboard y WebSocket. La prueba de contrato verifica que el frontend
sigue consumiendo las rutas públicas existentes.
