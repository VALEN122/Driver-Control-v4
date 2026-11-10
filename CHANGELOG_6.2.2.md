# Driver Control 6.2.2 — cierre y cálculos explicables

Cambios basados en la prueba ficticia de 7 viajes, $89.000, 60 km y una carga
de $20.000 por 7 litros:

- El cierre dice «Resultado estimado» y muestra duración, consumo, precio
  usado y precio promedio de las cargas con litros informados.
- Se detalla efectivo inicial, cobros, pagos (incluida nafta), efectivo esperado,
  contado y sobrante/faltante. La fórmula de caja se mantiene.
- El valor por hora se presenta desde 10 minutos; los registros se conservan.
  Esta versión no añade un modo de prueba ni excluye automáticamente jornadas.
- Los nuevos cierres distinguen comisión vacía y comisión explícitamente cero
  en su copia de los cálculos. Los cierres antiguos con cero ambiguo se muestran
  como «Sin informar», sin modificar sus importes guardados.
- Excel tiene un resumen compacto y el desglose en Resultados, kilómetros de
  jornadas separados de kilómetros en viajes y estados en español.
- Se da espacio al primer campo de los formularios y se permite que la tarjeta
  del resultado crezca con su contenido.
- El visor identifica el resultado tras nafta y muestra el umbral que causa
  el rechazo. Se conserva el lector Priority y sus pruebas.

Validación: pruebas automatizadas de caja Efectivo/MP, comisión vacía/cero,
exportación y conservación del precio histórico. El APK y el diseño visual
deben comprobarse en Android después de compilar. No se cambia la firma,
el paquete, la base de datos ni las reglas de rentabilidad.
