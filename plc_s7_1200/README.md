# Fuentes PLC S7-1200

Esta carpeta contiene fuentes SCL para importar en TIA Portal V17.

1. Añadir el archivo `.scl` como fuente externa (External source).
2. Generar los bloques desde la fuente.
3. Compilar y revisar todos los errores y advertencias.
4. Verificar el DB100 y sus offsets en TIA Portal; no asumir que el tamaño declarado por el backend demuestra el layout compilado.
5. No conectar salidas físicas ni habilitar escrituras SCADA hasta completar validaciones e interbloqueos.

El hardware analógico y la referencia/firmware exactos de CPU siguen pendientes de identificación.
