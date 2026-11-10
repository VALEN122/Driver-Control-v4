# Driver Control 6.3.0

- Integra en el código fuente las mejoras de lectura, cierre, caja y exportación de 6.2.2 que antes sólo estaban dentro de un parche de compilación.
- Unifica semáforo manual y flotante: rojo si hay pérdida o no alcanza ninguno de los mínimos; amarillo si falla un mínimo, el acercamiento es largo, hay fatiga moderada o puntaje insuficiente; verde sólo con ambos mínimos, acercamiento permitido y puntaje suficiente. Pausa o fatiga alta mantienen rojo.
- Reserva configurable de mantenimiento y desgaste en Ajustes ($/km), inicialmente 0 hasta que el conductor la configure. El análisis descuenta combustible y reserva en $/h y $/km y muestra ambos por separado. La reserva no genera un gasto ni modifica caja o cierres históricos.
- Flotante de 290 dp como máximo con tipografía y márgenes compactos; se mantiene la expansión de detalles al tocar.
- Meta de la jornada activa con ingresos registrados, objetivo y faltante; no suma ofertas vistas ni mezcla otras jornadas, incluso al cruzar medianoche. La meta usa ingresos del conductor, sin inventar comisión o facturación bruta.
- Rechaza lecturas de un único tramo reutilizado o viaje de duración/distancia cero. La respuesta de IA debe coincidir en importe, tiempos y distancias con la lectura local.
- Compilación canónica desde esta rama con firma de actualización existente. Archiva los flujos históricos que reconstruían versiones anteriores.

## Validación y límites
Pruebas de finanzas, parser Java, equivalencia manual/nativa, caja, cierres y exportación.
El comportamiento sobre Uber y la disposición del flotante requieren prueba en Android.
La cámara de atención no forma parte de esta entrega; quedó como idea por evaluar.
