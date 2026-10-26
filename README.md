# XPPC

Reproductor multimedia portable para Windows.

[![Descargar para Windows](docs/download-windows.svg)](https://github.com/syferzx/XPPC/releases/latest/download/XuperPC-Windows-x64-BAT.zip)

## Abrir la aplicación

1. Descarga **XuperPC-Windows-x64-BAT.zip** desde [Releases](https://github.com/syferzx/XPPC/releases/latest).
2. Haz clic derecho y elige **Extraer todo**.
3. Abre la carpeta y ejecuta **Iniciar.bat**.

La aplicación se abre en tu navegador. No necesitas instalar Python, FFmpeg ni BlueStacks. Conserva la carpeta `Engine` junto a `Iniciar.bat` y deja abierta la ventana de inicio. Para detener el servidor, pulsa **Ctrl+C** en esa ventana.

Esta variante inicia directamente el motor incluido y no contiene el lanzador `XuperPC.exe` de PyInstaller. Esto no certifica la seguridad de las dependencias incluidas.

## Novedades de la versión 0.1.4

- Corrección de TV en vivo: usa el DNS normal del sistema para el dominio validado del proveedor, en lugar de una IP fija desactualizada.
- Conserva la misma sesión, las comprobaciones HTTPS y las validaciones del servidor de video.
- Mantiene las tres descargas paralelas, el búfer de tres minutos y las mejoras de continuación de la versión 0.1.3.

Al actualizar, cierra la versión anterior y conserva tu carpeta `Datos`: contiene tu sesión, favoritos y progreso. No la compartas con otras personas. El ZIP publicado se prepara sin datos personales.

## Código fuente y colaboración

Aquí está el código del cliente: interfaz, catálogo, reproductor, favoritos, progreso y conexión al servicio. Puedes analizarlo, modificarlo y proponer mejoras mediante pull requests.

Consulta [Desarrollo](docs/DESARROLLO.md) para ejecutar las fuentes, probar cambios y preparar un portable. El motor utiliza un componente binario externo; esta publicación no incluye su código fuente ni permite reconstruirlo. Las fuentes del cliente por sí solas no son una distribución autónoma del motor.

El catálogo y la reproducción dependen de servicios externos. Cada instalación conserva sus datos localmente en `Datos`. No incluye VPN; puede no funcionar en países o redes donde el servicio esté bloqueado.

## Licencia

[MIT](LICENSE) para el código original del cliente. Los componentes externos conservan sus [licencias](THIRD_PARTY_NOTICES.md).
