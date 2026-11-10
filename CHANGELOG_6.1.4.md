# Driver Control 6.1.4 — cargas de nafta sin doble descuento

- Separa la **nafta consumida** de la **carga pagada**: solo el consumo estimado
  por kilometraje reduce la ganancia operativa.
- Reconoce registros existentes llamados `Nafta`, `Naftas`, `Gasolina`, `Fuel`
  o `Combustible`, incluso si se cargaron desde el formulario de gastos.
- Muestra las cargas pagadas y el saldo entre ingresos y pagos registrados como
  información separada, sin presentarlos como otra reducción de la ganancia.
- Agrega el acceso directo **Cargar nafta** en Inicio y conserva **Cargar gasto**
  para peajes, comida y otros costos operativos.
- Aplica la misma clasificación al cierre inteligente y a la exportación Excel.
- No altera importes históricos, no inventa litros y no modifica la conciliación
  entre el resumen de Uber y los viajes detallados.
