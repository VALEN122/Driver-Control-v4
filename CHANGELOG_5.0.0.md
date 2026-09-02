# Driver Control 5.0.0

- Fusión de Driver Control 4.5 con el OCR de UberFilter 0.10.
- Captura autorizada mediante MediaProjection y OCR local con ML Kit.
- Accesibilidad y OCR alimentan el mismo evaluador de viajes.
- Corrección de `I`, `l` y `|` como `1`, y `O` como `0` dentro de importes.
- Rechazo de falsos precios menores a $100, incluida la propia burbuja.
- Procesamiento limitado a una imagen cada 800 ms y al 70% inferior.
- Las capturas no se guardan ni se transmiten.
