# Driver Control 5.0.0

- Fusión de Driver Control 4.5 con el OCR de UberFilter 0.10.
- Captura autorizada mediante MediaProjection y OCR local con ML Kit.
- Accesibilidad y OCR alimentan el mismo evaluador de viajes.
- Corrección de `I`, `l` y `|` como `1`, y `O` como `0` dentro de importes.
- Rechazo de falsos precios menores a $100, incluida la propia burbuja.
- Procesamiento limitado a una imagen cada 800 ms y al 70% inferior.
- Las capturas no se guardan ni se transmiten.

## 5.0.1

- Corrige la tarjeta del asistente que recortaba el botón de OCR.
- Verifica que Accesibilidad esté habilitada antes de iniciar la captura visual.
- Reconoce más variantes de minutos y kilómetros usadas por Uber/OCR.
- Amplía las pistas de detección sin aceptar pantallas numéricas genéricas.
- Documenta el orden correcto de activación de los dos permisos.
