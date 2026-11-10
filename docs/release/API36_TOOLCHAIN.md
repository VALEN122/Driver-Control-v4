# Driver Control: toolchain Android API 36

Fecha de decisión: 14/09/2026.

## Alcance

La aplicación conserva `python-for-android v2024.01.21`, Python 3.11.5 y
Android NDK 25b. El cambio de API 34 a API 36 no modifica ninguna receta
nativa. El checkout efímero de p4a recibe el parche
`patches/p4a-v2024.01.21-api36.patch` antes de compilar:

- Android Gradle Plugin 8.1.1 a 8.9.1.
- Gradle 8.0.2 a 8.11.1.
- `jcenter()` a `mavenCentral()`.

AGP 8.9.1 es la versión mínima que Android documenta para API 36.0 y requiere
Gradle 8.11.1. El parche se aplica con `git apply --check` y el CI verifica el
tag y el commit de p4a antes de usarlo.

## Recetas y riesgos identificados

| Componente | Versión del tag | Acción en este cambio | Riesgo pendiente |
|---|---:|---|---|
| `python3` / `hostpython3` | 3.11.5 | Sin cambio | Actualización de seguridad posterior, con paridad funcional |
| `openssl` | 1.1.1w | Sin cambio | Rama sin soporte público general; actualizar en una entrega aislada |
| `sqlite3` | 3.35.5 | Sin cambio | Necesita reemplazo al introducir SQLCipher |
| `libffi` | 3.4.2 | Sin cambio | Verificar ELF ARM64 en cada AAB |
| SDL2/Kivy | Kivy 2.3.0 | Sin cambio | Probar render y ciclo de vida en Android 16 |
| ML Kit Text Recognition | 16.0.1 | Solo variante asistida | Verificar sus binarios nativos y Data Safety |

## Compatibilidad con páginas de 16 KB

NDK 25b no alinea a 16 KB de forma predeterminada. Una build que simplemente
termine no alcanza como evidencia de publicación. El pipeline debe inspeccionar
cada biblioteca `.so`, construir un APK universal desde el AAB y ejecutar
`zipalign -c -P 16 -v 4`. Si una sola dependencia queda en 4 KB, la puerta de
release falla y se actualiza o parchea esa receta de manera explícita.

## Criterio de rollback

El parche no se incorpora dentro del repositorio de p4a ni altera la base de
datos. Para volver atrás se elimina su aplicación en CI y se restaura
`android.api = 34`; los artefactos anteriores permanecen utilizables en las
pistas de prueba.
