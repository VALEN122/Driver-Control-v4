# Driver Control 5.9.2

## Interfaz

- Reorganiza el encabezado para que el título, la fecha y los filtros entren en
  pantallas angostas.
- Reemplaza la grilla comprimida del desglose por seis filas con altura propia.
- Acorta los rótulos extensos y evita que los textos de comisión y combustible
  se superpongan.
- Presenta mensajes de meta y confirmaciones de viaje más cercanos y dinámicos.

## Burbuja de vuelto

- Permite arrastrar la burbuja `$` a cualquier zona segura de la pantalla.
- Guarda la posición elegida para conservarla cuando se vuelve a abrir.
- Mantiene el toque para abrir la calculadora y la pulsación larga para consultar
  el estado del lector.

## Excel en Android

- Comparte el archivo mediante `FileProvider`, `ClipData` y permiso temporal de
  lectura.
- Agrega explícitamente AndroidX Core al APK para asegurar la disponibilidad del
  proveedor.
- Verifica que el libro exista y no esté vacío antes de abrir el selector.

## Verificación

- Pruebas de exportación, cálculos, mensajes de progreso e integración Android.
