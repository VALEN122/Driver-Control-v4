# Driver Control 5.9.2 — Más claro, móvil y compartible

Base estable 4.3.3 + Asistente de viajes.

Flujo rápido: Inicio → ¿Me conviene este viaje? → cargar datos de la oferta → Analizar.

Driver Control calcula costo de combustible, neto estimado, $/hora, $/km y un puntaje de conveniencia. La decisión final siempre queda en manos del conductor.

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
