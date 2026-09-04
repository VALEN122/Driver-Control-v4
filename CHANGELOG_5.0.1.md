# Driver Control v5.0.1 - corrección de compilación

- GitHub Actions fuerza JDK 17 en el segundo build Gradle sin usar `sudo`, evitando volver a Java 11.
- Se corrige la inyección de los servicios Android de Accesibilidad y OCR en el Manifest generado.
- El APK resultante se publica como artefacto `Driver-Control-v5.0.1-UberFilter-OCR-APK`.
- El mínimo de $/km queda editable y con valor inicial de $300/km.
- Regla dura: si el $/km calculado queda por debajo del mínimo configurado, la recomendación es `NO CONVIENE` aunque el resto del puntaje sea alto.
