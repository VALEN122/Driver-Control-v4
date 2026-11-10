# Driver Control 6.3.0

Actualización de lectura, rentabilidad y objetivos de jornada. Ver [cambios 6.3.0](CHANGELOG_6.3.0.md).

En **Ajustes**, configurá la reserva de mantenimiento y desgaste por kilómetro. El valor inicial es 0 (sin reserva); no es una estimación del costo real del vehículo. El asistente muestra combustible y reserva por separado y usa ambos al evaluar $/hora y $/km. Los ingresos de la meta son los registrados para el conductor, no ofertas vistas ni una facturación bruta inferida.

El flujo `.github/workflows/android.yml` compila el código de la rama, sin aplicar parches de versiones antiguas. Conserva la firma existente y verifica el APK. Los flujos históricos se conservan en `archive/workflows`.

## Funciones anteriores


Aplicación Android de control de jornadas, ingresos, combustible, caja, mantenimiento y análisis de ofertas.

Los cambios de esta entrega están en [CHANGELOG_6.2.0.md](CHANGELOG_6.2.0.md).
La compilación activa es **Driver Control Android** (`.github/workflows/android.yml`).
Produce `driver-control-6.2.0-beta.apk`; comprueba el paquete, la versión y la firma.
Requiere el secreto existente `DRIVER_CONTROL_DEBUG_KEYSTORE_B64` para poder actualizar
una instalación firmada con esa misma clave. No se debe desinstalar la app para sortear
un error de firma: primero exportar una copia de seguridad y recuperar la clave correcta.

Pruebas locales: `python3 -m unittest discover -s tests -v` (requiere `xlsxwriter==3.2.9`).
El análisis manual y las finanzas funcionan sin servidor. Gemini requiere URL HTTPS,
token y un servidor con una API configurada; no se incluyen claves en el APK.

Android 16 exige adaptar los márgenes de las barras del sistema; el puente nativo
`DriverWindowInsets` aplica esa adaptación siguiendo los
[cambios documentados de Android 16](https://developer.android.com/about/versions/16/behavior-changes-16).

## Funciones existentes

Base estable 4.3.3 + Asistente de viajes.

Flujo rápido: Inicio → ¿Me conviene este viaje? → cargar datos de la oferta → Analizar.

Driver Control calcula costo de combustible, neto estimado, $/hora, $/km y un puntaje de conveniencia. La decisión final siempre queda en manos del conductor.

Flujo financiero recomendado: abrir jornada → trabajar sin carga obligatoria →
cerrar con los totales de Uber → entender cuánto quedó → elegir una acción para
la próxima jornada.

## 4.5 — Asistente flotante sobre Uber
La versión 4.5 incorpora un servicio Android opcional que analiza localmente los datos numéricos visibles en ofertas de Uber Driver y muestra un resultado flotante. Requiere activación manual del servicio de accesibilidad y no realiza acciones automáticas sobre Uber.

## 5.5 — Visor de IA local

Driver Control usa una sola ruta de lectura. Accesibilidad detecta los cambios de
Uber y `DriverCopilotCoordinator` procesa con ML Kit en un hilo nativo secundario.
No existe un segundo OCR compitiendo por CPU o memoria. El visor clasifica ofertas,
cobros finales y pantallas irrelevantes; nunca guarda ni transmite capturas.

### Activación correcta

1. Tocá **ACTIVAR ASISTENTE + VUELTO** y permití mostrar sobre otras apps.
2. Tocá **LECTURA VISUAL AUTOMÁTICA** y habilitá Driver Control en Accesibilidad.
3. Abrí Uber Driver. No hace falta habilitar una segunda captura de pantalla.

## 5.6 — Bienestar y mapa

El apartado **Bienestar y mapa** registra pausas y muestra tiempo efectivo de
jornada. El conductor puede informar cómo se siente y el analizador ajusta el
veredicto: una oferta rentable puede pasar a dudosa o no conveniente si existe
fatiga alta o una pausa activa. Los accesos a estaciones y áreas de descanso
abren el mapa instalado y, durante una jornada, exigen iniciar antes una pausa.

## 5.9 — Rediseño operativo

- Inicio moderno con ganancia real estimada, explicación del cálculo y gráfico semanal interactivo.
- Navegación principal reducida a Inicio, Jornada, Historial, Vehículo y Ajustes.
- Ingreso del conductor, comisión Uber informada, facturación conocida, combustible y otros gastos separados.
- Odómetro actualizable durante la jornada para no mostrar combustible ficticiamente en cero.
- Calculadora de carga, accesos al mapa y registro de mantenimiento con próximos controles.
- Decisión de viaje compacta: veredicto, ganancia, $/km, $/hora, nafta y factor decisivo.
- Modo claro y oscuro, IA, Gemini visual, OCR, burbuja de vuelto y exportación completa a Excel.

## 5.9.2 — Interfaz y uso diario

- El resumen se adapta a pantallas angostas sin superponer rótulos ni importes.
- La burbuja `$` se puede arrastrar y recuerda su posición.
- Excel abre el selector nativo de Android con permiso de lectura para WhatsApp,
  Drive, correo y las demás aplicaciones compatibles.
- Mensajes breves celebran el avance de la meta y cada viaje cargado sin sumar
  animaciones que distraigan durante la conducción.

## 6.0 — Cierre inteligente

- Cierre rápido con total de ganancias, cobros y odómetro, sin exigir viajes individuales.
- Estado completo o parcial: un dato desconocido nunca bloquea ni se inventa.
- Resumen por jornada que prevalece sobre el detalle para evitar doble conteo.
- Historia posterior con resultado, ecuación, $/hora, $/km y una recomendación explicada.
- Motor local y finito de reglas financieras; no optimiza tiempo de pantalla.
- Hoja `Cierres` en Excel y versión identificable del esquema SQLite.

La auditoría de producto, arquitectura, Google Play, monetización y roadmap está en
[`PRODUCT_AUDIT_10X.md`](PRODUCT_AUDIT_10X.md). La compilación actual sigue siendo
de prueba: API 36, AAB firmado, privacidad, Billing y la estrategia de
AccessibilityService son puertas obligatorias antes de publicar.
