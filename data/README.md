# Datos locales

`flotation_historian.db` es el histórico SQLite local. Se conserva en el paquete de trabajo para continuidad, pero `.gitignore` evita versionar bases de datos locales.

`certs/` es la ubicación prevista para certificados OPC UA. No almacenar claves privadas en Git ni compartirlas en capturas.
