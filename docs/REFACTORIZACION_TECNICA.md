# Refactorización técnica S_C_PID

## Objetivo

Separar responsabilidades internas sin cambiar el contrato REST/WebSocket ni alterar
el comportamiento visible del dashboard. Esta iteración es una refactorización
incremental: no reescribe el controlador PI+FF ni modifica las direcciones del DB100 v2.

## Cambios realizados

1. `backend/settings.py`
   - Centraliza la carga de `.env` desde la raíz del proyecto.
   - Centraliza rutas `frontend/` y el archivo SCL.
   - Normaliza booleanos, enteros y flotantes de configuración.
   - Mantiene escrituras OPC UA deshabilitadas por defecto.
   - Centraliza orígenes CORS.

2. `backend/services/data_sources.py`
   - Encapsula el mapa OPC UA -> celdas.
   - Encapsula la aplicación de valores de PLC a telemetría.
   - Encapsula la sincronización de consignas permitidas.
   - Encapsula la selección de fuente activa.
   - Mantiene la regla de que solo SIMULATION ejecuta `process.step()`.
   - OPC UA actualiza el proceso únicamente a partir de lecturas recibidas.
   - Snap7 no produce muestras hasta contar con adquisición cíclica implementada.

3. `backend/main.py`
   - Conserva composición de FastAPI, ciclo de vida, REST y WebSocket.
   - Delega la lógica de fuentes al servicio.
   - Conserva wrappers de compatibilidad para no romper pruebas existentes.
   - Sustituye `print` del ciclo SCADA por logging estructurado mediante `logging`.
   - Elimina una asignación duplicada del payload de actualización de celda.

4. `backend/models.py`
   - Usa `default_factory` para listas de respuesta, evitando defaults mutables compartidos.

5. Pruebas
   - Añade pruebas unitarias independientes para selección de fuentes, no simulación
     en modo industrial y política de escritura OPC UA.

## Límites deliberados

- No se alteraron las rutas HTTP ni el WebSocket `/ws`.
- No se modificó `SCHEMA_VERSION` porque no cambió el contrato.
- No se renombraron tags DB100 ni se cambiaron offsets.
- No se habilitaron escrituras de control por defecto.
- No se afirma integración física PLC: PLCSIM estándar V17 no sustituye una prueba
  OPC UA/Snap7 TCP/IP con un runtime compatible o CPU real.
- Las rutas permanecen concentradas en `main.py` en esta iteración para minimizar
  riesgo de regresión. Una extracción posterior a routers por dominio debe realizarse
  conservando las mismas rutas y verificando el contrato automáticamente.

## Validación reproducible

Resultados ejecutados después de los cambios:

- `python -m compileall -q backend tests tools`: PASS.
- `python -m pytest -q`: 28 passed.
- `python tools/sync_contract.py --check`: PASS.
- `python tests/contract_sync_check.py`: todas las comprobaciones PASS.

La validación no incluye TIA Portal, PLCSIM, hardware S7-1200 ni servidor OPC UA Siemens.

## Evolución posterior: segunda iteración

La extracción de routers descrita como pendiente en esta primera iteración se completó
posteriormente. Consultar `docs/REFACTORIZACION_SEGUNDA_ITERACION.md` para la estructura
actual, inyección de `Runtime`, paths preservados y resultados de la nueva línea de pruebas.
