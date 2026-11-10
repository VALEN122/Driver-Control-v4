# Verificación del lector de Uber — Driver Control 6.1.3

Fecha: 14/09/2026.

## Diagnóstico

Había dos causas con el mismo síntoma visible en Android 14:

1. Un APK instalado fuera de Google Play queda sujeto a **Ajustes restringidos**.
   Android no permite habilitar Accesibilidad hasta que el usuario autorice el
   ajuste desde la ficha de la aplicación. La app no intenta eludir esa medida.
2. `DriverOverlayService` llamaba a `startForeground()` sin declarar un tipo de
   servicio. En una app que apunta a API 34 o superior, Android lanza
   `MissingForegroundServiceTypeException`; al compartir proceso, esa caída podía
   detener también `UberOfferAccessibilityService`.

ML Kit también se inicializaba de forma directa durante la conexión. Un error de
carga podía cerrar el lector sin dejar un diagnóstico útil.

## Cambio

- El flotante declara `foregroundServiceType="specialUse"`, el permiso
  `FOREGROUND_SERVICE_SPECIAL_USE` y un subtipo descriptivo revisable en Play.
- El inicio en primer plano queda contenido: cualquier excepción se registra y
  el servicio se detiene sin derribar el proceso.
- ML Kit se inicializa con manejo de errores y reintento cada 15 segundos como
  máximo.
- El estado se guarda localmente en `driver_control_overlay` sin imágenes ni
  textos financieros.
- La pantalla de autorización permite abrir directamente **Info de la app** y
  explica el paso manual para APK externos.

## Riesgo principal

`specialUse` exige una declaración coherente en Play Console y revisión del caso
de uso. La descripción debe coincidir con la función real: burbuja iniciada por
el usuario para análisis y vuelto, sin pulsar ni aceptar viajes automáticamente.

## Prueba de aceptación en dispositivo

1. Actualizar la app sin desinstalarla y confirmar versión 6.1.3.
2. En una instalación por APK: **Ajustes > Aplicaciones > Driver Control > ⋮ >
   Permitir ajustes restringidos**.
3. Abrir Driver Control, tocar **LECTURA DE UBER > YA PREPARÉ** y activar el
   servicio.
4. Volver a Driver Control: la app no debe cerrarse y la burbuja debe continuar
   disponible si tiene permiso.
5. Abrir Uber Driver con el vehículo detenido y mostrar una oferta de prueba.
6. Mantener pulsada la burbuja `$`: debe indicar lector activo o un error
   explícito; nunca debe quedar solamente en “No funciona”.
7. Desactivar Accesibilidad y comprobar que **ANALIZAR VIAJE** manual sigue
   calculando conveniencia.

La corrección solo se considera completa después de pasar esta prueba en el
Samsung objetivo y revisar que el proceso no produzca un crash/ANR.
