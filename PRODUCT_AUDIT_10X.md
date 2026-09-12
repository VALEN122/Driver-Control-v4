# Driver Control 10X — auditoría, producto y plan ejecutable

Fecha de corte: 12/09/2026  
Código auditado: Driver Control 5.9.2; primera entrega implementada: 6.0.0.

## Veredicto ejecutivo

Driver Control tiene una necesidad real, una base funcional valiosa y una ventaja local: entiende efectivo, Mercado Pago, nafta y la forma de trabajar de un conductor argentino. Sin embargo, el producto anterior obligaba al usuario a pensar como un contador, el código concentraba casi toda la aplicación en un solo archivo y la configuración Android no era publicable en Google Play al 12/09/2026.

La dirección correcta no es volverla “adictiva”. Es volverla **confiable, breve y habitual**: cerrar la jornada, entender el resultado y recibir una sola acción útil. La retención debe ser consecuencia del valor, no de ansiedad, culpa o tiempo de pantalla.

Esta entrega 6.0.0 implementa el primer corte P0 que sí puede resolverse en el repositorio sin credenciales externas: cierre rápido, datos parciales explícitos, conciliación sin doble conteo, resumen financiero posterior, ranking local y explicable, exportación de cierres y migración identificable. Aún no es una versión para publicar: faltan API 36, AAB firmado, política/consentimientos, variante sin AccessibilityService, telemetría de estabilidad y Billing.

## Crítica del prompt maestro

El prompt tiene una visión de producto sólida, pero abarca entre tres y seis meses de trabajo de un equipo real. Mezcla descubrimiento, rediseño, migración tecnológica, cumplimiento, monetización, aprendizaje automático y publicación. Exigir que todo se implemente de una vez elevaría el riesgo de perder datos o publicar permisos que Google Play rechace.

Los ajustes profesionales son:

1. Reemplazar “adictivo” por “hábito financiero saludable”. La métrica propuesta en el propio prompt ya respalda este cambio.
2. Separar hipótesis de hechos. Precio, disposición a pagar y efecto sobre ganancias requieren entrevistas y experimentos; no se pueden inventar desde el código.
3. Dividir “Play ready” en puertas de salida verificables: política, API, AAB, firma, pruebas, Data Safety y revisión de AccessibilityService.
4. Validar el cierre de 90 segundos con conductores antes de invertir en OCR avanzado o una migración completa a Kotlin.
5. Mantener el ML fuera del MVP. Con poco volumen, reglas explicables son más precisas, baratas y auditables.

---

## 1. Auditoría crítica del producto y del código existente

### Producto

- La pantalla de inicio sí intentaba responder cuánto quedó, pero combinaba facturación, comisión, cobros y ganancia sin un contrato contable formal.
- El flujo anterior hacía que el detalle por viaje fuese la fuente principal. Eso no coincide con el momento real de uso: el conductor cansado, en casa, con totales pero sin ganas de reconstruir cada viaje.
- El historial, vehículo, gastos, nafta, metas y Excel aportan valor. Deben conservarse; el error sería reemplazarlos por una estética nueva sin resolver el cierre.
- La burbuja y el análisis durante la conducción son funciones secundarias y de alto riesgo. El corazón comercial debe seguir funcionando aunque OCR y Accesibilidad estén apagados.
- No había una progresión clara desde “dato” hacia “decisión”. Mostrar muchos números no equivale a comprensión financiera.

### Código y datos

- `main.py` supera 5.700 líneas y concentra interfaz KV, navegación, SQL, cálculos, exportación, Android y lógica de producto en una clase de 126 métodos. Esto encarece pruebas y cambios.
- `_create_or_migrate_db`, `refresh_all` y `_range_metrics` concentran demasiadas responsabilidades. La pantalla completa recalcula numerosos agregados al navegar.
- Las fechas se guardan como texto `dd/mm/yyyy` y se filtran con `substr(...)`. Funciona hoy, pero limita índices, zonas horarias y consultas históricas.
- La base SQLite usa transacciones, WAL, restricciones y algunos índices: es una buena base. Antes de 6.0.0 no identificaba formalmente la versión del esquema.
- La semántica actual es: `trips.amount` / `session_summaries.income_total` representa lo que Uber muestra como **ganancia del conductor antes de costos del vehículo**; la comisión informada se conserva separada y no vuelve a descontarse. La facturación conocida es `ingreso + comisión`.
- El exportador XLSX es amplio y oculta el token de IA. En 6.0.0 también exporta cierres agregados y hace prevalecer el cierre sobre los viajes individuales para no duplicar ingresos.
- Hay 14 pruebas automáticas en verde, principalmente unitarias y de inspección estática. No hay pruebas instrumentadas en Android, capturas de UI ni medición de ANR.

### Android, seguridad y operación

- `buildozer.spec` mantiene `android.api = 33`, NDK 25b y `python-for-android v2024.01.21`. Desde el 31/08/2026 Google Play exige API 36 para apps nuevas y actualizaciones; por lo tanto, la configuración actual es un bloqueo de publicación: [requisito oficial](https://support.google.com/googleplay/android-developer/answer/11926878?hl=es-419).
- Los workflows actuales generan APK de depuración. No existe un pipeline de AAB de producción firmado, separación de secretos ni promoción entre pruebas interna/cerrada/producción.
- `UberOfferAccessibilityService` escucha eventos de Uber y puede tomar capturas para OCR local. No pulsa ni acepta viajes, lo cual es correcto, pero `canTakeScreenshot=true` y el propósito no es asistencia a personas con discapacidad. Google exige declaración, demostración, divulgación destacada y consentimiento afirmativo; la aprobación no está garantizada: [política de AccessibilityService](https://support.google.com/googleplay/android-developer/answer/10964491?hl=en) y [permisos sensibles](https://support.google.com/googleplay/android-developer/answer/16558241?hl=en).
- Si se activa Gemini visual, se envía una captura reducida a un servidor configurado. El código usa HTTPS y consentimiento en la interfaz, pero todavía no conserva una prueba de consentimiento versionada ni ofrece un centro de privacidad.
- El servidor usa secretos por variables de entorno y limita tamaño, esquema y frecuencia. El token de aplicación es compartido y el rate limit vive en memoria por IP; no alcanza para suscripciones, abuso, revocación por usuario ni auditoría.
- No se encontró política de privacidad, formulario Data Safety preparado, eliminación de cuenta, Billing, crash reporting ni analítica de producto.

---

## 2. Problemas P0, P1 y P2 con evidencia

### P0 — bloquean confianza, datos o publicación

| Estado | Problema y evidencia | Usuario beneficiado | Métrica | Riesgo | Esfuerzo | Criterio de éxito |
|---|---|---|---|---|---|---|
| Resuelto en 6.0.0 | El cierre dependía del detalle de viajes. Se agregó `SmartCloseScreen` y `session_summaries`. | Conductor cansado al finalizar | Finalización y tiempo de cierre | Totales mal interpretados | M | ≥80% completa el cierre mediano en ≤90 s en prueba moderada |
| Resuelto en 6.0.0 | Un resumen y sus viajes podían duplicar ingresos. `_session_metrics`, `_range_metrics` y Excel ahora dan prioridad al resumen. | Todos | Jornadas conciliadas, confianza | Regresión histórica | M | Prueba automática demuestra $25.000, no $35.000, cuando conviven resumen y detalle |
| Resuelto en 6.0.0 | Los datos faltantes podían terminar asignados implícitamente. Los medios desconocidos quedan sin clasificar y visibles. | Usuario que no entiende Uber | Datos desconocidos y correcciones | Más cierres parciales | S | Ningún valor vacío se transforma en un medio de cobro inventado |
| Resuelto en 5.9.2 | Textos superpuestos en pantallas angostas. Se reemplazaron filas comprimidas por alturas y bloques responsivos. | Teléfonos Android pequeños | Finalización de tareas | Variaciones de fuente | M | Sin solapamientos a 320 dp y tamaño de fuente grande |
| Resuelto en 5.9.2 | La burbuja `$` tenía posición fija. Ahora se arrastra, limita al área segura y persiste su posición. | Quien usa vuelto | Éxito de uso de vuelto | Conflicto toque/arrastre | M | Toque abre; arrastre mueve; reinicio conserva posición |
| Resuelto en 5.9.2/6.0.0 | Excel no podía compartirse y el resumen agregado no se exportaba. Se usa `FileProvider` y se agregó hoja `Cierres`. | Quien envía a contador/Drive | Exportaciones compartidas | Apps receptoras incompatibles | M | Selector Android abre y XLSX contiene las hojas esperadas sin secretos |
| Abierto — bloquea Play | Target API 33 frente a API 36 obligatoria. Evidencia: `buildozer.spec`. | Todos los nuevos usuarios | Aprobación de Play | La actualización de p4a puede romper recetas nativas | L | AAB API 36 instalado desde pista interna en Android 8–16 |
| Abierto — bloquea Play | No existe AAB release firmado ni gestión segura de keystore. Workflows usan `android debug`. | Negocio | Publicación | Pérdida de clave o build irreproducible | M | AAB firmado, `bundletool validate`, firma reproducible y secretos fuera del repo |
| Abierto — riesgo de rechazo | AccessibilityService captura pantalla de Uber; faltan declaración, video, consentimiento versionado y variante sin servicio. | Usuario y negocio | Aprobación, opt-in | Rechazo/suspensión y exposición sensible | L | Revisión interna de política + build Play-safe manual + expediente de declaración |
| Abierto — bloquea Play | No hay política de privacidad pública ni Data Safety reconciliado con el código. | Usuario | Confianza y aprobación | Declaración inconsistente | M | Matriz dato-finalidad-retención-tercero coincide con binario y política publicada |
| Abierto — bloquea monetización | No existe Play Billing ni validación de compra. | Cliente Pro | Conversión e ingresos | Fraude o acceso perdido | L | Compra de prueba, renovación, gracia, cancelación y restauración verificadas con backend/RTDN |

### P1 — impiden escalar con calidad

| Problema y evidencia | Usuario beneficiado | Métrica | Riesgo | Esfuerzo | Criterio de éxito |
|---|---|---|---|---|---|
| Monolito de más de 5.700 líneas; SQL y UI acoplados. | Equipo y usuario | Lead time, defectos | Refactor que cambie cálculos | L | Motor financiero ejecuta las mismas pruebas sin importar Kivy o Kotlin |
| No hay confianza/fuente por campo OCR; solo confianza global del cierre. | Usuario de capturas | Correcciones OCR | Falsa precisión | M | Cada campo conserva valor, fuente, confianza y confirmación humana |
| No hay importador de capturas de cierre; el OCR actual analiza ofertas en vivo. | Usuario en casa | Tiempo de cierre | Permisos y formatos cambiantes | L | Tres diseños de Uber procesados; campos dudosos nunca se confirman solos |
| No existe estado confiable “vehículo en movimiento”. | Conductor | Interacciones en movimiento | Falso positivo o distracción | L | Formularios bloqueados solo con señal suficiente y salida manual siempre disponible |
| SQLite local no está cifrado; tampoco hay estrategia de backup/restauración. | Usuario con datos financieros | Incidentes de datos | Pérdida/filtración | L | Backup cifrado restaurable y borrado verificable |
| Fechas locales en texto y consultas con `substr`. | Usuario histórico | Exactitud por período | Migración de datos | M | UTC/offset normalizados sin alterar días históricos del usuario |
| El servidor usa token compartido y rate limit en memoria. | Suscriptor Pro | Fraude, disponibilidad | Complejidad backend | L | Identidad por instalación/cuenta, tokens rotables, cuota duradera y auditoría mínima |
| No hay eventos de producto ni crash/ANR. | Equipo | North Star, crash-free | Recolección excesiva | M | Esquema mínimo, opt-in cuando corresponda y dashboard con calidad/retención |
| No hay pruebas Android reales ni suite de accesibilidad visual. | Usuarios Samsung/Motorola/Xiaomi | Crash-free/ANR | Matriz de dispositivos costosa | L | Smoke tests en al menos 3 fabricantes y API 26/33/36 |

### P2 — crecimiento posterior a la validación

- Comparaciones históricas avanzadas, pronóstico de metas y mantenimiento predictivo.
- Copia de seguridad/sincronización, cuentas, varios vehículos y plataformas.
- Informes impositivos revisados por profesional argentino.
- IA conversacional con límites, trazabilidad y costo controlado.
- Contextual bandit únicamente con volumen, consentimiento y experimento pre-registrado.
- Plan para flotas, remiserías y contadores.

---

## 3. Propuesta de valor en una oración

**Driver Control convierte los totales de tu jornada en la plata que realmente te quedó y en una decisión simple para trabajar mejor mañana.**

---

## 4. Flujo completo del conductor

1. **Primer uso:** elegir vehículo, consumo aproximado y meta; explicar que no es una app oficial de Uber; OCR/Accesibilidad permanecen apagados.
2. **Antes de trabajar:** “Empezar jornada” → odómetro → combustible aproximado → meta editable. Objetivo: menos de 20 segundos.
3. **En movimiento:** interfaz de solo lectura y acciones esenciales; vuelto opcional; sin animaciones, estadísticas ni pedidos de carga.
4. **Fin detectado o elegido:** recordatorio silencioso “Cuando estés detenido, cerrá tu jornada”. Nunca bloquear otras apps.
5. **Elección de cierre:** rápidos totales, importar capturas o detalle por viaje. El rápido es la opción recomendada.
6. **Captura de datos:** preguntar en lenguaje de Uber; aceptar “No lo sé”; mostrar costos ya cargados.
7. **Revisión:** distinguir confirmado, estimado y desconocido; detectar contradicciones sin inventar correcciones.
8. **Resultado:** mostrar ganancia operativa, fórmula, $/h, $/km y una acción prioritaria. Máximo 5–7 tarjetas.
9. **Corrección posterior:** permitir completar un cierre parcial sin perder su versión previa.
10. **Semana:** progreso contra la propia historia, resumen compartible y una meta alcanzable.
11. **Oferta Pro:** aparece después de al menos tres cierres útiles, nunca antes de que el usuario vea valor.

---

## 5. Wireframes de pantallas principales

| Pantalla | Jerarquía | Acción primaria | Estado vacío/error |
|---|---|---|---|
| Inicio sin jornada | “Cuánto te quedó” → meta → acción | Empezar jornada | Explica en una frase qué se calculará |
| Inicio con jornada | Estado activo → datos mínimos → seguridad | Cerrar jornada | Si falta odómetro, pedirlo al cerrar, no durante el viaje |
| Empezar | Odómetro, combustible aproximado, meta | Empezar | Validación junto al campo; conservar lo ingresado |
| Modo conducción | Estado, tiempo y acceso a vuelto | Terminar/recordar después | Sin formularios ni celebraciones |
| Elegir cierre | Rápido recomendado, capturas, detallado | Cierre rápido | Todas las rutas funcionan sin Accesibilidad |
| Cierre rápido | Ganancia Uber, cobros, saldo, km, costos | Cerrar y ver resultado | “No lo sé” y cierre parcial siempre disponibles |
| Importar/revisar | Campo, valor, fuente, confianza | Confirmar revisión | Nunca confirmar automáticamente una lectura dudosa |
| Cierre detallado | Viajes y ajustes agrupados | Conciliar | El detalle no impide volver a rápido |
| Resultado | Neto → fórmula → eficiencias → una acción | Listo | Etiqueta clara si es estimado/parcial |
| Historial | Jornadas, confianza, correcciones | Abrir jornada | Filtro simple, sin feed infinito |
| Vehículo | Costos y próximos controles | Registrar mantenimiento | Explica la reserva estimada |
| Pro | Beneficio desbloqueado con ejemplo propio | Probar Pro | Restaurar compra y seguir con Gratis visibles |

---

## 6. Diseño del cierre inteligente

### Cierre rápido implementado en 6.0.0

- Paso 1: “Tus ganancias” de Uber, cantidad de viajes opcional y efectivo opcional.
- Detalles opcionales: Mercado Pago, cobro por aplicación, comisión y saldo con Uber.
- Paso 2: odómetro final, efectivo contado opcional y accesos a gasto/nafta.
- Paso 3: completo o parcial. Un cierre parcial se guarda igual.
- Validaciones: odómetro no retrocede; medios conocidos no superan el ingreso; no pueden coexistir “Uber me debe” y “yo debo a Uber”; un vacío sigue siendo desconocido.
- Persistencia atómica: resumen, cierre de pausas, odómetro y jornada se guardan en una transacción. Si algo falla, la jornada sigue abierta.

### Siguiente iteración

- Cronómetro anónimo desde pantalla abierta hasta guardado.
- “No lo sé” explícito junto a cada campo, no solo vacío.
- Corrección posterior y bitácora de cambios.
- Ayuda visual “Dónde encontrarlo” basada en capturas autorizadas y actualizables.
- Modo de captura múltiple desde el selector del sistema, sin AccessibilityService.

---

## 7. Modelo financiero y ecuaciones

### Definiciones

- `B`: tarifa/facturación bruta conocida al pasajero.
- `C`: comisión/tasa de servicio y ajustes retenidos por la plataforma.
- `P`: promociones, bonos y ajustes a favor.
- `I`: ingreso del conductor antes de costos del vehículo. Si Uber muestra “Tus ganancias”, ese es el dato preferido.
- `K`: kilómetros trabajados según odómetro.
- `L`: consumo configurado en litros cada 100 km.
- `PL`: precio representativo por litro.
- `F`: combustible consumido estimado.
- `O`: gastos operativos efectivamente incurridos, sin duplicar cargas de combustible.
- `M`: reserva estimada de mantenimiento por kilómetro.
- `N`: ganancia neta operativa.

### Ecuaciones

```text
I = B − C + P                         si bruto y ajustes están completos
B_conocida = I + C                    cuando I ya es “Tus ganancias”
F = K × (L / 100) × PL
M = K × reserva_por_km
N_confirmada = I − F − O − M          con campos requeridos confirmados
N_estimada = Î − F̂ − Ô − M̂          si falta al menos un componente
$/hora = N / horas_netas_sin_pausas
$/km = N / K
```

Los medios de cobro **no son ingresos adicionales**. Efectivo, Mercado Pago, transferencia y cobro por aplicación explican cómo se liquidó `I`. El saldo con Uber explica flujo de caja pendiente; no se vuelve a sumar a la ganancia de la misma jornada.

```text
cobros_clasificados = efectivo + mercado_pago + app + otros
sin_clasificar = max(I − cobros_clasificados, 0)
caja_esperada = caja_inicial + efectivo_cobrado − gastos_en_efectivo
diferencia_caja = caja_contada − caja_esperada
```

En 6.0.0, `M=0` hasta diseñar y explicar una reserva configurable; por eso el resultado sigue rotulado como estimado. No se descontará una reserva oculta.

---

## 8. Especificación del algoritmo de personalización

### MVP implementado: reglas locales y explicables

Cada candidato usa señales normalizadas entre 0 y 1:

| Señal | Peso |
|---|---:|
| Impacto financiero | +0,30 |
| Capacidad de acción | +0,25 |
| Relevancia personal | +0,15 |
| Actualidad | +0,15 |
| Novedad | +0,10 |
| Confianza de datos | +0,05 |
| Repetición | −0,20 |
| Riesgo de ansiedad | −0,25 |
| Riesgo de distracción | −0,30 |

```text
score = clamp(100 × Σ(peso × señal), 0, 100)
```

Reglas iniciales implementadas: cierre parcial, resultado negativo, diferencia de caja, peso alto de combustible, meta alcanzada y cierre saludable. El resultado muestra una acción, su explicación y por qué fue elegida.

### Límites obligatorios

- Feed finito de 5–7 tarjetas; una sola acción primaria por cierre.
- Ninguna recomendación en movimiento.
- Si la confianza de los datos es baja, priorizar completar datos antes de optimizar horarios o gastos.
- Repetir el mismo consejo como máximo una vez cada tres cierres, salvo riesgo financiero grave.
- No recomendar trabajar más horas como respuesta predeterminada.
- Comparar solo contra la historia propia; exigir al menos tres observaciones comparables.
- Botón para pausar recomendaciones y texto “Te mostramos esto porque…”.

### Ejemplos

| Situación | Candidato ganador | Acción |
|---|---|---|
| Cierre parcial | Completar datos | Revisar el total cuando esté disponible, sin invalidar la jornada |
| Nafta >20% de ingreso | Peso de combustible | Comparar kilómetros sin pasajero en el próximo cierre |
| Caja difiere ≥$100 | Diferencia de caja | Buscar vuelto o gasto en efectivo no cargado |
| Meta cumplida | Meta alcanzada | Cerrar y descansar; no empujar más horas |

### Cold start y evolución

- Cierres 1–2: explicar el cálculo y pedir solo datos esenciales.
- Cierres 3–5: mostrar progreso contra la meta elegida.
- Desde 6 cierres: comparar día, hora y $/km contra su propia mediana.
- Registrar correcciones de OCR como señal de confianza del formato, no como juicio sobre el usuario.
- Evaluar un contextual bandit recién con ≥10.000 cierres consentidos y anonimizados, tres acciones bien definidas, guardrails de ansiedad y un experimento que mida acción útil, no clic.

---

## 9. Arquitectura técnica recomendada

| Criterio | A. Fortalecer Kivy temporalmente | B. Kotlin + Jetpack Compose progresivo |
|---|---|---|
| Primer valor | 2–6 semanas | 8–16 semanas para paridad mínima |
| Costo inicial | Bajo/medio | Alto |
| Riesgo inmediato | Bajo si los cambios son aditivos | Alto si se intenta reescritura total |
| Rendimiento/ANR | Aceptable con límites | Mejor observabilidad e integración nativa |
| Billing/Play | Posible, pero requiere puente Java y pruebas | Soporte oficial y menor fricción |
| UI nativa/accesibilidad | Limitada | Alta |
| Mantenimiento | Empeora si sigue el monolito | Mejor con módulos y tipado |
| Migración de datos | Ninguna en etapa inicial | Importar la misma SQLite con migraciones versionadas |
| Reversibilidad | Alta | Alta solo si se migra pantalla por pantalla y se conserva exportación |

### Decisión

Usar A durante 60 días para validar el cierre y separar dominio, persistencia, importación, recomendaciones y UI. En paralelo, construir una prueba técnica de API 36/AAB y un shell Kotlin pequeño. Migrar a B solo si el cierre alcanza la adopción objetivo y Kivy demuestra ser el cuello de botella. No mezclar dos interfaces completas dentro del mismo APK ni reescribir los cálculos sin pruebas de paridad.

### Límites de módulos

```text
finance/       ecuaciones puras y estados confirmado/estimado
storage/       SQLite, migraciones, repositorios, backup/exportación
importer/      archivos, capturas y normalización de fuentes
ocr/           ML Kit local y confianza por campo
insights/      candidatos, ranking, cooldowns y explicaciones
ui/            Inicio, jornada, cierre, historia e historial
android/       movimiento, overlay, permisos y share intents
billing/       productos, entitlement y restauración
analytics/     eventos mínimos, consentimiento y calidad
```

---

## 10. Modelo de monetización

### Gratis y Pro

La versión gratuita conserva inicio/cierre, ganancia diaria, gastos, historial esencial, datos propios, Excel básico y vuelto. Pro cobra por automatización y profundidad: múltiples capturas, conciliación, historia avanzada, alertas, pronóstico, costos del vehículo, PDF/impuestos, backup, varios vehículos/plataformas e IA.

La investigación competitiva muestra referencias internacionales cercanas a USD 9–11/mes para tracking de conductores/millaje, por ejemplo [Everlance](https://www.everlance.com/pricing), [Driversnote](https://www.driversnote.com/) y [Gridwise/Solo](https://www.worksolo.com/). Eso no demuestra disposición a pagar en Argentina.

Hipótesis inicial para validar, no precio definitivo:

- Test A: ARS 5.999/mes.
- Test B: ARS 7.999/mes.
- Anual: 8 mensualidades, con precio localizado y revisión frecuente por inflación.
- Regla de protección: no superar 0,5% de la ganancia neta mensual mediana de los usuarios entrevistados sin evidencia fuerte de ahorro superior.

### Embudo

1. Instala y cierra una jornada sin cuenta.
2. Completa tres cierres y recibe dos acciones útiles.
3. Vista previa Pro usa sus propios datos, sin ocultar el resumen gratuito.
4. Prueba de 7 días, con fecha/precio claros y restauración visible.
5. Mensual o anual; Play Billing otorga el entitlement solo después de verificación.
6. Antes de cancelar: pausar, bajar a Gratis o conservar solo backup; sin fricción engañosa.

El backend debe validar compras y procesar notificaciones del ciclo de vida/RTDN, como recomienda la [documentación oficial de Play Billing](https://developer.android.com/google/play/billing/backend). Presupuestar la comisión real de la cuenta; Google indica que la mayoría de desarrolladores sujetos a cargo califican a 15% o menos, pero debe verificarse en Play Console: [service fees](https://support.google.com/googleplay/android-developer/answer/112622?hl=en).

---

## 11. Checklist de Google Play

| Requisito | Estado 12/09/2026 | Puerta de salida |
|---|---|---|
| Target API 36 | Bloqueado: API 33 | Toolchain actualizado y pruebas API 26/33/36 |
| AAB release firmado | No | `bundletool validate` + pista interna |
| Keystore seguro | No | Secretos protegidos, backup offline y rotación documentada |
| Migración DB | Parcial | `user_version` existe; falta backup/restauración y pruebas desde bases antiguas |
| Política de privacidad pública | No | URL pública y acceso dentro de Ajustes/onboarding |
| Data Safety | No | Matriz verificada contra binario y proveedores |
| Cifrado en tránsito | Parcial | Solo HTTPS, pinning/rotación evaluados, sin URLs arbitrarias en release |
| Minimización | Parcial | Modo manual sin red; eliminar permisos no usados por variante |
| Consentimiento OCR/Accesibilidad | Parcial | Consentimiento afirmativo, versionado, revocable y previo al permiso |
| Eliminación de cuenta/datos | No aplica aún | Implementar antes de cuentas/sync |
| Play Billing | No | Sandbox completo + backend/RTDN |
| Internal/closed testing | No | Matriz de dispositivos y cohortes de conductores |
| Crash/ANR | No | Crash-free ≥99,5%; ANR <0,47% como guardrail interno inicial |
| Offline | Sí en finanzas básicas | Prueba sin red del flujo completo |
| Accesibilidad visual | Parcial | 320 dp, fuente grande, TalkBack, contraste y targets de 48 dp |
| Ficha profesional | No | Capturas reales, descripción, video y descargo “no oficial de Uber” |
| AccessibilityService | Crítico | Build manual sin servicio + expediente de revisión separado |

La versión recomendada para la primera revisión de Google Play debe omitir AccessibilityService si no se obtiene una validación previa convincente. El cierre manual, importación desde selector y finanzas deben conservar el valor principal.

---

## 12. Plan de analítica y experimentación

### North Star

**Conductores que completan al menos tres cierres confiables por semana y reciben una acción financiera útil.**

### Eventos mínimos

| Evento | Propiedades permitidas | Nunca enviar |
|---|---|---|
| `shift_started` | versión, modo, latencia | odómetro exacto, ubicación |
| `close_started` | ruta: rápido/capturas/detalle | importes brutos |
| `close_completed` | duración, confianza, cantidad de campos desconocidos | captura o texto de Uber |
| `ocr_field_reviewed` | tipo de campo, bucket de confianza, corregido sí/no | valor financiero exacto |
| `insight_shown` | regla, score por bucket, explicación | historia completa |
| `insight_applied` | regla y acción declarada | ubicación |
| `export_completed` | formato, éxito/error | archivo exportado |
| `billing_state_changed` | producto, estado, país | token de compra en analítica |
| `app_quality` | versión, dispositivo, crash/ANR | contenido financiero |

### Métricas y pruebas

- Tiempo mediano y P90 de cierre; tasa de abandono por paso.
- Cierre confiable: confirmado o parcial corregido, sin contradicciones.
- Retención D1/D7/D30 y tres cierres semanales.
- Tasa de corrección OCR y de “No lo sé”.
- Recomendación aplicada autoinformada y cambio posterior de la métrica relevante.
- Crash-free, ANR, conversión, cancelación y LTV.
- Encuesta breve de comprensión: “¿Cuánto te quedó y por qué?”; objetivo ≥80% correcto.

Primer experimento: cierre rápido versus flujo anterior, 100–200 conductores, dos semanas. Éxito si sube ≥15 puntos porcentuales la finalización sin aumentar correcciones graves ni tiempo en movimiento. No ejecutar a la vez un test de precio.

---

## 13. Roadmap 30, 60 y 90 días

### Días 0–30 — confianza y cierre

- Liberar 6.0.0 a testers: cierre rápido, resumen, Excel y reglas locales.
- Pruebas moderadas con 10–15 conductores; medir vocabulario y ≤90 s.
- Extraer `finance` y `storage`; fixtures de bases 5.x.
- Prototipo técnico API 36/AAB y matriz Android.
- Build sin AccessibilityService; borrador de privacidad/Data Safety.

Salida: ≥80% cierra, cero pérdidas de datos, cálculo explicado correctamente por ≥80%.

### Días 31–60 — importación y publicación cerrada

- Selector de múltiples capturas y OCR local por campo.
- Revisión con fuente/confianza/“No lo sé”.
- Consentimiento versionado y centro de privacidad.
- Telemetría mínima, crash/ANR y pruebas instrumentadas.
- AAB firmado en pista interna/cerrada; ficha preliminar.
- 30 entrevistas de precio y primer smoke test de Billing.

Salida: OCR preciso en campos confirmados ≥95%; crash-free ≥99,5%; revisión de política sin bloqueos conocidos.

### Días 61–90 — Pro y escalado controlado

- Billing con backend/RTDN, restauración y estados de gracia.
- Históricos Pro, alertas y reporte mensual/PDF.
- Experimento de precio localizado después de tres cierres.
- Prueba del shell Kotlin y decisión formal de migración.
- Producción gradual 5% → 20% → 100% con rollback.

Salida: conversión inicial 3–7%, cancelación mensual <8% como hipótesis, soporte y estabilidad dentro de guardrails.

---

## 14. Criterios de aceptación verificables

1. Cierre rápido requiere solo ingreso y odómetro; todo detalle puede quedar vacío.
2. Un cierre parcial se guarda y se identifica como parcial.
3. Ningún valor desconocido se inventa ni se clasifica automáticamente.
4. Resumen y viajes individuales de una jornada nunca duplican ingresos.
5. Comisión informada se muestra aparte y no se descuenta dos veces.
6. Combustible consumido usa kilometraje × consumo × precio; una carga no se resta además como gasto.
7. Fallo durante el guardado revierte la transacción y deja la jornada abierta.
8. Resultado muestra importe, ecuación, $/h, $/km, una acción y su “por qué”.
9. Excel contiene `Resumen`, `Jornadas`, `Cierres`, viajes, gastos, combustible y no contiene el token de IA.
10. Selector de compartir recibe permiso temporal de lectura mediante FileProvider.
11. Burbuja se arrastra dentro del área segura y persiste posición.
12. Pantallas no se superponen a 320 dp ni con fuente grande.
13. Modo manual funciona sin red, OCR ni AccessibilityService.
14. No aparece celebración o recomendación si el vehículo está en movimiento.
15. AAB de producción apunta a API 36, valida, instala desde Play interna y conserva una base 5.x.
16. Data Safety, política y consentimientos coinciden con cada variante del binario.
17. Compra, renovación, restauración, gracia, cancelación y revocación Pro pasan pruebas sandbox.

---

## 15. Implementación en versiones pequeñas

| Versión | Alcance | Reversible porque… |
|---|---|---|
| 6.0.0 | Cierre rápido, resumen local, historia, reglas, Excel, esquema v2 | Tabla aditiva; viajes originales se conservan |
| 6.0.1 | Pulido 320 dp, “No lo sé”, edición de cierre, fixtures 5.x | Solo UI y APIs de repositorio |
| 6.1.0 | Importación manual de capturas + confianza por campo | Se apaga por feature flag; manual sigue disponible |
| 6.1.1 | Privacidad, consentimiento versionado y build Play-safe | Variante sin servicio no toca datos financieros |
| 6.2.0 | API 36, AAB, pruebas cerradas y observabilidad | Canal separado; rollback a build interno anterior |
| 6.3.0 | Billing y Pro de históricos/reportes | Entitlements separados; datos siguen accesibles en Gratis |
| 6.4.0 | Sync cifrado opcional y varios vehículos | Opt-in y exportación previa |
| 7.0 piloto | Shell Kotlin/Compose con motor validado | Cohorte pequeña y migración comprobada antes de ampliar |

## Estado verificable de 6.0.0

- Compilación sintáctica Python: correcta.
- Pruebas automáticas: 14/14 correctas.
- Build Android real: pendiente de ejecutar en GitHub Actions; no se declara publicado ni Play-ready.
- Publicación: bloqueada hasta cerrar API 36, AAB/firma, privacidad, Data Safety y la decisión sobre AccessibilityService.
