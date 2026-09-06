# Driver Control 5.3.0 — lector visual de Uber

- Cambia la estrategia de lectura en Android 11+: ya no depende del texto accesible de la tarjeta.
- Usa AccessibilityService.takeScreenshot() + ML Kit OCR local.
- Evita recorrer ventanas y cientos de nodos en Android moderno para reducir tirones.
- Mantiene un fallback acotado para Android antiguo.
- No guarda capturas, no transmite imágenes y nunca pulsa Aceptar/Rechazar.
- El parser y el flotante siguen siendo los de v5.2.
