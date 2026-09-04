# Driver Control v5.1.0 - cierre de uso real

## Cambios principales

- El flotante deja de depender de `AccessibilityService` para dibujarse.
- Nuevo `DriverOverlayService` con permiso **Mostrar sobre otras apps**.
- Nueva burbuja `$` persistente sobre Uber para calcular el vuelto rápidamente.
- La calculadora de vuelto usa automáticamente la última tarifa detectada cuando está disponible.
- Botones rápidos de efectivo se adaptan al importe del viaje.
- Accesibilidad queda como una fuente opcional de lectura y se limita el recorrido de nodos para reducir tirones.
- OCR queda como fuente independiente de respaldo y ya no exige que Accesibilidad esté activa.
- OCR baja su frecuencia de análisis para reducir carga en el teléfono.
- Se puede detener OCR sin apagar el flotante ni el vuelto.
- Combustible ahora muestra un botón visible **BORRAR ÚLTIMA CARGA**.
- Cualquier carga del historial sigue pudiendo tocarse para eliminarla.
- Se mantiene la regla configurable de mínimo `$ / km` para `CONVIENE / NO CONVIENE`.

## Flujo recomendado

1. Activar **ASISTENTE + VUELTO** y permitir "Mostrar sobre otras apps".
2. Activar **LECTURA RÁPIDA (ACCESIBILIDAD)** si el teléfono se comporta bien.
3. Si Accesibilidad no lee correctamente o genera lentitud, desactivarla y usar **OCR (RESPALDO)**.
4. La burbuja `$` funciona independientemente de las dos fuentes de lectura.
