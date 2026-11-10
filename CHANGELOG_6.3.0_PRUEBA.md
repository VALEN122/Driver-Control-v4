# Driver Control 6.3.0 — compilación de prueba

Este número identifica la compilación de desarrollo; no implica una versión final publicada en Google Play.

## Cambios implementados

- Verde: la oferta cumple mínimos de $/h y $/km, con distancia de recogida dentro del máximo.
- Amarillo: la oferta requiere revisión por mínimos, acercamiento o puntaje.
- Rojo: pérdida estimada, rentabilidad muy baja o fatiga/pausa activa en el visor.
- La ventana flotante ocupa menos ancho y muestra métricas adicionales al tocar.
- Coste configurable `wear_per_km` para reserva de mantenimiento/desgaste. Inicial 0; no se inventan precios de repuestos.
- Ajustes guarda la reserva en SQLite, la envía a SharedPreferences Android y la usa en las ofertas manuales y flotantes.
- Cada jornada guarda su propia `target_billing` al abrirla. La pantalla Jornada enseña ingresos registrados contra esa meta; un cierre resumido prevalece sobre viajes individuales para evitar doble conteo.
- OCR de cobro: se exige contexto explícito de cobro y un único importe inequívoco antes de abrir el vuelto.
- Pruebas de regresión Python y de contrato Android; el workflow de GitHub Actions compila un APK debug y lo publica sólo si supera pruebas.

## Limitaciones conocidas

- Los veredictos son estimaciones basadas en la tarifa y los datos disponibles, no certificación de cobro real de Uber.
- Los valores de oferta dependen de la calidad de la lectura OCR/accesibilidad. Verificar antes de actuar.
- El costo de desgaste es una reserva estimada y no un gasto efectivamente pagado; no se descuenta otra vez del registro contable de jornada.
- En una jornada sin ingresos registrados, el progreso refleja 0 aunque se hayan realizado viajes no cargados.
- El módulo de Google Play Billing y sincronización opcional no forma parte de esta compilación de prueba.
- Una APK debug puede no actualizar una instalación anterior si cambió la firma; respaldar datos antes de desinstalar.

## Verificación

Workflow: `.github/workflows/build-driver-control-v6.3.0.yml`.
Resultado válido únicamente cuando la ejecución más reciente finaliza con estado exitoso y publica `Driver-Control-6.3.0-APK-PRUEBA`.
