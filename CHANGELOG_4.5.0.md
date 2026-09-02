# Driver Control 4.5.0 — Flotante sobre Uber

- Agrega un `AccessibilityService` Android limitado al paquete oficial `com.ubercab.driver`.
- Lee en el dispositivo el texto visible de una solicitud y extrae tarifa, minutos y kilómetros.
- Calcula combustible estimado, neto, $/hora, $/km y puntaje 0–100.
- Muestra una tarjeta flotante sobre Uber con CONVIENE / DUDOSO / NO CONVIENE.
- No pulsa botones de Uber y no automatiza aceptar/rechazar viajes.
- No guarda nombres ni direcciones: el servicio descarta el texto tras extraer los valores numéricos necesarios.
- Incluye aviso destacado antes de enviar al usuario a los Ajustes de accesibilidad.
- Sincroniza consumo, precio de nafta y umbrales del asistente desde Driver Control hacia el servicio Android.

## Activación
1. Abrir Driver Control > Asistente de viajes.
2. Tocar “ACTIVAR FLOTANTE SOBRE UBER”.
3. Leer el aviso y continuar.
4. En Ajustes de accesibilidad, activar “Driver Control - Asistente de viajes”.
5. Volver a Uber Driver. Al aparecer una oferta compatible, el flotante se muestra automáticamente.

## Nota técnica
La UI de Uber puede cambiar. El parser está diseñado para varios formatos comunes en español, pero debe probarse con capturas/ofertas reales y ajustarse si Uber cambia los textos o la jerarquía de accesibilidad.
