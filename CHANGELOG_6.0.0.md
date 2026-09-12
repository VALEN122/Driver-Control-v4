# Driver Control 6.0.0 — cierre inteligente

## Nuevo

- Cierre rápido de jornada con totales, detalles opcionales y estado completo/parcial.
- Resumen local por jornada sin obligar a cargar cada viaje.
- Historia posterior al cierre con ganancia, ecuación, $/h, $/km y una acción explicada.
- Motor local de recomendaciones éticas, finitas y basadas en reglas.
- Hoja `Cierres` en la exportación Excel.
- Versión de esquema SQLite mediante `PRAGMA user_version`.

## Correcciones de datos

- Un cierre agregado prevalece sobre sus viajes individuales para evitar doble conteo.
- Los medios de cobro desconocidos no se inventan; aparecen como importe sin clasificar.
- La comisión informada permanece separada y no se descuenta dos veces.
- El cierre se guarda en una transacción; ante un fallo la jornada permanece abierta.

## Verificación

- 14 pruebas automáticas.
- `main.py`, `insight_engine.py` y `excel_exporter.py` compilan sintácticamente.
- La compilación Android debe ejecutarse en GitHub Actions antes de instalar el APK de prueba.

## Aún no incluido

- Target API 36 y AAB firmado de producción.
- Google Play Billing.
- Importación de capturas de cierre y confianza por campo.
- Política de privacidad/Data Safety y variante Play-safe sin AccessibilityService.
