# Informe de correcciones y pruebas — S_C_PID

Fecha de ejecución: 2026-11-16  
Base: `S_C_PID(1).zip`  
Configuración solicitada: OPC UA / Siemens S7-1200 CPU 1214C / entorno SIM + PLCSIM.

## Cambios aplicados

1. **Rutas portables**
   - `backend/main.py` resuelve `BASE_DIR` desde la ubicación del módulo.
   - `backend/historian.py` resuelve la base SQLite desde el proyecto.
   - Se admite `SCADA_DB_PATH` para aislar datos por entorno.
   - Se eliminó la ruta absoluta obsoleta del README.

2. **Separación de fuentes de datos**
   - `SIMULATION`: ejecuta `process.step()`.
   - `OPC_UA`: usa la adquisición OPC UA y no ejecuta el modelo simulado.
   - `PLC_S7_1200`: no simula silenciosamente mientras no exista adquisición cíclica DB100 mediante Snap7.
   - El historiador registra datos externos sólo cuando hay una muestra OPC UA completa y fresca.

3. **Integridad de adquisición OPC UA**
   - Las lecturas parciales de nodos se descartan como muestra.
   - La conexión inicial exige que el mapa de lectura completo esté disponible.
   - Se agregó validación de endpoint `opc.tcp://`, puerto y limpieza de sesión ante fallos.
   - Se corrigió la reconexión para evitar adquirir dos veces el mismo `asyncio.Lock`.

4. **Protección de escrituras**
   - Las escrituras OPC UA están deshabilitadas por defecto.
   - Para habilitarlas se requiere `SCADA_ENABLE_CONTROL_WRITES=true`.
   - Se validan tipos Boolean estrictos y rangos de SP, RPM, Kp, Ki y Kff.
   - La interfaz API rechaza por defecto la escritura con HTTP 403.

5. **Entorno y arranque**
   - Se agregó `requirements.txt`.
   - `run.sh` instala desde ese archivo.
   - El servidor se enlaza por defecto a `127.0.0.1`, no a todas las interfaces.
   - Se restringió CORS a orígenes locales configurables.
   - El servidor OPC UA de prueba, cuando asyncua está instalado, escucha sólo en localhost.

6. **Pruebas**
   - Se agregó `tests/test_runtime_safety.py` con pruebas de separación de fuentes, validación de escritura y endpoint OPC UA.
   - Se conservaron los contratos y artefactos generados existentes.

## Resultados ejecutados

| Verificación | Resultado |
|---|---|
| `compileall` backend/tests/tools | PASS |
| Pytest | 8 passed |
| `tools/sync_contract.py --check` | PASS |
| `tests/test_contract_sync.py` directo | PASS |
| `node --check` api.js | PASS |
| `node --check` app.js | PASS |
| `node --check` charts.js | PASS |
| `node --check` contract.generated.js | PASS |
| Smoke test FastAPI + dashboard + WebSocket | PASS |
| SQLite `PRAGMA integrity_check` | `ok` |
| Registros históricos originales | 823 |

## Limitaciones que permanecen

- En el entorno de auditoría no está instalado `asyncua` ni hay acceso a Internet para instalarlo. Por tanto, no se pudo levantar aquí el servidor OPC UA de prueba ni completar un ciclo cliente-servidor OPC UA real.
- No se dispone de TIA Portal, PLCSIM/PLCSIM Advanced ni CPU física 1214C en este entorno. No se certifica conexión con PLC, NodeIds reales, firmware, seguridad OPC UA ni escritura de salidas.
- Snap7 continúa sin adquisición/escritura cíclica DB100. El modo `PLC_S7_1200` no debe utilizarse para control.
- La autenticación y autorización de usuarios/roles no están implementadas en esta fase. El binding local y el bloqueo por defecto de escrituras reducen exposición, pero no sustituyen un sistema de seguridad industrial.
- Las escrituras no deben habilitarse en producción sólo por configurar la variable de entorno. Primero deben implantarse autenticación/autorización, certificados OPC UA, revisión de interbloqueos, límites de proceso y pruebas de aceptación.

## Conclusión

La versión corregida supera las pruebas automatizadas locales y la verificación de contrato. La separación SIMULATION/OPC_UA evita que el modelo hidráulico sobrescriba mediciones externas. La integración OPC UA real con PLCSIM y CPU 1214C permanece pendiente de validación en un entorno que disponga de `asyncua`, TIA Portal y un servidor OPC UA activo.

Este informe no constituye certificación de seguridad funcional ni autorización para controlar equipos físicos.


## Anexo — Fase 3 DB100 v2

Se implementó el mapa DB100 v2 con 39 tags y 122 bytes de imagen, se sincronizaron los mapas OPC UA/Snap7, se separó RPM_SP de RPM_PV y se agregaron lectura de imagen y escritura Snap7 restringida. Se ejecutaron 19 pruebas automatizadas de DB100 v2 y seguridad/runtime, todas aprobadas. La aceptación con TIA Portal/PLCSIM permanece pendiente. Ver `docs/phase-3/FASE3_IMPLEMENTACION_DB100_V2.md` para mapa, pruebas y procedimiento de aceptación.
