# Driver Control 5.4.0 — conducción y vuelto contextual

- El flotante de una oferta muestra primero el veredicto y la ganancia estimada
  por hora/kilómetro; los detalles quedan en un segundo nivel tocable.
- El OCR reconoce el importe de la pantalla final de cobro y abre automáticamente
  Vuelto rápido con el importe precargado.
- Si el monto fue leído, el panel no abre el teclado: ofrece importes grandes y
  probables para resolver el vuelto con un toque.
- Incorpora patrones hápticos distintos para viaje conveniente, dudoso,
  inconveniente y cobro detectado.
- El estado normal del lector deja de mostrar confirmaciones intermitentes sobre
  la pantalla; el propio flotante funciona como confirmación visual.
- La métrica principal pasa a llamarse **Ganancia limpia disponible**.
- Un faltante al cerrar caja se presenta como una conciliación guiada y pregunta
  por gastos en efectivo no registrados, sin lenguaje punitivo.
- Mantiene OCR y flotante en servicios separados para que puedan detenerse de
  manera independiente.
