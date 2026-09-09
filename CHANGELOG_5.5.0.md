# Driver Control 5.5.0 — Copiloto local unificado

- Agrega `DriverCopilotCoordinator` como única autoridad de captura y visión.
- Elimina del manifiesto el servicio paralelo basado en MediaProjection.
- Procesa bitmap, recorte y ML Kit en `DriverCopilotVision`, fuera del hilo principal.
- Clasifica localmente oferta, cobro final o pantalla irrelevante.
- La misma ruta abre Vuelto rápido cuando detecta un cobro confiable.
- Deduplica cuadros, admite una sola captura activa y libera cada imagen al terminar.
- Separa el cálculo en `TripProfitabilityAnalyzer`, con resultados verificables.
- Conserva la sincronización segura de parámetros financieros desde SQLite.
- Retira los controles del segundo OCR para impedir su activación accidental.
