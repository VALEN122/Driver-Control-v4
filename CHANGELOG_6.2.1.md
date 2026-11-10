# Driver Control 6.2.1 — lectura de Uber Priority

- Distingue la tarifa principal de adicionales, propinas, peajes y precios por kilómetro/hora.
- No reemplaza el total ni le suma automáticamente el adicional por inicio de viaje.
- Conserva separados los datos de recogida y viaje; una línea de adicional no aporta contexto a los kilómetros siguientes.
- Una tarifa ausente o ambigua retira el veredicto anterior y pide revisar la lectura.
- Una respuesta de Gemini debe coincidir con la tarifa principal visible antes de reemplazar el cálculo local.
- Extrae el parser Java compartido para probar el mismo código que ejecuta Android.
- Incluye 14 pruebas nuevas del lector: los cuatro casos transcritos de las capturas del 28/09, formatos monetarios, líneas partidas, datos ambiguos y validación de Gemini.

Validación local: 54 pruebas aprobadas, incluidas las pruebas Java del parser.
La comprobación de compatibilidad de 16 KiB sigue siendo un requisito independiente para publicación; esta actualización es beta.
Falta repetir la lectura real en el teléfono después de instalar el APK actualizado.
