# Driver Control 5.6.0 — Bienestar y mapa

- Agrega un apartado de bienestar conectado con cada jornada.
- Registra inicio y fin de pausas en SQLite y calcula tiempo efectivo y descansos.
- Permite registrar atención percibida: bien, cansado o muy cansado.
- Recomienda una pausa según tiempo continuo, duración efectiva y estado informado.
- El analizador flotante baja el veredicto a dudoso o no conveniente cuando existe
  riesgo de fatiga, aunque la oferta sea rentable matemáticamente.
- Agrega accesos seguros a estaciones de servicio y áreas de descanso en el mapa
  instalado, sin cargar un motor cartográfico pesado dentro de la aplicación.
- Durante una jornada exige iniciar una pausa antes de abrir el mapa.
- Cierra automáticamente cualquier pausa abierta al finalizar la jornada.
