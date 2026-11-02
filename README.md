# XPPC

Reproductor multimedia portable para Windows.

[![Descargar para Windows](docs/download-windows.svg)](https://github.com/syferzx/XPPC/releases/latest/download/XuperPC-Windows-x64-BAT.zip)

## Abrir la aplicación

1. Descarga **XuperPC-Windows-x64-BAT.zip** desde [Releases](https://github.com/syferzx/XPPC/releases/latest).
2. Haz clic derecho y elige **Extraer todo**.
3. Abre la carpeta y ejecuta **Iniciar.bat**.

La aplicación se abre en tu navegador. No necesitas instalar Python, FFmpeg ni BlueStacks. Conserva la carpeta `Engine` junto a `Iniciar.bat` y deja abierta la ventana de inicio. Para detener el servidor, pulsa **Ctrl+C** en esa ventana.

Esta variante inicia directamente el motor incluido y no contiene el lanzador `XuperPC.exe` de PyInstaller. Esto no certifica la seguridad de las dependencias incluidas.

## Novedades de la versión 0.1.8

- Corrige TV en instalaciones a las que el proveedor asigna el servidor multimedia adicional observado el 2 de noviembre de 2026.
- El proveedor puede asignar servidores distintos a instalaciones diferentes; una copia antigua podía funcionar mientras una nueva rechazaba su destino.
- Conserva las validaciones de origen y los reintentos de la versión 0.1.7. No copia sesiones entre equipos ni acepta servidores arbitrarios.
- 23 pruebas de TV y DNS superadas. Comprobación en la instalación descargada: lista HLS y muestra de segmento de AMC HD con HTTP 200.

Mantiene el aporte de [romario-anchaise](https://github.com/romario-anchaise) en el [pull request #1](https://github.com/syferzx/XPPC/pull/1).

Consulta [Mis descargas](docs/DESCARGAS.md). Conserva el servidor abierto hasta terminar; una descarga interrumpida requiere volver a intentarlo.

Al actualizar, cierra la versión anterior y conserva tus carpetas `Datos` y `Descargas`. `Datos` contiene tu sesión, favoritos y progreso. No la compartas con otras personas. El ZIP publicado se prepara sin datos personales.

## Código fuente y colaboración

Aquí está el código del cliente: interfaz, catálogo, reproductor, favoritos, progreso y conexión al servicio. Puedes analizarlo, modificarlo y proponer mejoras mediante pull requests.

Consulta [Desarrollo](docs/DESARROLLO.md) para ejecutar las fuentes, probar cambios y preparar un portable. El motor utiliza un componente binario externo; esta publicación no incluye su código fuente ni permite reconstruirlo. Las fuentes del cliente por sí solas no son una distribución autónoma del motor.

El catálogo y la reproducción dependen de servicios externos. Cada instalación conserva sus datos localmente en `Datos`. No incluye VPN; puede no funcionar en países o redes donde el servicio esté bloqueado.

## Licencia

[MIT](LICENSE) para el código original del cliente. Los componentes externos conservan sus [licencias](THIRD_PARTY_NOTICES.md).


