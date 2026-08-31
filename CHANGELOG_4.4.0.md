# Driver Control 4.4.0 — Asistente de viajes

## Nuevo
- Pantalla **Asistente de viajes** accesible desde Inicio con “¿Me conviene este viaje?”.
- Entrada rápida de tarifa, minutos/km de pickup y minutos/km del viaje.
- Selector manual de calidad de destino: Mala / Normal / Buena.
- Cálculo automático de distancia total, tiempo total, litros y costo de combustible.
- Estimación de ganancia neta, $/hora y $/km.
- Puntaje 0–100 y recomendación: EXCELENTE / CONVIENE / DUDOSO / NO CONVIENE.
- Explicación breve de los factores principales de la recomendación.
- Resultado en ventana flotante dentro de Driver Control.
- Botones para marcar la evaluación como aceptada o rechazada y guardarla para análisis futuro.
- Nueva tabla `trip_assessments` en SQLite.
- Configuración de objetivo mínimo $/hora, mínimo $/km y pickup máximo deseado.

## Seguridad de la versión
Esta versión NO controla Uber, NO acepta viajes automáticamente y NO usa todavía una superposición Android sobre otras aplicaciones. La primera implementación es manual y modular para mantener estable la app. El overlay real se integrará como un módulo separado después de validar esta base.
