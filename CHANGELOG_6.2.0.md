# Driver Control 6.2.0 — estabilización

- Recupera las correcciones 6.1.3 y 6.1.4 que no habían llegado a `main`.
- La carga de nafta reduce la caja; el consumo por kilómetros reduce la ganancia.
- Al cerrar se guarda una instantánea financiera. Cambiar precio o consumo no altera ese cierre, Inicio ni Excel.
- La migración conserva los datos y fija las estimaciones antiguas con la marca `LEGACY_RECONSTRUCTED`: sus precios históricos originales no pueden recuperarse porque antes no se guardaban.
- La base se respalda automáticamente antes de migrar desde un esquema anterior.
- No permite borrar viajes o cargas de jornadas cerradas.
- Una jornada que cruza medianoche se contabiliza completa en su fecha de apertura.
- Un cierre parcial sin efectivo informado no muestra una conciliación como confirmada.
- En Android 14+ captura la ventana de Uber sin incluir su propia burbuja en el OCR.
- El lector muestra el análisis local mientras consulta Gemini y descarta respuestas tardías.
- Reintenta una captura al terminar de dibujarse la tarjeta y libera recursos ante fallos de OCR.
- Declara correctamente el servicio flotante de Android 14+ y añade márgenes del sistema en Android 15/16.
- Un único workflow compila el código del repositorio, verifica su versión y usa la firma de actualización existente. Los antiguos aplicadores quedan archivados.
- La compilación final selecciona expresamente la clave de actualización guardada, comprueba su huella y verifica los servicios con APK Analyzer antes de entregar el APK.

Es una beta de uso personal. Para declarar el lector operativo hace falta probar una oferta real en el teléfono; para publicar en Play hacen falta las comprobaciones de compatibilidad, AAB y firma de producción.
