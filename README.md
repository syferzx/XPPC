# XPPC

Reproductor multimedia portable para Windows.

[![Descargar para Windows](docs/download-windows.svg)](https://github.com/syferzx/XPPC/releases/latest/download/XuperPC-Windows-x64.zip)

## Abrir la aplicación

1. Descarga el ZIP de [Releases](https://github.com/syferzx/XPPC/releases/latest).
2. Haz clic derecho y elige **Extraer todo**.
3. Abre la carpeta y ejecuta **XuperPC.exe**.

## Código fuente y colaboración

Aquí está el código del cliente: interfaz, catálogo, reproductor, favoritos, progreso y conexión al servicio. Puedes analizarlo, modificarlo y proponer mejoras mediante pull requests.

Consulta [Desarrollo](docs/DESARROLLO.md) para ejecutar las fuentes, probar cambios y preparar un portable. El motor utiliza un componente binario externo; esta publicación no incluye su código fuente ni permite reconstruirlo. Las fuentes del cliente por sí solas no son una distribución autónoma del motor.

El catálogo y la reproducción dependen de servicios externos. Cada instalación conserva sus datos localmente en `Datos`.

## Licencia

[MIT](LICENSE) para el código original del cliente. Los componentes externos conservan sus [licencias](THIRD_PARTY_NOTICES.md).
