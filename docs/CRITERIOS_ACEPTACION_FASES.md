# Criterios de aceptación del proyecto S_C_PID

## Fase 1 — Backend
- Rutas y módulos organizados.
- Configuración mediante `.env`.
- Persistencia SQLite y rutas portables.
- Gestión de excepciones y registros.

## Fase 2 — Fuentes industriales
- SIMULATION genera telemetría simulada.
- OPC UA recibe datos del servidor PLC.
- Snap7 utiliza su propio canal de comunicación.
- Ninguna fuente debe generar datos simulados cuando está seleccionada una fuente industrial.

## Fase 3 — Integración PLC
- Definir mapa de variables del DB100.
- Establecer tipos de datos, direcciones y escalamiento.
- Implementar lectura cíclica y validación de calidad de datos.
- Implementar escritura controlada con límites e interbloqueos.
- Verificar comunicación con SIM_PLC y posteriormente con CPU 1214C.

## Fase 4 — Seguridad
- Autenticación y autorización por roles.
- Validación de rangos y tipos.
- Interbloqueos de operación.
- Protección de escrituras y registro de auditoría.

## Fase 5 — Pruebas
- Pruebas unitarias.
- Pruebas de API REST.
- Pruebas WebSocket.
- Pruebas de simulación.
- Pruebas de comunicación OPC UA.
- Pruebas de integración Snap7.

## Fase 6 — Aprobación técnica
Segunda auditoría con resultados reproducibles, evidencias, errores encontrados y correcciones. No se considera validada la integración física sin pruebas reales en el hardware correspondiente.

## Fase 7 — Ingeniería documental
Solo comienza después de aprobar las fases anteriores. Incluye arquitectura, diagramas de funcionamiento, UML, secuencia, actividades, modelo entidad-relación, esquema físico, endpoints, contratos y documentación de variables PLC/DB100.

## Regla de aprobación
Ninguna fase se declara aprobada por inferencia o por compilación aislada: cada criterio necesita evidencia reproducible.
