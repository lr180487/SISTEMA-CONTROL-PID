# Procedimiento de validación — Fase 3 / DB100 v2

**Entorno declarado:** TIA Portal V17 + S7-PLCSIM estándar  
**PLC objetivo:** Siemens S7-1200 CPU 1214C (referencia y firmware aún desconocidos)  
**Canal industrial previsto:** OPC UA principal; Snap7 complementario  
**Alcance de esta prueba:** importación, compilación, layout del DB100, ejecución del diagnóstico y observación de variables en PLCSIM estándar.

> **Limitación importante del simulador:** S7-PLCSIM V17 estándar utiliza Softbus. No proporciona el canal TCP/IP/OPC UA del simulador avanzado. Por tanto, con este entorno se puede validar lógica y variables desde TIA Portal, pero no se puede declarar aprobada la conexión del backend Python por OPC UA ni Snap7 TCP/IP. Para esas pruebas se requiere una CPU física o un simulador compatible con TCP/IP, como S7-PLCSIM Advanced de una versión compatible.

## 1. Resultado de auditoría estática previo

- El archivo SCL declara `DB100_FlotationSCADA` con los campos DB100 v2.
- El mapa de backend contiene 39 tags y los tests locales verifican offsets y codificación.
- El tamaño mínimo esperado para la imagen DB es 122 bytes.
- El bloque `FB_DB100_Diagnostics_500ms` está declarado, pero el archivo SCL no contiene un OB30 ni una llamada a dicho FB. Esa llamada debe agregarse en TIA Portal.
- El bloque `FB_LevelControl_PI_FF` está declarado, pero no hay tres instancias de control conectadas al DB100. Esta prueba no valida el lazo PI+FF ni salidas físicas.
- No se conocen los módulos analógicos. No asignar `%IW`/`%QW` ni cablear `Output_AQ` a hardware.
- La línea de conversión analógica del FB debe revisarse antes de ejecución con valores de `RPM_Max` inválidos: `RPM_Max` debe ser mayor que cero. No habilitar control físico en esta etapa.

## 2. Preparación

1. Crear una copia de seguridad del proyecto TIA Portal.
2. Abrir TIA Portal V17 y crear un proyecto nuevo, por ejemplo `S_C_PID_V17_DB100_TEST`.
3. En el catálogo de hardware, seleccionar una CPU S7-1200 CPU 1214C con una referencia y versión de dispositivo que aparezcan como soportadas por la instalación V17/PLCSIM disponible.
4. No adivinar la referencia física. Si el destino final es un PLC real, copiar la referencia `6ES7...` de la etiqueta lateral de la CPU y comprobar el firmware con el diagnóstico online del equipo.
5. Para una prueba puramente de DB, no configurar módulos AI/AQ ni direcciones físicas.
6. Abrir S7-PLCSIM estándar V17 y comprobar que está disponible para iniciar una instancia desde TIA Portal.

## 3. Importación del SCL

Archivo fuente:

`plc_s7_1200/FB_PI_Feedforward_S7_1200.scl`

Pasos:

1. En el árbol del proyecto, abrir **External source / Fuentes externas**.
2. Agregar el archivo SCL anterior.
3. Abrir la fuente y revisar que no haya caracteres dañados ni líneas truncadas.
4. Ejecutar **Generate blocks from source / Generar bloques desde fuente**.
5. Si hay errores, no descargar ni intentar corregir offsets a mano. Guardar el texto completo del primer error y la línea señalada.
6. Revisar en el árbol de bloques que aparezcan `DB100_FlotationSCADA`, `FB_LevelControl_PI_FF` y `FB_DB100_Diagnostics_500ms`.
7. Compilar el software del PLC y conservar el resultado de compilación.

La importación/compilación real solo se considera PASS cuando TIA Portal V17 la termina sin errores. La compilación Python y los tests locales no sustituyen este paso.

## 4. Verificación de layout DB100

Abrir `DB100_FlotationSCADA` en la vista de declaración/offsets. Confirmar acceso no optimizado y comparar:

| Dirección esperada | Campo | Tipo |
|---|---|---|
| DBD0 | Q_Feed_LPM | REAL |
| DBD4 / DBD28 / DBD52 | C1/C2/C3_PV_mm | REAL |
| DBD8 / DBD32 / DBD56 | C1/C2/C3_SP_mm | REAL |
| DBD12 / DBD36 / DBD60 | C1/C2/C3_Pump_RPM | REAL |
| DBD16–DBD72 | Kp/Ki/Kff por celda | REAL |
| DBX76.0–DBX76.5 | AUTO y FF por celda | BOOL |
| DBD80 / 84 / 88 | C1/C2/C3_Pump_RPM_PV | REAL |
| DBD92 / 96 / 100 | C1/C2/C3_Output_RPM | REAL |
| DBD104 | PLC_CycleCounter | DWORD |
| DBX108.0 / .1 / .2 | Heartbeat / DataValid / Fault | BOOL |
| DBD112 | DB_Version | DWORD |
| DBW116 / 118 / 120 | C1/C2/C3_Output_AQ | INT |

**Criterio de aceptación:** `DB_Version` en DBD112; tres `Output_AQ` en DBW116, DBW118 y DBW120; longitud mínima 122 bytes; todos los offsets coinciden exactamente. Si TIA Portal presenta cualquier desplazamiento, detener la prueba y reconciliar SCL, DB y mapas Python.

## 5. Agregar OB30 de diagnóstico

El fuente SCL declara el FB de diagnóstico, pero no lo llama. Agregar un OB de interrupción cíclica OB30:

1. Agregar un nuevo bloque de organización de tipo **Cyclic interrupt** y asignar el número OB30 si está disponible.
2. Configurar intervalo de 500 ms.
3. Insertar una llamada a `FB_DB100_Diagnostics_500ms`.
4. Crear/asignar un DB de instancia cuando TIA Portal lo solicite.
5. Compilar nuevamente.

No agregar aún las instancias PI+FF ni conectar salidas a hardware. La prueba actual solo confirma ejecución del bloque de diagnóstico y DB.

## 6. Descargar y ejecutar en PLCSIM estándar

1. Iniciar PLCSIM desde TIA Portal.
2. Seleccionar la instancia de CPU simulada.
3. Descargar el proyecto.
4. Poner la CPU simulada en RUN.
5. Abrir una Watch table y agregar los tags indicados abajo.
6. Observar durante al menos 30 segundos.

| Variable | Resultado esperado |
|---|---|
| DB100.DB_Version | 2 |
| DB100.PLC_CycleCounter | Incrementa aproximadamente cada 500 ms |
| DB100.PLC_Heartbeat | Alterna TRUE/FALSE aproximadamente cada 500 ms |
| DB100.PLC_DataValid | TRUE con PV iniciales dentro de 0–500 mm |
| DB100.PLC_Fault | FALSE con PV iniciales dentro de rango |

Si `PLC_CycleCounter` no incrementa, verificar OB30, su intervalo, la llamada al FB y el estado RUN. Si `PLC_DataValid` queda FALSE, revisar las tres PV y sus rangos.

## 7. Pruebas funcionales DB100 en PLCSIM

Realizar únicamente con CPU simulada y sin salidas físicas conectadas:

| ID | Acción | Resultado esperado |
|---|---|---|
| SIM-DB-01 | Leer DB_Version | 2 |
| SIM-DB-02 | Observar CycleCounter 10 s | Incrementa; no queda congelado |
| SIM-DB-03 | Observar Heartbeat | Alterna estados |
| SIM-DB-04 | Escribir C1_PV_mm = 330.0 | DataValid permanece TRUE |
| SIM-DB-05 | Escribir temporalmente C1_PV_mm = 501.0 | DataValid FALSE y PLC_Fault TRUE |
| SIM-DB-06 | Restaurar C1_PV_mm = 330.0 | DataValid TRUE y PLC_Fault FALSE |
| SIM-DB-07 | Verificar C1_Output_AQ/C2/C3 | Permanecen valores iniciales hasta que exista lógica explícita de cálculo/asignación |

Restaurar todos los PV a valores válidos al finalizar. No usar escrituras del SCADA para estas pruebas; usar Watch table en el entorno aislado.

## 8. Alcance OPC UA y Snap7 en el simulador declarado

Con S7-PLCSIM estándar V17:

- PASS posible: compilación, descarga, RUN, DB y diagnóstico por Watch table.
- NO APLICA / BLOQUEADO: conexión OPC UA del backend por `opc.tcp://...:4840` a la instancia estándar.
- NO APLICA / BLOQUEADO: conexión Snap7 del backend por TCP/102 a la instancia estándar.

No cambiar `SCADA_DATA_SOURCE` ni activar escritura de control para intentar forzar comunicación. Mantener `SCADA_ENABLE_CONTROL_WRITES=false`.

Para la siguiente prueba de protocolo, usar una CPU física aislada o confirmar disponibilidad/licencia/compatibilidad de S7-PLCSIM Advanced con TCP/IP y OPC UA. Después se descubrirán los NodeId reales del servidor y se verificará cada tag habilitado en la interfaz OPC UA de TIA Portal. No asumir que el namespace index ni los NodeId de ejemplo del backend son los definitivos.

## 9. Evidencias que debe guardar el usuario

1. Captura del dispositivo CPU y versión seleccionada en TIA Portal.
2. Captura de compilación sin errores.
3. Captura de DB100 mostrando offsets y acceso no optimizado.
4. Captura del OB30 con intervalo de 500 ms y llamada al FB.
5. Captura de PLCSIM con CPU en RUN.
6. Captura de Watch table con versión, contador, heartbeat y estados DataValid/Fault.
7. Captura de SIM-DB-05 y SIM-DB-06.

## 10. Registro de resultado

Completar después de ejecutar en el PC del usuario:

| Comprobación | Estado | Evidencia |
|---|---|---|
| Importación SCL | Pendiente | Captura/errores |
| Compilación TIA V17 | Pendiente | Resultado compilador |
| Layout DB100 = 122 bytes | Pendiente | Captura offsets |
| OB30 500 ms | Pendiente | Captura bloque |
| CPU PLCSIM en RUN | Pendiente | Captura estado |
| Heartbeat/contador | Pendiente | Watch table |
| DataValid/Fault | Pendiente | Watch table |
| OPC UA backend | Bloqueado en PLCSIM estándar | Requiere TCP/IP compatible |
| Snap7 backend | Bloqueado en PLCSIM estándar | Requiere TCP/IP compatible |

**Criterio final:** la validación DB100 v2 en PLCSIM estándar se aprueba únicamente al completar las pruebas SIM-DB-01 a SIM-DB-06 y adjuntar evidencias. La Fase 3 industrial completa sigue abierta hasta validar OPC UA y Snap7 con un endpoint de red real/simulado compatible.
