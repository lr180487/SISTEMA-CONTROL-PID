# Fase 3 — Implementación DB100 v2 y pruebas de comunicación

Fecha: 2026-11-16  
Proyecto: S_C_PID — Siemens S7-1200 CPU 1214C  
Protocolo principal: OPC UA  
Entorno objetivo: TIA Portal + S7-PLCSIM  
Hardware analógico: referencias aún no identificadas.

## 1. Cambios implementados

- Se amplió `DB100_FlotationSCADA` a versión 2 conservando las direcciones previas de 0 a 76.5.
- Los tags heredados `C1_Pump_RPM`, `C2_Pump_RPM`, `C3_Pump_RPM` se documentan como consignas RPM_SP para compatibilidad.
- Se separaron velocidades medidas: `C1_Pump_RPM_PV` DBD80, `C2_Pump_RPM_PV` DBD84, `C3_Pump_RPM_PV` DBD88.
- Se agregaron salidas calculadas PI+FF: DBD92, DBD96 y DBD100.
- Diagnóstico: contador DBD104, heartbeat DBX108.0, datos válidos DBX108.1, fallo DBX108.2 y versión DBD112.
- Se agregaron salidas analógicas escaladas INT en DBW116, DBW118 y DBW120. El tamaño mínimo del DB para la imagen de lectura es 122 bytes.
- Se añadieron bytes de reserva explícitos 77–79 y 109–111 en la declaración SCL para mantener alineación de offsets.
- Se sincronizaron los mapas OPC UA y Snap7. Ambos contienen 39 tags con las mismas direcciones DB.
- Se corrigió el puente de telemetría: el RPM real del proceso se toma de `*_Pump_RPM_PV`; `*_Pump_RPM` permanece como consigna.
- Snap7 ahora implementa lectura de imagen DB100 y escritura individual restringida a SP, RPM_SP, Kp, Ki, Kff y BOOL de modo/FF. No permite escribir PV, salidas ni diagnóstico.
- OPC UA permanece como canal principal y conserva la escritura deshabilitada por defecto.

## 2. Mapa DB100 v2

| Dirección | Tag | Tipo | Permiso |
|---|---|---|---|
| DBD0 | Q_Feed_LPM | REAL | R |
| DBD4/28/52 | C1/C2/C3_PV_mm | REAL | R |
| DBD8/32/56 | C1/C2/C3_SP_mm | REAL | R/W |
| DBD12/36/60 | C1/C2/C3_Pump_RPM (SP) | REAL | R/W |
| DBD16/20/24; 40/44/48; 64/68/72 | Kp/Ki/Kff por celda | REAL | R/W |
| DBX76.0–76.5 | AUTO y FF por celda | BOOL | R/W |
| DBD80/84/88 | C1/C2/C3_Pump_RPM_PV | REAL | R |
| DBD92/96/100 | C1/C2/C3_Output_RPM | REAL | R |
| DBD104 | PLC_CycleCounter | DWORD | R |
| DBX108.0/.1/.2 | PLC_Heartbeat/DataValid/Fault | BOOL | R |
| DBD112 | DB_Version = 2 | DWORD | R |
| DBW116/118/120 | C1/C2/C3_Output_AQ | INT | R |

## 3. Escalamiento analógico

La salida del FB PI+FF utiliza la escala nominal 0–350 RPM → 0–27648 cuentas. La relación es lineal y debe saturarse al rango permitido. Las palabras `C1_Output_AQ`, `C2_Output_AQ`, `C3_Output_AQ` reservan el intercambio de los valores escalados.

**No se asignaron direcciones `%IW` ni `%QW`.** El usuario indicó que el hardware analógico es desconocido. Antes de enlazar esas palabras con módulos físicos, se deben obtener las referencias exactas de CPU/módulos, canales, tipo de señal (0–10 V o 4–20 mA), rangos configurados y direcciones de hardware en TIA Portal.

## 4. Política de propiedad y seguridad

- PV, RPM real, salidas PI+FF y diagnóstico: sólo PLC escribe.
- SP, RPM_SP, Kp, Ki, Kff, AUTO y FF: SCADA puede solicitar cambios mediante el canal OPC UA, sujetos a validación y permisos.
- Snap7 se mantiene complementario/diagnóstico; no debe convertirse en segundo escritor simultáneo de los mismos tags.
- El PLC conserva la decisión final sobre límites, interbloqueos, estados de marcha y salidas físicas.
- `SCADA_ENABLE_CONTROL_WRITES=false` permanece como valor predeterminado.

## 5. Pruebas ejecutadas

| Prueba | Resultado |
|---|---|
| Compilación Python `compileall` | PASS |
| Decodificación REAL Siemens big-endian | PASS |
| Decodificación BOOL y DWORD | PASS |
| Lectura simulada completa de DB100 de 122 bytes | PASS |
| Escritura simulada REAL en offset correcto | PASS |
| Escritura BOOL preservando bits vecinos | PASS |
| Rechazo de tags de sólo lectura | PASS |
| Rechazo de SP fuera de rango | PASS |
| Consistencia de 39 tags OPC UA y Snap7 | PASS |
| Separación RPM_SP vs RPM_PV en telemetría | PASS |
| Pruebas DB100 v2 + seguridad/runtime | 19 passed |
| Contrato API/frontend | PASS |
| `tools/sync_contract.py --check` | PASS |

Las pruebas Snap7 utilizan un transporte falso en memoria. Validan offsets, codificación y reglas de acceso, pero no equivalen a comunicación con un PLC.

## 6. Pendiente para aceptación en PLCSIM

1. Importar/compilar el SCL en la versión concreta de TIA Portal.
2. Confirmar el layout real de DB100 con la vista de offsets de TIA Portal; comprobar especialmente los bytes de reserva y el tamaño de 122 bytes.
3. Instanciar `FB_DB100_Diagnostics_500ms` desde OB30 con periodo de 500 ms.
4. Integrar las instancias del controlador PI+FF y asignar las señales PV/caudal ya escaladas. Esta asignación aún no está conectada porque no se conocen los módulos analógicos.
5. Descargar a PLCSIM y verificar que DB_Version=2, PLC_CycleCounter incrementa y PLC_Heartbeat conmuta.
6. Configurar el servidor OPC UA del PLC/PLCSIM, confirmar URI de namespace y NodeIds reales; leer los 39 tags sin lecturas parciales.
7. Probar escritura de SP/RPM_SP sólo en entorno de simulación, con control de escritura habilitado temporalmente y después volver a deshabilitarlo.
8. Simular pérdida de conexión y comprobar que la muestra se invalida y no se sustituye por el modelo local.

## 7. Estado

**Implementación de software DB100 v2: completada y probada con pruebas automatizadas locales.**  
**Aceptación TIA Portal/PLCSIM: pendiente.** No se dispone de TIA Portal, PLCSIM ni librerías asyncua/python-snap7 instaladas en el entorno de ejecución actual. No se declara compilación SCL ni comunicación PLC real. La Fase 3 no debe marcarse como aprobada hasta cerrar la lista de aceptación anterior.
