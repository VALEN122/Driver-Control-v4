# Driver Control 5.9.1

## Estabilidad

- Corrige el cierre inmediato al activar el modo oscuro.
- Evita que los colores de la interfaz ocupen nombres reservados por Kivy para eventos.
- Si un cambio de tema falla, conserva el modo anterior en lugar de cerrar la app.
- El cierre de la base de datos ahora es seguro aunque Android repita el evento de salida.

## Verificación

- Alternancia real claro → oscuro → claro → oscuro con Kivy 2.3.0 y KivyMD 1.2.0.
- Prueba automática para impedir nuevas colisiones con manejadores `on_<propiedad>`.
