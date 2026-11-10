# Driver Control 6.1.3 — lector estable en Android 14+

- Declara el tipo `specialUse` y su permiso para el servicio flotante en primer
  plano. Esto evita `MissingForegroundServiceTypeException` al apuntar a API 34
  o superior.
- Evita que un fallo al iniciar ML Kit cierre todo el servicio de Accesibilidad;
  guarda el diagnóstico y reintenta de forma limitada.
- Conserva el estado del lector aunque la burbuja flotante no tenga permiso.
- Explica el paso obligatorio **Permitir ajustes restringidos** cuando el APK se
  instala manualmente en Android 13 o superior.
- Mantiene disponible el análisis manual sin OCR ni Accesibilidad.
- No modifica la base de datos, los viajes ni la conciliación financiera.
