# Driver Control 5.0 — Fusionado con UberFilter OCR

Base estable 4.3.3 + Asistente de viajes.

Flujo rápido: Inicio → ¿Me conviene este viaje? → cargar datos de la oferta → Analizar.

Driver Control calcula costo de combustible, neto estimado, $/hora, $/km y un puntaje de conveniencia. La decisión final siempre queda en manos del conductor.

## 4.5 — Asistente flotante sobre Uber
La versión 4.5 incorpora un servicio Android opcional que analiza localmente los datos numéricos visibles en ofertas de Uber Driver y muestra un resultado flotante. Requiere activación manual del servicio de accesibilidad y no realiza acciones automáticas sobre Uber.

## 5.0 — OCR real

Integra el lector visual de UberFilter 0.10 dentro de Driver Control. Conserva
Dashboard, viajes, caja, jornadas, gastos y combustible. Cuando Accesibilidad no
expone la tarjeta de Uber, el conductor puede activar **LECTURA VISUAL OCR** y
autorizar **Toda la pantalla**. ML Kit procesa localmente el sector inferior,
no guarda capturas y corrige confusiones como `ARS8,9I6` → `$8.916`.
