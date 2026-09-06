# Driver Control 5.2.0 — lectura de Uber estabilizada

- Corrige los diálogos de KivyMD que aparecían sin botones en algunos Samsung.
- Reestructura el lector de Accesibilidad con límites de nodos/frecuencia para evitar tirones.
- Agrega fallback de root activo + ventanas interactivas y lectura de texto/descripción/hint.
- Hace el parser tolerante a coma/punto, saltos de línea, `min ... km`, `km ... min` y errores OCR comunes.
- Elimina el recorte OCR fijo del 28% que podía ocultar la tarifa; ahora conserva casi toda la pantalla y reduce resolución si hace falta.
- Evita que OCR vuelva a analizar el propio flotante de Driver Control.
- Agrega diagnóstico visible: mantené pulsada la burbuja `$` para ver el último estado del lector.
- El flotante nunca pulsa Aceptar/Rechazar: la decisión sigue siendo del conductor.
